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
    """Test RedfishMCPServer.run() transport forwarding and HTTP auth wiring."""

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
        from test.utils import clear_auth_env

        clear_auth_env()

    def tearDown(self):
        """Clean up test environment."""
        self.env_patcher.stop()

    @patch("src.main.mcp.run")
    def test_run_stdio_forwards_transport_only(self, mock_run):
        """stdio does not pass HTTP host/TLS kwargs."""
        import src.main
        from src.main import RedfishMCPServer

        with self.assertLogs("src.main", level="INFO") as logs:
            with patch.object(src.main, "MCP_TRANSPORT", "stdio"):
                RedfishMCPServer().run()
        mock_run.assert_called_once_with(transport="stdio")
        self.assertIn("http_authentication=not_applicable", "\n".join(logs.output))

    @patch("src.main.mcp.run")
    def test_run_http_default_auth_exits(self, mock_run):
        """HTTP + default MCP_HTTP_AUTH + MODE=none exits non-zero.

        "http" is included because FastMCP accepts it as a transport name: if
        run() and the validator disagreed about what counts as HTTP, that value
        would start an unauthenticated listener.
        """
        import src.main
        from src.main import RedfishMCPServer

        for transport in ("sse", "streamable-http", "http"):
            with self.subTest(transport=transport):
                mock_run.reset_mock()
                with patch.object(src.main, "MCP_TRANSPORT", transport):
                    with self.assertRaises(SystemExit) as ctx:
                        RedfishMCPServer().run()
                self.assertEqual(ctx.exception.code, 1)
                mock_run.assert_not_called()

    @patch("src.main.mcp.run", side_effect=RuntimeError("address already in use"))
    def test_run_failure_exits_non_zero(self, mock_run):
        """A server that failed to start must not report success to a supervisor."""
        import src.main
        from src.main import RedfishMCPServer

        os.environ["MCP_HTTP_AUTH"] = "false"
        with self.assertLogs("src.main", level="DEBUG") as logs:
            for transport in ("stdio", "streamable-http"):
                with self.subTest(transport=transport):
                    with patch.object(src.main, "MCP_TRANSPORT", transport):
                        with self.assertRaises(SystemExit) as ctx:
                            RedfishMCPServer().run()
                    self.assertEqual(ctx.exception.code, 1)
        output = "\n".join(logs.output)
        self.assertIn("error_type=RuntimeError", output)
        self.assertIn("startup failure locations", output)
        self.assertNotIn("address already in use", output)

    @patch("src.main.mcp.run")
    def test_run_http_auth_disabled_binds_loopback(self, mock_run):
        """Unset FASTMCP_HOST is passed as 127.0.0.1, including with auth disabled."""
        import src.main
        from src.main import RedfishMCPServer

        os.environ["MCP_HTTP_AUTH"] = "false"
        os.environ.pop("FASTMCP_HOST", None)
        with patch.object(src.main, "MCP_TRANSPORT", "streamable-http"):
            RedfishMCPServer().run()
        mock_run.assert_called_once()
        kwargs = mock_run.call_args.kwargs
        self.assertEqual(mock_run.call_args.args, ())
        self.assertEqual(kwargs["transport"], "streamable-http")
        self.assertEqual(kwargs["host"], "127.0.0.1")
        self.assertEqual(kwargs["host_origin_protection"], "auto")
        self.assertNotIn("uvicorn_config", kwargs)

    @patch("src.main.mcp.run")
    def test_run_http_host_passthrough_with_auth_disabled(self, mock_run):
        """FASTMCP_HOST=0.0.0.0 is honored even when MCP_HTTP_AUTH=false."""
        import src.main
        from src.main import RedfishMCPServer

        os.environ["MCP_HTTP_AUTH"] = "false"
        os.environ["FASTMCP_HOST"] = "0.0.0.0"
        os.environ["FASTMCP_HTTP_ALLOWED_HOSTS"] = '["mcp.example.com"]'
        with patch.object(src.main, "MCP_TRANSPORT", "streamable-http"):
            RedfishMCPServer().run()
        self.assertEqual(mock_run.call_args.kwargs["host"], "0.0.0.0")
        self.assertEqual(mock_run.call_args.kwargs["transport"], "streamable-http")

    @patch("src.main.mcp.run")
    def test_run_http_token_loopback_without_tls_flag(self, mock_run):
        """Auth on default loopback bind starts without MCP_TLS_TERMINATED."""
        from fastmcp.server.auth.providers.jwt import RSAKeyPair

        import src.main
        from src.main import RedfishMCPServer

        keypair = RSAKeyPair.generate()
        os.environ["MCP_AUTH_MODE"] = "token"
        os.environ["MCP_AUTH_JWT_ISSUER"] = "https://issuer.example"
        os.environ["MCP_AUTH_JWT_AUDIENCE"] = "mcp-redfish"
        os.environ["MCP_AUTH_JWT_PUBLIC_KEY"] = keypair.public_key
        os.environ.pop("FASTMCP_HOST", None)
        os.environ.pop("MCP_TLS_TERMINATED", None)
        with patch.object(src.main, "MCP_TRANSPORT", "streamable-http"):
            RedfishMCPServer().run()
        kwargs = mock_run.call_args.kwargs
        self.assertEqual(kwargs["host"], "127.0.0.1")
        self.assertNotIn("uvicorn_config", kwargs)

    @patch("src.main.mcp.run")
    def test_run_http_token_non_loopback_without_tls_exits(self, mock_run):
        """Auth + FASTMCP_HOST=0.0.0.0 without flag or certs exits."""
        from fastmcp.server.auth.providers.jwt import RSAKeyPair

        import src.main
        from src.main import RedfishMCPServer

        keypair = RSAKeyPair.generate()
        os.environ["MCP_AUTH_MODE"] = "token"
        os.environ["MCP_AUTH_JWT_ISSUER"] = "https://issuer.example"
        os.environ["MCP_AUTH_JWT_AUDIENCE"] = "mcp-redfish"
        os.environ["MCP_AUTH_JWT_PUBLIC_KEY"] = keypair.public_key
        os.environ["FASTMCP_HOST"] = "0.0.0.0"
        with patch.object(src.main, "MCP_TRANSPORT", "streamable-http"):
            with self.assertRaises(SystemExit) as ctx:
                RedfishMCPServer().run()
        self.assertEqual(ctx.exception.code, 1)
        mock_run.assert_not_called()

    @patch("src.main.mcp.run")
    def test_run_http_cert_key_passed_to_uvicorn(self, mock_run):
        """Readable cert+key are passed as uvicorn ssl_* without proxy warning."""
        import tempfile

        from fastmcp.server.auth.providers.jwt import RSAKeyPair

        import src.main
        from src.main import RedfishMCPServer

        from test.utils import write_self_signed_tls_pair

        keypair = RSAKeyPair.generate()
        with tempfile.TemporaryDirectory() as tmp:
            cert, key = write_self_signed_tls_pair(tmp)
            os.environ["MCP_AUTH_MODE"] = "token"
            os.environ["MCP_AUTH_JWT_ISSUER"] = "https://issuer.example"
            os.environ["MCP_AUTH_JWT_AUDIENCE"] = "mcp-redfish"
            os.environ["MCP_AUTH_JWT_PUBLIC_KEY"] = keypair.public_key
            os.environ["FASTMCP_HOST"] = "0.0.0.0"
            os.environ["MCP_TLS_CERTFILE"] = cert
            os.environ["MCP_TLS_KEYFILE"] = key
            os.environ["FASTMCP_HTTP_ALLOWED_HOSTS"] = '["mcp.example.com"]'
            os.environ.pop("MCP_TLS_TERMINATED", None)
            with patch.object(src.main, "MCP_TRANSPORT", "streamable-http"):
                RedfishMCPServer().run()
        uvicorn_config = mock_run.call_args.kwargs["uvicorn_config"]
        self.assertEqual(uvicorn_config["ssl_certfile"], os.environ["MCP_TLS_CERTFILE"])
        self.assertEqual(uvicorn_config["ssl_keyfile"], os.environ["MCP_TLS_KEYFILE"])


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
