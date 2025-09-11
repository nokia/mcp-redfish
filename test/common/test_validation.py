# Copyright 2025 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause

import os
import sys
import unittest

# Patch sys.path to import from src
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src"))
)

from common.validation import (
    ConfigurationError,
    ConfigValidator,
    HostConfig,
    MCPConfig,
    RedfishConfig,
)

from test.utils import MockEnvironment


class TestHostConfig(unittest.TestCase):
    def test_valid_host_config(self):
        """Test creating a valid host configuration."""
        host = HostConfig(address="test.example.com", port=443, username="user")
        self.assertEqual(host.address, "test.example.com")
        self.assertEqual(host.port, 443)
        self.assertEqual(host.username, "user")

    def test_empty_address_raises_error(self):
        """Test that empty address raises ValueError."""
        with self.assertRaises(ValueError) as context:
            HostConfig(address="")
        self.assertIn("cannot be empty", str(context.exception))

    def test_invalid_port_raises_error(self):
        """Test that invalid port raises ValueError."""
        with self.assertRaises(ValueError) as context:
            HostConfig(address="test.example.com", port=70000)
        self.assertIn("Port must be between", str(context.exception))

    def test_invalid_auth_method_raises_error(self):
        """Test that invalid auth method raises ValueError."""
        with self.assertRaises(ValueError) as context:
            HostConfig(address="test.example.com", auth_method="invalid")
        self.assertIn("Invalid auth_method", str(context.exception))


class TestRedfishConfig(unittest.TestCase):
    def test_valid_redfish_config(self):
        """Test creating a valid Redfish configuration."""
        hosts = [HostConfig(address="test.example.com")]
        config = RedfishConfig(hosts=hosts, port=443, auth_method="session")
        self.assertEqual(len(config.hosts), 1)
        self.assertEqual(config.port, 443)
        self.assertEqual(config.auth_method, "session")

    def test_invalid_port_raises_error(self):
        """Test that invalid port raises ValueError."""
        with self.assertRaises(ValueError) as context:
            RedfishConfig(port=0)
        self.assertIn("Port must be between", str(context.exception))

    def test_invalid_auth_method_raises_error(self):
        """Test that invalid auth method raises ValueError."""
        with self.assertRaises(ValueError) as context:
            RedfishConfig(auth_method="invalid")
        self.assertIn("Invalid auth_method", str(context.exception))

    def test_invalid_discovery_interval_raises_error(self):
        """Test that invalid discovery interval raises ValueError."""
        with self.assertRaises(ValueError) as context:
            RedfishConfig(discovery_interval=0)
        self.assertIn("Discovery interval must be positive", str(context.exception))


class TestMCPConfig(unittest.TestCase):
    def test_valid_mcp_config(self):
        """Test creating a valid MCP configuration."""
        config = MCPConfig(transport="stdio", log_level="INFO")
        self.assertEqual(config.transport, "stdio")
        self.assertEqual(config.log_level, "INFO")

    def test_invalid_transport_raises_error(self):
        """Test that invalid transport raises ValueError."""
        with self.assertRaises(ValueError) as context:
            MCPConfig(transport="invalid")
        self.assertIn("Invalid transport", str(context.exception))

    def test_invalid_log_level_raises_error(self):
        """Test that invalid log level raises ValueError."""
        with self.assertRaises(ValueError) as context:
            MCPConfig(log_level="INVALID")
        self.assertIn("Invalid log_level", str(context.exception))

    def test_log_level_case_normalization(self):
        """Test that log level is normalized to uppercase."""
        config = MCPConfig(log_level="info")
        self.assertEqual(config.log_level, "INFO")


class TestConfigValidator(unittest.TestCase):
    def test_parse_valid_hosts_json(self):
        """Test parsing valid hosts JSON."""
        hosts_json = '[{"address": "host1.example.com"}, {"address": "host2.example.com", "port": 8443}]'
        hosts = ConfigValidator.parse_hosts(hosts_json)
        self.assertEqual(len(hosts), 2)
        self.assertEqual(hosts[0].address, "host1.example.com")
        self.assertEqual(hosts[1].address, "host2.example.com")
        self.assertEqual(hosts[1].port, 8443)

    def test_parse_invalid_json_raises_error(self):
        """Test that invalid JSON raises ConfigurationError."""
        with self.assertRaises(ConfigurationError) as context:
            ConfigValidator.parse_hosts("invalid json")
        self.assertIn("Invalid JSON", str(context.exception))

    def test_parse_non_array_json_raises_error(self):
        """Test that non-array JSON raises ConfigurationError."""
        with self.assertRaises(ConfigurationError) as context:
            ConfigValidator.parse_hosts('{"not": "array"}')
        self.assertIn("must be a JSON array", str(context.exception))

    def test_parse_invalid_host_data_raises_error(self):
        """Test that invalid host data raises ConfigurationError."""
        with self.assertRaises(ConfigurationError) as context:
            ConfigValidator.parse_hosts('[{"invalid": "no address"}]')
        self.assertIn("Invalid host configuration", str(context.exception))

    def test_get_env_bool(self):
        """Test getting boolean values from environment."""
        with MockEnvironment({"TEST_BOOL": "true"}):
            self.assertTrue(ConfigValidator.get_env_bool("TEST_BOOL"))

        with MockEnvironment({"TEST_BOOL": "false"}):
            self.assertFalse(ConfigValidator.get_env_bool("TEST_BOOL"))

        self.assertFalse(ConfigValidator.get_env_bool("NONEXISTENT", False))

    def test_get_env_int(self):
        """Test getting integer values from environment."""
        with MockEnvironment({"TEST_INT": "42"}):
            self.assertEqual(ConfigValidator.get_env_int("TEST_INT", 0), 42)

        with MockEnvironment({"TEST_INT": "invalid"}):
            with self.assertRaises(ConfigurationError):
                ConfigValidator.get_env_int("TEST_INT", 0)

    def test_get_env_int_with_bounds(self):
        """Test getting integer values with bounds checking."""
        with MockEnvironment({"TEST_INT": "5"}):
            self.assertEqual(ConfigValidator.get_env_int("TEST_INT", 0, 1, 10), 5)

        with MockEnvironment({"TEST_INT": "0"}):
            with self.assertRaises(ConfigurationError):
                ConfigValidator.get_env_int("TEST_INT", 0, 1, 10)

    def test_load_config_success(self):
        """Test successful configuration loading."""
        env_vars = {
            "REDFISH_HOSTS": '[{"address": "test.example.com"}]',
            "REDFISH_PORT": "443",
            "REDFISH_AUTH_METHOD": "session",
            "MCP_TRANSPORT": "stdio",
            "MCP_REDFISH_LOG_LEVEL": "INFO",
        }

        with MockEnvironment(env_vars):
            redfish_config, mcp_config = ConfigValidator.load_config()

            self.assertEqual(len(redfish_config.hosts), 1)
            self.assertEqual(redfish_config.hosts[0].address, "test.example.com")
            self.assertEqual(redfish_config.port, 443)
            self.assertEqual(mcp_config.transport, "stdio")
            self.assertEqual(mcp_config.log_level, "INFO")

    def test_load_config_with_invalid_hosts(self):
        """Test configuration loading with invalid hosts."""
        env_vars = {
            "REDFISH_HOSTS": "invalid json",
        }

        with MockEnvironment(env_vars):
            with self.assertRaises(ConfigurationError):
                ConfigValidator.load_config()


if __name__ == "__main__":
    unittest.main()
