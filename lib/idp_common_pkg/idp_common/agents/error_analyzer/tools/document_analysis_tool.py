# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
Document-specific analysis tool.
"""

import logging
from datetime import datetime
from typing import Any, Dict

from strands import tool

from ..config import (
    create_error_response,
    get_config_with_fallback,
    truncate_message,
)
from .cloudwatch_tool import cloudwatch_document_logs
from .lambda_tool import lambda_document_context
from .stepfunction_tool import stepfunction_execution_details
from .xray_tool import xray_document_analysis

logger = logging.getLogger(__name__)


def _truncate_log_results(log_results: Dict[str, Any], config: Dict[str, Any]) -> None:
    """
    Applies size constraints to log results to prevent context overflow.
    Applies configured limits to log events and message lengths to ensure
    the response stays within context size constraints.

    Args:
        log_results: Log search results dictionary to truncate
        config: Configuration dictionary with truncation limits
    """
    if not log_results or not log_results.get("results"):
        return

    # Cache config values once
    max_events_per_group = config.get("max_events_per_log_group", 3)
    max_message_length = config.get("max_log_message_length", 400)

    for result in log_results["results"]:
        events = result.get("events", [])
        result["events"] = events[:max_events_per_group]

        for event in result["events"]:
            message = event.get("message", "")
            event["message"] = truncate_message(message, max_message_length)


def _truncate_stepfunction_analysis(
    sf_analysis: Dict[str, Any], config: Dict[str, Any]
) -> None:
    """
    Applies size constraints to Step Function analysis to prevent overflow.
    Applies configured limits to timeline events and error message lengths
    to keep Step Function analysis within context constraints.

    Args:
        sf_analysis: Step Function analysis results to truncate
        config: Configuration dictionary with truncation limits
    """
    if not sf_analysis or sf_analysis.get("error"):
        return

    # Cache config values once
    max_timeline_events = config.get("max_stepfunction_timeline_events", 3)
    max_error_length = config.get("max_stepfunction_error_length", 400)

    timeline_analysis = sf_analysis.get("timeline_analysis", {})
    if "timeline" in timeline_analysis:
        timeline_analysis["timeline"] = timeline_analysis["timeline"][
            :max_timeline_events
        ]

    failure_point = timeline_analysis.get("failure_point")
    if failure_point and "details" in failure_point:
        details = failure_point["details"]
        for key in ["error", "cause"]:
            if key in details:
                details[key] = truncate_message(str(details[key]), max_error_length)


def _truncate_context_data(context: Dict[str, Any], config: Dict[str, Any]) -> None:
    """
    Truncate document context data to prevent overflow.
    Removes large response objects and applies limits to context data
    to optimize memory usage and response size.

    Args:
        context: Document context dictionary to truncate
        config: Configuration dictionary with limits
    """
    if "lookup_function_response" in context:
        del context["lookup_function_response"]


def _generate_recommendations(
    cloudwatch_results, stepfunction_results, xray_results, document_id=None
):
    """Generate prioritized recommendations: CloudWatch → Step Functions → X-Ray."""
    recommendations = []

    # CloudWatch errors (highest priority)
    if cloudwatch_results and cloudwatch_results.get("search_attempted"):
        if cloudwatch_results.get("total_events_found", 0) > 0:
            recommendations.append("Review CloudWatch error logs for failure details")
        else:
            recommendations.append(
                "No ERROR-level logs found in CloudWatch - check Step Functions for workflow failures"
            )

    # Step Functions failures
    if (
        stepfunction_results
        and stepfunction_results.get("execution_status") == "FAILED"
    ):
        recommendations.append("Analyze Step Functions execution failure timeline")

    # X-Ray recommendations
    recommendations.extend(_generate_xray_recommendations(xray_results))

    # Document-specific
    if document_id:
        recommendations.append(f"Consider reprocessing document '{document_id}'")

    return recommendations or [
        "No issues detected - document may have processed successfully"
    ]


def _generate_xray_recommendations(xray_results):
    """Generate X-Ray specific recommendations with enhanced context."""
    recommendations = []

    if not xray_results:
        return recommendations

    if xray_results.get("trace_found"):
        total_services = xray_results.get("total_services", 0)
        service_timeline = xray_results.get("service_timeline", [])

        # Infrastructure health assessment
        if xray_results.get("total_errors", 0) == 0:
            recommendations.append(
                "X-Ray shows all AWS services responded successfully - focus on application logic errors"
            )
        else:
            recommendations.append(
                "X-Ray detected infrastructure-level errors - investigate service failures"
            )

        # Performance context
        if not xray_results.get("has_performance_issues"):
            recommendations.append(
                "No performance bottlenecks detected in service timeline - investigate configuration issues"
            )
        else:
            recommendations.append(
                "X-Ray shows performance issues - optimize slow Lambda functions or API calls"
            )

        # Service flow analysis
        if total_services > 0:
            recommendations.append(
                f"Service execution flow involved {total_services} components - verify each step completed correctly"
            )

        # Timing insights
        if service_timeline:
            total_duration = sum(s.get("duration_ms", 0) for s in service_timeline)
            if total_duration < 30000:  # Less than 30 seconds
                recommendations.append(
                    f"Processing completed in {total_duration / 1000:.1f}s - timeout not a factor"
                )
            else:
                recommendations.append(
                    f"Processing took {total_duration / 1000:.1f}s - investigate potential timeout issues"
                )
    else:
        recommendations.append("No X-Ray trace found")

    return recommendations


def _get_document_context(document_id: str, stack_name: str) -> Dict[str, Any]:
    """Retrieve document context and validate existence."""
    context = lambda_document_context(document_id, stack_name)

    if not context.get("document_found"):
        return create_error_response(
            context.get("error", "Document not found"),
            analysis_type="document_not_found",
            document_id=document_id,
            document_found=False,
            analysis_summary=f"Document '{document_id}' was not found in the tracking database",
            root_cause="The specified document could not be located in the system's tracking database",
            recommendations=[
                "Verify the document filename is correct and matches exactly",
                "Check if the document was successfully uploaded to the system",
                "Ensure the document processing was initiated",
                "Contact support if the document should exist in the system",
            ],
        )

    return context


def _analyze_execution_traces(
    execution_arn: str, document_id: str = None
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """Analyze Step Function execution and X-Ray traces."""
    stepfunction_analysis = stepfunction_execution_details(execution_arn)

    # Always initialize X-Ray analysis structure
    xray_analysis = {
        "trace_found": False,
        "trace_id": "",
        "has_performance_issues": False,
        "service_timeline": [],
        "query_attempted": False,
    }

    if document_id:
        import os

        tracking_table_name = os.environ.get("TRACKING_TABLE_NAME")

        # Log X-Ray query details as single line
        import json

        xray_analysis["query_attempted"] = True
        xray_result = xray_document_analysis(document_id, tracking_table_name)

        if not xray_result.get("error") and xray_result.get("trace_found"):
            xray_data = xray_result
            trace_id = xray_data.get("trace_id", "")

            # Log successful trace retrieval as single line
            trace_info = {
                "xray_trace_found": {
                    "document_id": document_id,
                    "trace_id": trace_id,
                    "timestamp": datetime.now().isoformat(),
                }
            }
            logger.info(f"Context: {json.dumps(trace_info)}")

            # Limit service timeline to prevent large responses
            service_timeline = xray_data.get("service_timeline", [])
            limited_timeline = service_timeline[:3] if service_timeline else []

            xray_analysis.update(
                {
                    "trace_found": True,
                    "trace_id": trace_id,
                    "has_performance_issues": xray_data.get(
                        "detailed_analysis", {}
                    ).get("has_performance_issues", False),
                    "service_timeline": limited_timeline,
                    "total_services": len(service_timeline),
                }
            )
        else:
            # Log when no trace is found as single line
            no_trace_info = {
                "xray_trace_not_found": {
                    "document_id": document_id,
                    "timestamp": datetime.now().isoformat(),
                }
            }
            logger.info(f"Context: {json.dumps(no_trace_info)}")

    return stepfunction_analysis, xray_analysis


def _build_analysis_summary(
    document_id: str,
    document_status: str,
    completion_time: str | None,
    execution_arn: str | None,
    stepfunction_analysis: Dict[str, Any] | None,
) -> str:
    """Build comprehensive analysis summary from document and execution data."""
    analysis_summary = f"Document {document_id} failed with status {document_status}"

    if completion_time:
        analysis_summary += f" at {completion_time}"

    if execution_arn:
        analysis_summary += f". Execution: {execution_arn.split(':')[-1]}"

    if stepfunction_analysis and not stepfunction_analysis.get("error"):
        sf_summary = stepfunction_analysis.get("analysis_summary", "")
        if sf_summary:
            analysis_summary += f". Workflow: {sf_summary}"

    return analysis_summary


def _add_lambda_results(response: Dict[str, Any], context: Dict[str, Any]) -> None:
    """Add Lambda context results if available."""
    if context.get("lambda_request_ids"):
        response["lambda_results"] = {"request_ids": context["lambda_request_ids"]}


def _add_stepfunction_results(
    response: Dict[str, Any], stepfunction_analysis: Dict[str, Any] | None
) -> None:
    """Add Step Function analysis results if available."""
    if stepfunction_analysis and not stepfunction_analysis.get("error"):
        response["stepfunction_results"] = {
            "execution_status": stepfunction_analysis.get("execution_status"),
            "duration_seconds": stepfunction_analysis.get("duration_seconds"),
            "timeline_analysis": stepfunction_analysis.get("timeline_analysis"),
        }


def _add_cloudwatch_results(
    response: Dict[str, Any], log_results: Dict[str, Any]
) -> None:
    """Add CloudWatch logs results - always include even if no events found."""
    results = log_results.get("results", [])
    total_events = log_results.get("total_events_found", 0)

    response["cloudwatch_results"] = {
        "total_groups_searched": len(results),
        "total_events_found": total_events,
        "results": results,
        "search_attempted": True,
        "has_error_logs": total_events > 0,
    }


def _add_dynamodb_results(
    response: Dict[str, Any],
    document_status: str,
    completion_time: str | None,
    context: Dict[str, Any],
) -> None:
    """Add DynamoDB context results."""
    dynamodb_results: Dict[str, Any] = {
        "document_status": document_status,
        "completion_time": completion_time,
    }
    timestamps = context.get("timestamps")
    if timestamps and isinstance(timestamps, dict):
        dynamodb_results["timestamps"] = timestamps
    response["dynamodb_results"] = dynamodb_results


def _build_response_data(
    document_id: str,
    document_status: str,
    completion_time: str | None,
    execution_arn: str | None,
    analysis_summary: str,
    context: Dict[str, Any],
    stepfunction_analysis: Dict[str, Any] | None,
    xray_analysis: Dict[str, Any] | None,
    log_results: Dict[str, Any],
) -> Dict[str, Any]:
    """Build comprehensive response with all analysis results."""
    response: Dict[str, Any] = {
        "analysis_type": "document_specific",
        "document_id": document_id,
        "document_found": True,
        "document_status": document_status,
        "completion_time": completion_time,
        "analysis_summary": analysis_summary,
    }

    if execution_arn:
        response["execution_arn"] = execution_arn

    # Always include X-Ray results (even if empty)
    response["xray_results"] = xray_analysis

    _add_lambda_results(response, context)
    _add_stepfunction_results(response, stepfunction_analysis)
    _add_cloudwatch_results(response, log_results)
    _add_dynamodb_results(response, document_status, completion_time, context)

    cloudwatch_data = response.get("cloudwatch_results")
    stepfunction_data = response.get("stepfunction_results")
    xray_data = response.get("xray_results")

    response["recommendations"] = _generate_recommendations(
        cloudwatch_data,
        stepfunction_data,
        xray_data,
        document_id,
    )

    return response


@tool
def analyze_document_error(
    document_id: str, stack_name: str, max_log_events: int = 5
) -> Dict[str, Any]:
    """
    Perform comprehensive failure analysis for a specific document.
    Combines document context lookup, Step Function execution analysis, and targeted
    log searching to provide detailed insights into document processing failures.

    Args:
        document_id: Document ObjectKey to analyze
        stack_name: CloudFormation stack name
        max_log_events: Maximum log events to include (default: 5)

    Returns:
        Dict containing comprehensive document failure analysis
    """
    try:
        # Get document context and validate existence
        context = _get_document_context(document_id, stack_name)
        if context.get("analysis_type") == "document_not_found":
            return context

        # Extract document details from context
        document_status = context.get("document_status")
        execution_arn = context.get("execution_arn")
        timestamps = context.get("timestamps", {})
        completion_time = timestamps.get("CompletionTime")

        # Analyze execution traces if available
        stepfunction_analysis = None
        xray_analysis = None
        if execution_arn:
            stepfunction_analysis, xray_analysis = _analyze_execution_traces(
                execution_arn, document_id
            )

        # Get configuration and search logs
        config = get_config_with_fallback()
        configured_log_events = int(config.get("max_log_events", max_log_events))
        configured_log_groups = int(config.get("max_log_groups", 20))

        log_results = cloudwatch_document_logs(
            document_id=document_id,
            stack_name=stack_name,
            filter_pattern="ERROR",
            max_log_events=configured_log_events,
            max_log_groups=configured_log_groups,
        )

        # Truncate data for context management
        _truncate_log_results(log_results, config)
        _truncate_stepfunction_analysis(stepfunction_analysis, config)
        _truncate_context_data(context, config)

        # Build analysis summary
        analysis_summary = _build_analysis_summary(
            document_id,
            document_status,
            completion_time,
            execution_arn,
            stepfunction_analysis,
        )

        # Build and return comprehensive response
        return _build_response_data(
            document_id,
            document_status,
            completion_time,
            execution_arn,
            analysis_summary,
            context,
            stepfunction_analysis,
            xray_analysis,
            log_results,
        )

    except Exception as e:
        logger.error(f"Error analyzing document failure: {e}")
        return create_error_response(str(e))
