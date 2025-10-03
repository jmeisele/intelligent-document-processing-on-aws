# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
Unified analysis tool for intelligent error routing.
"""

import logging
import os
import re
from typing import Any, Dict, Tuple

from strands import tool

from .document_analysis_tool import analyze_document_failure
from .general_analysis_tool import analyze_recent_system_errors

logger = logging.getLogger(__name__)


def _classify_query_intent(query: str) -> Tuple[str, str]:
    """Classify query as document-specific vs general system analysis."""
    # Document-specific patterns - require colon immediately after keyword
    specific_doc_patterns = [
        r"document:\s*([^\s]+)",  # "document: filename.pdf"
        r"file:\s*([^\s]+)",  # "file: report.docx"
        r"ObjectKey:\s*([^\s]+)",  # "ObjectKey: path/file.pdf"
    ]

    # Check for specific document patterns first
    for pattern in specific_doc_patterns:
        match = re.search(pattern, query, re.IGNORECASE)
        if match:
            document_id = match.group(1).strip()
            return ("document_specific", document_id)

    # If no specific document pattern found, it's general analysis
    return ("general_analysis", "")


@tool
def analyze_errors(query: str, time_range_hours: int = 1) -> Dict[str, Any]:
    """
    Intelligent error analysis with precise query classification.

    Document-specific examples:
    - "document: lending_package.pdf"
    - "file: report.docx"
    - "ObjectKey: uploads/2024/contract.pdf"

    General analysis examples:
    - "Find failure for document processing"
    - "Can you summarize all the errors in processing?"
    - "Recent processing errors"
    """
    try:
        stack_name = os.environ.get("AWS_STACK_NAME", "")
        if not stack_name:
            return {
                "error": "AWS_STACK_NAME not configured",
                "analysis_summary": "Configuration error",
            }

        try:
            from ..config import get_error_analyzer_config

            config = get_error_analyzer_config()
            max_log_events = int(float(config.get("max_log_events", 5)))
            time_range_default = int(float(config.get("time_range_hours_default", 24)))
        except Exception as e:
            logger.warning(f"Failed to load config, using defaults: {e}")
            max_log_events = 5
            time_range_default = 24

        # Ensure time_range_hours is an integer and use config default if not specified
        time_range_hours = int(float(time_range_hours))
        if time_range_hours == 1:  # Default parameter value
            time_range_hours = time_range_default

        # Enhanced query classification
        intent, document_id = _classify_query_intent(query)

        if intent == "document_specific" and document_id:
            logger.info(f"Document-specific analysis for: {document_id}")
            return analyze_document_failure(document_id, stack_name, max_log_events)
        else:
            logger.info(f"General system analysis for query: {query[:50]}...")
            return analyze_recent_system_errors(
                time_range_hours, stack_name, max_log_events
            )

    except Exception as e:
        logger.error(f"Error in unified analysis: {e}")
        return {"error": str(e)}
