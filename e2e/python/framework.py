#!/usr/bin/env python3
# Copyright 2025 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause

"""
E2E Test Framework for MCP Redfish Server

A flexible, extensible framework for testing MCP tools using the official MCP Inspector CLI.
Provides easy test case definition, rich response validation, and clear reporting.
"""

import json
import os
import subprocess
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass
class TestResult:
    """Result of a single test case execution."""

    name: str
    passed: bool
    message: str
    details: dict[str, Any] | None = None
    duration: float | None = None


@dataclass
class ToolCallResult:
    """Result of a MCP tool call via Inspector CLI."""

    success: bool
    content: list[dict[str, Any]]
    structured_content: dict[str, Any] | None
    is_error: bool
    raw_output: str
    error_message: str | None = None


class MCPClient:
    """Client for interacting with MCP server via Inspector CLI."""

    def __init__(self, server_command: list[str], env: dict[str, str] | None = None):
        self.server_command = server_command
        self.env = env or {}
        self.base_cmd = [
            "npx",
            "@modelcontextprotocol/inspector",
            "--cli",
            "--transport",
            "stdio",
        ] + server_command

    def list_tools(self) -> ToolCallResult:
        """List available MCP tools."""
        return self._execute_inspector_command(["--method", "tools/list"])

    def call_tool(
        self, tool_name: str, arguments: dict[str, Any] | None = None
    ) -> ToolCallResult:
        """Call a specific MCP tool with arguments."""
        cmd = ["--method", "tools/call", "--tool-name", tool_name]

        if arguments:
            # Convert arguments to CLI format
            for key, value in arguments.items():
                cmd.extend(["--tool-arg", f"{key}={value}"])

        return self._execute_inspector_command(cmd)

    def _execute_inspector_command(self, args: list[str]) -> ToolCallResult:
        """Execute MCP Inspector CLI command and parse result."""
        full_cmd = self.base_cmd + args

        # Merge environment variables
        full_env = os.environ.copy()
        full_env.update(self.env)

        try:
            result = subprocess.run(
                full_cmd, capture_output=True, text=True, env=full_env, timeout=30
            )

            if result.returncode != 0:
                return ToolCallResult(
                    success=False,
                    content=[],
                    structured_content=None,
                    is_error=True,
                    raw_output=result.stderr,
                    error_message=f"Inspector CLI failed: {result.stderr}",
                )

            # Parse JSON response
            try:
                response = json.loads(result.stdout)

                # Handle tool list response
                if "tools" in response:
                    return ToolCallResult(
                        success=True,
                        content=[],
                        structured_content=response,
                        is_error=False,
                        raw_output=result.stdout,
                    )

                # Handle tool call response
                return ToolCallResult(
                    success=True,
                    content=response.get("content", []),
                    structured_content=response.get("structuredContent"),
                    is_error=response.get("isError", False),
                    raw_output=result.stdout,
                    error_message=None
                    if not response.get("isError")
                    else "Tool returned error",
                )

            except json.JSONDecodeError as e:
                return ToolCallResult(
                    success=False,
                    content=[],
                    structured_content=None,
                    is_error=True,
                    raw_output=result.stdout,
                    error_message=f"Failed to parse JSON response: {e}",
                )

        except subprocess.TimeoutExpired:
            return ToolCallResult(
                success=False,
                content=[],
                structured_content=None,
                is_error=True,
                raw_output="",
                error_message="Command timed out",
            )
        except Exception as e:
            return ToolCallResult(
                success=False,
                content=[],
                structured_content=None,
                is_error=True,
                raw_output="",
                error_message=f"Unexpected error: {e}",
            )


class TestCase(ABC):
    """Abstract base class for test cases."""

    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description

    @abstractmethod
    def run(self, client: MCPClient) -> TestResult:
        """Execute the test case and return the result."""
        pass


