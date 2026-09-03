# Copyright 2025 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause

"""Unit tests for e2e result classification used by negative assertions."""

from e2e.framework import ToolCallResult
from e2e.test_http_auth import _clear_http_auth_env


def _result(error: str) -> ToolCallResult:
    return ToolCallResult(
        success=False,
        content=[],
        structured_content=None,
        is_error=True,
        raw_output="",
        error_message=error,
    )


def test_infrastructure_failure_detects_timeout_and_connection_errors() -> None:
    assert _result("Tool call timed out").is_infrastructure_failure()
    assert _result("Connection refused").is_infrastructure_failure()


def test_tool_level_error_is_not_infrastructure_failure() -> None:
    assert not _result("Unknown tool: non_existent_tool").is_infrastructure_failure()


def test_http_auth_e2e_environment_is_self_contained() -> None:
    environment = {
        "MCP_AUTH_MODE": "token",
        "MCP_HTTP_AUTH": "false",
        "MCP_TLS_TERMINATED": "true",
        "FASTMCP_HOST": "0.0.0.0",
        "HTTPS_PROXY": "http://proxy.example",
        "REDFISH_HOSTS": '[{"address":"127.0.0.1"}]',
    }
    _clear_http_auth_env(environment)
    assert environment == {"REDFISH_HOSTS": '[{"address":"127.0.0.1"}]'}
