# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
Document-specific analysis tool.
"""

import logging
from typing import Any, Dict

from strands import tool

from .cloudwatch_tools import search_document_logs
from .lambda_tools import get_document_context

logger = logging.getLogger(__name__)


@tool
def analyze_document_failure(
    document_id: str, stack_name: str, max_log_events: int = 10
) -> Dict[str, Any]:
    """
    Analyze failure for a specific document using lookup function and enhanced log search.

    Args:
        document_id: Document ObjectKey to analyze
        stack_name: CloudFormation stack name
    """
    try:
        # Get document context via lookup function
        context = get_document_context(document_id, stack_name)

        if not context.get("document_found"):
            return {
                "analysis_type": "document_not_found",
                "document_id": document_id,
                "document_found": False,
                "error": context.get("error", "Document not found"),
                "analysis_summary": f"Document '{document_id}' was not found in the tracking database",
                "root_cause": "The specified document could not be located in the system's tracking database",
                "recommendations": [
                    "Verify the document filename is correct and matches exactly",
                    "Check if the document was successfully uploaded to the system",
                    "Ensure the document processing was initiated",
                    "Contact support if the document should exist in the system",
                ],
            }

        # Search document-specific logs
        log_results = search_document_logs(
            document_id=document_id,
            stack_name=stack_name,
            filter_pattern="ERROR",
            max_log_events=int(max_log_events),
            max_log_groups=20,
        )

        # Extract document details from context
        document_status = context.get("document_status")
        execution_arn = context.get("execution_arn")
        timestamps = context.get("timestamps", {})
        completion_time = timestamps.get("CompletionTime")

        # Build analysis summary
        analysis_summary = (
            f"Document {document_id} failed with status {document_status}"
        )
        if completion_time:
            analysis_summary += f" at {completion_time}"

        # Add execution context to summary
        if execution_arn:
            analysis_summary += f". Execution: {execution_arn.split(':')[-1]}"

        return {
            "analysis_type": "document_specific",
            "document_id": document_id,
            "document_found": True,
            "document_status": document_status,
            "execution_arn": execution_arn,
            "completion_time": completion_time,
            "timestamps": timestamps,
            "lambda_request_ids": context.get("lambda_request_ids", []),
            "log_analysis": log_results,
            "analysis_summary": analysis_summary,
            "recommendations": [
                "Review the document-specific logs filtered by execution context",
                "Check Lambda request IDs for detailed function-level errors",
                "Examine Step Function execution history for workflow failures",
                "Consider reprocessing the document if it was a transient error",
            ],
        }

    except Exception as e:
        logger.error(f"Error analyzing document failure: {e}")
        return {"error": str(e), "document_id": document_id}
