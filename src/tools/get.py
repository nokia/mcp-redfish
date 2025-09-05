# Copyright 2025 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause

import urllib.parse

from fastmcp.exceptions import ToolError, ValidationError

import common.config
from common.client import RedfishClient
from common.server import mcp

@mcp.tool()
async def get_endpoint_data(url: str) -> dict:
    """Given a Redfish resource URL (e.g., 'https://<endpoint address>/redfish/v1'), fetches and returns its data as JSON.
    To construct a valid Redfish resource URL as input, use the following url schema 'https://<endpoint address>/redfish/v1/<resource path>'.

    Args:
        url: The Redfish URL to access the resource.

    Returns:
        data: The data of the resource in JSON format or an error message if the URL is invalid.
    """
    parsed = urllib.parse.urlparse(url)
    server_address = parsed.hostname
    resource_path = parsed.path
    if not server_address or not resource_path:
        raise ValidationError(f"Invalid URL: missing server address or resource path: {url}")

    # Find server config
    try:
        endpoints = common.config.get_hosts()
    except Exception as e:
        raise ToolError(f"Failed to load Redfish endpoints: {e}")
    server_cfg = None
    for ep in endpoints:
        if ep.get("address") == server_address:
            server_cfg = ep
            break
    if not server_cfg:
        raise ValidationError(f"Server {server_address} not found in config")

    client = None
    try:
        client = RedfishClient(server_cfg, common.config)
        response_dict = client.get(resource_path)
        return response_dict
    finally:
        if client:
            client.logout()