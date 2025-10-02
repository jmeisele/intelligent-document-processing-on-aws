# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
Unit tests for Error Analyzer configuration.
"""

from unittest.mock import patch

import pytest
from idp_common.agents.error_analyzer.config import (
    get_aws_service_capabilities,
    get_default_error_patterns,
    get_error_analyzer_config,
)


@pytest.mark.unit
class TestErrorAnalyzerConfig:
    """Test error analyzer configuration functions."""

    def test_get_default_error_patterns(self):
        """Test default error patterns are returned."""
        patterns = get_default_error_patterns()

        assert isinstance(patterns, list)
        assert len(patterns) > 0
        assert "ERROR" in patterns
        assert "Exception" in patterns
        assert "Timeout" in patterns
        assert "ThrottlingException" in patterns

    def test_get_aws_service_capabilities(self):
        """Test AWS service capabilities are returned."""
        capabilities = get_aws_service_capabilities()

        assert isinstance(capabilities, dict)
        assert "cloudwatch_logs" in capabilities
        assert "dynamodb" in capabilities
        assert "benefits" in capabilities

        # Check CloudWatch capabilities
        cw_caps = capabilities["cloudwatch_logs"]
        assert "description" in cw_caps
        assert "capabilities" in cw_caps
        assert "search_log_events" in cw_caps["capabilities"]
        assert "implementation" in cw_caps

        # Check DynamoDB capabilities
        db_caps = capabilities["dynamodb"]
        assert "description" in db_caps
        assert "capabilities" in db_caps
        assert "scan_table" in db_caps["capabilities"]
        assert "implementation" in db_caps

    @patch.dict(
        "os.environ",
        {
            "CLOUDWATCH_LOG_GROUP_PREFIX": "/aws/lambda/test",
            "AWS_STACK_NAME": "test-stack",
            "CONFIGURATION_TABLE_NAME": "test-config-table",
        },
    )
    @patch("idp_common.get_config")
    def test_get_error_analyzer_config(self, mock_get_config):
        """Test error analyzer configuration loading."""
        mock_get_config.return_value = {
            "agents": {
                "error_analyzer": {
                    "system_prompt": "Test system prompt for error analysis"
                }
            }
        }
        pattern_config = {
            "agents": {
                "error_analyzer": {
                    "system_prompt": "Test system prompt for error analysis"
                }
            }
        }
        config = get_error_analyzer_config(pattern_config)

        assert config["cloudwatch_log_group_prefix"] == "/aws/lambda/test"
        assert config["aws_stack_name"] == "test-stack"
        assert config["max_log_events"] == 5
        assert config["system_prompt"] == "Test system prompt for error analysis"
        assert isinstance(config["error_patterns"], list)
        assert "aws_capabilities" in config
        assert isinstance(config["aws_capabilities"], dict)

    @patch.dict(
        "os.environ",
        {
            "CLOUDWATCH_LOG_GROUP_PREFIX": "/aws/lambda/test",
            "AWS_STACK_NAME": "test-stack",
            "LOG_LEVEL": "DEBUG",
            "CONFIGURATION_TABLE_NAME": "test-config-table",
        },
    )
    @patch("idp_common.get_config")
    def test_get_error_analyzer_config_with_log_level(self, mock_get_config):
        """Test configuration with custom log level."""
        mock_get_config.return_value = {
            "agents": {
                "error_analyzer": {
                    "system_prompt": "Test system prompt with debug logging"
                }
            }
        }
        pattern_config = {
            "agents": {
                "error_analyzer": {
                    "system_prompt": "Test system prompt with debug logging"
                }
            }
        }
        config = get_error_analyzer_config(pattern_config)

        assert "error_patterns" in config
        assert len(config["error_patterns"]) > 0
        assert config["system_prompt"] == "Test system prompt with debug logging"
