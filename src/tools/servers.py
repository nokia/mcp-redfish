
# Copyright 2025 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause

"""
Tool for listing accessible Redfish servers via MCP integration.
"""

import os
import logging
import common.hosts
from common.server import mcp

LOG_LEVEL = os.getenv('MCP_LOG_LEVEL', 'INFO').upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO), format='%(asctime)s %(levelname)s %(message)s')

@mcp.tool()
async def list_servers() -> list:
    """
    List all Redfish Servers that can be accessed.

    Returns:
        list: A list of Redfish Servers that can be accessed
    """
    logging.info("Listing accessible Redfish servers.")
    try:
        servers = common.hosts.get_hosts()
    except Exception as e:
        logging.error(f"Failed to get Redfish servers: {e}")
        return []
    if not servers:
        logging.warning("No Redfish servers found.")
        return []
    return [srv['address'] for srv in servers if 'address' in srv]

