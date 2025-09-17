# Copyright 2025 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause

"""
Tool for fetching Redfish resource data via MCP server integration.
"""

import logging
import urllib.parse

from fastmcp.exceptions import ToolError, ValidationError

from .. import common
from ..common.client import RedfishClient
from ..common.server import mcp

logger = logging.getLogger(__name__)


@mcp.tool()
async def get_resource_data(url: str) -> dict:
    """
    Given a Redfish resource URL (e.g., 'https://<server address>/redfish/v1'), fetches and returns its data as JSON.
    To construct a valid Redfish resource URL as input, use the following url schema 'https://<server address>/redfish/v1/<resource path>'.

    Args:
        url (str): The Redfish URL to access the resource.

    Returns:
        dict: A JSON document containing:
            - "headers": Response headers including Allow, Content-Type, Content-Encoding (optional), ETag, and Link
            - "data": The actual resource data in JSON format
        Returns an error message if the URL is invalid.
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
        raise ToolError(f"Failed to load Redfish servers: {e}") from e
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
        response = client.get_with_headers(resource_path)
        # Ensure we return a properly formatted response
        if isinstance(response, dict) and "headers" in response and "data" in response:
            return response
        # Fallback for unexpected response format
        return {"headers": {}, "data": response if isinstance(response, dict) else {}}
    finally:
        if client:
            client.logout()
