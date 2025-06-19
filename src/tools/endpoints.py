# Copyright 2025 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause

import common.config
from common.server import mcp

@mcp.tool()
async def list_endpoints() -> list:
    """List all Redfish Endpoints that can be accessed.

    Args:
        None

    Returns:
        list: A list of Redfish Endpoints that can be accessed
    """
    
    endpoints = common.config.get_hosts()
    if not endpoints:
        return []
    return [ep['address'] for ep in endpoints if 'address' in ep]

