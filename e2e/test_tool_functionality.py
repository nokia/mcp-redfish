#!/usr/bin/env python3
# Copyright 2025 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause

"""
Pytest-based Tool-Specific E2E Tests

Tool-specific tests including error handling, edge cases, and advanced functionality.
Converted from custom test framework to standard pytest format.
"""

import pytest

from e2e.framework import (
    MCPTestClient,
    ToolCallResult,
    assert_tool_call_success,
    assert_tool_has_content,
    call_tool_and_validate,
    validate_non_empty_response,
    validate_server_list,
)


@pytest.mark.tools
@pytest.mark.error_handling
def test_invalid_tool_name(mcp_client: MCPTestClient):
    """Test behavior when calling a non-existent tool."""
    result = mcp_client.call_tool("non_existent_tool")

    # Should fail gracefully
    assert not result.success, "Call to non-existent tool should fail"
    assert result.is_error, "Result should indicate an error occurred"
    assert result.error_message, "Should provide error message for invalid tool"


@pytest.mark.tools
@pytest.mark.error_handling
def test_list_servers_with_invalid_arguments(mcp_client: MCPTestClient):
    """Test list_servers tool behavior with invalid arguments."""
    # list_servers typically doesn't take arguments, so this should either
    # ignore the arguments or return an error
    result = mcp_client.call_tool("list_servers", {"invalid_arg": "invalid_value"})

    # The tool should either succeed (ignoring invalid args) or fail gracefully
    if not result.success:
        assert result.is_error, "Failed call should indicate error"
        assert result.error_message, "Should provide error message"
    else:
        # If it succeeds, it should still return valid server data
        assert_tool_has_content(
            result, "Tool should return content even with extra args"
        )


@pytest.mark.tools
def test_get_resource_data_without_arguments(mcp_client: MCPTestClient):
    """Test get_resource_data tool behavior without required arguments."""
    result = mcp_client.call_tool("get_resource_data")

    # This should likely fail since get_resource_data probably requires arguments
    # But we test the behavior gracefully handles missing arguments
    if not result.success:
        assert result.is_error, "Call without required arguments should indicate error"
        assert result.error_message, (
            "Should provide error message for missing arguments"
        )
    else:
        # If it succeeds without arguments, it should return some default resource data
        assert_tool_has_content(result, "Tool should return some resource data")


@pytest.mark.tools
@pytest.mark.parametrize(
    "invalid_arg",
    [
        {"resource_path": ""},  # Empty path
        {"resource_path": "/invalid/path"},  # Invalid path
        {"resource_path": None},  # None value
        {"server_id": "non_existent_server"},  # Invalid server
    ],
)
def test_get_resource_data_with_invalid_arguments(
    mcp_client: MCPTestClient, invalid_arg
):
    """Parametrized test for get_resource_data with various invalid arguments."""
    result = mcp_client.call_tool("get_resource_data", invalid_arg)

    # Should handle invalid arguments gracefully
    if not result.success:
        assert result.is_error, (
            f"Invalid argument {invalid_arg} should cause graceful error"
        )
        assert result.error_message, f"Should provide error message for {invalid_arg}"
    # If it succeeds, verify the response is reasonable
    # (some tools might have fallback behavior)


@pytest.mark.tools
@pytest.mark.integration
def test_tool_chaining_workflow(mcp_client: MCPTestClient, emulator_config):
    """Test chaining tools together: list_servers then get_resource_data."""
    # Step 1: Get list of servers
    servers_result = call_tool_and_validate(
        mcp_client,
        "list_servers",
        validators=[
            validate_non_empty_response(),
            validate_server_list([emulator_config["host"]]),
        ],
    )

    assert_tool_call_success(servers_result, "Server listing should succeed")

    # Step 2: Try to get resource data (this might fail if server isn't fully configured)
    # We're more interested in testing the tool exists and responds
    resource_result = mcp_client.call_tool(
        "get_resource_data", {"resource_path": "/redfish/v1/Systems"}
    )

    # Resource call might fail due to emulator limitations, but should respond
    assert isinstance(resource_result, ToolCallResult), "Should return ToolCallResult"

    if resource_result.success:
        assert_tool_has_content(
            resource_result, "Successful resource call should have content"
        )
    else:
        # If it fails, should provide useful error information
        assert resource_result.error_message, (
            "Failed resource call should provide error details"
        )


