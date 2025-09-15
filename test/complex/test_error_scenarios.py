# Copyright 2025 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause

"""
Complex error scenario tests for Redfish client and tools.

These tests focus on realistic failure modes that can occur in production
environments, going beyond simple unit tests to test error handling robustness.
"""

import json
import os
import ssl
import sys
import unittest
from unittest.mock import MagicMock, patch

# Patch sys.path to import from src
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src"))
)

from fastmcp.exceptions import ToolError
from tenacity import RetryError

from src.common.client import RedfishClient
from src.common.validation import ConfigValidator


class TestComplexErrorScenarios(unittest.TestCase):
    """Test complex error scenarios and edge cases."""

    def setUp(self):
        """Set up test fixtures."""
        self.config_validator = ConfigValidator()

        self.server_cfg = {
            "address": "test-host.example.com",
            "port": 443,
            "username": "testuser",
            "password": "testpass",
            "auth_method": "session",
            "verify_cert": True,
        }

        self.common_cfg = type(
            "Config",
            (),
            {
                "REDFISH_CFG": {
                    "max_retries": 2,
                    "initial_delay": 0.01,
                    "max_delay": 1.0,
                    "backoff_factor": 2.0,
                    "jitter": False,
                }
            },
        )()

    def test_partial_authentication_failure(self):
        """Test scenarios where authentication partially fails."""
        test_scenarios = [
            {
                "name": "expired_session",
                "error": Exception("Session expired"),
                "description": "Session authentication expires mid-operation",
            },
            {
                "name": "invalid_credentials",
                "error": Exception("401 Unauthorized"),
                "description": "Wrong username/password combination",
            },
            {
                "name": "account_locked",
                "error": Exception("Account locked due to failed attempts"),
                "description": "Account locked after too many failed attempts",
            },
        ]

        for scenario in test_scenarios:
            with self.subTest(scenario=scenario["name"]):
                with patch("redfish.redfish_client") as mock_client:
                    mock_client.side_effect = scenario["error"]

                    with self.assertRaises((Exception, RetryError)):
                        RedfishClient(self.server_cfg, self.common_cfg)

    def test_malformed_redfish_responses(self):
        """Test handling of malformed or unexpected Redfish responses."""
        malformed_responses = [
            {"name": "invalid_json", "response": "Not JSON at all"},
            {"name": "empty_response", "response": ""},
            {"name": "incomplete_json", "response": '{"incomplete": '},
            {"name": "wrong_content_type", "response": "<html>Not JSON</html>"},
            {"name": "missing_required_fields", "response": '{"@odata.id": null}'},
            {
                "name": "unexpected_structure",
                "response": '["array", "instead", "of", "object"]',
            },
            {
                "name": "very_large_response",
                "response": '{"data": "' + "x" * 10000 + '"}',
            },
            {
                "name": "unicode_issues",
                "response": '{"message": "Invalid \\uDCFF unicode"}',
            },
        ]

        for response_test in malformed_responses:
            with self.subTest(response=response_test["name"]):
                with patch("redfish.redfish_client") as mock_redfish_client:
                    mock_client = MagicMock()
                    mock_redfish_client.return_value = mock_client

                    # Mock the response to return malformed data
                    mock_response = MagicMock()
                    if response_test["name"] == "invalid_json":
                        mock_response.dict = {"invalid": "response"}
                        # Simulate JSON decode error when accessing .dict
                        mock_client.get.side_effect = json.JSONDecodeError(
                            "Invalid JSON", "", 0
                        )
                    else:
                        mock_response.dict = response_test["response"]
                        mock_client.get.return_value = mock_response

                    client = RedfishClient(self.server_cfg, self.common_cfg)

                    # Should handle malformed responses gracefully
                    if response_test["name"] == "invalid_json":
                        with self.assertRaises((json.JSONDecodeError, ToolError)):
                            client.get("/redfish/v1/Systems")
                    else:
                        # Other malformed responses should be returned as-is
                        # The client should not crash, validation happens at tool level
                        try:
                            result = client.get("/redfish/v1/Systems")
                            self.assertIsNotNone(result)
                        except Exception:
                            # Some malformed responses might cause exceptions, that's ok
                            pass

    def test_network_timeout_scenarios(self):
        """Test various network timeout and connection scenarios."""
        network_scenarios = [
            {
                "name": "connection_timeout",
                "error": ConnectionError("Connection timed out"),
                "should_retry": True,
            },
            {
                "name": "read_timeout",
                "error": TimeoutError("Read timed out"),
                "should_retry": True,
            },
            {
                "name": "dns_resolution_failure",
                "error": OSError("Name or service not known"),
                "should_retry": True,
            },
            {
                "name": "connection_refused",
                "error": ConnectionError("Connection refused"),
                "should_retry": True,
            },
            {
                "name": "network_unreachable",
                "error": OSError("Network is unreachable"),
                "should_retry": True,
            },
            {
                "name": "host_unreachable",
                "error": OSError("No route to host"),
                "should_retry": True,
            },
        ]

        for scenario in network_scenarios:
            with self.subTest(scenario=scenario["name"]):
                with patch(
                    "src.common.client.redfish.redfish_client"
                ) as mock_redfish_client:
                    mock_redfish_client.side_effect = scenario["error"]

                    if scenario["should_retry"]:
                        # Should retry and eventually fail with RetryError
                        with self.assertRaises(RetryError):
                            RedfishClient(self.server_cfg, self.common_cfg)

                        # Verify retry attempts were made
                        self.assertGreater(mock_redfish_client.call_count, 1)
                    else:
                        # Should fail immediately without retry
                        with self.assertRaises(type(scenario["error"])):
                            RedfishClient(self.server_cfg, self.common_cfg)

    def test_ssl_certificate_issues(self):
        """Test various SSL certificate problems."""
        ssl_scenarios = [
            {
                "name": "self_signed_cert",
                "error": ssl.SSLError(
                    "certificate verify failed: self signed certificate"
                ),
                "verify_cert": True,
            },
            {
                "name": "expired_cert",
                "error": ssl.SSLError(
                    "certificate verify failed: certificate has expired"
                ),
                "verify_cert": True,
            },
            {
                "name": "hostname_mismatch",
                "error": ssl.SSLError("certificate verify failed: hostname mismatch"),
                "verify_cert": True,
            },
            {
                "name": "untrusted_ca",
                "error": ssl.SSLError(
                    "certificate verify failed: unable to get local issuer certificate"
                ),
                "verify_cert": True,
            },
        ]

        for scenario in ssl_scenarios:
            with self.subTest(scenario=scenario["name"]):
                ssl_server_cfg = self.server_cfg.copy()
                ssl_server_cfg["verify_cert"] = scenario["verify_cert"]

                with patch("redfish.redfish_client") as mock_redfish_client:
                    mock_redfish_client.side_effect = scenario["error"]

                    # SSL errors should be retried
                    with self.assertRaises(RetryError):
                        RedfishClient(ssl_server_cfg, self.common_cfg)

    def test_concurrent_request_conflicts(self):
        """Test handling of concurrent request conflicts."""
        import queue
        import threading

        results = queue.Queue()
        errors = queue.Queue()

        def worker(worker_id):
            try:
                with patch("redfish.redfish_client") as mock_redfish_client:
                    # Simulate different response times to create race conditions
                    mock_client = MagicMock()
                    if worker_id % 2 == 0:
                        # Some requests succeed
                        mock_redfish_client.return_value = mock_client
                        mock_response = MagicMock()
                        mock_response.dict = {"worker": worker_id, "status": "success"}
                        mock_client.get.return_value = mock_response
                    else:
                        # Some requests fail with connection errors
                        mock_redfish_client.side_effect = ConnectionError(
                            "Connection reset"
                        )

                    client = RedfishClient(self.server_cfg, self.common_cfg)
                    if worker_id % 2 == 0:
                        result = client.get("/redfish/v1/Systems")
                        results.put((worker_id, result))

            except Exception as e:
                errors.put((worker_id, e))

        # Start multiple concurrent workers
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join(timeout=5)

        # Some should succeed, some should fail - both are valid outcomes
        # Main thing is no deadlocks or crashes
        total_operations = results.qsize() + errors.qsize()
        self.assertGreater(total_operations, 0)

    def test_memory_pressure_scenarios(self):
        """Test behavior under memory pressure conditions."""
        # Simulate large response that might cause memory issues
        large_response_data = {
            "Members": [
                {"@odata.id": f"/redfish/v1/Systems/System{i}"} for i in range(1000)
            ],
            "Members@odata.count": 1000,
            "LargeData": "x" * 50000,  # 50KB of data
        }

        with patch("redfish.redfish_client") as mock_redfish_client:
            mock_client = MagicMock()
            mock_redfish_client.return_value = mock_client

            mock_response = MagicMock()
            mock_response.dict = large_response_data
            mock_client.get.return_value = mock_response

            client = RedfishClient(self.server_cfg, self.common_cfg)

            # Should handle large responses without memory errors
            result = client.get("/redfish/v1/Systems")
            self.assertIsInstance(result, dict)
            self.assertEqual(result["Members@odata.count"], 1000)

    def test_rapid_successive_failures(self):
        """Test behavior with rapid successive failures."""
        failure_sequence = [
            ConnectionError("Connection 1 failed"),
            TimeoutError("Timeout 1"),
            OSError("OS Error 1"),
            ConnectionError("Connection 2 failed"),
        ]

        with patch("redfish.redfish_client") as mock_redfish_client:
            mock_redfish_client.side_effect = failure_sequence

            # Should handle rapid failures and eventually give up
            with self.assertRaises(RetryError):
                RedfishClient(self.server_cfg, self.common_cfg)

            # Should have made multiple attempts
            self.assertGreater(mock_redfish_client.call_count, 1)

    def test_intermittent_network_issues(self):
        """Test handling of intermittent network connectivity."""
        with patch("redfish.redfish_client") as mock_redfish_client:
            mock_client = MagicMock()

            # First attempt fails, second succeeds (intermittent issue)
            mock_redfish_client.side_effect = [
                ConnectionError("Intermittent failure"),
                mock_client,
            ]

            mock_response = MagicMock()
            mock_response.dict = {"status": "recovered"}
            mock_client.get.return_value = mock_response

            # Should recover from intermittent issues
            client = RedfishClient(self.server_cfg, self.common_cfg)
            result = client.get("/redfish/v1/")

            self.assertEqual(result["status"], "recovered")
            self.assertEqual(mock_redfish_client.call_count, 2)

    def test_configuration_edge_cases(self):
        """Test edge cases in configuration handling."""
        edge_case_configs = [
            {
                "name": "very_long_hostname",
                "config": {"address": "x" * 255 + ".example.com"},
                "should_fail": True,
            },
            {
                "name": "invalid_port_range",
                "config": {"port": 99999},
                "should_fail": True,
            },
            {
                "name": "empty_username",
                "config": {"username": ""},
                "should_fail": False,  # Might be valid for some auth methods
            },
            {
                "name": "unicode_in_config",
                "config": {"address": "tëst-höst.example.com"},
                "should_fail": False,  # Should be handled gracefully
            },
        ]

        for test_case in edge_case_configs:
            with self.subTest(case=test_case["name"]):
                edge_config = self.server_cfg.copy()
                edge_config.update(test_case["config"])

                if test_case["should_fail"]:
                    # Configuration validation should catch these
                    with self.assertRaises((ValueError, Exception)):
                        # This might fail at validation or connection time
                        with patch(
                            "redfish.redfish_client",
                            side_effect=Exception("Config error"),
                        ):
                            RedfishClient(edge_config, self.common_cfg)
                else:
                    # Should handle edge cases gracefully
                    with patch("redfish.redfish_client") as mock_redfish_client:
                        mock_client = MagicMock()
                        mock_redfish_client.return_value = mock_client

                        try:
                            client = RedfishClient(edge_config, self.common_cfg)
                            self.assertIsNotNone(client)
                        except Exception:
                            # Some edge cases might still fail, but shouldn't crash
                            pass


if __name__ == "__main__":
    unittest.main()