class ToolListTestCase(TestCase):
    """Test case for verifying tool listing functionality."""

    def __init__(self, expected_tools: list[str] | None = None, min_tools: int = 1):
        super().__init__("tool_list", "Verify MCP server provides expected tools")
        self.expected_tools = expected_tools or []
        self.min_tools = min_tools

    def run(self, client: MCPClient) -> TestResult:
        result = client.list_tools()

        if not result.success:
            return TestResult(
                name=self.name,
                passed=False,
                message=f"Failed to list tools: {result.error_message}",
                details={"error": result.error_message},
            )

        tools = (
            result.structured_content.get("tools", [])
            if result.structured_content
            else []
        )
        tool_names = [tool["name"] for tool in tools]

        # Check minimum number of tools
        if len(tool_names) < self.min_tools:
            return TestResult(
                name=self.name,
                passed=False,
                message=f"Expected at least {self.min_tools} tools, found {len(tool_names)}",
                details={"found_tools": tool_names},
            )

        # Check for expected tools
        missing_tools = [tool for tool in self.expected_tools if tool not in tool_names]
        if missing_tools:
            return TestResult(
                name=self.name,
                passed=False,
                message=f"Missing expected tools: {missing_tools}",
                details={"found_tools": tool_names, "missing_tools": missing_tools},
            )

        return TestResult(
            name=self.name,
            passed=True,
            message=f"Found {len(tool_names)} tools: {', '.join(tool_names)}",
            details={"tools": tool_names},
        )


class ToolCallTestCase(TestCase):
    """Test case for calling a specific MCP tool."""

    def __init__(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        validators: list[Callable] | None = None,
    ):
        super().__init__(
            f"tool_call_{tool_name}", f"Test {tool_name} tool functionality"
        )
        self.tool_name = tool_name
        self.arguments = arguments or {}
        self.validators = validators or []

    def run(self, client: MCPClient) -> TestResult:
        result = client.call_tool(self.tool_name, self.arguments)

        if not result.success:
            return TestResult(
                name=self.name,
                passed=False,
                message=f"Failed to call {self.tool_name}: {result.error_message}",
                details={"error": result.error_message, "arguments": self.arguments},
            )

        if result.is_error:
            error_text = ""
            if result.content:
                error_text = result.content[0].get("text", "Unknown error")
            return TestResult(
                name=self.name,
                passed=False,
                message=f"Tool {self.tool_name} returned error: {error_text}",
                details={"error_content": result.content, "arguments": self.arguments},
            )

        # Run custom validators
        for validator in self.validators:
            try:
                validation_result = validator(result)
                if not validation_result.get("valid", True):
                    return TestResult(
                        name=self.name,
                        passed=False,
                        message=f"Validation failed: {validation_result.get('message', 'Unknown validation error')}",
                        details={
                            "validation_error": validation_result,
                            "response": result.structured_content,
                        },
                    )
            except Exception as e:
                return TestResult(
                    name=self.name,
                    passed=False,
                    message=f"Validator exception: {e}",
                    details={"validator_error": str(e)},
                )

        return TestResult(
            name=self.name,
            passed=True,
            message=f"Tool {self.tool_name} executed successfully",
            details={
                "arguments": self.arguments,
                "response": result.structured_content,
                "content_items": len(result.content),
            },
        )


