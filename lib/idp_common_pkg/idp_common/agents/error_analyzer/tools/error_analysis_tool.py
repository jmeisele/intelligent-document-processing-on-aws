# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
Unified analysis tool for intelligent error routing.
"""

import logging
import os
import re
from typing import Any, Dict

from strands import tool

from .document_analysis_tool import analyze_document_failure
from .general_analysis_tool import analyze_recent_system_errors

logger = logging.getLogger(__name__)


@tool
def analyze_errors(query: str, time_range_hours: int = 1) -> Dict[str, Any]:
    """
    Intelligent error analysis supporting both document-specific and general queries.

    Examples:
    - "Find the root cause of this failure" (document-specific from Troubleshoot button)
    - "Find recent processing errors and root cause" (general from Agent Analysis)
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
            max_log_events = config.get("max_log_events", 10)
            time_range_default = config.get("time_range_hours_default", 24)
        except Exception as e:
            logger.warning(f"Failed to load config, using defaults: {e}")
            max_log_events = 10
            time_range_default = 24

        # Use config default if time_range_hours not specified
        if time_range_hours == 1:  # Default parameter value
            time_range_hours = time_range_default

        # Extract document context from query
        doc_patterns = [
            r"document[:\s]+([^\s]+)",
            r"file[:\s]+([^\s]+)",
            r"ObjectKey[:\s]+([^\s]+)",
        ]

        document_id = None
        for pattern in doc_patterns:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                document_id = match.group(1).strip()
                break

        if document_id:
            # Document-specific analysis
            return analyze_document_failure(document_id, stack_name, max_log_events)
        else:
            # General system analysis
            return analyze_recent_system_errors(
                time_range_hours, stack_name, max_log_events
            )

    except Exception as e:
        logger.error(f"Error in unified analysis: {e}")
        return {
            "error": str(e),
            "analysis_summary": "Failed to analyze errors",
            "recommendations": [
                "Check system logs manually",
                "Contact support if issue persists",
            ],
        }
