#!/usr/bin/env python3
# Copyright 2025 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause

"""
E2E Test Runner for MCP Redfish Server

Main test runner that orchestrates test execution using organized test case modules.
This file focuses on test suite composition and execution, while test cases are
defined in separate modules for better organization.
"""

import os
import sys
from pathlib import Path

# Add the project root to Python path for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from e2e.python.framework import MCPClient, TestSuite
from e2e.python.test_cases.base_tests import register_base_tests
from e2e.python.test_cases.tool_tests import register_tool_tests


def create_test_suite() -> TestSuite:
    """Create and configure the e2e test suite."""

    # Configuration from environment
    emulator_host = os.environ.get("EMULATOR_HOST", "127.0.0.1")
    emulator_port = os.environ.get("EMULATOR_PORT", "5000")

    # MCP server configuration
    server_env = {
        "REDFISH_HOSTS": f'[{{"address": "{emulator_host}", "port": {emulator_port}}}]',
        "REDFISH_USERNAME": "",
        "REDFISH_PASSWORD": "",
        "REDFISH_AUTH_METHOD": "basic",
    }

    # Create MCP client
    client = MCPClient(
        server_command=["uv", "run", "python", "-m", "src.main"], env=server_env
    )

    # Create test suite
    suite = TestSuite("MCP Redfish Server E2E Tests", client)

    return suite


def register_all_test_cases(suite: TestSuite) -> None:
    """Register all test cases from organized modules."""

    # Register base functionality tests
    register_base_tests(suite)

    # Register tool-specific tests (including tool error cases)
    register_tool_tests(suite)


def add_custom_test_cases(suite: TestSuite) -> None:
    """
    Extension point for adding custom test cases.

    This function can be used to add project-specific or experimental
    test cases without modifying the core test modules.
    """

    # TODO: Add custom test cases here as needed
    # Example:
    # - Environment-specific tests
    # - Experimental feature tests
    # - Integration-specific validations

    pass


def main() -> int:
    """Main test runner entry point."""

    print("🚀 MCP Redfish Server E2E Test Framework")
    print("=" * 50)

    # Check prerequisites
    emulator_host = os.environ.get("EMULATOR_HOST", "127.0.0.1")
    emulator_port = os.environ.get("EMULATOR_PORT", "5000")

    print(f"📡 Target emulator: https://{emulator_host}:{emulator_port}")
    print()

    # Create and run test suite
    try:
        suite = create_test_suite()

        # Register all test cases from modules
        register_all_test_cases(suite)

        # Add any custom test cases
        add_custom_test_cases(suite)

        # Run tests
        all_passed = suite.run(verbose=True)

        # Exit with appropriate code
        if all_passed:
            print("\n🎉 All tests passed! E2E testing successful.")
            return 0
        else:
            print("\n❌ Some tests failed. Check output above for details.")
            return 1

    except KeyboardInterrupt:
        print("\n⚠️  Test execution interrupted by user")
        return 130
    except Exception as e:
        print(f"\n💥 Test framework error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
