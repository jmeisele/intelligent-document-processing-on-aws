# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
CloudWatch tools for error analysis.
"""

import logging
import os
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

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

        logger.debug(f"CloudWatch search params: {params}")
        response = client.filter_log_events(**params)
        logger.debug(
            f"CloudWatch API returned {len(response.get('events', []))} raw events"
        )

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

        result = {
            "log_group": log_group_name,
            "events_found": len(events),
            "events": events,
            "filter_pattern": final_filter_pattern,
            "request_id_used": request_id,
            "search_strategy": "request_id" if request_id else "pattern",
        }

        if events:
            for i, event in enumerate(events[:3]):  # Log first 3 events
                logger.error(f"Found error: {event['message']}")
        else:
            logger.debug(
                f"No events found in {log_group_name} with filter '{final_filter_pattern}'"
            )

        return result

    except Exception as e:
        logger.error(f"CloudWatch search failed for log group '{log_group_name}': {e}")
        return create_error_response(str(e), events_found=0, events=[])


def _build_filter_pattern(base_pattern: str, request_id: str = None) -> str:
    """
    Build CloudWatch filter pattern with request ID priority.
    Uses request ID alone first for maximum precision, then combines with error patterns.

    Args:
        base_pattern: Base filter pattern (e.g., "ERROR")
        request_id: Lambda request ID for precise filtering

    Returns:
        Optimized filter pattern string
    """
    if request_id:
        # Use request ID alone for maximum precision
        logger.debug(f"Building filter pattern with request ID: {request_id}")
        return request_id
    elif base_pattern:
        # Fallback to base pattern only
        sanitized_pattern = base_pattern.replace(":", "")
        logger.debug(f"Building filter pattern with base pattern: {sanitized_pattern}")
        return sanitized_pattern
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


def extract_request_ids_from_logs(
    log_groups: List[str], execution_id: str, start_time: datetime, end_time: datetime
) -> Dict[str, Any]:
    """
    Extract Lambda request IDs from CloudWatch logs using execution ID correlation.
    Searches CloudWatch logs for the execution ID and extracts associated request IDs.

    Args:
        log_groups: List of log group names to search
        execution_id: Step Functions execution ID for correlation
        start_time: Start time for log search
        end_time: End time for log search

    Returns:
        Dict containing function-to-request-ID mapping and extraction metadata
    """
    function_request_map = {}
    all_request_ids = []

    client = boto3.client("logs")
    logger.info(
        f"Extracting request IDs from {len(log_groups)} log groups using execution ID: {execution_id}"
    )

    for log_group in log_groups[:5]:  # Limit to first 5 groups for performance
        try:
            # Search for all logs in the time window (no filter pattern)
            # We'll extract request IDs from any logs in the execution timeframe
            response = client.filter_log_events(
                logGroupName=log_group,
                startTime=int(start_time.timestamp() * 1000),
                endTime=int(end_time.timestamp() * 1000),
                limit=50,  # Increased limit to find request IDs
            )

            for event in response.get("events", []):
                message = event["message"]

                # Extract request ID from log message
                request_id = _extract_request_id_from_log_message(message)
                if request_id:
                    # Extract function name from log group
                    function_name = _extract_function_name_from_log_group(log_group)

                    if function_name and request_id not in all_request_ids:
                        function_request_map[function_name] = request_id
                        all_request_ids.append(request_id)
                        logger.info(
                            f"Extracted request ID '{request_id}' for function '{function_name}' from CloudWatch logs"
                        )
                        logger.debug(f"Request ID found in message: {message[:200]}...")
                        break  # One request ID per function is sufficient

        except Exception as e:
            logger.debug(f"Failed to search log group {log_group}: {e}")
            continue

    logger.info(
        f"CloudWatch extraction found {len(function_request_map)} function-request mappings"
    )
    return {
        "function_request_map": function_request_map,
        "all_request_ids": list(set(all_request_ids)),
        "extraction_method": "cloudwatch_logs",
        "extraction_success": len(all_request_ids) > 0,
    }


def _extract_request_id_from_log_message(message: str) -> Optional[str]:
    """
    Extract Lambda request ID from CloudWatch log message.
    Lambda logs format: [LEVEL] timestamp request_id message

    Args:
        message: CloudWatch log message

    Returns:
        Request ID string if found, None otherwise
    """
    if not message:
        return None

    # Pattern for Lambda request ID in log messages
    # Format: [INFO] 2025-10-22T18:35:40.357Z 1386c0d2-a9d1-4169-940a-8d35c8899e27 message
    pattern = r"\[\w+\]\s+\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z\s+([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})"

    match = re.search(pattern, message)
    if match:
        return match.group(1)

    # Alternative pattern for different log formats - look for any UUID
    uuid_pattern = r"([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})"
    matches = re.findall(uuid_pattern, message, re.IGNORECASE)

    # Return first UUID that looks like a request ID (not execution ID)
    for match in matches:
        if len(match) == 36:  # Standard UUID length
            return match

    return None


def _extract_function_name_from_log_group(log_group: str) -> str:
    """
    Extract Lambda function name from log group name.

    Args:
        log_group: CloudWatch log group name

    Returns:
        Function name string
    """
    # Log group format: /aws/lambda/FunctionName or /prefix/lambda/FunctionName
    if "/lambda/" in log_group:
        return log_group.split("/lambda/")[-1]

    # Fallback: use last part of log group name
    return log_group.split("/")[-1] if "/" in log_group else log_group


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
        cf_client = boto3.client("cloudformation")
        stack_response = cf_client.describe_stacks(StackName=stack_name)
        stacks = stack_response.get("Stacks", [])

        if stacks:
            outputs = stacks[0].get("Outputs", [])

            for output in outputs:
                output_key = output.get("OutputKey", "")
                output_value = output.get("OutputValue", "")
                logger.debug(f"Checking output: {output_key} = {output_value}")

                if output_key == "StateMachineArn":
                    extracted_prefix = _extract_prefix_from_state_machine_arn(
                        output_value
                    )

                    if extracted_prefix:
                        pattern_prefix = f"/{extracted_prefix}/lambda"

                        return {
                            "stack_name": stack_name,
                            "prefix_type": "pattern",
                            "log_group_prefix": pattern_prefix,
                            "nested_stack_name": extracted_prefix,
                        }

        main_prefix = f"/aws/lambda/{stack_name}"

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
        logger.info(
            f"Found {log_groups.get('log_groups_found', 0)} log groups with prefix '{log_prefix}'"
        )

        if log_groups.get("log_groups_found", 0) > 0:
            group_names = [g["name"] for g in log_groups.get("log_groups", [])]
            logger.info(f"Log group names: {group_names[:3]}...")  # Show first 3

        if log_groups.get("log_groups_found", 0) == 0:
            return {
                "document_id": document_id,
                "log_prefix": log_prefix,
                "events_found": 0,
                "message": "No log groups found",
            }

        # Use precise time window from document context with buffer for batch operations
        start_time = context.get("processing_start_time")
        end_time = context.get("processing_end_time")

        # Add small buffer for batch operations but keep window tight
        if start_time and end_time:
            time_diff = end_time - start_time
            buffer = min(
                timedelta(minutes=2), time_diff * 0.1
            )  # Max 2min buffer or 10% of processing time
            start_time = start_time - buffer
            end_time = end_time + buffer
            logger.info(
                f"Using time window with {buffer.total_seconds()}s buffer for batch operation isolation"
            )

        # Enhanced search strategy with request ID priority
        request_ids = context.get("lambda_request_ids", [])
        function_request_map = context.get("function_request_map", {})
        failed_functions = context.get("failed_functions", [])
        primary_failed_function = context.get("primary_failed_function")
        execution_arn = context.get("execution_arn")
        execution_events_count = context.get("execution_events_count", 0)

        logger.info(
            f"Step Functions extraction - Total request IDs: {len(request_ids)}, Failed functions: {len(failed_functions)}, Events: {execution_events_count}"
        )
        logger.info(
            f"CloudWatch extraction conditions - request_ids: {len(request_ids)}, execution_arn: {bool(execution_arn)}, start_time: {bool(start_time)}, end_time: {bool(end_time)}"
        )

        # NEW: CloudWatch-based request ID extraction if Step Functions extraction failed
        cloudwatch_extraction_used = False
        if len(request_ids) == 0 and execution_arn and start_time and end_time:
            logger.info(
                "Step Functions extraction yielded 0 request IDs, attempting CloudWatch log extraction"
            )

            # Get log group names for extraction
            group_names = [g["name"] for g in log_groups.get("log_groups", [])]
            execution_id = execution_arn.split(":")[-1]

            cloudwatch_extraction = extract_request_ids_from_logs(
                group_names, execution_id, start_time, end_time
            )

            if cloudwatch_extraction.get("extraction_success"):
                # Override Step Functions results with CloudWatch extraction
                function_request_map = cloudwatch_extraction.get(
                    "function_request_map", {}
                )
                request_ids = cloudwatch_extraction.get("all_request_ids", [])
                cloudwatch_extraction_used = True
                logger.info(
                    f"CloudWatch extraction successful - Found {len(request_ids)} request IDs from {len(function_request_map)} functions"
                )
            else:
                logger.warning("CloudWatch extraction also failed to find request IDs")
        elif len(request_ids) == 0:
            logger.warning(
                f"CloudWatch extraction not attempted - missing conditions: execution_arn={bool(execution_arn)}, start_time={bool(start_time)}, end_time={bool(end_time)}"
            )
        else:
            logger.info(
                f"CloudWatch extraction not needed - Step Functions found {len(request_ids)} request IDs"
            )

        logger.info(
            f"Total request IDs: {len(request_ids)}, Function mappings: {len(function_request_map)}"
        )
        logger.info(f"Function request mapping: {function_request_map}")
        logger.info(
            f"Extraction method: {'CloudWatch logs' if cloudwatch_extraction_used else 'Step Functions events'}"
        )

        # Priority 1: Request IDs from failed functions (highest priority)
        failed_function_request_ids = []
        if primary_failed_function and primary_failed_function in function_request_map:
            req_id = function_request_map[primary_failed_function]
            failed_function_request_ids.append(req_id)
            logger.info(
                f"Primary failed function '{primary_failed_function}' has request ID: {req_id}"
            )

        # Add other failed function request IDs
        for func in failed_functions:
            if func in function_request_map:
                req_id = function_request_map[func]
                if req_id not in failed_function_request_ids:
                    failed_function_request_ids.append(req_id)
                    logger.info(f"Failed function '{func}' has request ID: {req_id}")

        # Priority 2: All other request IDs (medium priority)
        other_request_ids = [
            rid for rid in request_ids if rid not in failed_function_request_ids
        ]

        # Priority 3: Step Functions execution-based search (fallback only)
        execution_patterns = []
        if execution_arn and not failed_function_request_ids:
            execution_name = execution_arn.split(":")[-1]
            execution_patterns.append(execution_name)
            logger.info(f"Using execution based pattern: {execution_name}")

        # Build search strategy
        search_strategy = {
            "failed_function_request_ids": failed_function_request_ids,
            "other_request_ids": other_request_ids,
            "execution_patterns": execution_patterns,
        }

        # Search logs with prioritized strategy
        all_results = []
        total_events = 0
        groups_to_search = log_groups["log_groups"][:max_log_groups]

        # Search with failed function request IDs (highest priority)
        for request_id in search_strategy["failed_function_request_ids"]:
            for group in groups_to_search:
                log_group_name = group["name"]
                search_result = search_cloudwatch_logs(
                    log_group_name=log_group_name,
                    filter_pattern="ERROR",
                    max_events=max_log_events,
                    start_time=start_time,
                    end_time=end_time,
                    request_id=request_id,
                )
                logger.debug(
                    f"Search result for request ID '{request_id}': {search_result.get('events_found', 0)} events found"
                )

                if search_result.get("events_found", 0) > 0:
                    logger.info(
                        f"Found {search_result['events_found']} events in {log_group_name} with request ID {request_id}"
                    )

                    all_results.append(
                        {
                            "log_group": log_group_name,
                            "search_type": "failed_function_request_id",
                            "pattern_used": request_id,
                            "events_found": search_result["events_found"],
                            "events": search_result["events"],
                        }
                    )
                    total_events += search_result["events_found"]

            # If we found errors from failed functions, we have what we need
            if total_events > 0:
                logger.info(
                    f"Found {total_events} events from failed function request IDs, stopping search"
                )
                break

        # Search with other request IDs if no errors found yet
        if total_events == 0 and search_strategy["other_request_ids"]:
            for request_id in search_strategy["other_request_ids"][
                :3
            ]:  # Limit to first 3
                for group in groups_to_search:
                    log_group_name = group["name"]

                    search_result = search_cloudwatch_logs(
                        log_group_name=log_group_name,
                        filter_pattern="ERROR",
                        max_events=max_log_events,
                        start_time=start_time,
                        end_time=end_time,
                        request_id=request_id,
                    )

                    if search_result.get("events_found", 0) > 0:
                        logger.info(
                            f"Found {search_result['events_found']} events in {log_group_name} with request ID {request_id}"
                        )

                        all_results.append(
                            {
                                "log_group": log_group_name,
                                "search_type": "other_request_id",
                                "pattern_used": request_id,
                                "events_found": search_result["events_found"],
                                "events": search_result["events"],
                            }
                        )
                        total_events += search_result["events_found"]

                if total_events > 0:
                    break

        # Fallback to execution-based search if still no results
        if total_events == 0 and search_strategy["execution_patterns"]:
            # Document-specific search using document ID for batch operation safety
            if total_events == 0:
                # Extract document identifier for precise filtering
                doc_identifier = document_id.replace(".pdf", "").replace(".", "-")

                for group in groups_to_search[:3]:  # Limit to first 3 groups
                    log_group_name = group["name"]
                    # Try document-specific search first
                    search_result = search_cloudwatch_logs(
                        log_group_name=log_group_name,
                        filter_pattern=doc_identifier,
                        max_events=max_log_events,
                        start_time=start_time,
                        end_time=end_time,
                    )

                    if search_result.get("events_found", 0) > 0:
                        logger.info(
                            f"Found {search_result['events_found']} document-specific events in {log_group_name}"
                        )

                        # Filter for actual errors in document-specific logs
                        error_events = []
                        for event in search_result.get("events", []):
                            message = event.get("message", "")
                            if any(
                                error_term in message.upper()
                                for error_term in [
                                    "ERROR",
                                    "EXCEPTION",
                                    "FAILED",
                                    "TIMEOUT",
                                ]
                            ):
                                error_events.append(event)

                        if error_events:
                            logger.info(
                                f"Found {len(error_events)} actual errors in document-specific search"
                            )
                            for i, event in enumerate(error_events[:2]):
                                logger.info(
                                    f"Document Error {i + 1}: {event.get('message', '')[:300]}..."
                                )

                            all_results.append(
                                {
                                    "log_group": log_group_name,
                                    "search_type": "document_specific_error_search",
                                    "pattern_used": doc_identifier,
                                    "events_found": len(error_events),
                                    "events": error_events,
                                }
                            )
                            total_events += len(error_events)
                            break

                # Fallback to broad ERROR search only if document-specific search fails
                if total_events == 0:
                    for group in groups_to_search[:2]:  # Further limit for broad search
                        log_group_name = group["name"]

                        search_result = search_cloudwatch_logs(
                            log_group_name=log_group_name,
                            filter_pattern="ERROR",
                            max_events=max_log_events,
                            start_time=start_time,
                            end_time=end_time,
                        )

                        if search_result.get("events_found", 0) > 0:
                            logger.info(
                                f"Found {search_result['events_found']} events in {log_group_name} with broad ERROR search"
                            )

                            all_results.append(
                                {
                                    "log_group": log_group_name,
                                    "search_type": "broad_error_search_fallback",
                                    "pattern_used": "ERROR",
                                    "events_found": search_result["events_found"],
                                    "events": search_result["events"],
                                    "warning": "May include errors from other concurrent documents",
                                }
                            )
                            total_events += search_result["events_found"]
                            break

            for pattern in search_strategy["execution_patterns"]:
                for group in groups_to_search:
                    log_group_name = group["name"]
                    search_result = search_cloudwatch_logs(
                        log_group_name=log_group_name,
                        filter_pattern=pattern,
                        max_events=max_log_events,
                        start_time=start_time,
                        end_time=end_time,
                    )
                    logger.debug(
                        f"Search result for execution pattern '{pattern}': {search_result.get('events_found', 0)} events found"
                    )

                    if search_result.get("events_found", 0) > 0:
                        logger.info(
                            f"Found {search_result['events_found']} events in {log_group_name} with execution pattern {pattern}"
                        )

                        all_results.append(
                            {
                                "log_group": log_group_name,
                                "search_type": "execution_fallback",
                                "pattern_used": pattern,
                                "events_found": search_result["events_found"],
                                "events": search_result["events"],
                            }
                        )
                        total_events += search_result["events_found"]

                if total_events > 0:
                    break

        return {
            "analysis_type": "document_specific",
            "document_id": document_id,
            "document_status": context.get("document_status"),
            "execution_arn": execution_arn,
            "search_strategy": search_strategy,
            "cloudwatch_extraction_used": cloudwatch_extraction_used,
            "extraction_method": "cloudwatch_logs"
            if cloudwatch_extraction_used
            else "step_functions",
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
