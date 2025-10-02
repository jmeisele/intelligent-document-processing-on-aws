# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
Error Analyzer Agent - Enhanced with modular tools.
"""

import logging
from typing import Any, Dict

import boto3
import strands

from ..common.strands_bedrock_model import create_strands_bedrock_model
from .config import get_error_analyzer_config
from .tools import analyze_errors

logger = logging.getLogger(__name__)


def create_error_analyzer_agent(
    config: Dict[str, Any] = None,
    session: boto3.Session = None,
    pattern_config: Dict[str, Any] = None,
    **kwargs,
) -> strands.Agent:
    """
    Create the Error Analyzer Agent with modular tools.

    Args:
        config: Legacy configuration (deprecated)
        session: Boto3 session
        pattern_config: Pattern configuration containing agents section
        **kwargs: Additional arguments
    """
    # Debug logging to see what's being passed
    logger.info("create_error_analyzer_agent called with:")
    logger.info(f"  pattern_config: {pattern_config is not None}")
    logger.info(f"  config: {config is not None}")
    logger.info(f"  kwargs: {list(kwargs.keys())}")

    # Load configuration - try pattern_config first, then fall back to config parameter
    effective_pattern_config = pattern_config or config
    logger.info(f"  effective_pattern_config: {effective_pattern_config is not None}")
    config = get_error_analyzer_config(effective_pattern_config)

    # Create session if not provided
    if session is None:
        session = boto3.Session()

    # Create agent
    tools = [analyze_errors]
    bedrock_model = create_strands_bedrock_model(
        model_id=config["model_id"], boto_session=session
    )

    return strands.Agent(
        tools=tools, system_prompt=config["system_prompt"], model=bedrock_model
    )
