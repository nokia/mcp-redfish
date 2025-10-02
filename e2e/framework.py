#!/usr/bin/env python3
# Copyright 2025 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause

"""
Pytest-compatible E2E Test Utilities for MCP Redfish Server

This module provides utilities and helpers for pytest-based e2e testing.
It preserves the MCP-specific functionality while integrating with pytest's
fixture and assertion system.
"""

import json
import os
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass
class ToolCallResult:
    """Result of a MCP tool call via Inspector CLI."""

    success: bool
    content: list[dict[str, Any]]
    structured_content: dict[str, Any] | None
    is_error: bool
    raw_output: str
    error_message: str | None = None


class MCPTestClient:
    """
    Test harness for MCP server e2e testing.

    This class starts the MCP server as a subprocess and provides methods
    to interact with it via the MCP Inspector CLI for testing purposes.
    It's not a client application, but rather a testing utility that manages
    the server lifecycle and facilitates test interactions.
    """

    def __init__(self, server_command: list[str], env: dict[str, str] | None = None):
        self.server_command = server_command
        self.env = env or {}

    def call_tool(
        self, tool_name: str, arguments: dict[str, Any] | None = None
    ) -> ToolCallResult:
        """Call a tool via MCP Inspector CLI."""
        try:
            # Prepare environment
            full_env = os.environ.copy()
            full_env.update(self.env)

            # Build inspector command
            cmd = [
                "npx",
                "@modelcontextprotocol/inspector",
                "--cli",
                "--transport",
                "stdio",
                "--method",
                "tools/call",
                "--tool-name",
                tool_name,
            ] + self.server_command

            if arguments:
                cmd.extend(["--arguments", json.dumps(arguments)])

            # Execute command
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30, env=full_env
            )

            # Parse output
            content = []
            structured_content = None
            is_error = result.returncode != 0
            error_message = None

            if result.stdout:
                try:
                    # Try to parse as JSON
                    parsed = json.loads(result.stdout)
                    if isinstance(parsed, list):
                        content = parsed
                    else:
                        content = [parsed]
                        structured_content = parsed

                    # Check if the response indicates an error
                    if isinstance(parsed, dict) and parsed.get("isError", False):
                        is_error = True
                        error_message = "Tool returned error: " + str(
                            parsed.get("content", "")
                        )

                except json.JSONDecodeError:
                    # Fallback to text content
                    content = [{"type": "text", "text": result.stdout}]

            if result.stderr:
                if not error_message:
                    error_message = result.stderr
                else:
                    error_message += f"; stderr: {result.stderr}"

            return ToolCallResult(
                success=not is_error,
                content=content,
                structured_content=structured_content,
                is_error=is_error,
                raw_output=result.stdout,
                error_message=error_message,
            )

        except subprocess.TimeoutExpired:
            return ToolCallResult(
                success=False,
                content=[],
                structured_content=None,
                is_error=True,
                raw_output="",
                error_message="Tool call timed out",
            )
        except Exception as e:
            return ToolCallResult(
                success=False,
                content=[],
                structured_content=None,
                is_error=True,
                raw_output="",
                error_message=f"Tool call failed: {str(e)}",
            )

    def list_tools(self) -> ToolCallResult:
        """List available tools via MCP Inspector CLI."""
        try:
            # Prepare environment
            full_env = os.environ.copy()
            full_env.update(self.env)

            # Build inspector command
            cmd = [
                "npx",
                "@modelcontextprotocol/inspector",
                "--cli",
                "--transport",
                "stdio",
                "--method",
                "tools/list",
            ] + self.server_command

            # Execute command
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30, env=full_env
            )

            # Parse tools list
            tools = []
            if result.stdout:
                try:
                    parsed = json.loads(result.stdout)
                    if isinstance(parsed, dict) and "tools" in parsed:
                        tools = parsed["tools"]
                    elif isinstance(parsed, list):
                        tools = parsed
                except json.JSONDecodeError:
                    pass

            return ToolCallResult(
                success=result.returncode == 0,
                content=tools,
                structured_content={"tools": tools} if tools else None,
                is_error=result.returncode != 0,
                raw_output=result.stdout,
                error_message=result.stderr if result.returncode != 0 else None,
            )

        except Exception as e:
            return ToolCallResult(
                success=False,
                content=[],
                structured_content=None,
                is_error=True,
                raw_output="",
                error_message=f"List tools failed: {str(e)}",
            )


# Validation functions for pytest assertions
def validate_non_empty_response() -> Callable[[ToolCallResult], None]:
    """Create a validator that checks for non-empty response content."""

    def validator(result: ToolCallResult) -> None:
        assert result.success, f"Tool call failed: {result.error_message}"
        assert result.content, "Response content is empty"
        assert len(result.content) > 0, "Response content list is empty"

    return validator


