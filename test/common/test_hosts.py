# Copyright 2025 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause

"""
Tests for host storage and discovery candidate separation.
"""

import os
import sys
import unittest
from unittest.mock import patch

# Patch sys.path to import from src
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src"))
)

from src.common import hosts


class TestHosts(unittest.TestCase):
    def setUp(self):
        self.original_static_hosts = hosts._static_hosts
        self.original_discovered_hosts = hosts._discovered_hosts.copy()
        hosts._static_hosts = [{"address": "configured.example.com"}]
        hosts.update_discovered_hosts([])

    def tearDown(self):
        hosts._static_hosts = self.original_static_hosts
        hosts.update_discovered_hosts(self.original_discovered_hosts)

    def test_get_hosts_excludes_discovered_candidates(self):
        discovered = [
            {
                "source_address": "192.168.1.10",
                "service_root": "https://candidate.example.com/redfish/v1/",
                "service_host": "candidate.example.com",
                "service_port": 443,
                "scheme": "https",
            }
        ]
        hosts.update_discovered_hosts(discovered)

        self.assertEqual(hosts.get_hosts(), [{"address": "configured.example.com"}])
        self.assertEqual(hosts.get_discovered_hosts(), discovered)

    def test_static_hosts_come_from_validated_config(self):
        validated = [{"address": "127.0.0.1", "port": None}]
        with patch.object(hosts.common_config, "REDFISH_CFG", {"hosts": validated}):
            hosts._load_static_hosts()
        self.assertEqual(hosts.get_hosts(), validated)


if __name__ == "__main__":
    unittest.main()
