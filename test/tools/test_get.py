# Copyright 2025 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause

import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Patch sys.path to import from src
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src"))
)

from fastmcp import Client
from fastmcp.exceptions import ToolError

import common.server


class TestGetEndpointData(unittest.IsolatedAsyncioTestCase):
    @patch("common.hosts.get_hosts")
    async def test_invalid_url(self, mock_get_hosts):
        async with Client(common.server.mcp) as client:
            with self.assertRaises(ToolError):
                await client.call_tool("get_resource_data", {"url": "not-a-url"})

    @patch("common.hosts.get_hosts")
    async def test_server_not_found(self, mock_get_hosts):
        mock_get_hosts.return_value = [{"address": "host1"}]
        url = "https://host2/redfish/v1/Systems/1"
        async with Client(common.server.mcp) as client:
            with self.assertRaises(ToolError):
                await client.call_tool("get_resource_data", {"url": url})

    @patch("common.hosts.get_hosts")
    async def test_redfish_client_error(self, mock_get_hosts):
        mock_get_hosts.return_value = [
            {"address": "host1", "username": "u", "password": "p"}
        ]
        url = "https://host1/redfish/v1/Systems/1"
        with patch("redfish.redfish_client", side_effect=Exception("fail")):
            async with Client(common.server.mcp) as client:
                with self.assertRaises(ToolError):
                    await client.call_tool("get_resource_data", {"url": url})

    @patch("common.hosts.get_hosts")
    @patch("redfish.redfish_client")
    async def test_successful_fetch(self, mock_redfish_client, mock_get_hosts):
        mock_get_hosts.return_value = [
            {"address": "host1", "username": "u", "password": "p"}
        ]
        url = "https://host1/redfish/v1/Systems/1"
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.dict = {"data": "ok"}
        mock_redfish_client_instance = MagicMock()
        mock_redfish_client_instance.login.return_value = None
        mock_redfish_client_instance.cafile = None
        mock_redfish_client_instance.get.return_value = mock_response
        mock_redfish_client_instance.logout.return_value = None
        mock_redfish_client.return_value = mock_redfish_client_instance

        async with Client(common.server.mcp) as client:
            result = await client.call_tool("get_resource_data", {"url": url})
            # Handle both direct result and CallToolResult
            if hasattr(result, "content"):
                data = json.loads(result.content[0].text) if result.content else {}
            else:
                data = result
            self.assertEqual(data, {"data": "ok"})


if __name__ == "__main__":
    unittest.main()
