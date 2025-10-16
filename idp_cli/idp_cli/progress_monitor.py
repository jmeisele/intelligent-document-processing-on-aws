# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
Progress Monitor Module

Monitors batch processing progress by querying document status via LookupFunction.
"""

import json
import logging
from typing import Dict, List

import boto3

logger = logging.getLogger(__name__)


class ProgressMonitor:
    """Monitors document processing progress"""

    def __init__(self, stack_name: str, resources: Dict[str, str]):
        """
        Initialize progress monitor

        Args:
            stack_name: Name of the CloudFormation stack
            resources: Dictionary of stack resources
        """
        self.stack_name = stack_name
        self.resources = resources
        self.lambda_client = boto3.client("lambda")
        self.lookup_function = resources.get("LookupFunctionName", "")

        # Track finished documents to avoid redundant queries
        self.finished_docs = {}  # {doc_id: status_info}

        if not self.lookup_function:
            raise ValueError("LookupFunctionName not found in stack resources")

    def get_batch_status(self, document_ids: List[str]) -> Dict:
        """
        Get status of all documents in batch using optimized batch query

        Uses batch Lambda invocation and caches finished documents to reduce API calls.

        Args:
            document_ids: List of document IDs to check

        Returns:
            Dictionary with status summary
        """
        status_summary = {
            "completed": [],
            "running": [],
            "queued": [],
            "failed": [],
            "all_complete": False,
            "total": len(document_ids),
        }

        # Separate finished (cached) from active (need to query) documents
        docs_to_query = []
        for doc_id in document_ids:
            if doc_id in self.finished_docs:
                # Use cached status
                cached = self.finished_docs[doc_id]
                self._categorize_document(cached, status_summary)
            else:
                docs_to_query.append(doc_id)

        # If all docs are finished, return cached results
        if not docs_to_query:
            logger.debug("All documents finished (using cache)")
            finished = len(status_summary["completed"]) + len(status_summary["failed"])
            status_summary["all_complete"] = finished == len(document_ids)
            return status_summary

        logger.debug(
            f"Querying {len(docs_to_query)} active documents ({len(self.finished_docs)} cached)"
        )

        # Batch query active documents
        try:
            statuses = self._batch_query_documents(docs_to_query)

            for status in statuses:
                self._categorize_document(status, status_summary)

                # Cache finished documents
                if status["status"] in ["COMPLETED", "FAILED"]:
                    self.finished_docs[status["document_id"]] = status

        except Exception as e:
            logger.error(f"Error in batch query: {e}", exc_info=True)
            # Fall back to individual queries if batch fails
            for doc_id in docs_to_query:
                try:
                    status = self.get_document_status(doc_id)
                    self._categorize_document(status, status_summary)

                    if status["status"] in ["COMPLETED", "FAILED"]:
                        self.finished_docs[status["document_id"]] = status
                except Exception as e:
                    logger.error(f"Error getting status for {doc_id}: {e}")
                    status_summary["queued"].append(
                        {"document_id": doc_id, "status": "UNKNOWN", "error": str(e)}
                    )

        # Check if all complete
        finished = len(status_summary["completed"]) + len(status_summary["failed"])
        status_summary["all_complete"] = finished == len(document_ids)

        return status_summary

    def _batch_query_documents(self, document_ids: List[str]) -> List[Dict]:
        """
        Query multiple documents in a single Lambda invocation

        Args:
            document_ids: List of document IDs to query

        Returns:
            List of document status dictionaries
        """
        # Invoke Lambda with batch request (status_only=True includes timing, excludes Step Functions)
        response = self.lambda_client.invoke(
            FunctionName=self.lookup_function,
            InvocationType="RequestResponse",
            Payload=json.dumps(
                {
                    "object_keys": document_ids,
                    "status_only": True,  # Includes status + timing, excludes processingDetail
                }
            ),
        )

        # Parse response
        payload = response["Payload"].read()
        result = json.loads(payload)

        # Handle Lambda error
        if response.get("FunctionError"):
            logger.error(f"Batch Lambda error: {result}")
            raise Exception(result.get("errorMessage", "Unknown batch query error"))

        # Extract results from batch response
        batch_results = result.get("results", [])

        # Convert to standard format
        statuses = []
        for doc_result in batch_results:
            # Extract timing info if available
            timing = doc_result.get("timing", {})
            elapsed = timing.get("elapsed", {})

            status = {
                "document_id": doc_result.get("object_key"),
                "status": doc_result.get("status", "UNKNOWN"),
                "workflow_arn": "",
                "start_time": "",
                "end_time": "",
                "duration": elapsed.get("total", 0) / 1000.0
                if elapsed.get("total")
                else 0,  # Convert ms to seconds
            }
            statuses.append(status)

        return statuses

    def _categorize_document(self, status: Dict, status_summary: Dict):
        """
        Categorize a document status into the appropriate summary bucket

        Args:
            status: Document status dictionary
            status_summary: Status summary dictionary to update
        """
        status_value = status["status"]

        if status_value == "COMPLETED":
            status_summary["completed"].append(status)
        elif status_value == "FAILED":
            status_summary["failed"].append(status)
        elif status_value in [
            "RUNNING",
            "CLASSIFYING",
            "EXTRACTING",
            "ASSESSING",
            "SUMMARIZING",
            "EVALUATING",
        ]:
            status_summary["running"].append(status)
        else:
            status_summary["queued"].append(status)

    def get_document_status(self, doc_id: str) -> Dict:
        """
        Get detailed status of a single document

        Args:
            doc_id: Document identifier (object key)

        Returns:
            Dictionary with document status information
        """
        try:
            # Invoke LookupFunction Lambda
            payload_request = {"object_key": doc_id}

            response = self.lambda_client.invoke(
                FunctionName=self.lookup_function,
                InvocationType="RequestResponse",
                Payload=json.dumps(payload_request),
            )

            # Parse response
            payload = response["Payload"].read()
            result = json.loads(payload)

            # Handle Lambda error
            if response.get("FunctionError"):
                logger.error(f"Lambda error for {doc_id}: {result}")
                return {
                    "document_id": doc_id,
                    "status": "ERROR",
                    "error": result.get("errorMessage", "Unknown error"),
                }

            # Extract status information (note: Lambda returns lowercase 'status')
            status = result.get("status", "UNKNOWN")

            doc_status = {
                "document_id": doc_id,
                "status": status,
                "workflow_arn": result.get("WorkflowExecutionArn", ""),
                "start_time": result.get("StartTime", ""),
                "end_time": result.get("EndTime", ""),
                "duration": result.get("Duration", 0),
            }

            # Add status-specific fields
            if status == "RUNNING":
                doc_status["current_step"] = result.get("CurrentStep", "Unknown")
            elif status == "FAILED":
                doc_status["error"] = result.get("Error", "Unknown error")
                doc_status["failed_step"] = result.get("FailedStep", "Unknown")
            elif status == "COMPLETED":
                doc_status["num_sections"] = result.get("NumSections", 0)

            return doc_status

        except Exception as e:
            logger.error(f"Error querying document status for {doc_id}: {e}")
            return {"document_id": doc_id, "status": "ERROR", "error": str(e)}

    def get_recent_completions(self, status_data: Dict, limit: int = 5) -> List[Dict]:
        """
        Get most recent completions

        Args:
            status_data: Status data from get_batch_status
            limit: Maximum number to return

        Returns:
            List of recently completed documents
        """
        completed = status_data.get("completed", [])

        # Sort by end_time (most recent first)
        sorted_completed = sorted(
            completed, key=lambda x: x.get("end_time", ""), reverse=True
        )

        return sorted_completed[:limit]

    def calculate_statistics(self, status_data: Dict) -> Dict:
        """
        Calculate batch statistics

        Args:
            status_data: Status data from get_batch_status

        Returns:
            Dictionary with statistics
        """
        total = status_data["total"]
        completed = len(status_data["completed"])
        failed = len(status_data["failed"])
        running = len(status_data["running"])
        queued = len(status_data["queued"])

        # Calculate average duration for completed documents
        durations = [
            doc.get("duration", 0)
            for doc in status_data["completed"]
            if doc.get("duration", 0) > 0
        ]

        avg_duration = sum(durations) / len(durations) if durations else 0

        # Calculate completion percentage
        finished = completed + failed
        completion_pct = (finished / total * 100) if total > 0 else 0

        # Calculate success rate
        success_rate = (completed / finished * 100) if finished > 0 else 0

        return {
            "total": total,
            "completed": completed,
            "failed": failed,
            "running": running,
            "queued": queued,
            "completion_percentage": completion_pct,
            "success_rate": success_rate,
            "avg_duration_seconds": avg_duration,
            "all_complete": status_data["all_complete"],
        }

    def get_failed_documents(self, status_data: Dict) -> List[Dict]:
        """
        Get list of failed documents with error details

        Args:
            status_data: Status data from get_batch_status

        Returns:
            List of failed documents with error information
        """
        failed = status_data.get("failed", [])

        return [
            {
                "document_id": doc["document_id"],
                "error": doc.get("error", "Unknown error"),
                "failed_step": doc.get("failed_step", "Unknown"),
            }
            for doc in failed
        ]
