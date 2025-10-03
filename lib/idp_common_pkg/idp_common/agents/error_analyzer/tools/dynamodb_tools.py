# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
DynamoDB tools for error analysis.
"""

import logging
from typing import Any, Dict

import boto3
from strands import tool

logger = logging.getLogger(__name__)


@tool
def scan_dynamodb_table(
    table_name: str, filter_expression: str = "", limit: int = 100
) -> Dict[str, Any]:
    """
    Scan DynamoDB table for analysis.
    """
    try:
        dynamodb = boto3.resource("dynamodb")
        table = dynamodb.Table(table_name)

        scan_params = {"Limit": limit}

        if filter_expression and "=" in filter_expression:
            from boto3.dynamodb.conditions import Attr

            attr_name, attr_value = filter_expression.split("=", 1)
            attr_name = attr_name.strip()
            attr_value = attr_value.strip().strip("\"'")
            scan_params["FilterExpression"] = Attr(attr_name).eq(attr_value)

        response = table.scan(**scan_params)

        def decimal_to_float(obj):
            if hasattr(obj, "__class__") and obj.__class__.__name__ == "Decimal":
                return float(obj)
            elif isinstance(obj, dict):
                return {k: decimal_to_float(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [decimal_to_float(v) for v in obj]
            return obj

        items = [decimal_to_float(item) for item in response.get("Items", [])]

        return {
            "table_name": table_name,
            "items_found": len(items),
            "items": items,
            "scanned_count": response.get("ScannedCount", 0),
        }

    except Exception as e:
        logger.error(f"DynamoDB scan failed: {e}")
        return {"error": str(e), "items_found": 0, "items": []}


@tool
def find_tracking_table(stack_name: str) -> Dict[str, Any]:
    """
    Find the TrackingTable for a given stack.
    """
    try:
        dynamodb = boto3.client("dynamodb")
        response = dynamodb.list_tables()

        # Look for the main TrackingTable, excluding DiscoveryTrackingTable
        tracking_tables = []
        for table_name in response.get("TableNames", []):
            if stack_name in table_name and "TrackingTable" in table_name:
                tracking_tables.append(table_name)

        logger.info(f"Found tables with 'TrackingTable': {tracking_tables}")

        # Prefer the main TrackingTable over DiscoveryTrackingTable
        main_tracking_table = None
        for table_name in tracking_tables:
            if "DiscoveryTrackingTable" not in table_name:
                main_tracking_table = table_name
                break

        # If no main tracking table found, use any tracking table as fallback
        if not main_tracking_table and tracking_tables:
            main_tracking_table = tracking_tables[0]
            logger.warning(f"Using fallback tracking table: {main_tracking_table}")

        if main_tracking_table:
            logger.info(f"Selected tracking table: {main_tracking_table}")
            return {
                "tracking_table_found": True,
                "table_name": main_tracking_table,
                "stack_name": stack_name,
            }

        return {
            "tracking_table_found": False,
            "error": f"No TrackingTable found for stack '{stack_name}'",
            "stack_name": stack_name,
        }

    except Exception as e:
        logger.error(f"Failed to find tracking table for stack '{stack_name}': {e}")
        return {
            "tracking_table_found": False,
            "error": str(e),
            "stack_name": stack_name,
        }
