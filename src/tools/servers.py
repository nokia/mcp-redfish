# Copyright 2025 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause

"""
Tool for listing accessible Redfish servers via MCP integration.
"""

import logging

from .. import common
from ..common.server import mcp

logger = logging.getLogger(__name__)


@mcp.tool()
async def list_servers() -> list:
    """
    List configured Redfish servers that can be managed.

    Returns:
        list: A list of configured Redfish servers that can be managed
    """
    logger.info("Listing configured Redfish servers.")
    try:
        servers = common.hosts.get_hosts()
    except Exception as e:
        logger.error(f"Failed to get Redfish servers: {e}")
        return []
    if not servers:
        logger.warning("No Redfish servers found.")
        return []
    return [srv["address"] for srv in servers if "address" in srv]


@mcp.tool()
async def list_discovered_servers() -> list:
    """
    List discovered Redfish server candidates for review.

    Returns:
        list: A list of discovered Redfish server candidates. These candidates
        are informational only and are not managed unless explicitly configured.
    """
    logger.info("Listing discovered Redfish server candidates.")
    try:
        return common.hosts.get_discovered_hosts()
    except Exception as e:
        logger.error(f"Failed to get discovered Redfish servers: {e}")
        return []
