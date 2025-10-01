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

from ..config import get_error_analyzer_config
from .lambda_tools import get_document_context

logger = logging.getLogger(__name__)


def search_cloudwatch_logs(
    log_group_name: str,
    filter_pattern: str = "",
    hours_back: int = 24,
    max_events: int = 5,
    start_time: datetime = None,
    end_time: datetime = None,
) -> Dict[str, Any]:
    """Internal function: Search CloudWatch logs for error patterns."""
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

        params = {
            "logGroupName": log_group_name,
            "startTime": int(search_start.timestamp() * 1000),
            "endTime": int(search_end.timestamp() * 1000),
            "limit": max_events,
        }

        if filter_pattern:
            params["filterPattern"] = filter_pattern

        response = client.filter_log_events(**params)

        events = []
        for event in response.get("events", []):
            events.append(
                {
                    "timestamp": datetime.fromtimestamp(
                        event["timestamp"] / 1000
                    ).isoformat(),
                    "message": event["message"],
                    "log_stream": event.get("logStreamName", ""),
                }
            )

        return {
            "log_group": log_group_name,
            "events_found": len(events),
            "events": events,
            "filter_pattern": filter_pattern,
        }

    except Exception as e:
        logger.error(f"CloudWatch search failed for log group '{log_group_name}': {e}")
        return {"error": str(e), "events_found": 0, "events": []}


def get_cloudwatch_log_groups(prefix: str = "") -> Dict[str, Any]:
    """Internal function: List CloudWatch log groups with prefix filter."""
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
        return {"error": str(e), "log_groups_found": 0, "log_groups": []}


def _extract_prefix_from_state_machine_arn(arn: str) -> str:
    """Extract prefix from StateMachineArn."""
    if ":stateMachine:" in arn:
        state_machine_name = arn.split(":stateMachine:")[-1]
        if "-DocumentProcessingWorkflow" in state_machine_name:
            return state_machine_name.replace("-DocumentProcessingWorkflow", "")
        parts = state_machine_name.split("-")
        if len(parts) > 1:
            return "-".join(parts[:-1])
    return ""


def get_log_group_prefix(stack_name: str) -> Dict[str, Any]:
    """Determine the correct CloudWatch log group prefix for a stack."""
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
        return {"error": str(e), "stack_name": stack_name}


@tool
def search_document_logs(
    document_id: str,
    stack_name: str,
    filter_pattern: str = "ERROR",
    max_events_per_group: int = None,
    max_log_groups: int = 15,
) -> Dict[str, Any]:
    """
    Search CloudWatch logs for a specific document using execution context.
    """
    try:
        # Load configuration to get max_log_events parameter
        config = get_error_analyzer_config()
        if max_events_per_group is None:
            max_events_per_group = config.get("max_log_events", 10)
        # Get document execution context
        context = get_document_context(document_id, stack_name)

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

        # Build filter patterns for document-specific search
        search_patterns = [filter_pattern]

        # Add execution ARN as filter if available
        execution_arn = context.get("execution_arn")
        if execution_arn:
            # Extract execution name from ARN for filtering
            execution_name = execution_arn.split(":")[-1]
            search_patterns.append(execution_name)

        # Add Lambda request IDs as filters
        request_ids = context.get("lambda_request_ids", [])
        search_patterns.extend(request_ids)

        # Add document ID as filter
        search_patterns.append(document_id)

        # Search logs with multiple patterns
        all_results = []
        total_events = 0

        groups_to_search = log_groups["log_groups"][:max_log_groups]

        for group in groups_to_search:
            log_group_name = group["name"]
            logger.info(f"Searching log group: {log_group_name}")

            # Try each search pattern
            for pattern in search_patterns:
                if not pattern:
                    continue

                logger.info(f"  Using filter pattern: '{pattern}'")
                search_result = search_cloudwatch_logs(
                    log_group_name=log_group_name,
                    filter_pattern=pattern,
                    max_events=max_events_per_group,
                    start_time=start_time,
                    end_time=end_time,
                )

                if search_result.get("events_found", 0) > 0:
                    logger.info(
                        f"  Found {search_result['events_found']} events in {log_group_name}"
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

                    # Continue searching other groups for more errors
                    # break  # Removed to search ALL log groups
                else:
                    logger.info(
                        f"  No events found in {log_group_name} with pattern '{pattern}'"
                    )

        return {
            "analysis_type": "document_specific",
            "document_id": document_id,
            "document_status": context.get("document_status"),
            "execution_arn": execution_arn,
            "search_patterns_used": search_patterns,
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
        return {"error": str(e), "document_id": document_id, "events_found": 0}


@tool
def search_stack_logs(
    filter_pattern: str = "ERROR",
    hours_back: int = None,
    max_events_per_group: int = None,
    max_log_groups: int = 15,
    start_time: datetime = None,
    end_time: datetime = None,
) -> Dict[str, Any]:
    """
    PRIMARY TOOL: Search CloudWatch logs by automatically finding correct log groups.
    """
    stack_name = os.environ.get("AWS_STACK_NAME", "")

    if not stack_name:
        return {
            "error": "AWS_STACK_NAME not configured in environment",
            "events_found": 0,
        }

    try:
        # Load configuration to get parameters
        config = get_error_analyzer_config()
        if max_events_per_group is None:
            max_events_per_group = config.get("max_log_events", 5)
        if hours_back is None:
            hours_back = config.get("time_range_hours_default", 24)
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
            logger.info(
                f"Searching log group: {log_group_name} with pattern '{filter_pattern}'"
            )

            search_result = search_cloudwatch_logs(
                log_group_name=log_group_name,
                filter_pattern=filter_pattern,
                hours_back=hours_back,
                max_events=max_events_per_group,
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
                logger.info(f"No events found in {log_group_name}")

        return {
            "stack_name": stack_name,
            "log_prefix_used": log_prefix,
            "prefix_type": prefix_type,
            "filter_pattern": filter_pattern,
            "total_log_groups_found": log_groups.get("log_groups_found", 0),
            "log_groups_searched": len(groups_to_search),
            "log_groups_with_events": len(all_results),
            "total_events_found": total_events,
            "max_events_per_group": max_events_per_group,
            "results": all_results,
        }

    except Exception as e:
        logger.error(f"Stack log search failed for '{stack_name}': {e}")
        return {"error": str(e), "stack_name": stack_name, "events_found": 0}
