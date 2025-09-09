# Copyright 2025 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause

"""
Tool for fetching Redfish resource data via MCP server integration.
"""

import os
import urllib.parse

from fastmcp.exceptions import ToolError, ValidationError

import common.config
from common.client import RedfishClient
import logging
import common.config
import common.hosts
from common.server import mcp

logger = logging.getLogger(__name__)


@mcp.tool()
async def get_resource_data(url: str) -> dict:
    """
    Given a Redfish resource URL (e.g., 'https://<server address>/redfish/v1'), fetches and returns its data as JSON.
    To construct a valid Redfish resource URL as input, use the following url schema 'https://<server address>/redfish/v1/<resource path>'.

    Args:
        url (str): The Redfish URL to access the resource.

    Returns:
        data: The data of the resource in JSON format or an error message if the URL is invalid.
    """
    logger.info(f"Fetching Redfish resource data for URL: {url}")

    parsed = urllib.parse.urlparse(url)
    server_address = parsed.hostname
    resource_path = parsed.path
    if not server_address or not resource_path:
        logger.error(f"Invalid URL: missing server address or resource path: {url}")
        raise ValidationError(
            f"Invalid URL: missing server address or resource path: {url}"
        )

    # Find server config
    try:
        servers = common.hosts.get_hosts()
    except Exception as e:
        logger.error(f"Failed to load Redfish servers: {e}")
        raise ToolError(f"Failed to load Redfish servers: {e}")
    server_cfg = None
    for srv in servers:
        if srv.get("address") == server_address:
            server_cfg = srv
            break
    if not server_cfg:
        logger.error(f"Server {server_address} not found in config")
        raise ValidationError(f"Server {server_address} not found in config")

    client = None
    try:
        client = RedfishClient(server_cfg, common.config)
        response = client.get(resource_path)
        return response.dict
    finally:
        if client:
            client.logout()