def validate_server_list(expected_hosts: list[str]) -> Callable[[ToolCallResult], None]:
    """Create a validator that checks for expected hosts in server list."""

    def validator(result: ToolCallResult) -> None:
        assert result.success, f"Tool call failed: {result.error_message}"
        assert result.content, "No servers found in response"

        # Extract server addresses from MCP Inspector CLI response format
        found_hosts = []

        # First try structured_content if available (preferred)
        if result.structured_content and "result" in result.structured_content:
            servers = result.structured_content["result"]
            if isinstance(servers, list):
                found_hosts.extend([str(server) for server in servers])

        # Also check content array for text that might contain server info
        for item in result.content:
            if isinstance(item, dict):
                # Check for direct server info
                for key in ["address", "host", "hostname", "server", "url"]:
                    if key in item:
                        found_hosts.append(str(item[key]))
                        break

                # Check structured content within the item
                if (
                    "structuredContent" in item
                    and "result" in item["structuredContent"]
                ):
                    servers = item["structuredContent"]["result"]
                    if isinstance(servers, list):
                        found_hosts.extend([str(server) for server in servers])

                # Check text content that might contain JSON
                if "content" in item:
                    for content_item in item["content"]:
                        if (
                            isinstance(content_item, dict)
                            and content_item.get("type") == "text"
                        ):
                            text = content_item.get("text", "")
                            try:
                                # Try to parse JSON from text
                                parsed_text = json.loads(text)
                                if isinstance(parsed_text, list):
                                    found_hosts.extend(
                                        [str(server) for server in parsed_text]
                                    )
                            except (json.JSONDecodeError, TypeError):
                                # If not JSON, check if text contains expected hosts
                                for expected_host in expected_hosts:
                                    if expected_host in text:
                                        found_hosts.append(expected_host)

        # Check if any expected host is found
        for expected_host in expected_hosts:
            assert any(expected_host in found_host for found_host in found_hosts), (
                f"Expected host '{expected_host}' not found in server list: {found_hosts}"
            )

    return validator


def validate_tool_success() -> Callable[[ToolCallResult], None]:
    """Create a validator that simply checks if the tool call was successful."""

    def validator(result: ToolCallResult) -> None:
        assert result.success, f"Tool call failed: {result.error_message}"
        assert not result.is_error, f"Tool returned error: {result.error_message}"

    return validator


def validate_contains_keys(
    required_keys: list[str],
) -> Callable[[ToolCallResult], None]:
    """Create a validator that checks if response contains required keys."""

    def validator(result: ToolCallResult) -> None:
        assert result.success, f"Tool call failed: {result.error_message}"
        assert result.structured_content, "No structured content in response"

        for key in required_keys:
            assert key in result.structured_content, (
                f"Required key '{key}' not found in response: {list(result.structured_content.keys())}"
            )

    return validator


def validate_tool_list(
    expected_tools: list[str], min_tools: int = 0
) -> Callable[[ToolCallResult], None]:
    """Create a validator for tool list responses."""

    def validator(result: ToolCallResult) -> None:
        assert result.success, f"Tool list failed: {result.error_message}"
        assert result.content, "No tools found in response"

        if min_tools > 0:
            assert len(result.content) >= min_tools, (
                f"Expected at least {min_tools} tools, found {len(result.content)}"
            )

        # Extract tool names
        tool_names = []
        for tool in result.content:
            if isinstance(tool, dict) and "name" in tool:
                tool_names.append(tool["name"])
            elif isinstance(tool, str):
                tool_names.append(tool)

        # Check for expected tools
        for expected_tool in expected_tools:
            assert expected_tool in tool_names, (
                f"Expected tool '{expected_tool}' not found in available tools: {tool_names}"
            )

    return validator


# Pytest helper functions
def assert_tool_call_success(
    result: ToolCallResult, message: str = "Tool call should succeed"
):
    """Pytest-style assertion for successful tool calls."""
    assert result.success, f"{message}: {result.error_message}"
    assert not result.is_error, f"{message}: Tool returned error"


def assert_tool_has_content(
    result: ToolCallResult, message: str = "Tool should return content"
):
    """Pytest-style assertion for non-empty tool response."""
    assert_tool_call_success(result, message)
    assert result.content, f"{message}: Response content is empty"
    assert len(result.content) > 0, f"{message}: Response content list is empty"


def call_tool_and_validate(
    client: MCPTestClient,
    tool_name: str,
    arguments: dict[str, Any] | None = None,
    validators: list[Callable[[ToolCallResult], None]] | None = None,
) -> ToolCallResult:
    """Helper to call a tool and run validators in pytest context."""
    result = client.call_tool(tool_name, arguments)

    if validators:
        for validator in validators:
            validator(result)

    return result


def list_tools_and_validate(
    client: MCPTestClient,
    validators: list[Callable[[ToolCallResult], None]] | None = None,
) -> ToolCallResult:
    """Helper to list tools and run validators in pytest context."""
    result = client.list_tools()

    if validators:
        for validator in validators:
            validator(result)

    return result
