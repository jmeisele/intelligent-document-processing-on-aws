# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
X-Ray tools for tracing analysis and performance monitoring.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List

import boto3
from strands import tool

from ..config import (
    create_error_response,
    create_response,
    get_config_with_fallback,
    safe_int_conversion,
)

logger = logging.getLogger(__name__)


def _extract_trace_summary(trace: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract key information from X-Ray trace summary.

    Args:
        trace: X-Ray trace summary dictionary

    Returns:
        Dict containing extracted trace information
    """
    return {
        "trace_id": trace.get("Id"),
        "duration": trace.get("Duration", 0),
        "response_time": trace.get("ResponseTime", 0),
        "has_error": trace.get("HasError", False),
        "has_fault": trace.get("HasFault", False),
        "has_throttle": trace.get("HasThrottle", False),
        "service_ids": [service.get("Name") for service in trace.get("ServiceIds", [])],
    }


def _parse_segment_document(segment_doc: Any) -> Dict[str, Any]:
    """
    Parse segment document from string or dict format.

    Args:
        segment_doc: Segment document (string or dict)

    Returns:
        Parsed segment document as dict
    """
    if isinstance(segment_doc, str):
        import json

        try:
            return json.loads(segment_doc)
        except json.JSONDecodeError:
            return {}
    return segment_doc or {}


def _analyze_trace_segments(segments: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Analyze X-Ray trace segments to identify performance bottlenecks.

    Args:
        segments: List of X-Ray trace segments

    Returns:
        Dict containing segment analysis
    """
    if not segments:
        return {"error": "No trace segments available"}

    total_duration = 0
    error_segments = []
    slow_segments = []

    config = get_config_with_fallback()
    slow_threshold = config.get("xray_slow_segment_threshold_ms", 5000)

    for segment in segments:
        segment_doc = _parse_segment_document(segment.get("Document", {}))
        if not segment_doc:
            continue

        duration = segment_doc.get("end_time", 0) - segment_doc.get("start_time", 0)
        total_duration += duration

        # Check for errors
        if segment_doc.get("error") or segment_doc.get("fault"):
            error_segments.append(
                {
                    "id": segment_doc.get("id"),
                    "name": segment_doc.get("name"),
                    "error": segment_doc.get("error"),
                    "fault": segment_doc.get("fault"),
                    "cause": segment_doc.get("cause", {}).get("exceptions", []),
                }
            )

        # Check for slow segments
        if duration * 1000 > slow_threshold:  # Convert to ms
            slow_segments.append(
                {
                    "id": segment_doc.get("id"),
                    "name": segment_doc.get("name"),
                    "duration_ms": duration * 1000,
                    "service": segment_doc.get("service", {}).get("name"),
                }
            )

    return {
        "total_segments": len(segments),
        "total_duration_ms": total_duration * 1000,
        "error_segments": error_segments,
        "slow_segments": slow_segments,
        "has_performance_issues": len(slow_segments) > 0 or len(error_segments) > 0,
    }


@tool
def xray_service_map(
    service_name: str = None, hours_back: int = None
) -> Dict[str, Any]:
    """
    Analyze X-Ray service map to identify service dependencies and performance patterns.

    Args:
        service_name: Optional service name to filter by
        hours_back: Hours to look back for service map data (default: 1)

    Returns:
        Dict containing service map analysis and dependency insights
    """
    try:
        hours_back = safe_int_conversion(hours_back, 1)
        xray_client = boto3.client("xray")

        # Set time range
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=hours_back)

        # Get service statistics
        response = xray_client.get_service_graph(StartTime=start_time, EndTime=end_time)

        services = response.get("Services", [])

        if not services:
            return create_response(
                {
                    "services_found": 0,
                    "message": "No service map data available",
                    "recommendations": [
                        "Ensure X-Ray tracing is enabled",
                        "Check if services have been active in the time window",
                        "Verify X-Ray daemon is running",
                    ],
                }
            )

        # Analyze services
        service_analysis = []
        high_error_services = []
        slow_services = []

        config = get_config_with_fallback()
        error_rate_threshold = config.get("xray_error_rate_threshold", 0.05)  # 5%
        response_time_threshold = config.get(
            "xray_response_time_threshold_ms", 10000
        )  # 10s

        for service in services:
            service_stats = service.get("SummaryStatistics", {})

            error_rate = service_stats.get("ErrorStatistics", {}).get("ErrorRate", 0)
            response_time = service_stats.get("ResponseTimeHistogram", {}).get(
                "TotalTime", 0
            )
            request_count = service_stats.get("RequestCount", 0)

            analysis = {
                "name": service.get("Name"),
                "type": service.get("Type"),
                "request_count": request_count,
                "error_rate": error_rate,
                "response_time_ms": response_time * 1000,
                "edges": len(service.get("Edges", [])),
            }

            service_analysis.append(analysis)

            # Identify problematic services
            if error_rate > error_rate_threshold:
                high_error_services.append(analysis["name"])

            if response_time * 1000 > response_time_threshold:
                slow_services.append(analysis["name"])

        return create_response(
            {
                "services_found": len(services),
                "service_analysis": service_analysis,
                "high_error_services": high_error_services,
                "slow_services": slow_services,
                "recommendations": [
                    f"Investigate services with error rates above {error_rate_threshold * 100}%",
                    f"Optimize services with response times above {response_time_threshold}ms",
                    "Review service dependencies for potential bottlenecks",
                ],
            }
        )

    except Exception as e:
        logger.error(f"Error analyzing X-Ray service map: {e}")
        return create_error_response(str(e))


