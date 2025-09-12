#!/usr/bin/env python3
# Copyright 2025 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause

"""
Base E2E Test Cases

Core functionality tests including tool discovery and basic MCP server operations.
"""

import os
import sys
from pathlib import Path

# Add the project root to Python path for imports
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from e2e.python.framework import (
    TestSuite,
    ToolCallTestCase,
    ToolListTestCase,
    validate_non_empty_response,
    validate_server_list,
)


def add_tool_discovery_tests(suite: TestSuite) -> None:
    """Add tool discovery tests to the suite."""

    # Test: Tool Discovery - verify expected tools are available
    suite.add_test(
        ToolListTestCase(
            expected_tools=["list_servers", "get_resource_data"], min_tools=2
        )
    )


def add_server_management_tests(suite: TestSuite) -> None:
    """Add server management and listing tests to the suite."""

    # Configuration from environment
    emulator_host = os.environ.get("EMULATOR_HOST", "127.0.0.1")

    # Test: List Servers Tool - basic server discovery
    suite.add_test(
        ToolCallTestCase(
            tool_name="list_servers",
            validators=[
                validate_non_empty_response(),
                validate_server_list([emulator_host]),
            ],
        )
    )


def register_base_tests(suite: TestSuite) -> None:
    """Register all base test cases with the test suite."""
    add_tool_discovery_tests(suite)
    add_server_management_tests(suite)
