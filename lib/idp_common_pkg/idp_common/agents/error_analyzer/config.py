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
    Get error analyzer configuration from pattern config or environment variables.

    Args:
        pattern_config: Optional pattern configuration containing agents section

    Returns:
        Dict containing error analyzer configuration values

    Raises:
        ValueError: If required environment variables are missing
    """
    # Define required environment variables
    required_keys = [
        "CLOUDWATCH_LOG_GROUP_PREFIX",
        "AWS_STACK_NAME",  # Used as DynamoDB table prefix
    ]

    # Get base configuration
    config = get_environment_config(required_keys)
    logger.info(f"Base config from environment: {list(config.keys())}")

    # Set code-based defaults first (force set, not setdefault)
    config["model_id"] = "anthropic.claude-3-sonnet-20240229-v1:0"
    config["max_log_events"] = 100
    config["time_range_hours_default"] = 24
    logger.info(f"After setting defaults: {list(config.keys())}")

    # Apply pattern-specific configuration if available
    if (
        pattern_config
        and "agents" in pattern_config
        and "error_analyzer" in pattern_config["agents"]
    ):
        agent_config = pattern_config["agents"]["error_analyzer"]
        logger.info("Applying pattern-specific error_analyzer configuration")

        # Override defaults with pattern config values
        if "model_id" in agent_config:
            config["model_id"] = agent_config["model_id"]

        if "system_prompt" in agent_config and agent_config["system_prompt"]:
            config["system_prompt"] = agent_config["system_prompt"]

        # Load parameters if provided
        if "parameters" in agent_config:
            params = agent_config["parameters"]
            if "max_log_events" in params:
                config["max_log_events"] = params["max_log_events"]
            if "time_range_hours_default" in params:
                config["time_range_hours_default"] = params["time_range_hours_default"]

    # Always check for UI overrides (highest priority)
    try:
        from ...config.configuration_manager import ConfigurationManager

        config_manager = ConfigurationManager()
        custom_config = config_manager.get_configuration("Custom")
        if custom_config:
            custom_pattern_config = config_manager.remove_configuration_key(
                custom_config
            )
            if (
                custom_pattern_config
                and "agents" in custom_pattern_config
                and "error_analyzer" in custom_pattern_config["agents"]
            ):
                ui_agent_config = custom_pattern_config["agents"]["error_analyzer"]
                logger.info("Applying UI override for error_analyzer configuration")

                # UI overrides take highest priority
                if "model_id" in ui_agent_config:
                    config["model_id"] = ui_agent_config["model_id"]

                if (
                    "system_prompt" in ui_agent_config
                    and ui_agent_config["system_prompt"]
                ):
                    config["system_prompt"] = ui_agent_config["system_prompt"]
                    logger.info(
                        f"Using UI override system_prompt, length: {len(ui_agent_config['system_prompt'])}"
                    )

                # Load UI override parameters
                if "parameters" in ui_agent_config:
                    ui_params = ui_agent_config["parameters"]
                    if "max_log_events" in ui_params:
                        config["max_log_events"] = ui_params["max_log_events"]
                    if "time_range_hours_default" in ui_params:
                        config["time_range_hours_default"] = ui_params[
                            "time_range_hours_default"
                        ]
    except Exception as e:
        logger.warning(f"Could not load UI overrides: {e}")

    # Add error analyzer specific defaults (force set)
    config["error_patterns"] = get_default_error_patterns()
    config["aws_capabilities"] = get_aws_service_capabilities()
    logger.info(f"After adding error analyzer defaults: {list(config.keys())}")

    # Configure logging
    configure_logging(
        log_level=config.get("log_level"),
        strands_log_level=config.get("strands_log_level"),
    )

    # Comprehensive validation and error handling
    try:
        # Validate config is a dictionary
        if not isinstance(config, dict):
            logger.error(f"Configuration is not a dict: {type(config)} - {config}")
            raise ValueError(f"Invalid configuration type: {type(config)}")

        # Debug: Check what's in config before validation
        logger.info(f"Final config keys before validation: {list(config.keys())}")

        # Validate required configuration keys exist
        required_config_keys = ["model_id", "system_prompt"]
        missing_keys = [key for key in required_config_keys if key not in config]
        if missing_keys:
            logger.error(f"Missing required configuration keys: {missing_keys}")
            logger.error(f"Current config keys: {list(config.keys())}")
            logger.error(f"Full config content: {config}")
            raise KeyError(f"Missing required configuration keys: {missing_keys}")

        # Validate model_id is not None/empty
        if not config.get("model_id"):
            logger.error(f"model_id is None or empty: {config.get('model_id')}")
            logger.error(f"Full config: {config}")
            raise ValueError("model_id cannot be None or empty")

        # Validate system_prompt is not None/empty
        if not config.get("system_prompt"):
            logger.error(
                f"system_prompt is None or empty: {config.get('system_prompt')}"
            )
            logger.error(f"Full config: {config}")
            raise ValueError(
                "system_prompt must be provided in pattern configuration or UI override"
            )

    except Exception as e:
        logger.error(f"Configuration validation failed: {e}")
        logger.error(
            f"Failed config keys: {list(config.keys()) if isinstance(config, dict) else 'Not a dict'}"
        )
        raise

    # Final debug logging
    logger.info("Error Analyzer Agent Configuration:")
    logger.info(f"Model ID: {config['model_id']}")
    logger.info(f"Model ID type: {type(config['model_id'])}")
    final_prompt = config.get("system_prompt")
    logger.info(
        f"System Prompt Length: {len(final_prompt) if final_prompt else 0} characters"
    )
    if final_prompt:
        logger.info(f"System Prompt Preview: {final_prompt[:2000]}...")
    else:
        logger.warning("System prompt is None!")

    logger.info("Error analyzer configuration loaded successfully")
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