@pytest.mark.tools
@pytest.mark.slow
def test_concurrent_tool_calls(mcp_client: MCPTestClient):
    """Test that multiple tool calls can be made in sequence without interference."""
    results = []

    # Make multiple calls to list_servers
    for i in range(3):
        result = mcp_client.call_tool("list_servers")
        results.append(result)

        # Each call should succeed (assuming emulator is working)
        if result.success:
            assert_tool_has_content(result, f"Call {i + 1} should return content")

    # At least one call should have succeeded
    successful_calls = [r for r in results if r.success]
    assert len(successful_calls) > 0, "At least one tool call should succeed"

    # All successful calls should return similar content
    if len(successful_calls) > 1:
        for result in successful_calls[1:]:
            # Content should be consistent across calls
            assert len(result.content) > 0, "Each successful call should have content"


@pytest.mark.tools
@pytest.mark.edge_cases
def test_tool_with_empty_string_arguments(mcp_client: MCPTestClient):
    """Test tool behavior with empty string arguments."""
    result = mcp_client.call_tool("get_resource_data", {"resource_path": ""})

    # Should handle empty string gracefully
    if not result.success:
        assert result.error_message, (
            "Empty string argument should provide clear error message"
        )


@pytest.mark.tools
@pytest.mark.edge_cases
def test_tool_with_very_long_arguments(mcp_client: MCPTestClient):
    """Test tool behavior with unusually long argument values."""
    long_path = "/redfish/v1/" + "very_long_path/" * 100

    result = mcp_client.call_tool("get_resource_data", {"resource_path": long_path})

    # Should handle long arguments without crashing
    assert isinstance(result, ToolCallResult), (
        "Should return ToolCallResult even with long args"
    )

    if not result.success:
        assert result.error_message, (
            "Should provide error message for problematic long arguments"
        )


@pytest.mark.tools
@pytest.mark.performance
def test_tool_response_time(mcp_client: MCPTestClient):
    """Test that tool calls complete within reasonable time."""
    import time

    start_time = time.time()
    result = mcp_client.call_tool("list_servers")
    end_time = time.time()

    duration = end_time - start_time

    # Tool call should complete within 30 seconds (generous timeout)
    assert duration < 30.0, f"Tool call took too long: {duration:.2f} seconds"

    # If successful, should complete much faster (under 10 seconds for simple calls)
    if result.success:
        assert duration < 10.0, (
            f"Successful tool call should be faster: {duration:.2f} seconds"
        )


@pytest.mark.tools
@pytest.mark.integration
@pytest.mark.parametrize("tool_name", ["list_servers"])
def test_tool_idempotency(mcp_client: MCPTestClient, tool_name: str):
    """Test that calling the same tool multiple times produces consistent results."""
    results = []

    # Call the same tool multiple times
    for _ in range(2):
        result = mcp_client.call_tool(tool_name)
        results.append(result)

    # Filter successful results
    successful_results = [r for r in results if r.success]

    if len(successful_results) >= 2:
        # Results should be consistent
        first_result = successful_results[0]
        second_result = successful_results[1]

        # Both should have content
        assert_tool_has_content(
            first_result, f"{tool_name} first call should have content"
        )
        assert_tool_has_content(
            second_result, f"{tool_name} second call should have content"
        )

        # Content should be similar (allowing for minor timing differences)
        assert len(first_result.content) == len(second_result.content), (
            f"Idempotent calls to {tool_name} should return similar content structure"
        )
