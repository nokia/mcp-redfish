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

import src.common.server
import src.tools  # This ensures tools are registered


class TestGetEndpointData(unittest.IsolatedAsyncioTestCase):
    @patch("src.common.hosts.get_hosts")
    async def test_invalid_url(self, mock_get_hosts):
        async with Client(src.common.server.mcp) as client:
            with self.assertRaises(ToolError):
                await client.call_tool("get_resource_data", {"url": "not-a-url"})

    @patch("src.common.hosts.get_hosts")
    async def test_server_not_found(self, mock_get_hosts):
        mock_get_hosts.return_value = [{"address": "host1"}]
        url = "https://host2/redfish/v1/Systems/1"
        async with Client(src.common.server.mcp) as client:
            with self.assertRaises(ToolError):
                await client.call_tool("get_resource_data", {"url": url})

    @patch("src.common.hosts.get_hosts")
    async def test_redfish_client_error(self, mock_get_hosts):
        mock_get_hosts.return_value = [
            {"address": "host1", "username": "u", "password": "p"}
        ]
        url = "https://host1/redfish/v1/Systems/1"
        with patch("redfish.redfish_client", side_effect=Exception("fail")):
            async with Client(src.common.server.mcp) as client:
                with self.assertRaises(ToolError):
                    await client.call_tool("get_resource_data", {"url": url})

    @patch("src.common.hosts.get_hosts")
    @patch("redfish.redfish_client")
    async def test_successful_fetch(self, mock_redfish_client, mock_get_hosts):
        mock_get_hosts.return_value = [
            {"address": "host1", "username": "u", "password": "p"}
        ]
        url = "https://host1/redfish/v1/Systems/1"
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.dict = {"name": "System1", "id": "1"}
        mock_response.getheaders.return_value = [
            ("Content-Type", "application/json"),
            ("ETag", '"123456"'),
            ("Allow", "GET, POST, PATCH"),
            ("Link", "</redfish/v1/Systems/1/Actions>; rel=actions"),
        ]
        mock_redfish_client_instance = MagicMock()
        mock_redfish_client_instance.login.return_value = None
        mock_redfish_client_instance.cafile = None
        mock_redfish_client_instance.get.return_value = mock_response
        mock_redfish_client_instance.logout.return_value = None
        mock_redfish_client.return_value = mock_redfish_client_instance

        async with Client(src.common.server.mcp) as client:
            result = await client.call_tool("get_resource_data", {"url": url})
            # Handle both direct result and CallToolResult
            if hasattr(result, "content"):
                data = json.loads(result.content[0].text) if result.content else {}
            else:
                data = result

            # Verify the new format with headers and data
            self.assertIn("headers", data)
            self.assertIn("data", data)
            self.assertEqual(data["data"], {"name": "System1", "id": "1"})

            # Verify headers are extracted correctly
            headers = data["headers"]
            self.assertEqual(headers["Content-Type"], "application/json")
            self.assertEqual(headers["ETag"], '"123456"')
            self.assertEqual(headers["Allow"], "GET, POST, PATCH")
            self.assertEqual(
                headers["Link"], "</redfish/v1/Systems/1/Actions>; rel=actions"
            )

    @patch("src.common.hosts.get_hosts")
    @patch("redfish.redfish_client")
    async def test_multiple_link_headers(self, mock_redfish_client, mock_get_hosts):
        mock_get_hosts.return_value = [
            {"address": "host1", "username": "u", "password": "p"}
        ]
        url = "https://host1/redfish/v1/Systems/1"
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.dict = {"name": "System1"}
        mock_response.getheaders.return_value = [
            ("Content-Type", "application/json"),
            ("Link", "</redfish/v1/Systems/1/Actions>; rel=actions"),
            ("Link", "</redfish/v1/Systems/1/Storage>; rel=storage"),
        ]
        mock_redfish_client_instance = MagicMock()
        mock_redfish_client_instance.login.return_value = None
        mock_redfish_client_instance.cafile = None
        mock_redfish_client_instance.get.return_value = mock_response
        mock_redfish_client_instance.logout.return_value = None
        mock_redfish_client.return_value = mock_redfish_client_instance

        async with Client(src.common.server.mcp) as client:
            result = await client.call_tool("get_resource_data", {"url": url})
            if hasattr(result, "content"):
                data = json.loads(result.content[0].text) if result.content else {}
            else:
                data = result

            # Verify multiple Link headers are handled as array
            headers = data["headers"]
            self.assertIsInstance(headers["Link"], list)
            self.assertEqual(len(headers["Link"]), 2)
            self.assertIn(
                "</redfish/v1/Systems/1/Actions>; rel=actions", headers["Link"]
            )
            self.assertIn(
                "</redfish/v1/Systems/1/Storage>; rel=storage", headers["Link"]
            )

    @patch("src.common.hosts.get_hosts")
    @patch("redfish.redfish_client")
    async def test_optional_headers_missing(self, mock_redfish_client, mock_get_hosts):
        mock_get_hosts.return_value = [
            {"address": "host1", "username": "u", "password": "p"}
        ]
        url = "https://host1/redfish/v1/Systems/1"
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.dict = {"name": "System1"}
        # Only include required headers, omit optional ones like Content-Encoding
        mock_response.getheaders.return_value = [
            ("Content-Type", "application/json"),
            ("Allow", "GET"),
        ]
        mock_redfish_client_instance = MagicMock()
        mock_redfish_client_instance.login.return_value = None
        mock_redfish_client_instance.cafile = None
        mock_redfish_client_instance.get.return_value = mock_response
        mock_redfish_client_instance.logout.return_value = None
        mock_redfish_client.return_value = mock_redfish_client_instance

        async with Client(src.common.server.mcp) as client:
            result = await client.call_tool("get_resource_data", {"url": url})
            if hasattr(result, "content"):
                data = json.loads(result.content[0].text) if result.content else {}
            else:
                data = result

            headers = data["headers"]
            # Verify present headers
            self.assertEqual(headers["Content-Type"], "application/json")
            self.assertEqual(headers["Allow"], "GET")
            # Verify optional headers are not present
            self.assertNotIn("Content-Encoding", headers)
            self.assertNotIn("ETag", headers)
            self.assertNotIn("Link", headers)


if __name__ == "__main__":
    unittest.main()
