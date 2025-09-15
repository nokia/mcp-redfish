# Copyright 2025 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause

"""
Integration tests for Redfish client using real DMTF Redfish Interface Emulator.

These tests complement the unit tests by testing against a real Redfish server,
validating actual HTTP interactions, authentication, and protocol compliance.
"""

import os
import subprocess
import sys
import time
import unittest
from pathlib import Path

# Patch sys.path to import from src
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src"))
)

from fastmcp.exceptions import ToolError

from src.common.client import RedfishClient
from src.common.validation import ConfigValidator


class TestRedfishClientIntegration(unittest.TestCase):
    """Integration tests using real DMTF Redfish Interface Emulator."""

    @classmethod
    def setUpClass(cls):
        """Set up the Redfish emulator for integration testing."""
        cls.emulator_url = "https://localhost:8000"
        cls.emulator_username = "root"
        cls.emulator_password = "calvin"

        # Check if emulator is already running
        if not cls._is_emulator_running():
            cls._start_emulator()
            # Give emulator time to start
            time.sleep(3)

        # Verify emulator is accessible
        if not cls._is_emulator_running():
            raise unittest.SkipTest(
                "Redfish emulator not available for integration tests"
            )

    @classmethod
    def _is_emulator_running(cls):
        """Check if the Redfish emulator is running."""
        try:
            result = subprocess.run(
                ["curl", "-k", "-s", f"{cls.emulator_url}/redfish/v1/"],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    @classmethod
    def _start_emulator(cls):
        """Start the Redfish emulator using make commands."""
        try:
            # Use the existing makefile commands
            project_root = Path(__file__).parent.parent.parent
            subprocess.run(
                ["make", "e2e-emulator-setup"],
                cwd=project_root,
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["make", "e2e-emulator-start"],
                cwd=project_root,
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError as e:
            raise unittest.SkipTest(f"Failed to start emulator: {e}") from e

    def setUp(self):
        """Set up test fixtures for each test."""
        # Create realistic configuration
        self.config_validator = ConfigValidator()

        # Server configuration for emulator
        self.server_cfg = {
            "address": "localhost",
            "port": 8000,
            "username": self.emulator_username,
            "password": self.emulator_password,
            "auth_method": "session",
            "verify_cert": False,  # Self-signed cert in emulator
        }

        # Common configuration with retry settings
        self.common_cfg = type(
            "Config",
            (),
            {
                "REDFISH_CFG": {
                    "max_retries": 3,
                    "initial_delay": 0.5,
                    "max_delay": 10.0,
                    "backoff_factor": 2.0,
                    "jitter": True,
                }
            },
        )()

    def test_real_service_root_access(self):
        """Test accessing real Redfish service root."""
        client = RedfishClient(self.server_cfg, self.common_cfg)

        # Get service root - this tests real authentication and HTTP
        service_root = client.get("/redfish/v1/")

        # Validate real Redfish service root structure
        self.assertIn("@odata.id", service_root)
        self.assertIn("@odata.type", service_root)
        self.assertIn("Id", service_root)
        self.assertIn("Name", service_root)
        self.assertEqual(service_root["@odata.id"], "/redfish/v1/")

    def test_real_systems_collection(self):
        """Test accessing real Systems collection."""
        client = RedfishClient(self.server_cfg, self.common_cfg)

        # Get systems collection
        systems = client.get("/redfish/v1/Systems")

        # Validate collection structure
        self.assertIn("@odata.id", systems)
        self.assertIn("Members", systems)
        self.assertIn("Members@odata.count", systems)
        self.assertIsInstance(systems["Members"], list)

    def test_real_system_resource(self):
        """Test accessing individual system resource."""
        client = RedfishClient(self.server_cfg, self.common_cfg)

        # First get the systems collection to find a system ID
        systems = client.get("/redfish/v1/Systems")

        if systems["Members@odata.count"] > 0:
            # Get the first system
            system_url = systems["Members"][0]["@odata.id"]
            system = client.get(system_url)

            # Validate system resource structure
            self.assertIn("@odata.id", system)
            self.assertIn("@odata.type", system)
            self.assertIn("Id", system)
            self.assertIn("Name", system)
            self.assertIn("SystemType", system)

    def test_real_authentication_failure(self):
        """Test real authentication failure handling."""
        # Use wrong credentials
        bad_server_cfg = self.server_cfg.copy()
        bad_server_cfg["password"] = "wrong_password"

        # Should fail with authentication error (not a mock)
        with self.assertRaises(
            (ToolError, Exception)
        ):  # Real auth error from redfish library
            RedfishClient(bad_server_cfg, self.common_cfg)

    def test_real_invalid_endpoint(self):
        """Test accessing non-existent endpoint on real server."""
        client = RedfishClient(self.server_cfg, self.common_cfg)

        # Try to access non-existent resource
        with self.assertRaises(
            (ToolError, ValueError, RuntimeError)
        ):  # Real HTTP 404 from server
            client.get("/redfish/v1/NonExistentResource")

    def test_real_retry_behavior(self):
        """Test retry behavior with real network conditions."""
        # Configure very short timeout to force some failures
        retry_server_cfg = self.server_cfg.copy()

        # Common config with aggressive retry settings
        retry_common_cfg = type(
            "Config",
            (),
            {
                "REDFISH_CFG": {
                    "max_retries": 2,
                    "initial_delay": 0.1,
                    "max_delay": 1.0,
                    "backoff_factor": 2.0,
                    "jitter": False,  # Predictable timing for test
                }
            },
        )()

        client = RedfishClient(retry_server_cfg, retry_common_cfg)

        # This should eventually succeed even if there are transient issues
        service_root = client.get("/redfish/v1/")
        self.assertIn("@odata.id", service_root)

    def test_real_concurrent_access(self):
        """Test concurrent access to real Redfish server."""
        import queue
        import threading

        results = queue.Queue()
        errors = queue.Queue()

        def worker():
            try:
                client = RedfishClient(self.server_cfg, self.common_cfg)
                result = client.get("/redfish/v1/")
                results.put(result)
            except Exception as e:
                errors.put(e)

        # Start multiple concurrent requests
        threads = [threading.Thread(target=worker) for _ in range(3)]
        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join(timeout=10)

        # All requests should succeed
        self.assertEqual(results.qsize(), 3)
        self.assertEqual(errors.qsize(), 0)

    def test_real_large_response_handling(self):
        """Test handling of large responses from real server."""
        client = RedfishClient(self.server_cfg, self.common_cfg)

        # Get a potentially large response (all systems)
        systems = client.get("/redfish/v1/Systems")

        # Validate we can handle the full response
        self.assertIsInstance(systems, dict)
        self.assertIn("Members", systems)

        # If there are systems, try to get one with full details
        if systems["Members@odata.count"] > 0:
            system_url = systems["Members"][0]["@odata.id"]
            system = client.get(system_url)

            # Large system response should be handled properly
            self.assertIsInstance(system, dict)
            self.assertIn("@odata.id", system)

    @unittest.skipIf(os.getenv("SKIP_SSL_TESTS") == "true", "SSL tests disabled")
    def test_real_ssl_handling(self):
        """Test SSL certificate handling with real server."""
        # Test with cert verification disabled (emulator uses self-signed)
        client = RedfishClient(self.server_cfg, self.common_cfg)

        # Should work with verify_cert=False
        service_root = client.get("/redfish/v1/")
        self.assertIn("@odata.id", service_root)

        # Test with cert verification enabled (should fail with self-signed)
        ssl_server_cfg = self.server_cfg.copy()
        ssl_server_cfg["verify_cert"] = True

        # This should fail due to self-signed certificate
        with self.assertRaises((ToolError, RuntimeError, OSError)):  # Real SSL error
            client = RedfishClient(ssl_server_cfg, self.common_cfg)
            client.get("/redfish/v1/")


if __name__ == "__main__":
    # Integration tests can be skipped if emulator is not available
    unittest.main()
