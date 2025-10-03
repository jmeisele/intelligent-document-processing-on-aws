# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
Unit tests for main Error Analyzer Agent.
"""

from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.unit
class TestErrorAnalyzerAgent:
    """Test main error analyzer agent."""

    @patch("strands.Agent")
    @patch("boto3.Session")
    @patch("idp_common.agents.error_analyzer.agent.get_error_analyzer_config")
    def test_create_error_analyzer_agent(
        self, mock_config, mock_session, mock_agent_class
    ):
        """Test main error analyzer agent creation."""
        from idp_common.agents.error_analyzer.agent import create_error_analyzer_agent

        mock_config.return_value = {
            "AWS_STACK_NAME": "test-stack",
            "model_id": "anthropic.claude-3-sonnet-20240229-v1:0",
            "system_prompt": "Test system prompt",
        }
        mock_session.return_value = MagicMock()
        mock_agent = MagicMock()
        mock_agent.tools = [MagicMock()]  # Only one tool now
        mock_agent_class.return_value = mock_agent

        config = {
            "AWS_STACK_NAME": "test-stack",
            "model_id": "anthropic.claude-3-sonnet-20240229-v1:0",
        }

        agent = create_error_analyzer_agent(
            config=config, session=mock_session.return_value
        )

        assert agent is not None
        assert hasattr(agent, "tools")
        assert len(agent.tools) == 1  # Only analyze_errors tool

    @patch("strands.Agent")
    @patch("boto3.Session")
    @patch("idp_common.agents.error_analyzer.agent.get_error_analyzer_config")
    def test_create_error_analyzer_agent_with_defaults(
        self, mock_config, mock_session, mock_agent_class
    ):
        """Test agent creation with default config and session."""
        from idp_common.agents.error_analyzer.agent import create_error_analyzer_agent

        mock_config.return_value = {
            "AWS_STACK_NAME": "test-stack",
            "model_id": "anthropic.claude-3-sonnet-20240229-v1:0",
            "system_prompt": "Test system prompt",
        }
        mock_session.return_value = MagicMock()
        mock_agent = MagicMock()
        mock_agent.tools = [MagicMock()]
        mock_agent_class.return_value = mock_agent

        agent = create_error_analyzer_agent()

        assert agent is not None
        assert hasattr(agent, "tools")
        assert len(agent.tools) == 1

    @patch("strands.Agent")
    @patch("boto3.Session")
    @patch("idp_common.agents.error_analyzer.agent.get_error_analyzer_config")
    def test_agent_system_prompt_format(
        self, mock_config, mock_session, mock_agent_class
    ):
        """Test that agent is created with correct system prompt format."""
        from idp_common.agents.error_analyzer.agent import create_error_analyzer_agent

        mock_config.return_value = {
            "AWS_STACK_NAME": "test-stack",
            "model_id": "anthropic.claude-3-sonnet-20240229-v1:0",
            "system_prompt": "You are an intelligent error analysis agent for the GenAI IDP system.\n\n## Root Cause\n## Recommendations\n\nDO NOT include:",
        }
        mock_session.return_value = MagicMock()
        mock_agent = MagicMock()
        mock_agent_class.return_value = mock_agent

        create_error_analyzer_agent()

        # Verify strands.Agent was called with correct parameters
        mock_agent_class.assert_called_once()
        call_args = mock_agent_class.call_args

        assert "tools" in call_args.kwargs
        assert "system_prompt" in call_args.kwargs
        assert "model" in call_args.kwargs

        # Check system prompt contains required sections
        system_prompt = call_args.kwargs["system_prompt"]
        assert "Root Cause" in system_prompt
        assert "Recommendations" in system_prompt
        assert "DO NOT include" in system_prompt

    def test_analyze_errors_tool_import(self):
        """Test that analyze_errors tool can be imported correctly."""
        from idp_common.agents.error_analyzer.tools import analyze_errors

        assert analyze_errors is not None
        assert callable(analyze_errors)
