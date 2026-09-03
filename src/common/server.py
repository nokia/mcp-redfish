# Copyright 2025 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause

"""
Redfish MCP server initialization module.
Initializes MCP server for Redfish integration.
"""

import logging

from fastmcp import FastMCP

from . import config as _config  # noqa: F401 - load .env and REDFISH config first
from .auth import build_auth_provider
from .validation import (
    AuthConfigurationError,
    MCPAuthConfig,
    fatal_configuration_error,
    is_http_transport,
)

logger = logging.getLogger(__name__)

# Initialize FastMCP server with error handling.
# Auth provider is built from MCP_AUTH_* after validation so FASTMCP_SERVER_AUTH
# auto-wiring cannot slip through.
try:
    _auth_config = _config.MCP_CONFIG.auth or MCPAuthConfig()
    _auth_provider = (
        build_auth_provider(_auth_config)
        if is_http_transport(_config.MCP_CONFIG.transport)
        else None
    )
    mcp = FastMCP("Redfish MCP Server", auth=_auth_provider)
    logger.info("MCP server initialized successfully.")
except AuthConfigurationError as error:
    raise fatal_configuration_error(error) from None
except Exception as e:
    logger.error("Failed to initialize MCP Server: error_type=%s", type(e).__name__)
    raise
