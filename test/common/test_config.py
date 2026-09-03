# Copyright 2025 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause

"""
Tests for strict configuration loading. There is no legacy fallback parser:
configuration the validator rejects aborts the process with a readable message
rather than starting the server with substituted defaults.
"""

import importlib
import os
import sys
import unittest

# Patch sys.path to import from src
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src"))
)

import src.common.config as config

from test.utils import MockEnvironment


class TestStrictConfigLoading(unittest.TestCase):
    def tearDown(self):
        """Reload with the suite's valid environment so later tests see it."""
        importlib.reload(config)

    def _assert_aborts(self, env_vars: dict[str, str]) -> str:
        """Reload the config module and assert a clean non-zero abort."""
        with MockEnvironment(env_vars):
            with self.assertLogs("src.common.validation", level="ERROR") as logs:
                with self.assertRaises(SystemExit) as ctx:
                    importlib.reload(config)
        self.assertEqual(ctx.exception.code, 1)
        return "\n".join(logs.output)

    def test_invalid_tls_verify_aborts(self):
        """Invalid TLS verification values abort instead of defaulting."""
        output = self._assert_aborts(
            {
                "REDFISH_HOSTS": '[{"address": "test.example.com"}]',
                "REDFISH_TLS_VERIFY": "definitely-not-a-bool",
            }
        )
        self.assertIn("REDFISH_TLS_VERIFY", output)

    def test_unparseable_hosts_abort(self):
        """A malformed REDFISH_HOSTS is not replaced with a localhost default."""
        output = self._assert_aborts({"REDFISH_HOSTS": "not-json-at-all"})
        self.assertIn("REDFISH_HOSTS", output)

    def test_out_of_range_port_aborts(self):
        output = self._assert_aborts(
            {
                "REDFISH_HOSTS": '[{"address": "test.example.com"}]',
                "REDFISH_PORT": "70000",
            }
        )
        self.assertIn("REDFISH_PORT", output)

    def test_unknown_transport_aborts(self):
        """An unrecognised transport must never reach mcp.run() unvalidated."""
        for transport in ("http", "SSE", "bogus"):
            with self.subTest(transport=transport):
                output = self._assert_aborts({"MCP_TRANSPORT": transport})
                self.assertIn("Invalid transport", output)

    def test_abort_message_is_reported_without_a_traceback(self):
        """The operator gets the error and the remediation hint, not a stack."""
        output = self._assert_aborts({"REDFISH_HOSTS": "not-json-at-all"})
        self.assertIn("Configuration error:", output)
        self.assertIn("Check your environment variables and .env file", output)

    def test_abort_message_redacts_configured_secret_values(self):
        secret = "never-log-this-secret"
        output = self._assert_aborts(
            {
                "MCP_TRANSPORT": secret,
                "MCP_AUTH_CLIENT_SECRET": secret,
            }
        )
        self.assertNotIn(secret, output)
        self.assertIn("<redacted>", output)

    def test_http_auth_abort_repeats_the_breaking_change_message(self):
        """An auth abort carries the migration sentence from the plan."""
        output = self._assert_aborts(
            {
                "REDFISH_HOSTS": '[{"address": "test.example.com"}]',
                "MCP_TRANSPORT": "streamable-http",
            }
        )
        self.assertIn("now require authentication", output)
        self.assertIn("MCP_HTTP_AUTH=false", output)
        self.assertIn("stdio is unchanged", output)

    def test_unrelated_auth_error_omits_the_migration_message(self):
        """Telling an operator who already set MCP_AUTH_MODE to set it is noise."""
        output = self._assert_aborts(
            {
                "REDFISH_HOSTS": '[{"address": "test.example.com"}]',
                "MCP_TRANSPORT": "streamable-http",
                "MCP_AUTH_MODE": "token",
                "MCP_AUTH_JWT_AUDIENCE": "mcp-redfish",
                "MCP_AUTH_JWT_PUBLIC_KEY": "-----BEGIN PUBLIC KEY-----",
            }
        )
        self.assertIn("MCP_AUTH_JWT_ISSUER", output)
        self.assertNotIn("Breaking change", output)

    def test_valid_config_loads(self):
        with MockEnvironment(
            {
                "REDFISH_HOSTS": '[{"address": "valid.example.com"}]',
                "MCP_TRANSPORT": "stdio",
            }
        ):
            importlib.reload(config)
        self.assertEqual(config.MCP_TRANSPORT, "stdio")
        self.assertEqual(config.REDFISH_CFG["hosts"][0]["address"], "valid.example.com")
        self.assertTrue(config.REDFISH_CFG["tls_verify"])
        self.assertIsNotNone(config.REDFISH_CONFIG)
        self.assertIsNotNone(config.MCP_CONFIG)


if __name__ == "__main__":
    unittest.main()
