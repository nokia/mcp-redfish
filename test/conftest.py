# Copyright 2025 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause

"""
Test configuration and fixtures for mcp-redfish test suite.
"""

import os
import sys
from pathlib import Path

import pytest

# Add src directory to Python path for imports
src_dir = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_dir))

# Import the package properly - this will trigger tool registration
import src.tools  # noqa: F401, E402

# Test environment variables
os.environ.update(
    {
        "REDFISH_HOSTS": '[{"address": "test-host.example.com"}]',
        "REDFISH_PORT": "443",
        "REDFISH_USERNAME": "test_user",
        "REDFISH_PASSWORD": "test_password",
        "MCP_TRANSPORT": "stdio",
        "REDFISH_DISCOVERY_ENABLED": "false",
        "MCP_REDFISH_LOG_LEVEL": "WARNING",  # Reduce log noise in tests
    }
)


@pytest.fixture(scope="session")
def test_config():
    """Provide test configuration data."""
    return {
        "redfish_hosts": [
            {
                "address": "test-host1.example.com",
                "username": "test_user1",
                "password": "test_pass1",
            },
            {
                "address": "test-host2.example.com",
                "username": "test_user2",
                "password": "test_pass2",
            },
        ],
        "test_urls": {
            "valid": "https://test-host1.example.com/redfish/v1/Systems/1",
            "invalid_host": "https://unknown-host.example.com/redfish/v1/Systems/1",
            "invalid_format": "not-a-valid-url",
        },
    }


@pytest.fixture
def mock_redfish_client():
    """Provide a mock Redfish client for testing."""
    from unittest.mock import MagicMock

    mock_client = MagicMock()
    mock_client.login.return_value = None
    mock_client.logout.return_value = None
    mock_client.cafile = None

    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.dict = {"test": "data"}
    mock_client.get.return_value = mock_response

    return mock_client


@pytest.fixture
def sample_hosts():
    """Provide sample host configurations for testing."""
    return [
        {"address": "host1.example.com", "username": "user1", "password": "pass1"},
        {"address": "host2.example.com", "username": "user2", "password": "pass2"},
        {"address": "host3.example.com"},  # Host without credentials
    ]
