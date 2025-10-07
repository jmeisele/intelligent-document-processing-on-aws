# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
DynamoDB tools for error analysis.
"""

import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict

import boto3
from strands import tool

logger = logging.getLogger(__name__)


@tool
def get_document_status(object_key: str) -> Dict[str, Any]:
    """
    Get document status using direct DynamoDB lookup.

    Args:
        object_key: The S3 object key for the document
    """
    try:
        result = get_document_by_key(object_key)

        if result.get("document_found"):
            document = result.get("document", {})
            return {
                "document_found": True,
                "object_key": object_key,
                "status": document.get("Status"),
                "initial_event_time": document.get("InitialEventTime"),
                "completion_time": document.get("CompletionTime"),
                "execution_arn": document.get("ExecutionArn"),
            }
        else:
            return result

    except Exception as e:
        logger.error(f"Status lookup failed for '{object_key}': {e}")
        return {"document_found": False, "object_key": object_key, "error": str(e)}


@tool
def get_tracking_table_name() -> Dict[str, Any]:
    """
    Get the TrackingTable name from environment variable.
    """
    table_name = os.environ.get("TRACKING_TABLE_NAME")
    if table_name:
        return {
            "tracking_table_found": True,
            "table_name": table_name,
        }
    return {
        "tracking_table_found": False,
        "error": "TRACKING_TABLE_NAME environment variable not set",
    }


@tool
def query_tracking_table(
    date: str = "", hours_back: int = 24, limit: int = 100
) -> Dict[str, Any]:
    """
    Query TrackingTable efficiently using time-based partitions.

    Args:
        date: Date in YYYY-MM-DD format (defaults to today)
        hours_back: Number of hours to look back from date (default 24)
        limit: Maximum number of items to return
    """
    try:
        table_name = os.environ.get("TRACKING_TABLE_NAME")
        if not table_name:
            return {"error": "TRACKING_TABLE_NAME environment variable not set"}

        dynamodb = boto3.resource("dynamodb")
        table = dynamodb.Table(table_name)

        # Use current date if not provided
        if not date:
            date = datetime.now().strftime("%Y-%m-%d")

        # Generate time-based partition keys to query
        base_date = datetime.strptime(date, "%Y-%m-%d")
        end_time = base_date + timedelta(days=1)
        start_time = end_time - timedelta(hours=hours_back)

        all_items = []
        current_time = start_time

        # Query by hour partitions for efficiency
        while current_time < end_time and len(all_items) < limit:
            hour_str = current_time.strftime("%Y-%m-%dT%H")

            # Query the list partition for this hour
            pk = f"list#{current_time.strftime('%Y-%m-%d')}#s#{current_time.hour // 4:02d}"
            sk_prefix = f"ts#{hour_str}"

            try:
                response = table.query(
                    KeyConditionExpression="PK = :pk AND begins_with(SK, :sk_prefix)",
                    ExpressionAttributeValues={":pk": pk, ":sk_prefix": sk_prefix},
                    Limit=min(limit - len(all_items), 50),
                )

                items = response.get("Items", [])
                all_items.extend(items)

            except Exception as query_error:
                logger.debug(f"Query failed for {pk}: {query_error}")

            current_time += timedelta(hours=1)

        def decimal_to_float(obj):
            if hasattr(obj, "__class__") and obj.__class__.__name__ == "Decimal":
                return float(obj)
            elif isinstance(obj, dict):
                return {k: decimal_to_float(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [decimal_to_float(v) for v in obj]
            return obj

        items = [decimal_to_float(item) for item in all_items[:limit]]

        return {
            "table_name": table_name,
            "items_found": len(items),
            "items": items,
            "query_date": date,
            "hours_back": hours_back,
        }

    except Exception as e:
        logger.error(f"TrackingTable query failed: {e}")
        return {"error": str(e), "items_found": 0, "items": []}


@tool
def get_document_by_key(object_key: str) -> Dict[str, Any]:
    """
    Get a specific document from TrackingTable by object key.

    Args:
        object_key: The S3 object key for the document
    """
    try:
        table_name = os.environ.get("TRACKING_TABLE_NAME")
        if not table_name:
            return {"error": "TRACKING_TABLE_NAME environment variable not set"}

        dynamodb = boto3.resource("dynamodb")
        table = dynamodb.Table(table_name)

        # Direct key lookup
        response = table.get_item(Key={"PK": f"doc#{object_key}", "SK": "none"})

        if "Item" in response:

            def decimal_to_float(obj):
                if hasattr(obj, "__class__") and obj.__class__.__name__ == "Decimal":
                    return float(obj)
                elif isinstance(obj, dict):
                    return {k: decimal_to_float(v) for k, v in obj.items()}
                elif isinstance(obj, list):
                    return [decimal_to_float(v) for v in obj]
                return obj

            item = decimal_to_float(response["Item"])
            return {
                "document_found": True,
                "document": item,
                "object_key": object_key,
            }
        else:
            return {
                "document_found": False,
                "object_key": object_key,
                "error": f"Document not found for key: {object_key}",
            }

    except Exception as e:
        logger.error(f"Document lookup failed for key '{object_key}': {e}")
        return {"document_found": False, "object_key": object_key, "error": str(e)}
