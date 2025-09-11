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
    List all Redfish Servers that can be accessed.

    Returns:
        list: A list of Redfish Servers that can be accessed
    """
    logger.info("Listing accessible Redfish servers.")
    try:
        servers = common.hosts.get_hosts()
    except Exception as e:
        logger.error(f"Failed to get Redfish servers: {e}")
        return []
    if not servers:
        logger.warning("No Redfish servers found.")
        return []
    return [srv["address"] for srv in servers if "address" in srv]
