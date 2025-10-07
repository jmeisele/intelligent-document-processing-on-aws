# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
Configuration management for error analyzer agents.
"""

import logging
from typing import Any, Dict, List

from ..common.config import configure_logging, get_environment_config

logger = logging.getLogger(__name__)


def get_error_analyzer_config(pattern_config: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Get error analyzer configuration from pattern config or DynamoDB.
    Args:
        pattern_config: Optional pattern configuration containing agents section
    Returns:
        Dict containing error analyzer configuration values
    Raises:
        ValueError: If required configuration is missing
    """
    # Get base environment configuration
    required_keys = ["CLOUDWATCH_LOG_GROUP_PREFIX", "AWS_STACK_NAME"]
    config = get_environment_config(required_keys)
    from ... import get_config

    # Call get_config() to load merged configuration
    full_config = get_config()
    logger.info(f"get_config() returned type: {type(full_config)}")
    logger.info(
        f"get_config() keys: {list(full_config.keys()) if full_config else 'None'}"
    )

    # Extract error analyzer configuration
    if (
        full_config
        and "agents" in full_config
        and "error_analyzer" in full_config["agents"]
    ):
        agent_config = full_config["agents"]["error_analyzer"]
        logger.info("Found error_analyzer configuration")

        # Apply agent configuration
        config["model_id"] = agent_config.get(
            "model_id", "anthropic.claude-3-sonnet-20240229-v1:0"
        )
        config["system_prompt"] = agent_config.get("system_prompt")

        # Load parameters with proper type conversion
        if "parameters" in agent_config:
            params = agent_config["parameters"]
            config["max_log_events"] = int(float(params.get("max_log_events", 5)))
            config["time_range_hours_default"] = int(
                float(params.get("time_range_hours_default", 24))
            )
        else:
            config["max_log_events"] = 5
            config["time_range_hours_default"] = 24
    else:
        logger.info("No error_analyzer configuration found in agents section")
        raise ValueError(
            "error_analyzer configuration not found in pattern configuration"
        )

    # Add error analyzer specific defaults
    config["error_patterns"] = get_default_error_patterns()
    config["aws_capabilities"] = get_aws_service_capabilities()

    # Apply context limits with UI overrides
    config = _apply_context_limits(config)

    # Configure logging
    configure_logging(
        log_level=config.get("log_level"),
        strands_log_level=config.get("strands_log_level"),
    )

    # Validate required fields
    if not config.get("system_prompt"):
        logger.error("system_prompt is missing from error_analyzer configuration")
        raise ValueError("system_prompt is required in error_analyzer configuration")

    if not config.get("model_id"):
        logger.error("model_id is missing from error_analyzer configuration")
        raise ValueError("model_id is required in error_analyzer configuration")

    logger.info(f"Model: {config['model_id']}")
    logger.info(f"Max log events: {config['max_log_events']}")
    logger.info(f"Default time range: {config['time_range_hours_default']}")
    logger.info(f"System prompt length: {len(config['system_prompt'])} characters")
    logger.info(f"System prompt preview: {config['system_prompt'][:100]}...")

    return config


def get_default_error_patterns() -> List[str]:
    """
    Get default error patterns to search for in logs.

    Returns:
        List of error patterns to match against
    """
    return [
        "ERROR",
        "CRITICAL",
        "FATAL",
        "Exception",
        "Traceback",
        "Failed",
        "Timeout",
        "AccessDenied",
        "ThrottlingException",
        "ServiceException",
    ]


def _apply_context_limits(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Apply context limits to configuration.

    Args:
        config: Base configuration dictionary

    Returns:
        Updated config with all limits applied directly to config object
    """
    # Get base context limits
    base_limits = get_context_limits()

    # Apply UI overrides
    if config.get("max_log_events"):
        # Override max_events_per_log_group with configured value, respecting minimum
        base_limits["max_events_per_log_group"] = min(
            config["max_log_events"], base_limits["max_events_per_log_group"]
        )

    # Add all limits directly to config for easy access
    for key, value in base_limits.items():
        config[key] = value

    return config


def get_context_limits() -> Dict[str, int]:
    """
    Get default context size limits to prevent Bedrock token overflow.

    Returns:
        Dict containing default truncation limits:
        - max_log_message_length: Maximum characters per log message (200)
        - max_events_per_log_group: Maximum events kept per log group during processing (5)
        - max_lambda_request_ids: Maximum Lambda request IDs to include in response (3)
        - max_stepfunction_timeline_events: Maximum Step Function timeline events (3)
        - max_stepfunction_error_length: Maximum characters for Step Function error details (150)
        - max_response_log_groups: Maximum log groups included in response sample (2)
        - max_response_events_per_group: Maximum events per group in final response (1)
    """
    return {
        "max_log_message_length": 200,
        "max_events_per_log_group": 5,
        "max_lambda_request_ids": 3,
        "max_stepfunction_timeline_events": 3,
        "max_stepfunction_error_length": 150,
        "max_response_log_groups": 2,
        "max_response_events_per_group": 1,
    }


def get_aws_service_capabilities() -> Dict[str, Any]:
    """
    Get AWS service capabilities available through direct SDK integration.

    Returns:
        Dict containing AWS service capabilities and tools
    """
    return {
        "cloudwatch_logs": {
            "description": "Direct CloudWatch Logs integration",
            "implementation": "boto3.client('logs')",
            "capabilities": [
                "search_log_events",
                "get_log_groups",
                "get_log_streams",
                "filter_log_events",
            ],
        },
        "dynamodb": {
            "description": "Direct DynamoDB integration",
            "implementation": "boto3.resource('dynamodb')",
            "capabilities": [
                "scan_table",
                "query_table",
                "get_item",
                "describe_table",
            ],
        },
        "benefits": [
            "No external server dependencies",
            "Native Lambda integration",
            "Optimal performance",
            "Automatic AWS credential handling",
        ],
    }
