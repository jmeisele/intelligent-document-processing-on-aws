# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
System-wide analysis tool.
"""

import logging
from typing import Any, Dict, List

from strands import tool

from ..config import (
    create_error_response,
    create_response,
    get_config_with_fallback,
    safe_int_conversion,
    truncate_message,
)
from .cloudwatch_tool import cloudwatch_stack_logs
from .dynamodb_tool import dynamodb_table_name, dynamodb_tracking_query
from .stepfunction_tool import stepfunction_execution_details
from .xray_tool import xray_service_map, xray_stack_traces

logger = logging.getLogger(__name__)


def _get_failed_documents(time_range_hours: int) -> List[Dict]:
    """Query DynamoDB tracking table for documents with FAILED status."""
    error_records = dynamodb_tracking_query(hours_back=time_range_hours, limit=50)
    failed_docs = []

    for item in error_records.get("items", []):
        status = item.get("Status") or item.get("ObjectStatus")
        if status == "FAILED":
            failed_docs.append(
                {
                    "document_id": item.get("ObjectKey"),
                    "status": status,
                    "completion_time": item.get("CompletionTime"),
                    "error_message": item.get("ErrorMessage"),
                }
            )

    return failed_docs


def _collect_log_events(
    time_range_hours: int, max_log_events: int, config: Dict
) -> tuple[Dict, List, int]:
    """Search CloudWatch logs using prioritized error patterns and collect events."""
    patterns = [
        ("ERROR", 5),
        ("Exception", 3),
        ("ValidationException", 2),
        ("Failed", 2),
        ("Timeout", 1),
    ]

    error_summary = {}
    all_events = []
    total_collected = 0

    for pattern, max_events in patterns:
        if total_collected >= max_log_events:
            break

        results = cloudwatch_stack_logs(
            filter_pattern=pattern,
            hours_back=time_range_hours,
            max_log_events=min(max_events, max_log_events - total_collected),
            max_log_groups=10,
        )

        if results.get("total_events_found", 0) > 0:
            pattern_events = []
            for result in results.get("results", []):
                pattern_events.extend(result.get("events", []))

            filtered_events = _filter_events(pattern_events, config)
            error_summary[pattern] = {
                "count": results.get("total_events_found", 0),
                "sample_events": filtered_events,
            }
            all_events.extend(filtered_events)
            total_collected += len(filtered_events)

    return error_summary, all_events, total_collected


def _filter_events(events: List[Dict], config: Dict) -> List[Dict]:
    """Remove duplicate events and truncate messages to reduce context size."""
    import re

    max_length = config.get("max_log_message_length", 200)
    seen = set()
    filtered = []

    for event in events:
        message = event.get("message", "")
        signature = re.sub(r"\d{4}-\d{2}-\d{2}.*?Z", "", message)
        signature = re.sub(r"RequestId: [a-f0-9-]+", "", signature)

        if signature not in seen and len(filtered) < 10:
            seen.add(signature)
            filtered.append(
                {
                    "timestamp": event["timestamp"],
                    "message": truncate_message(message, max_length),
                    "log_stream": event.get("log_stream", "")[:50],
                }
            )

    return filtered


def _categorize_errors(events: List[Dict]) -> Dict[str, List[Dict]]:
    """Group log events into categories based on message content patterns."""
    categories = {
        "validation_errors": [],
        "processing_errors": [],
        "system_errors": [],
        "timeout_errors": [],
        "access_errors": [],
    }

    for event in events:
        message = event.get("message", "").lower()
        if "validation" in message or "invalid" in message:
            categories["validation_errors"].append(event)
        elif "timeout" in message:
            categories["timeout_errors"].append(event)
        elif "access" in message or "denied" in message:
            categories["access_errors"].append(event)
        elif "exception" in message or "error" in message:
            categories["processing_errors"].append(event)
        else:
            categories["system_errors"].append(event)

    return categories


def _get_stepfunction_analysis(failed_docs: List[Dict], time_range_hours: int) -> Dict:
    """Analyze Step Function executions for failed documents to identify workflow issues."""
    for failure in failed_docs[:2]:
        execution_arn = failure.get("execution_arn")
        if execution_arn:
            sf_result = stepfunction_execution_details(execution_arn)
            if sf_result.get("success"):
                return {
                    "execution_status": sf_result.get("data", {}).get(
                        "execution_status"
                    ),
                    "failure_point": sf_result.get("data", {})
                    .get("timeline_analysis", {})
                    .get("failure_point"),
                    "duration_seconds": sf_result.get("data", {}).get(
                        "duration_seconds"
                    ),
                }
    return None


def _get_xray_analysis(stack_name: str, time_range_hours: int) -> Dict:
    """Collect X-Ray traces for stack-wide performance analysis."""
    import os

    # Use stack-specific X-Ray analysis
    stack_name = stack_name or os.environ.get("AWS_STACK_NAME", "")
    if stack_name:
        xray_result = xray_stack_traces(stack_name, hours_back=time_range_hours)
        if xray_result.get("success"):
            xray_data = xray_result.get("data", {})
            return {
                "traces_found": xray_data.get("traces_found", 0),
                "total_errors": xray_data.get("total_errors", 0),
                "total_faults": xray_data.get("total_faults", 0),
                "total_throttles": xray_data.get("total_throttles", 0),
                "error_rate": xray_data.get("error_rate", 0),
                "services_involved": xray_data.get("services_involved", []),
            }

    # Fallback to service map if no stack name
    service_map_result = xray_service_map(hours_back=time_range_hours)
    if service_map_result.get("success"):
        service_data = service_map_result.get("data", {})
        return {
            "services_found": service_data.get("services_found", 0),
            "high_error_services": service_data.get("high_error_services", []),
            "slow_services": service_data.get("slow_services", []),
        }

    return None


def _generate_summary(categories: Dict, failed_docs: List, total_estimate: int) -> str:
    """Create human-readable summary of error analysis with counts and categories."""
    total_errors = sum(len(errors) for errors in categories.values())

    if total_errors == 0:
        return "No processing errors found in the specified time range"

    summary_parts = [
        f"Found {total_estimate} total errors across {len(failed_docs)} failed documents"
    ]

    for category, errors in categories.items():
        if errors:
            category_name = category.replace("_", " ")
            summary_parts.append(f"{len(errors)} {category_name}")

    return ". ".join(summary_parts)


def _generate_recommendations(
    total_errors, stepfunction_results, xray_results, failed_docs
):
    """Create actionable recommendations based on analysis results with priority ordering."""
    recommendations = []

    if total_errors > 0:
        recommendations.append("Review CloudWatch error logs for failure patterns")

    if (
        stepfunction_results
        and stepfunction_results.get("execution_status") == "FAILED"
    ):
        recommendations.append("Analyze Step Function execution failures")

    if xray_results:
        if xray_results.get("has_performance_issues"):
            recommendations.append(
                "Investigate performance bottlenecks in service traces"
            )
        if xray_results.get("high_error_services"):
            recommendations.append("Review high-error services in X-Ray")

    if failed_docs > 0:
        recommendations.append("Monitor recent document processing failures")

    return recommendations or ["System appears healthy"]


@tool
def analyze_general_errors(
    time_range_hours: int, stack_name: str, max_log_events: int = 5
) -> Dict[str, Any]:
    """Analyze system-wide errors across CloudWatch, Step Functions, X-Ray, and DynamoDB."""
    try:
        config = get_config_with_fallback()
        time_range_hours = safe_int_conversion(time_range_hours)
        max_log_events = safe_int_conversion(
            config.get("max_log_events", max_log_events)
        )

        tracking_info = dynamodb_table_name()
        if not tracking_info.get("tracking_table_found"):
            return create_error_response("TrackingTable not found")

        # Get error estimate
        initial_scan = cloudwatch_stack_logs(
            "ERROR", hours_back=time_range_hours, max_log_events=5, max_log_groups=5
        )
        total_errors_estimate = initial_scan.get("total_events_found", 0)

        # Collect data
        failed_docs = _get_failed_documents(time_range_hours)
        error_summary, all_events, total_collected = _collect_log_events(
            time_range_hours, max_log_events, config
        )
        categorized_errors = _categorize_errors(all_events)

        # Get analysis
        stepfunction_analysis = _get_stepfunction_analysis(
            failed_docs, time_range_hours
        )
        xray_analysis = _get_xray_analysis(stack_name, time_range_hours)

        # Generate summary and recommendations
        analysis_summary = _generate_summary(
            categorized_errors, failed_docs, total_errors_estimate
        )
        recommendations = _generate_recommendations(
            total_errors_estimate,
            stepfunction_analysis,
            xray_analysis,
            len(failed_docs),
        )

        return create_response(
            {
                "analysis_type": "system_wide",
                "time_range_hours": time_range_hours,
                "analysis_summary": analysis_summary,
                "cloudwatch_results": {
                    "total_errors_estimate": total_errors_estimate,
                    "error_categories": {
                        category: {
                            "count": len(errors),
                            "sample": truncate_message(
                                errors[0]["message"],
                                config.get("max_log_message_length", 200),
                            )
                            if errors
                            else None,
                        }
                        for category, errors in categorized_errors.items()
                        if errors
                    },
                    "error_summary": error_summary,
                },
                "stepfunction_results": stepfunction_analysis,
                "xray_results": xray_analysis,
                "dynamodb_results": {
                    "recent_failures_count": len(failed_docs),
                    "recent_failures": failed_docs[
                        : config.get("max_stepfunction_timeline_events", 3)
                    ],
                },
                "context_management": {
                    "events_collected": total_collected,
                    "max_events_limit": max_log_events,
                },
                "recommendations": recommendations,
            }
        )

    except Exception as e:
        logger.error(f"Error in system-wide analysis: {e}")
        return create_error_response(str(e))
