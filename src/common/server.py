
# Copyright 2025 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause

"""
Redfish MCP server initialization module.
Initializes MCP server for Redfish integration.
"""

import os
import logging
from fastmcp import FastMCP

# Configure logging to stderr
LOG_LEVEL = os.getenv('MCP_LOG_LEVEL', 'INFO').upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO), format='%(asctime)s %(levelname)s %(message)s')

# Initialize FastMCP server with error handling
try:
    mcp = FastMCP(
        "Redfish MCP Server",
        dependencies=["redfish", "dotenv", "urllib"]
    )
    logging.info("MCP server initialized successfully.")
except Exception as e:
    logging.error(f"Failed to initialize MCP server: {e}")

