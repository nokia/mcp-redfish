# Copyright 2025 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause

import unittest
from unittest.mock import patch
import sys
import os
import json

# Patch sys.path to import from src
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src"))
)

from fastmcp import Client
import tools.servers as servers
import common.server


class TestListEndpoints(unittest.IsolatedAsyncioTestCase):
    @patch("common.hosts.get_hosts")
    async def test_list_endpoints_empty(self, mock_get_hosts):
        mock_get_hosts.return_value = []
        async with Client(common.server.mcp) as client:
            result = await client.call_tool("list_servers", {})
            # Handle both direct result and CallToolResult
            if hasattr(result, "content"):
                data = json.loads(result.content[0].text) if result.content else []
            else:
                data = result
            self.assertEqual(len(data), 0)

    @patch("common.hosts.get_hosts")
    async def test_list_endpoints_with_addresses(self, mock_get_hosts):
        mock_get_hosts.return_value = [
            {"address": "host1"},
            {"address": "host2"},
            {"noaddress": "host3"},
        ]
        async with Client(common.server.mcp) as client:
            result = await client.call_tool("list_servers", {})
            # Handle both direct result and CallToolResult
            if hasattr(result, "content"):
                data = json.loads(result.content[0].text) if result.content else []
            else:
                data = result
            self.assertEqual(len(data), 2)
            self.assertEqual(data, ["host1", "host2"])


if __name__ == "__main__":
    unittest.main()