@tool
def xray_stack_traces(stack_name: str, hours_back: int = None) -> Dict[str, Any]:
    """
    Analyze X-Ray traces for a specific stack to identify system-wide performance issues.

    Args:
        stack_name: CloudFormation stack name to filter traces
        hours_back: Hours to look back for traces (default: 2)

    Returns:
        Dict containing stack-wide trace analysis
    """
    try:
        if not stack_name:
            return create_error_response("No stack name provided")

        hours_back = safe_int_conversion(hours_back, 2)
        xray_client = boto3.client("xray")

        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=hours_back)

        # Search for traces with stack_name annotation
        response = xray_client.get_trace_summaries(
            TimeRangeType="TimeRangeByStartTime",
            StartTime=start_time,
            EndTime=end_time,
            FilterExpression=f'annotation.stack_name = "{stack_name}"',
            MaxResults=50,
        )

        traces = response.get("TraceSummaries", [])

        if not traces:
            return create_response(
                {
                    "stack_name": stack_name,
                    "traces_found": 0,
                    "message": "No X-Ray traces found for this stack",
                    "recommendations": [
                        "Verify X-Ray tracing is enabled for Lambda functions",
                        "Check if stack has been active in the time window",
                        "Ensure stack name annotation is correct",
                    ],
                }
            )

        # Analyze trace summaries
        total_errors = 0
        total_faults = 0
        total_throttles = 0
        service_names = set()

        for trace in traces:
            if trace.get("HasError"):
                total_errors += 1
            if trace.get("HasFault"):
                total_faults += 1
            if trace.get("HasThrottle"):
                total_throttles += 1

            # Collect service names
            for service in trace.get("ServiceIds", []):
                service_names.add(service.get("Name"))

        return create_response(
            {
                "stack_name": stack_name,
                "traces_found": len(traces),
                "total_errors": total_errors,
                "total_faults": total_faults,
                "total_throttles": total_throttles,
                "services_involved": list(service_names),
                "error_rate": total_errors / len(traces) if traces else 0,
                "recommendations": [
                    "Review error traces for specific failure patterns",
                    "Check throttling patterns for capacity issues",
                    "Monitor service dependencies for bottlenecks",
                ],
            }
        )

    except Exception as e:
        logger.error(f"Error analyzing X-Ray traces for stack {stack_name}: {e}")
        return create_error_response(str(e))


