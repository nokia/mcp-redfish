#!/usr/bin/env python3
# Copyright 2025 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause

"""
Pytest-based Base E2E Tests

Core functionality tests including tool discovery and basic MCP server operations.
Converted from custom test framework to standard pytest format.
"""

import pytest

from e2e.framework import (
    MCPTestClient,
    assert_tool_call_success,
    assert_tool_has_content,
    call_tool_and_validate,
    list_tools_and_validate,
    validate_non_empty_response,
    validate_server_list,
    validate_tool_list,
)


@pytest.mark.discovery
def test_tool_discovery_available_tools(mcp_client: MCPTestClient, expected_tools):
    """Test that expected MCP tools are discoverable and available."""
    result = list_tools_and_validate(
        mcp_client, validators=[validate_tool_list(expected_tools, min_tools=2)]
    )

    # Additional pytest-style assertions
    assert len(result.content) >= len(expected_tools), (
        f"Expected at least {len(expected_tools)} tools, found {len(result.content)}"
    )

    tool_names = [
        tool.get("name", tool) if isinstance(tool, dict) else tool
        for tool in result.content
    ]

    for expected_tool in expected_tools:
        assert expected_tool in tool_names, (
            f"Tool '{expected_tool}' not found in available tools: {tool_names}"
        )


@pytest.mark.discovery
def test_tool_discovery_minimum_tools(mcp_client: MCPTestClient):
    """Test that at least the minimum expected number of tools are available."""
    result = list_tools_and_validate(
        mcp_client, validators=[validate_tool_list([], min_tools=2)]
    )

    assert len(result.content) >= 2, "Expected at least 2 tools to be available"


@pytest.mark.tools
def test_list_servers_tool_basic(mcp_client: MCPTestClient, emulator_config):
    """Test basic server discovery using list_servers tool."""
    expected_host = emulator_config["host"]

    result = call_tool_and_validate(
        mcp_client,
        "list_servers",
        validators=[
            validate_non_empty_response(),
            validate_server_list([expected_host]),
        ],
    )

    # Additional pytest assertions
    assert_tool_has_content(result, "list_servers should return server information")

    # Verify the expected host appears in the response
    response_text = str(result.content).lower()
    assert expected_host.lower() in response_text, (
        f"Expected host '{expected_host}' not found in response: {result.content}"
    )


@pytest.mark.tools
def test_list_servers_tool_response_structure(mcp_client: MCPTestClient):
    """Test that list_servers tool returns properly structured response."""
    result = call_tool_and_validate(
        mcp_client, "list_servers", validators=[validate_non_empty_response()]
    )

    # Check response structure
    assert_tool_has_content(result, "list_servers should return structured content")

    # Verify we have some form of server information
    assert result.content, "Response should contain server information"

    # Check if response contains server-related information
    response_str = str(result.content).lower()

    # Also check for IP addresses which are common in server responses
    import re

    ip_pattern = r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b"
    has_ip = bool(re.search(ip_pattern, response_str))

    server_keywords = ["server", "host", "address", "redfish", "system"]
    has_server_info = (
        any(keyword in response_str for keyword in server_keywords) or has_ip
    )

    assert has_server_info, (
        f"Response should contain server-related information (keywords or IP addresses): {result.content}"
    )


@pytest.mark.tools
@pytest.mark.slow
def test_get_resource_data_tool_available(mcp_client: MCPTestClient):
    """Test that get_resource_data tool is available and can be called."""
    # First verify the tool exists
    tools_result = list_tools_and_validate(
        mcp_client, validators=[validate_tool_list(["get_resource_data"])]
    )

    tool_names = [
        tool.get("name", tool) if isinstance(tool, dict) else tool
        for tool in tools_result.content
    ]
    assert "get_resource_data" in tool_names, (
        "get_resource_data tool should be available"
    )


@pytest.mark.tools
@pytest.mark.parametrize("tool_name", ["list_servers", "get_resource_data"])
def test_tool_exists_in_discovery(mcp_client: MCPTestClient, tool_name: str):
    """Parametrized test to verify specific tools exist in tool discovery."""
    result = list_tools_and_validate(
        mcp_client, validators=[validate_tool_list([tool_name])]
    )

    tool_names = [
        tool.get("name", tool) if isinstance(tool, dict) else tool
        for tool in result.content
    ]

    assert tool_name in tool_names, (
        f"Tool '{tool_name}' should be available in MCP server"
    )


# Integration test combining multiple operations
@pytest.mark.tools
@pytest.mark.integration
def test_basic_server_workflow(mcp_client: MCPTestClient, emulator_config):
    """Test a basic workflow: discover tools, then list servers."""
    # Step 1: Discover available tools
    tools_result = list_tools_and_validate(
        mcp_client, validators=[validate_tool_list(["list_servers"], min_tools=1)]
    )

    assert_tool_call_success(tools_result, "Tool discovery should succeed")

    # Step 2: Use list_servers tool
    servers_result = call_tool_and_validate(
        mcp_client,
        "list_servers",
        validators=[
            validate_non_empty_response(),
            validate_server_list([emulator_config["host"]]),
        ],
    )

    assert_tool_call_success(servers_result, "Server listing should succeed")

    # Verify workflow completed successfully
    assert tools_result.success and servers_result.success, (
        "Complete workflow should succeed"
    )
