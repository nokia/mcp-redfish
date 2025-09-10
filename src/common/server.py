# Copyright 2025 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause

"""
Redfish MCP server initialization module.
Initializes MCP server for Redfish integration.
"""

import logging

from fastmcp import FastMCP

logger = logging.getLogger(__name__)

# Initialize FastMCP server with error handling
try:
    mcp = FastMCP("Redfish MCP Server")
    logger.info("MCP server initialized successfully.")
except Exception as e:
    logger.error(f"Failed to initialize MCP server: {e}")
