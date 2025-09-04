# Copyright 2025 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause

import unittest
from unittest.mock import patch, MagicMock
import sys
import os
import json

# Patch sys.path to import from src
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../src')))

from fastmcp import Client
import tools.get as get_mod
import common.server
from fastmcp.exceptions import ValidationError, ToolError

class TestGetEndpointData(unittest.IsolatedAsyncioTestCase):
    @patch('common.config.get_hosts')
    async def test_invalid_url(self, mock_get_hosts):
        async with Client(common.server.mcp) as client:
            with self.assertRaises(ToolError):
                await client.call_tool("get_endpoint_data", {"url": "not-a-url"})

    @patch('common.config.get_hosts')
    async def test_server_not_found(self, mock_get_hosts):
        mock_get_hosts.return_value = [{'address': 'host1'}]
        url = 'https://host2/redfish/v1/Systems/1'
        async with Client(common.server.mcp) as client:
            with self.assertRaises(ToolError):
                await client.call_tool("get_endpoint_data", {"url": url})

    @patch('common.config.get_hosts')
    async def test_redfish_client_error(self, mock_get_hosts):
        mock_get_hosts.return_value = [{'address': 'host1', 'username': 'u', 'password': 'p'}]
        url = 'https://host1/redfish/v1/Systems/1'
        with patch('tools.get.redfish.redfish_client', side_effect=Exception('fail')):
            async with Client(common.server.mcp) as client:
                with self.assertRaises(ToolError):
                    await client.call_tool("get_endpoint_data", {"url": url})

    @patch('common.config.get_hosts')
    @patch('tools.get.RedfishClient')
    async def test_successful_fetch(self, mock_redfish_client, mock_get_hosts):
        mock_get_hosts.return_value = [{'address': 'host1', 'username': 'u', 'password': 'p'}]
        url = 'https://host1/redfish/v1/Systems/1'
        mock_instance = MagicMock()
        mock_instance.get.return_value = {'data': 'ok'}
        mock_redfish_client.return_value = mock_instance
        async with Client(common.server.mcp) as client:
            result = await client.call_tool("get_endpoint_data", {"url": url})
            self.assertEqual(len(result), 1)
            self.assertEqual(json.loads(result[0].text), {'data': 'ok'})

if __name__ == '__main__':
    unittest.main()
