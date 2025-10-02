#!/usr/bin/env python3
# Copyright 2025 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause

"""
Pytest configuration and fixtures for e2e tests.

This module provides pytest fixtures for e2e testing including:
- MCP client setup and teardown
- Emulator configuration
- Common test utilities
- Shared validation functions
"""

import os
import sys
from pathlib import Path

import pytest

# Add the project root to Python path for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


@pytest.fixture(scope="session")
def emulator_config() -> dict[str, str]:
    """Provide emulator configuration from environment variables."""
    return {
        "host": os.environ.get("EMULATOR_HOST", "127.0.0.1"),
        "port": os.environ.get("EMULATOR_PORT", "5000"),
        "base_url": f"https://{os.environ.get('EMULATOR_HOST', '127.0.0.1')}:{os.environ.get('EMULATOR_PORT', '5000')}",
    }


@pytest.fixture(scope="session")
def mcp_server_env(emulator_config: dict[str, str]) -> dict[str, str]:
    """Provide MCP server environment configuration."""
    return {
        "REDFISH_HOSTS": f'[{{"address": "{emulator_config["host"]}", "port": {emulator_config["port"]}}}]',
        "REDFISH_USERNAME": "",
        "REDFISH_PASSWORD": "",
        "REDFISH_AUTH_METHOD": "basic",
        "MCP_TRANSPORT": "stdio",
        "MCP_REDFISH_LOG_LEVEL": "WARNING",  # Reduce log noise in e2e tests
    }


@pytest.fixture(scope="session")
def mcp_client(mcp_server_env: dict[str, str]):
    """Provide an MCP test client instance for the test session."""
    from e2e.framework import MCPTestClient

    client = MCPTestClient(
        server_command=["uv", "run", "python", "-m", "src.main"], env=mcp_server_env
    )

    yield client

    # Cleanup happens automatically in MCPTestClient if needed


@pytest.fixture
def tool_validator():
    """Provide validation utilities for MCP tool responses."""
    from e2e.framework import (
        validate_contains_keys,
        validate_non_empty_response,
        validate_server_list,
        validate_tool_success,
    )

    return {
        "non_empty": validate_non_empty_response,
        "server_list": validate_server_list,
        "tool_success": validate_tool_success,
        "contains_keys": validate_contains_keys,
    }


@pytest.fixture
def expected_tools() -> list[str]:
    """List of tools that should be available in the MCP server."""
    return ["list_servers", "get_resource_data"]


# Pytest markers for e2e tests
def pytest_configure(config):
    """Configure custom pytest markers."""
    config.addinivalue_line("markers", "e2e: End-to-end integration tests")
    config.addinivalue_line("markers", "tools: Tool-specific tests")
    config.addinivalue_line("markers", "discovery: Tool discovery tests")
    config.addinivalue_line(
        "markers", "connectivity: Tests that verify actual emulator connectivity"
    )
    config.addinivalue_line("markers", "slow: Slow-running tests that may take longer")


def pytest_collection_modifyitems(config, items):
    """Automatically mark e2e tests based on their location."""
    e2e_path = Path(__file__).parent

    for item in items:
        # Add e2e marker to all tests in e2e directory
        if e2e_path in Path(item.fspath).parents:
            item.add_marker(pytest.mark.e2e)


# Environment validation
def pytest_sessionstart(session):
    """Validate environment before running e2e tests."""
    emulator_host = os.environ.get("EMULATOR_HOST", "127.0.0.1")
    emulator_port = os.environ.get("EMULATOR_PORT", "5000")

    print(
        f"\nStarting e2e tests against emulator at https://{emulator_host}:{emulator_port}"
    )

    # Strict e2e behavior: Ensure emulator is responding before running tests
    try:
        import requests
        import urllib3

        # Disable SSL warnings for self-signed certificates
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        print("Checking emulator health...")
        response = requests.get(
            f"https://{emulator_host}:{emulator_port}/redfish/v1",
            verify=False,
            timeout=10,
        )
        if response.status_code != 200:
            pytest.exit(
                f"❌ Emulator not responding correctly at https://{emulator_host}:{emulator_port}\n"
                f"   Status code: {response.status_code}\n"
                f"   Start emulator with: make e2e-emulator-start"
            )
        print("✅ Emulator is responding correctly")
    except requests.exceptions.ConnectionError:
        pytest.exit(
            f"❌ Cannot connect to emulator at https://{emulator_host}:{emulator_port}\n"
            f"   Emulator is not running. Start it with: make e2e-emulator-start"
        )
    except requests.exceptions.Timeout:
        pytest.exit(
            f"❌ Emulator timeout at https://{emulator_host}:{emulator_port}\n"
            f"   Emulator may be starting up. Wait and try again."
        )
    except Exception as e:
        pytest.exit(
            f"❌ Cannot reach emulator: {e}\n   Start emulator with: make e2e-emulator-start"
        )


def pytest_sessionfinish(session, exitstatus):
    """Cleanup after all e2e tests complete."""
    if exitstatus == 0:
        print("\nAll e2e tests passed!")
    else:
        print(f"\nSome e2e tests failed (exit code: {exitstatus})")
