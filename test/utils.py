# Copyright 2025 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause

"""
Test utilities and helper functions for mcp-redfish test suite.
"""

import json
import os
from typing import Any
from unittest.mock import MagicMock


def create_mock_redfish_response(data: dict[str, Any], status: int = 200) -> MagicMock:
    """Create a mock Redfish response object."""
    mock_response = MagicMock()
    mock_response.status = status
    mock_response.dict = data
    return mock_response


def create_mock_redfish_client(response_data: dict[str, Any] = None) -> MagicMock:
    """Create a mock Redfish client with configurable response."""
    if response_data is None:
        response_data = {"mock": "data"}

    mock_client = MagicMock()
    mock_client.login.return_value = None
    mock_client.logout.return_value = None
    mock_client.cafile = None
    mock_client.get.return_value = create_mock_redfish_response(response_data)
    return mock_client


def extract_call_tool_result(result) -> Any:
    """
    Extract data from CallToolResult or return direct result.

    This helper handles the different ways MCP tools can return data
    depending on the test context.
    """
    if hasattr(result, "content") and result.content:
        # Handle CallToolResult with TextContent
        return json.loads(result.content[0].text)
    else:
        # Handle direct result
        return result


def create_host_config(address: str, **kwargs) -> dict[str, str]:
    """Create a host configuration dictionary with optional parameters."""
    config = {"address": address}
    config.update(kwargs)
    return config


def create_multiple_hosts(
    addresses: list[str], **common_config
) -> list[dict[str, str]]:
    """Create multiple host configurations with common settings."""
    return [create_host_config(addr, **common_config) for addr in addresses]


class MockEnvironment:
    """Context manager for temporarily setting environment variables in tests."""

    def __init__(self, env_vars: dict[str, str]):
        self.env_vars = env_vars
        self.original_values = {}

    def __enter__(self):
        for key, value in self.env_vars.items():
            self.original_values[key] = os.environ.get(key)
            os.environ[key] = value
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        for key in self.env_vars:
            original_value = self.original_values[key]
            if original_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = original_value