class TestSuite:
    """Collection of test cases with execution and reporting."""

    def __init__(self, name: str, client: MCPClient):
        self.name = name
        self.client = client
        self.test_cases: list[TestCase] = []
        self.results: list[TestResult] = []

    def add_test(self, test_case: TestCase) -> "TestSuite":
        """Add a test case to the suite."""
        self.test_cases.append(test_case)
        return self

    def run(self, verbose: bool = True) -> bool:
        """Run all test cases and return True if all passed."""
        if verbose:
            print(f"🧪 Running test suite: {self.name}")
            print(f"📋 {len(self.test_cases)} test cases to execute\n")

        passed_count = 0

        for i, test_case in enumerate(self.test_cases, 1):
            if verbose:
                print(
                    f"[{i}/{len(self.test_cases)}] {test_case.name}: {test_case.description}"
                )

            try:
                result = test_case.run(self.client)
                self.results.append(result)

                if result.passed:
                    passed_count += 1
                    if verbose:
                        print(f"  ✅ PASS: {result.message}")
                else:
                    if verbose:
                        print(f"  ❌ FAIL: {result.message}")
                        if result.details and verbose:
                            print(
                                f"     Details: {json.dumps(result.details, indent=6)}"
                            )

            except Exception as e:
                error_result = TestResult(
                    name=test_case.name,
                    passed=False,
                    message=f"Test execution failed: {e}",
                    details={"exception": str(e)},
                )
                self.results.append(error_result)
                if verbose:
                    print(f"  💥 ERROR: {e}")

            if verbose:
                print()

        # Summary
        failed_count = len(self.test_cases) - passed_count
        if verbose:
            print(f"📊 Test Results: {passed_count}/{len(self.test_cases)} passed")
            if failed_count > 0:
                print(f"❌ {failed_count} test(s) failed")
                failed_tests = [r.name for r in self.results if not r.passed]
                print(f"   Failed tests: {', '.join(failed_tests)}")
            else:
                print("🎉 All tests passed!")

        return failed_count == 0

    def get_results(self) -> list[TestResult]:
        """Get all test results."""
        return self.results.copy()


# Validation helper functions
def validate_redfish_service_root(result: ToolCallResult) -> dict[str, Any]:
    """Validate that response contains valid Redfish service root data."""
    if not result.structured_content:
        return {"valid": False, "message": "No structured content in response"}

    response_data = result.structured_content

    # Handle new format with headers and data structure
    if "data" in response_data and "headers" in response_data:
        data = response_data["data"]
        # Optionally validate headers too
        headers = response_data["headers"]
        if (
            "Content-Type" in headers
            and "application/json" not in headers["Content-Type"]
        ):
            return {
                "valid": False,
                "message": f"Unexpected Content-Type: {headers['Content-Type']}",
            }
    else:
        # Fallback for old format during transition
        data = response_data

    # Check for required Redfish service root fields
    required_fields = ["@odata.type", "Id", "Name", "RedfishVersion"]
    missing_fields = [field for field in required_fields if field not in data]

    if missing_fields:
        return {
            "valid": False,
            "message": f"Missing required Redfish fields: {missing_fields}",
        }

    # Validate specific field values
    if not data.get("@odata.type", "").startswith("#ServiceRoot"):
        return {
            "valid": False,
            "message": f"Invalid @odata.type: {data.get('@odata.type')}",
        }

    return {"valid": True, "message": "Valid Redfish service root"}


def validate_server_list(expected_servers: list[str]) -> Callable:
    """Create validator for server list responses."""

    def validator(result: ToolCallResult) -> dict[str, Any]:
        if not result.structured_content:
            return {"valid": False, "message": "No structured content in response"}

        servers = result.structured_content.get("result", [])

        missing_servers = [
            server for server in expected_servers if server not in servers
        ]
        if missing_servers:
            return {
                "valid": False,
                "message": f"Missing expected servers: {missing_servers}",
            }

        return {"valid": True, "message": f"Found expected servers: {servers}"}

    return validator


def validate_non_empty_response() -> Callable:
    """Create validator that ensures response is not empty."""

    def validator(result: ToolCallResult) -> dict[str, Any]:
        has_content = bool(result.content or result.structured_content)

        # For the new format, also check that data section is not empty
        if result.structured_content and "data" in result.structured_content:
            data_not_empty = bool(result.structured_content["data"])
            return {
                "valid": has_content and data_not_empty,
                "message": "Response has content and data"
                if (has_content and data_not_empty)
                else "Response is empty or missing data",
            }

        return {
            "valid": has_content,
            "message": "Response is not empty" if has_content else "Response is empty",
        }

    return validator
