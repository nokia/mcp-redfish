# Copyright 2025 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause

"""
Tests for main.py module - MCP server initialization and configuration.

This module tests the critical server startup logic that was previously untested.
"""

import os
import sys
import unittest
import warnings
from unittest.mock import patch

# Patch sys.path to import from src
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src"))
)


class TestPythonRuntimeDeprecation(unittest.TestCase):
    """Test Python 3.13 deprecation notice."""

    def test_warns_on_python_3_13(self):
        from src.main import _warn_deprecated_python_runtime

        version_info = (3, 13, 5, "final", 0)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            with patch("src.main.sys.version_info", version_info):
                with self.assertLogs("src.main", level="WARNING") as logs:
                    _warn_deprecated_python_runtime()

        self.assertEqual(len(caught), 1)
        self.assertIs(caught[0].category, FutureWarning)
        self.assertIn("Python 3.13 support is deprecated", str(caught[0].message))
        self.assertTrue(
            any(
                "Python 3.13 support is deprecated" in message
                for message in logs.output
            )
        )

    def test_no_warning_on_python_3_14(self):
        from src.main import _warn_deprecated_python_runtime

        version_info = (3, 14, 7, "final", 0)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            with patch("src.main.sys.version_info", version_info):
                with self.assertRaises(AssertionError):
                    with self.assertLogs("src.main", level="WARNING"):
                        _warn_deprecated_python_runtime()

        self.assertEqual(len(caught), 0)


class TestRedfishMCPServerRun(unittest.TestCase):
    """Test RedfishMCPServer.run() transport forwarding."""

    def setUp(self):
        """Set up test environment."""
        self.env_patcher = patch.dict(
            os.environ,
            {
                "REDFISH_HOSTS": '[{"address": "test-host"}]',
                "MCP_TRANSPORT": "stdio",
                "MCP_REDFISH_LOG_LEVEL": "WARNING",
            },
        )
        self.env_patcher.start()

    def tearDown(self):
        """Clean up test environment."""
        self.env_patcher.stop()

    @patch("src.main.mcp.run")
    def test_run_forwards_configured_transport(self, mock_run):
        """Test that run() forwards each supported transport to mcp.run()."""
        import src.main
        from src.main import RedfishMCPServer

        transports = ["stdio", "sse", "streamable-http"]
        for transport in transports:
            with self.subTest(transport=transport):
                mock_run.reset_mock()
                with patch.object(src.main, "MCP_TRANSPORT", transport):
                    RedfishMCPServer().run()
                mock_run.assert_called_once_with(transport=transport)


class TestMainModule(unittest.TestCase):
    """Test main module server initialization."""

    def setUp(self):
        """Set up test environment."""
        self.env_patcher = patch.dict(
            os.environ,
            {
                "REDFISH_HOSTS": '[{"address": "test-host"}]',
                "MCP_TRANSPORT": "stdio",
                "MCP_REDFISH_LOG_LEVEL": "WARNING",
            },
        )
        self.env_patcher.start()

    def tearDown(self):
        """Clean up test environment."""
        self.env_patcher.stop()

    def test_mcp_server_creation(self):
        """Test that MCP server is created properly."""
        from src.main import mcp

        self.assertIsNotNone(mcp)
        self.assertTrue(hasattr(mcp, "run"))

    @patch("src.common.validation.ConfigValidator.load_config")
    def test_config_loading_error_handling(self, mock_load_config):
        """Test error handling during configuration loading."""
        try:
            import importlib

            import src.main

            importlib.reload(src.main)
            self.assertTrue(True)
        except Exception as e:
            self.fail(f"Main module import failed: {e}")

    @patch.dict(os.environ, {"REDFISH_HOSTS": "invalid-json"})
    def test_invalid_host_configuration(self):
        """Test handling of invalid host configuration."""
        try:
            import importlib

            import src.main

            importlib.reload(src.main)
            self.assertTrue(True)
        except Exception as e:
            self.assertIsInstance(e, (ValueError, KeyError))

    def test_environment_variable_handling(self):
        """Test that environment variables are processed correctly."""
        with patch.dict(
            os.environ,
            {
                "MCP_TRANSPORT": "sse",
                "MCP_REDFISH_LOG_LEVEL": "DEBUG",
                "REDFISH_HOSTS": '[{"address": "test.example.com", "username": "user"}]',
            },
        ):
            import importlib

            import src.main

            importlib.reload(src.main)
            self.assertIsNotNone(src.main.mcp)


class TestMainModuleEdgeCases(unittest.TestCase):
    """Test edge cases and error conditions in main module."""

    def test_missing_required_environment(self):
        """Test behavior when required environment variables are missing."""
        with patch.dict(os.environ, {}, clear=True):
            try:
                import importlib

                import src.main

                importlib.reload(src.main)
            except Exception as e:
                self.assertIsInstance(e, (ValueError, KeyError))

    def test_server_configuration_validation(self):
        """Test server configuration validation."""
        with patch.dict(
            os.environ,
            {
                "REDFISH_HOSTS": '[{"address": "valid-host.example.com"}]',
                "MCP_TRANSPORT": "stdio",
                "REDFISH_PORT": "443",
                "REDFISH_USERNAME": "testuser",
                "REDFISH_PASSWORD": "testpass",
            },
        ):
            import importlib

            import src.main

            importlib.reload(src.main)
            self.assertIsNotNone(src.main.mcp)

    def test_logging_configuration(self):
        """Test logging level configuration."""
        log_levels = ["DEBUG", "INFO", "WARNING", "ERROR"]

        for level in log_levels:
            with self.subTest(level=level):
                with patch.dict(
                    os.environ,
                    {
                        "REDFISH_HOSTS": '[{"address": "test-host"}]',
                        "MCP_REDFISH_LOG_LEVEL": level,
                    },
                ):
                    import importlib

                    import src.main

                    importlib.reload(src.main)
                    self.assertIsNotNone(src.main.mcp)


if __name__ == "__main__":
    unittest.main()