@tool
def xray_document_analysis(
    document_id: str, tracking_table_name: str = None
) -> Dict[str, Any]:
    """
    Analyze X-Ray traces for a specific document to identify performance issues and errors.

    Args:
        document_id: The document ID to analyze
        tracking_table_name: DynamoDB table name containing document records

    Returns:
        Dict containing comprehensive trace analysis for the document
    """
    try:
        if not document_id:
            return create_error_response("No document ID provided")

        xray_client = boto3.client("xray")
        trace_id = None

        # Try to get trace_id from DynamoDB first
        if tracking_table_name:
            try:
                dynamodb = boto3.resource("dynamodb")
                table = dynamodb.Table(tracking_table_name)

                response = table.get_item(
                    Key={"PK": f"doc#{document_id}", "SK": "none"}
                )

                if "Item" in response:
                    trace_id = response["Item"].get("TraceId")
                    logger.info(f"TraceId: {trace_id} for document {document_id}")

            except Exception as e:
                logger.warning(f"Could not retrieve trace_id from DynamoDB: {e}")

        # Fallback to X-Ray annotation query if no trace_id found
        if not trace_id:
            logger.info(
                f"Searching X-Ray traces by annotation for document {document_id}"
            )

            end_time = datetime.utcnow()
            start_time = end_time - timedelta(hours=24)  # Search last 24 hours

            response = xray_client.get_trace_summaries(
                TimeRangeType="TimeRangeByStartTime",
                StartTime=start_time,
                EndTime=end_time,
                FilterExpression=f'annotation.document_id = "{document_id}"',
                MaxResults=10,
            )

            traces = response.get("TraceSummaries", [])
            if not traces:
                return create_response(
                    {
                        "document_id": document_id,
                        "trace_found": False,
                        "traces_found": 0,
                        "message": "No X-Ray traces found for this document",
                        "recommendations": [
                            "Verify document was processed recently (within 24 hours)",
                            "Check if X-Ray tracing is enabled for all Lambda functions",
                            "Ensure document ID is correct",
                        ],
                    }
                )

            # Use the most recent trace
            trace_id = traces[0].get("Id")
            logger.info(f"Found trace_id {trace_id} via annotation query")

        # Get detailed trace analysis
        if trace_id:
            logger.info(f"Attempting to get trace details for trace_id: {trace_id}")
            segments_response = xray_client.batch_get_traces(TraceIds=[trace_id])
            logger.info(f"X-Ray batch_get_traces response: {segments_response}")

            if not segments_response.get("Traces"):
                return create_error_response(
                    f"Could not retrieve trace details for {trace_id}"
                )

            trace_data = segments_response["Traces"][0]
            segments = trace_data.get("Segments", [])

            # Analyze segments for performance and errors
            detailed_analysis = _analyze_trace_segments(segments)

            # Extract service timeline
            service_timeline = []
            for segment in segments:
                segment_doc = _parse_segment_document(segment.get("Document", {}))
                if not segment_doc:
                    continue

                service_timeline.append(
                    {
                        "service_name": segment_doc.get("name"),
                        "start_time": segment_doc.get("start_time"),
                        "end_time": segment_doc.get("end_time"),
                        "duration_ms": (
                            segment_doc.get("end_time", 0)
                            - segment_doc.get("start_time", 0)
                        )
                        * 1000,
                        "has_error": bool(
                            segment_doc.get("error") or segment_doc.get("fault")
                        ),
                        "annotations": segment_doc.get("annotations", {}),
                    }
                )

            return create_response(
                {
                    "document_id": document_id,
                    "trace_id": trace_id,
                    "trace_found": True,
                    "detailed_analysis": detailed_analysis,
                    "service_timeline": sorted(
                        service_timeline, key=lambda x: x.get("start_time", 0)
                    ),
                    "recommendations": [
                        "Review error segments for specific failure causes",
                        "Check slow segments for performance optimization",
                        "Analyze service timeline for bottlenecks",
                    ],
                }
            )

        return create_response(
            {
                "document_id": document_id,
                "trace_found": False,
                "message": "Could not find or analyze trace for document",
                "recommendations": [
                    "Verify document was processed recently",
                    "Check X-Ray tracing configuration",
                    "Ensure document ID is correct",
                ],
            }
        )

    except Exception as e:
        logger.error(f"Error analyzing X-Ray traces for document {document_id}: {e}")
        return create_error_response(str(e))
