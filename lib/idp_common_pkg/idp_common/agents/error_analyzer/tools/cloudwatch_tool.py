# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
CloudWatch tools for error analysis.
"""

import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict

import boto3
from strands import tool

from ..config import create_error_response, safe_int_conversion
from .lambda_tool import lambda_document_context

logger = logging.getLogger(__name__)


def search_cloudwatch_logs(
    log_group_name: str,
    filter_pattern: str = "",
    hours_back: int = 24,
    max_events: int = 10,
    start_time: datetime = None,
    end_time: datetime = None,
    request_id: str = None,
) -> Dict[str, Any]:
    """
    Search CloudWatch logs within a specific log group for matching patterns.
    Enhanced with request ID-first search strategy for precise log correlation.

    Args:
        log_group_name: CloudWatch log group name to search
        filter_pattern: CloudWatch filter pattern for log events
        hours_back: Hours to look back from current time
        max_events: Maximum number of events to return
        start_time: Optional start time for search window
        end_time: Optional end time for search window
        request_id: Optional Lambda request ID for precise filtering

    Returns:
        Dict containing found events and search metadata
    """
    try:
        logger.debug(
            f"Searching CloudWatch logs in {log_group_name} with filter '{filter_pattern}'"
        )
        client = boto3.client("logs")

        # Use provided time window or default to hours_back from now
        if start_time and end_time:
            search_start = start_time
            search_end = end_time
        else:
            search_end = datetime.utcnow()
            search_start = search_end - timedelta(hours=hours_back)

        # Use higher limit for error patterns to account for INFO log filtering
        search_limit = (
            int(max_events) * 5
            if filter_pattern
            in ["[ERROR]", "[WARN]", "ERROR:", "WARN:", "Exception", "Failed"]
            else int(max_events)
        )

        params = {
            "logGroupName": log_group_name,
            "startTime": int(search_start.timestamp() * 1000),
            "endTime": int(search_end.timestamp() * 1000),
            "limit": search_limit,
        }

        # Build filter pattern with request ID priority
        final_filter_pattern = _build_filter_pattern(filter_pattern, request_id)
        if final_filter_pattern:
            params["filterPattern"] = final_filter_pattern

        response = client.filter_log_events(**params)

        events = []
        for event in response.get("events", []):
            message = event["message"]

            # Filter out non-error logs when searching for error patterns
            if filter_pattern in [
                "[ERROR]",
                "[WARN]",
                "ERROR:",
                "WARN:",
                "Exception",
                "Failed",
            ]:
                # Skip INFO logs
                if message.strip().startswith("[INFO]"):
                    continue
                # Skip Lambda system logs
                if any(
                    message.strip().startswith(prefix)
                    for prefix in ["INIT_START", "START", "END", "REPORT"]
                ):
                    continue

            events.append(
                {
                    "timestamp": datetime.fromtimestamp(
                        event["timestamp"] / 1000
                    ).isoformat(),
                    "message": message,
                    "log_stream": event.get("logStreamName", ""),
                }
            )

            # Stop when we have enough actual error events
            if len(events) >= max_events:
                break

        return {
            "log_group": log_group_name,
            "events_found": len(events),
            "events": events,
            "filter_pattern": final_filter_pattern,
            "request_id_used": request_id,
            "search_strategy": "request_id" if request_id else "pattern",
        }

    except Exception as e:
        logger.error(f"CloudWatch search failed for log group '{log_group_name}': {e}")
        return create_error_response(str(e), events_found=0, events=[])


def _build_filter_pattern(base_pattern: str, request_id: str = None) -> str:
    """
    Build CloudWatch filter pattern with request ID priority.

    Args:
        base_pattern: Base filter pattern (e.g., "ERROR")
        request_id: Lambda request ID for precise filtering

    Returns:
        Optimized filter pattern string
    """
    if request_id:
        # Request ID-first strategy: combine request ID with error patterns
        if base_pattern and base_pattern.strip():
            # Sanitize base pattern
            sanitized_base = base_pattern.replace(":", "")
            return f"{request_id} {sanitized_base}"
        else:
            return request_id
    elif base_pattern:
        # Fallback to base pattern only
        return base_pattern.replace(":", "")
    else:
        return ""


def get_cloudwatch_log_groups(prefix: str = "") -> Dict[str, Any]:
    """
    Lists CloudWatch log groups matching specified prefix.
    Internal utility function that lists available log groups and their metadata.
    Filters by prefix to reduce API calls and focus on relevant groups.

    Args:
        prefix: Log group name prefix to filter by

    Returns:
        Dict containing found log groups and their metadata
    """
    try:
        if not prefix or len(prefix) < 5:
            return {
                "log_groups_found": 0,
                "log_groups": [],
                "warning": "Empty prefix provided",
            }

        client = boto3.client("logs")
        response = client.describe_log_groups(logGroupNamePrefix=prefix)

        groups = []
        for group in response.get("logGroups", []):
            groups.append(
                {
                    "name": group["logGroupName"],
                    "creation_time": datetime.fromtimestamp(
                        group["creationTime"] / 1000
                    ).isoformat(),
                    "retention_days": group.get("retentionInDays", "Never expire"),
                    "size_bytes": group.get("storedBytes", 0),
                }
            )

        return {"log_groups_found": len(groups), "log_groups": groups}

    except Exception as e:
        logger.error(f"Failed to get log groups with prefix '{prefix}': {e}")
        return create_error_response(str(e), log_groups_found=0, log_groups=[])


def _extract_prefix_from_state_machine_arn(arn: str) -> str:
    """
    Extracts log group prefix from Step Functions State Machine ARN.
    Parses the State Machine ARN to determine the appropriate CloudWatch log group prefix
    for finding related Lambda function logs.

    Args:
        arn: Step Functions State Machine ARN

    Returns:
        Extracted prefix string or empty string if parsing fails
    """
    if ":stateMachine:" in arn:
        state_machine_name = arn.split(":stateMachine:")[-1]
        if "-DocumentProcessingWorkflow" in state_machine_name:
            return state_machine_name.replace("-DocumentProcessingWorkflow", "")
        parts = state_machine_name.split("-")
        if len(parts) > 1:
            return "-".join(parts[:-1])
    return ""


def get_log_group_prefix(stack_name: str) -> Dict[str, Any]:
    """
    Determines CloudWatch log group prefix from CloudFormation stack.
    Analyzes CloudFormation stack outputs to find the correct log group prefix pattern.
    Prioritizes pattern-based prefixes from State Machine ARNs over generic stack prefixes.

    Args:
        stack_name: CloudFormation stack name

    Returns:
        Dict containing prefix information and metadata
    """
    try:
        logger.info(f"Getting log group prefix for stack: {stack_name}")
        cf_client = boto3.client("cloudformation")
        stack_response = cf_client.describe_stacks(StackName=stack_name)
        stacks = stack_response.get("Stacks", [])
        logger.info(f"Found {len(stacks)} stacks in CloudFormation response")

        if stacks:
            outputs = stacks[0].get("Outputs", [])
            logger.info(f"Stack has {len(outputs)} outputs")

            for output in outputs:
                output_key = output.get("OutputKey", "")
                output_value = output.get("OutputValue", "")
                logger.debug(f"Checking output: {output_key} = {output_value}")

                if output_key == "StateMachineArn":
                    logger.info(f"Found StateMachineArn: {output_value}")
                    extracted_prefix = _extract_prefix_from_state_machine_arn(
                        output_value
                    )
                    logger.info(
                        f"Extracted prefix from StateMachine ARN: '{extracted_prefix}'"
                    )

                    if extracted_prefix:
                        pattern_prefix = f"/{extracted_prefix}/lambda"
                        logger.info(
                            f"Using pattern-based log prefix: '{pattern_prefix}'"
                        )
                        return {
                            "stack_name": stack_name,
                            "prefix_type": "pattern",
                            "log_group_prefix": pattern_prefix,
                            "nested_stack_name": extracted_prefix,
                        }

        main_prefix = f"/aws/lambda/{stack_name}"
        logger.info(
            f"No StateMachineArn found, using main stack prefix: '{main_prefix}'"
        )
        return {
            "stack_name": stack_name,
            "prefix_type": "main",
            "log_group_prefix": main_prefix,
        }

    except Exception as e:
        logger.error(
            f"Failed to determine log group prefix for stack '{stack_name}': {e}"
        )
        return create_error_response(str(e), stack_name=stack_name)


@tool
def cloudwatch_document_logs(
    document_id: str,
    stack_name: str,
    filter_pattern: str = "ERROR",
    max_log_events: int = None,
    max_log_groups: int = 20,
) -> Dict[str, Any]:
    """
    Finds document-specific errors using execution context.
    Leverages document execution context to perform targeted log searches with precise
    time windows and execution-specific filters for enhanced accuracy.

    Args:
        document_id: Document ObjectKey to search logs for
        stack_name: CloudFormation stack name for log group discovery
        filter_pattern: CloudWatch filter pattern (default: "ERROR")
        max_log_events: Maximum events per log group (default: 10)
        max_log_groups: Maximum log groups to search (default: 20)

    Returns:
        Dict containing document-specific log search results
    """
    try:
        # Use safe integer conversion with defaults
        max_log_events = safe_int_conversion(max_log_events, 10)
        max_log_groups = safe_int_conversion(max_log_groups, 20)
        # Get document execution context with enhanced request ID mapping
        context = lambda_document_context(document_id, stack_name)

        if not context.get("document_found"):
            return {
                "analysis_type": "document_not_found",
                "document_id": document_id,
                "error": context.get("error", "Document not found"),
                "events_found": 0,
            }

        # Get log group prefix
        prefix_info = get_log_group_prefix(stack_name)
        if "error" in prefix_info:
            return {
                "error": f"Failed to get log prefix: {prefix_info['error']}",
                "events_found": 0,
            }

        log_prefix = prefix_info.get("log_group_prefix")
        log_groups = get_cloudwatch_log_groups(prefix=log_prefix)

        if log_groups.get("log_groups_found", 0) == 0:
            return {
                "document_id": document_id,
                "log_prefix": log_prefix,
                "events_found": 0,
                "message": "No log groups found",
            }

        # Use precise time window from document context
        start_time = context.get("processing_start_time")
        end_time = context.get("processing_end_time")

        # Enhanced search strategy with request ID priority
        request_ids = context.get("lambda_request_ids", [])
        function_request_map = context.get("function_request_map", {})
        failed_functions = context.get("failed_functions", [])
        primary_failed_function = context.get("primary_failed_function")

        # Priority 1: Request IDs from failed functions
        priority_request_ids = []
        if primary_failed_function and primary_failed_function in function_request_map:
            priority_request_ids.append(function_request_map[primary_failed_function])

        # Priority 2: All request IDs from failed functions
        for func in failed_functions:
            if func in function_request_map:
                req_id = function_request_map[func]
                if req_id not in priority_request_ids:
                    priority_request_ids.append(req_id)

        # Priority 3: All other request IDs
        fallback_request_ids = [
            rid for rid in request_ids if rid not in priority_request_ids
        ]

        # Priority 4: Fallback patterns
        execution_arn = context.get("execution_arn")
        fallback_patterns = []
        if execution_arn:
            execution_name = execution_arn.split(":")[-1]
            fallback_patterns.append(execution_name)

        # Combine all search patterns in priority order
        search_patterns = (
            priority_request_ids + fallback_request_ids + fallback_patterns
        )

        # Search logs with multiple patterns, prioritizing error patterns
        all_results = []
        total_events = 0
        found_actual_errors = False

        groups_to_search = log_groups["log_groups"][:max_log_groups]

        for group in groups_to_search:
            log_group_name = group["name"]

            # Try each search pattern with request ID priority
            for pattern in search_patterns:
                if not pattern:
                    continue

                # Determine if this is a request ID or fallback pattern
                is_request_id = pattern in (priority_request_ids + fallback_request_ids)

                search_result = search_cloudwatch_logs(
                    log_group_name=log_group_name,
                    filter_pattern="ERROR" if is_request_id else pattern,
                    max_events=max_log_events,
                    start_time=start_time,
                    end_time=end_time,
                    request_id=pattern if is_request_id else None,
                )

                if search_result.get("events_found", 0) > 0:
                    logger.info(
                        f"  Found {search_result['events_found']} events in {log_group_name} with pattern '{pattern}'"
                    )

                    all_results.append(
                        {
                            "log_group": log_group_name,
                            "filter_pattern": pattern,
                            "events_found": search_result["events_found"],
                            "events": search_result["events"],
                        }
                    )
                    total_events += search_result["events_found"]

                    # Mark if we found actual errors from request ID search
                    if is_request_id:
                        found_actual_errors = True
                else:
                    logger.debug(
                        f"  No events found in {log_group_name} with pattern '{pattern}'"
                    )

            # If we found actual errors, prioritize them and stop searching context patterns
            if found_actual_errors and total_events >= max_log_events:
                break

        return {
            "analysis_type": "document_specific",
            "document_id": document_id,
            "document_status": context.get("document_status"),
            "execution_arn": execution_arn,
            "search_patterns_used": search_patterns,
            "priority_request_ids": priority_request_ids,
            "failed_functions": failed_functions,
            "primary_failed_function": primary_failed_function,
            "processing_time_window": {
                "start": start_time.isoformat() if start_time else None,
                "end": end_time.isoformat() if end_time else None,
            },
            "total_events_found": total_events,
            "log_groups_searched": len(groups_to_search),
            "log_groups_with_events": len(all_results),
            "results": all_results,
        }

    except Exception as e:
        logger.error(f"Document log search failed for {document_id}: {e}")
        return create_error_response(str(e), document_id=document_id, events_found=0)


@tool
def cloudwatch_stack_logs(
    filter_pattern: str = "ERROR",
    hours_back: int = None,
    max_log_events: int = None,
    max_log_groups: int = 20,
    start_time: datetime = None,
    end_time: datetime = None,
) -> Dict[str, Any]:
    """
    Searches all stack-related log groups for error patterns.
    Primary tool for system-wide log analysis. Automatically discovers relevant log groups
    based on CloudFormation stack configuration and searches for specified patterns.

    Args:
        filter_pattern: CloudWatch filter pattern (default: "ERROR")
        hours_back: Hours to look back from current time (default: 24)
        max_log_events: Maximum events per log group (default: 10)
        max_log_groups: Maximum log groups to search (default: 20)
        start_time: Optional start time for search window
        end_time: Optional end time for search window

    Returns:
        Dict containing comprehensive log search results across all relevant groups
    """
    stack_name = os.environ.get("AWS_STACK_NAME", "")

    if not stack_name:
        return {
            "error": "AWS_STACK_NAME not configured in environment",
            "events_found": 0,
        }

    try:
        # Use safe integer conversion with defaults
        max_log_events = safe_int_conversion(max_log_events, 10)
        max_log_groups = safe_int_conversion(max_log_groups, 20)
        hours_back = safe_int_conversion(hours_back, 24)
        logger.info(f"Starting log search for stack: {stack_name}")
        prefix_info = get_log_group_prefix(stack_name)
        logger.info(f"Prefix info result: {prefix_info}")

        if "error" in prefix_info:
            logger.error(f"Failed to get log prefix: {prefix_info['error']}")
            return {
                "error": f"Failed to get log prefix: {prefix_info['error']}",
                "events_found": 0,
            }

        log_prefix = prefix_info.get("log_group_prefix")
        prefix_type = prefix_info.get("prefix_type")
        logger.info(f"Using log prefix: '{log_prefix}' (type: {prefix_type})")

        # Get log groups with the prefix
        log_groups = get_cloudwatch_log_groups(prefix=log_prefix)
        logger.info(
            f"Found {log_groups.get('log_groups_found', 0)} log groups with prefix '{log_prefix}'"
        )

        if log_groups.get("log_groups_found", 0) > 0:
            group_names = [g["name"] for g in log_groups.get("log_groups", [])]
            logger.info(f"Log group names: {group_names[:5]}...")  # Show first 5

        if log_groups.get("log_groups_found", 0) == 0:
            return {
                "stack_name": stack_name,
                "log_prefix": log_prefix,
                "events_found": 0,
                "message": "No log groups found with the determined prefix",
            }

        # Search each log group
        groups_to_search = log_groups["log_groups"][:max_log_groups]
        all_results = []
        total_events = 0

        for group in groups_to_search:
            log_group_name = group["name"]

            search_result = search_cloudwatch_logs(
                log_group_name=log_group_name,
                filter_pattern=filter_pattern,
                hours_back=hours_back,
                max_events=max_log_events,
                start_time=start_time,
                end_time=end_time,
            )

            if search_result.get("events_found", 0) > 0:
                logger.info(
                    f"Found {search_result['events_found']} events in {log_group_name}"
                )

                all_results.append(
                    {
                        "log_group": log_group_name,
                        "events_found": search_result["events_found"],
                        "events": search_result["events"],
                    }
                )
                total_events += search_result["events_found"]
            else:
                logger.debug(f"No events found in {log_group_name}")

        return {
            "stack_name": stack_name,
            "log_prefix_used": log_prefix,
            "prefix_type": prefix_type,
            "filter_pattern": filter_pattern,
            "total_log_groups_found": log_groups.get("log_groups_found", 0),
            "log_groups_searched": len(groups_to_search),
            "log_groups_with_events": len(all_results),
            "total_events_found": total_events,
            "max_log_events": max_log_events,
            "results": all_results,
        }

    except Exception as e:
        logger.error(f"Stack log search failed for '{stack_name}': {e}")
        return create_error_response(str(e), stack_name=stack_name, events_found=0)
