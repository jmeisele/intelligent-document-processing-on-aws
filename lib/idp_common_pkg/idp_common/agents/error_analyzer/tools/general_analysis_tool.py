# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
System-wide analysis tool.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List

from strands import tool

from .cloudwatch_tools import search_stack_logs
from .dynamodb_tools import find_tracking_table, scan_dynamodb_table

logger = logging.getLogger(__name__)


def _get_prioritized_error_patterns() -> List[tuple[str, int]]:
    """Return error patterns with priority and max events per pattern."""
    return [
        ("ERROR", 5),  # Most critical, get 5 events
        ("Exception", 3),  # Important, get 3 events
        ("ValidationException", 2),  # Specific validation issues
        ("Failed", 2),  # General failures
        ("Timeout", 1),  # Performance issues
    ]


def _filter_and_deduplicate_events(events: List[Dict]) -> List[Dict]:
    """Keep only unique, meaningful error events."""
    import re

    seen_messages = set()
    filtered = []

    for event in events:
        message = event.get("message", "")
        # Extract error signature (remove timestamps, request IDs, etc.)
        error_signature = re.sub(r"\d{4}-\d{2}-\d{2}.*?Z", "", message)
        error_signature = re.sub(r"RequestId: [a-f0-9-]+", "", error_signature)

        if error_signature not in seen_messages and len(filtered) < 10:
            seen_messages.add(error_signature)
            filtered.append(
                {
                    "timestamp": event["timestamp"],
                    "message": message[:200] + "..." if len(message) > 200 else message,
                    "log_stream": event.get("log_stream", "")[:50],
                }
            )

    return filtered


def _categorize_errors(log_events: List[Dict]) -> Dict[str, List[Dict]]:
    """Categorize errors by type and analyze patterns."""
    categories = {
        "validation_errors": [],
        "processing_errors": [],
        "system_errors": [],
        "timeout_errors": [],
        "access_errors": [],
    }

    for event in log_events:
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


def _generate_error_summary(
    categories: Dict, failed_documents: List, total_estimate: int
) -> str:
    """Generate comprehensive error summary with insights."""
    total_errors = sum(len(errors) for errors in categories.values())

    if total_errors == 0:
        return "No processing errors found in the specified time range"

    summary_parts = [
        f"Found {total_estimate} total errors across {len(failed_documents)} failed documents"
    ]

    # Add category breakdown
    for category, errors in categories.items():
        if errors:
            category_name = category.replace("_", " ")
            summary_parts.append(f"{len(errors)} {category_name}")

    return ". ".join(summary_parts)


@tool
def analyze_recent_system_errors(
    time_range_hours: int, stack_name: str, max_log_events: int = 5
) -> Dict[str, Any]:
    """
    Enhanced system-wide error analysis with multi-pattern detection and categorization.

    Args:
        time_range_hours: Hours to look back for analysis
        stack_name: CloudFormation stack name
        max_log_events: Maximum log events to include in response
    """
    try:
        # Ensure parameters are integers
        time_range_hours = int(float(time_range_hours))
        max_log_events = int(float(max_log_events))

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
        threshold_time = datetime.utcnow() - timedelta(hours=int(time_range_hours))
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

        # Step 1: Quick scan to estimate error volume
        initial_scan = search_stack_logs(
            filter_pattern="ERROR",
            hours_back=int(time_range_hours),
            max_log_events=5,
            max_log_groups=5,
        )

        total_errors_estimate = initial_scan.get("total_events_found", 0)

        # Step 2: Multi-pattern error search with limits
        error_summary = {}
        all_log_events = []
        total_events_collected = 0

        for pattern, max_events in _get_prioritized_error_patterns():
            if total_events_collected >= int(max_log_events):
                break

            results = search_stack_logs(
                filter_pattern=pattern,
                hours_back=int(time_range_hours),
                max_log_events=min(
                    max_events, int(max_log_events) - total_events_collected
                ),
                max_log_groups=10,
            )

            if results.get("total_events_found", 0) > 0:
                # Collect events from all log groups
                pattern_events = []
                for result in results.get("results", []):
                    pattern_events.extend(result.get("events", []))

                # Filter and deduplicate
                filtered_events = _filter_and_deduplicate_events(pattern_events)

                error_summary[pattern] = {
                    "count": results.get("total_events_found", 0),
                    "sample_events": filtered_events[:2],  # Only keep 2 sample events
                }
                all_log_events.extend(filtered_events)
                total_events_collected += len(filtered_events)

        # Step 3: Categorize errors
        categorized_errors = _categorize_errors(all_log_events)

        # Step 4: Generate compact summary
        analysis_summary = _generate_error_summary(
            categorized_errors, recent_failures, total_errors_estimate
        )

        return {
            "analysis_type": "system_wide",
            "time_range_hours": time_range_hours,
            "total_errors_estimate": total_errors_estimate,
            "recent_failures_count": len(recent_failures),
            "recent_failures": recent_failures[:3],  # Show top 3
            "error_categories": {
                category: {
                    "count": len(errors),
                    "sample": errors[0]["message"][:100] + "..." if errors else None,
                }
                for category, errors in categorized_errors.items()
                if errors
            },
            "error_summary": error_summary,
            "analysis_summary": analysis_summary,
            "context_management": {
                "events_collected": total_events_collected,
                "events_limit": int(max_log_events),
                "strategy": "adaptive_sampling",
            },
            "recommendations": [
                "Review error categories for patterns",
                "Check validation errors for data quality issues",
                "Monitor timeout errors for performance problems",
                "Consider adjusting retry policies if errors are transient",
            ],
        }

    except Exception as e:
        logger.error(f"Error analyzing recent system errors: {e}")
        return {"error": str(e)}
