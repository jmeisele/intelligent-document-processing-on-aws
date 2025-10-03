# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
Lambda tools for document context extraction.
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List

import boto3
from strands import tool

logger = logging.getLogger(__name__)


def get_lookup_function_name(stack_name: str) -> str:
    """Get lookup function name from stack."""
    try:
        cf_client = boto3.client("cloudformation")
        response = cf_client.describe_stack_resources(
            StackName=stack_name, LogicalResourceId="LookupFunction"
        )
        return response["StackResources"][0]["PhysicalResourceId"]
    except Exception:
        return f"{stack_name}-LookupFunction"


def extract_lambda_request_ids(execution_events: List[Dict[str, Any]]) -> List[str]:
    """Extract Lambda request IDs from Step Function execution events."""
    request_ids = []

    for event in execution_events:
        event_type = event.get("type", "")

        # Look for Lambda task events
        if event_type in [
            "LambdaFunctionSucceeded",
            "LambdaFunctionFailed",
            "LambdaFunctionTimedOut",
        ]:
            # Extract request ID from event details if available
            event_detail = (
                event.get("lambdaFunctionSucceededEventDetails")
                or event.get("lambdaFunctionFailedEventDetails")
                or event.get("lambdaFunctionTimedOutEventDetails")
            )

            if event_detail and isinstance(event_detail, dict):
                # Request ID might be in output or error details
                output = event_detail.get("output", "")
                if output:
                    try:
                        output_data = json.loads(output)
                        if "requestId" in output_data:
                            request_ids.append(output_data["requestId"])
                    except (json.JSONDecodeError, TypeError):
                        pass

    return list(set(request_ids))  # Remove duplicates


@tool
def get_document_context(document_id: str, stack_name: str) -> Dict[str, Any]:
    """
    Get document execution context via lookup_function Lambda.

    Args:
        document_id: Document ObjectKey to analyze
        stack_name: CloudFormation stack name
    """
    try:
        lambda_client = boto3.client("lambda")
        function_name = get_lookup_function_name(stack_name)

        logger.info(
            f"Invoking lookup function: {function_name} for document: {document_id}"
        )

        # Invoke lookup function
        response = lambda_client.invoke(
            FunctionName=function_name,
            InvocationType="RequestResponse",
            Payload=json.dumps({"object_key": document_id}),
        )

        # Parse response
        payload = json.loads(response["Payload"].read().decode("utf-8"))

        if payload.get("status") == "NOT_FOUND":
            return {
                "document_found": False,
                "document_id": document_id,
                "error": "Document not found in tracking database",
            }

        if payload.get("status") == "ERROR":
            return {
                "document_found": False,
                "document_id": document_id,
                "error": payload.get("message", "Unknown error from lookup function"),
            }

        # Extract execution context
        processing_detail = payload.get("processingDetail", {})
        execution_arn = processing_detail.get("executionArn")
        execution_events = processing_detail.get("events", [])

        # Extract Lambda request IDs from execution events
        request_ids = extract_lambda_request_ids(execution_events)

        # Get timestamps for precise time windows
        timestamps = payload.get("timing", {}).get("timestamps", {})

        # Calculate processing time window
        start_time = None
        end_time = None

        if timestamps.get("WorkflowStartTime"):
            start_time = datetime.fromisoformat(
                timestamps["WorkflowStartTime"].replace("Z", "+00:00")
            )

        if timestamps.get("CompletionTime"):
            end_time = datetime.fromisoformat(
                timestamps["CompletionTime"].replace("Z", "+00:00")
            )

        return {
            "document_found": True,
            "document_id": document_id,
            "document_status": payload.get("status"),
            "execution_arn": execution_arn,
            "lambda_request_ids": request_ids,
            "timestamps": timestamps,
            "processing_start_time": start_time,
            "processing_end_time": end_time,
            "execution_events_count": len(execution_events),
            "lookup_function_response": payload,
        }

    except Exception as e:
        logger.error(f"Error getting document context for {document_id}: {e}")
        return {"document_found": False, "document_id": document_id, "error": str(e)}
