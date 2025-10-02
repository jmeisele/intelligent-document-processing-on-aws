# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
System-wide analysis tool.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict

from strands import tool

from .cloudwatch_tools import search_stack_logs
from .dynamodb_tools import find_tracking_table, scan_dynamodb_table

logger = logging.getLogger(__name__)


@tool
def analyze_recent_system_errors(
    time_range_hours: int, stack_name: str, max_log_events: int = 10
) -> Dict[str, Any]:
    """
    Analyze recent system errors by finding failed documents and correlating with logs.

    Args:
        time_range_hours: Hours to look back for analysis
        stack_name: CloudFormation stack name
    """
    try:
        # Find recent failed documents
        tracking_info = find_tracking_table(stack_name)
        if not tracking_info.get("tracking_table_found"):
            return {"error": "TrackingTable not found"}

        table_name = tracking_info.get("table_name")

        # Scan for recent failed documents using correct field names
        error_records = scan_dynamodb_table(
            table_name, filter_expression="ObjectStatus = 'FAILED'", limit=20
        )

        # Filter by time range
        threshold_time = datetime.utcnow() - timedelta(hours=time_range_hours)
        recent_failures = []

        for item in error_records.get("items", []):
            # Use CompletionTime if available, otherwise fall back to LastModified
            completion_time = item.get("CompletionTime") or item.get("LastModified")
            if completion_time:
                try:
                    if isinstance(completion_time, str):
                        # Handle different timestamp formats
                        if completion_time.endswith("Z"):
                            completion_dt = datetime.fromisoformat(
                                completion_time.replace("Z", "+00:00")
                            )
                        elif "+00:00" in completion_time:
                            completion_dt = datetime.fromisoformat(completion_time)
                        else:
                            completion_dt = datetime.fromisoformat(
                                completion_time + "+00:00"
                            )
                    else:
                        continue

                    if completion_dt > threshold_time:
                        recent_failures.append(
                            {
                                "document_id": item.get("ObjectKey"),
                                "status": item.get("ObjectStatus")
                                or item.get("Status"),
                                "completion_time": completion_time,
                                "error_message": item.get("ErrorMessage"),
                            }
                        )
                except (ValueError, TypeError) as e:
                    logger.debug(f"Could not parse timestamp {completion_time}: {e}")
                    continue

        # Search stack logs for errors in the time range
        log_results = search_stack_logs(
            filter_pattern="ERROR",
            hours_back=time_range_hours,
            max_log_events=max_log_events,
            max_log_groups=20,
        )

        return {
            "analysis_type": "system_wide",
            "time_range_hours": time_range_hours,
            "recent_failures_count": len(recent_failures),
            "recent_failures": recent_failures[:5],  # Show top 5
            "log_analysis": log_results,
            "analysis_summary": f"Found {len(recent_failures)} recent failures in the last {time_range_hours} hours",
            "recommendations": [
                "Review the failed documents for common patterns",
                "Check CloudWatch logs for recurring error messages",
                "Monitor system resources and scaling",
                "Consider adjusting retry policies if errors are transient",
            ],
        }

    except Exception as e:
        logger.error(f"Error analyzing recent system errors: {e}")
        return {"error": str(e)}
