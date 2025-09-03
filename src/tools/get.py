# Copyright 2025 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause

import urllib.parse
import common.config
from common.server import mcp
import redfish
from fastmcp.exceptions import ValidationError, ToolError
from redfish.rest.v1 import AuthMethod

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

    # Get connection parameters

    try:
        auth_method = server_cfg.get("auth_method") or common.config.REDFISH_CFG.get("auth_method")
        if auth_method not in (AuthMethod.BASIC, AuthMethod.SESSION):
            raise ValidationError(f"Invalid auth_method: {auth_method}. Allowed values: {AuthMethod.BASIC}, {AuthMethod.SESSION}")
        username = server_cfg.get("username") or common.config.REDFISH_CFG.get("username")
        password = server_cfg.get("password") or common.config.REDFISH_CFG.get("password")
        port = server_cfg.get("port") or common.config.REDFISH_CFG.get("port", 443)
    except Exception as e:
        raise ToolError(f"Failed to read server config: {e}")

    base_url = f"https://{server_address}:{port}"
    client = None
    try:
        try:
            client = redfish.redfish_client(base_url=base_url, username=username, password=password, default_prefix="/redfish/v1")
        except Exception as e:
            raise ToolError(f"Failed to create Redfish client: {e}")
        # Set CA cert or skip verification as needed
        ca_cert = server_cfg.get("tls_server_ca_cert") or common.config.REDFISH_CFG.get("tls_server_ca_cert")
        if ca_cert:
            client.cafile = ca_cert
        try:
            client.login(auth=auth_method)
        except Exception as e:
            raise ToolError(f"Redfish login failed: {e}")
        try:
            response = client.get(resource_path)
        except Exception as e:
            raise ToolError(f"Redfish GET request failed: {e}")
        if response.status not in (200, 201):
            raise ToolError(f"Redfish GET failed: HTTP {response.status}", getattr(response, 'dict', None))
        return response.dict
    finally:
        if client:
            try:
                client.logout()
            except Exception:
                pass