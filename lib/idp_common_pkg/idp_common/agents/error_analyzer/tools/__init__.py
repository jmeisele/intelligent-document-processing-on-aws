# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
Error Analyzer tools for Strands agents.

Provides comprehensive error analysis capabilities including:
- Document-specific failure analysis
- System-wide error pattern detection
- CloudWatch log searching and filtering
- DynamoDB tracking table queries
- Step Function execution analysis
- Lambda function context extraction
"""

from .cloudwatch_tool import cloudwatch_document_logs, cloudwatch_stack_logs
from .document_analysis_tool import analyze_document_error
from .dynamodb_tool import (
    dynamodb_document_record,
    dynamodb_document_status,
    dynamodb_table_name,
    dynamodb_tracking_query,
)
from .error_analysis_tool import analyze_errors
from .general_analysis_tool import analyze_general_errors
from .lambda_tool import lambda_document_context
from .stepfunction_tool import stepfunction_execution_details
from .xray_tool import xray_document_analysis, xray_service_map, xray_stack_traces

__all__ = [
    "analyze_errors",
    "analyze_document_error",
    "analyze_general_errors",
    "cloudwatch_document_logs",
    "cloudwatch_stack_logs",
    "lambda_document_context",
    "dynamodb_document_record",
    "dynamodb_document_status",
    "dynamodb_table_name",
    "dynamodb_tracking_query",
    "stepfunction_execution_details",
    "xray_document_analysis",
    "xray_service_map",
    "xray_stack_traces",
]
