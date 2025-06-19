# Copyright 2025 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause

from fastmcp import FastMCP

# Initialize FastMCP server
mcp = FastMCP(
    "Redfish MCP Server",
    dependencies=["redfish", "dotenv", "urllib"]
)

