#!/usr/bin/env python3
# Copyright 2025 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause

"""
Tool-Specific E2E Test Cases

Tests for individual MCP tools including data retrieval and endpoint testing.
"""

import os
import sys
from pathlib import Path

# Add the project root to Python path for imports
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

import sys
from pathlib import Path

from e2e.python.framework import (
    TestResult,
    TestSuite,
    ToolCallTestCase,
    validate_non_empty_response,
    validate_redfish_service_root,
)

# Add the project root to Python path for imports
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))


class ErrorHandlingToolTestCase(ToolCallTestCase):
    """Test case that expects tool calls to return errors (negative testing)."""

    def __init__(self, tool_name: str, arguments: dict, description: str = ""):
        super().__init__(tool_name, arguments)
        self.description = description

    def run(self, client):
        """Run the test case expecting an error response."""
        result = client.call_tool(self.tool_name, self.arguments)

        if not result.success:
            return TestResult(
                name=self.name,
                passed=False,
                message=f"Failed to call {self.tool_name}: {result.error_message}",
                details={"error": result.error_message},
            )

        # For this test, we EXPECT an error
        if result.is_error:
            return TestResult(
                name=self.name,
                passed=True,
                message=f"Tool {self.tool_name} correctly returned error for invalid input",
                details={"expected_error": True, "error_content": result.content},
            )
        else:
            return TestResult(
                name=self.name,
                passed=False,
                message=f"Tool {self.tool_name} should have returned error for invalid input",
                details={
                    "unexpected_success": True,
                    "response": result.structured_content,
                },
            )


def add_data_retrieval_tests(suite: TestSuite) -> None:
    """Add data retrieval tests for the get_resource_data tool."""

    # Configuration from environment
    emulator_host = os.environ.get("EMULATOR_HOST", "127.0.0.1")
    emulator_port = os.environ.get("EMULATOR_PORT", "5000")

    # Success cases

    # Test: Get Service Root Data - fundamental Redfish endpoint
    suite.add_test(
        ToolCallTestCase(
            tool_name="get_resource_data",
            arguments={"url": f"https://{emulator_host}:{emulator_port}/redfish/v1"},
            validators=[validate_non_empty_response(), validate_redfish_service_root],
        )
    )

    # Test: Get Systems Collection - additional endpoint validation
    suite.add_test(
        ToolCallTestCase(
            tool_name="get_resource_data",
            arguments={
                "url": f"https://{emulator_host}:{emulator_port}/redfish/v1/Systems"
            },
            validators=[validate_non_empty_response()],
        )
    )

    # Error cases

    # Test: Invalid server (network error handling)
    suite.add_test(
        ErrorHandlingToolTestCase(
            tool_name="get_resource_data",
            arguments={"url": "https://invalid-server:9999/redfish/v1"},
        )
    )


def add_endpoint_coverage_tests(suite: TestSuite) -> None:
    """Add tests for additional Redfish endpoints and server listing."""

    # Success cases

    # Test: List servers functionality
    suite.add_test(
        ToolCallTestCase(
            tool_name="list_servers",
            arguments={},
            validators=[validate_non_empty_response()],
        )
    )

    # Error cases for various tools can be added here as needed

    # TODO: Add more endpoint tests as needed
    # Examples:
    # - Chassis endpoint: /redfish/v1/Chassis
    # - Managers endpoint: /redfish/v1/Managers
    # - SessionService: /redfish/v1/SessionService
    # - AccountService: /redfish/v1/AccountService

    # Placeholder for future endpoint tests
    pass


def register_tool_tests(suite: TestSuite) -> None:
    """Register all tool-specific test cases with the test suite."""
    add_data_retrieval_tests(suite)
    add_endpoint_coverage_tests(suite)
