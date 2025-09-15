# Copyright 2025 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause

"""
Property-based testing using Hypothesis to find edge cases in validation logic.

These tests use randomized inputs to discover corner cases that manual tests might miss.
"""

import os
import sys
import unittest
from unittest.mock import patch

# Patch sys.path to import from src
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src"))
)

try:
    from hypothesis import HealthCheck, assume, given, settings
    from hypothesis import strategies as st

    hypothesis_available = True
except ImportError:
    hypothesis_available = False

    # Create dummy decorators if hypothesis is not available
    def given(*args, **kwargs):
        def decorator(func):
            return func

        return decorator

    def settings(*args, **kwargs):
        def decorator(func):
            return func

        return decorator

    class st:
        @staticmethod
        def text():
            return lambda: "test"

        @staticmethod
        def integers():
            return lambda: 42

        @staticmethod
        def dictionaries(keys, values):
            return lambda: {}


from src.common.validation import ConfigValidator


@unittest.skipUnless(hypothesis_available, "Hypothesis library not available")
class TestPropertyBasedValidation(unittest.TestCase):
    """Property-based tests for validation logic."""

    def setUp(self):
        """Set up test fixtures."""
        self.validator = ConfigValidator()

    @given(st.text())
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_host_address_validation_fuzzing(self, address):
        """Test host address validation with random string inputs."""
        # Skip obviously invalid cases that we expect to fail
        assume(len(address) < 1000)  # Avoid extremely long strings
        assume(address != "")  # Empty string is a known invalid case

        host_config = {
            "address": address,
            "port": 443,
            "username": "user",
            "password": "pass",
        }

        try:
            from src.common.validation import HostConfig

            result = HostConfig(**host_config)
            # If validation passes, address should be normalized/validated
            self.assertIsInstance(result, HostConfig)
            self.assertEqual(result.address, address)
        except (ValueError, TypeError):
            # Validation should fail gracefully with proper exceptions
            pass
        except Exception as e:
            # Should not raise unexpected exceptions
            self.fail(f"Unexpected exception for address '{address}': {e}")

    @given(st.integers())
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_port_validation_fuzzing(self, port):
        """Test port validation with random integer inputs."""
        host_config = {
            "address": "valid-host.example.com",
            "port": port,
            "username": "user",
            "password": "pass",
        }

        try:
            from src.common.validation import HostConfig

            result = HostConfig(**host_config)
            # If validation passes, port should be in valid range
            self.assertIsInstance(result.port, int)
            self.assertGreaterEqual(result.port, 1)
            self.assertLessEqual(result.port, 65535)
        except (ValueError, TypeError):
            # Invalid ports should be rejected gracefully
            pass
        except Exception as e:
            self.fail(f"Unexpected exception for port {port}: {e}")

    @given(st.text(), st.text())
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_credentials_validation_fuzzing(self, username, password):
        """Test credential validation with random string inputs."""
        # Skip extremely long credentials to focus on edge cases
        assume(len(username) < 1000)
        assume(len(password) < 1000)

        host_config = {
            "address": "valid-host.example.com",
            "port": 443,
            "username": username,
            "password": password,
        }

        try:
            from src.common.validation import HostConfig

            result = HostConfig(**host_config)
            # If validation passes, credentials should be preserved
            self.assertEqual(result.username, username)
            self.assertEqual(result.password, password)
        except (ValueError, TypeError):
            # Some credential combinations might be invalid
            pass
        except Exception as e:
            self.fail(
                f"Unexpected exception for username='{username}', password='{password}': {e}"
            )

    @given(st.dictionaries(st.text(), st.text()))
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_host_config_structure_fuzzing(self, config_dict):
        """Test host configuration validation with random dictionary structures."""
        # Skip extremely large dictionaries
        assume(len(config_dict) < 50)

        try:
            from src.common.validation import HostConfig

            result = HostConfig(**config_dict)
            # If validation passes, should return a valid config
            self.assertIsInstance(result, HostConfig)
            self.assertTrue(hasattr(result, "address"))
        except (ValueError, TypeError, KeyError):
            # Many random dictionaries will be invalid
            pass
        except Exception as e:
            self.fail(f"Unexpected exception for config {config_dict}: {e}")

    # Note: JSON parsing and timeout validation edge cases are thoroughly tested
    # in the regular validation test suite (test/common/test_validation.py)
    # These property-based tests focus on randomized input testing

    @given(st.text())
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_log_level_validation_fuzzing(self, log_level):
        """Test log level validation with random inputs."""
        assume(len(log_level) < 100)
        # Skip strings with null bytes that would break environment variables
        assume("\x00" not in log_level)

        with patch.dict(os.environ, {"MCP_REDFISH_LOG_LEVEL": log_level}):
            try:
                # Create a config that includes log level validation
                from src.common.validation import MCPConfig

                mcp_config = MCPConfig(transport="stdio", log_level=log_level.upper())

                # If validation passes, log level should be valid
                valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
                self.assertIn(mcp_config.log_level, valid_levels)
            except (ValueError, TypeError):
                # Invalid log levels should be rejected
                pass
            except Exception as e:
                self.fail(f"Unexpected exception for log level '{log_level}': {e}")

    @given(st.lists(st.dictionaries(st.text(), st.text()), min_size=0, max_size=10))
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_hosts_list_validation_fuzzing(self, hosts_list):
        """Test hosts list validation with random list structures."""
        # Limit dictionary size to avoid memory issues
        for host_dict in hosts_list:
            assume(len(host_dict) < 20)
            for key, value in host_dict.items():
                assume(len(key) < 100)
                assume(len(value) < 1000)

        try:
            # Test each host in the list
            from src.common.validation import HostConfig

            for host_config in hosts_list:
                try:
                    HostConfig(**host_config)
                except (ValueError, TypeError, KeyError):
                    # Individual hosts can fail validation
                    pass
        except Exception as e:
            self.fail(f"Unexpected exception validating hosts list: {e}")

    @given(st.text(min_size=1, max_size=1000))
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_url_parsing_edge_cases(self, url_string):
        """Test URL parsing with random string inputs."""
        # This tests URL parsing logic that might be used in tools
        import urllib.parse

        try:
            parsed = urllib.parse.urlparse(url_string)
            # URL parsing should never crash, even with invalid URLs
            self.assertIsInstance(parsed.scheme, str)
            self.assertIsInstance(parsed.netloc, str)
            self.assertIsInstance(parsed.path, str)
        except Exception as e:
            self.fail(f"URL parsing failed for '{url_string}': {e}")

    @given(st.text(), st.text())
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_environment_variable_handling(self, var_name, var_value):
        """Test environment variable handling with random inputs."""
        # Limit length to avoid memory issues
        assume(len(var_name) < 100)
        assume(len(var_value) < 1000)

        # Skip empty variable names and names with invalid characters
        assume(var_name != "")
        assume(not any(c in var_name for c in ["\x00", "="]))
        assume(not any(c in var_value for c in ["\x00"]))

        # Test environment variable processing
        with patch.dict(os.environ, {var_name: var_value}, clear=False):
            try:
                # Test different type conversions
                str_result = os.getenv(var_name, "default")
                self.assertIsInstance(str_result, str)

                # Boolean conversion should handle various inputs gracefully
                bool_result = self.validator.get_env_bool(var_name, default=False)
                self.assertIsInstance(bool_result, bool)

            except Exception as e:
                # Environment variable processing should be robust
                self.fail(
                    f"Environment variable processing failed for {var_name}={var_value}: {e}"
                )


@unittest.skipUnless(hypothesis_available, "Hypothesis library not available")
class TestPropertyBasedRetryLogic(unittest.TestCase):
    """Property-based tests for retry logic edge cases."""

    @given(
        st.integers(min_value=0, max_value=10),
        st.floats(min_value=0.01, max_value=10.0),
        st.floats(min_value=1.0, max_value=20.0),
    )
    @settings(
        suppress_health_check=[
            HealthCheck.function_scoped_fixture,
            HealthCheck.filter_too_much,
        ]
    )
    def test_retry_configuration_edge_cases(
        self, max_retries, initial_delay, max_delay
    ):
        """Test retry configuration with random valid inputs."""
        from src.common.client import get_retry_configuration

        # Skip invalid combinations more efficiently
        assume(initial_delay <= max_delay)

        with patch.dict(
            os.environ,
            {
                "REDFISH_MAX_RETRIES": str(max_retries),
                "REDFISH_INITIAL_DELAY": str(initial_delay),
                "REDFISH_MAX_DELAY": str(max_delay),
                "REDFISH_BACKOFF_FACTOR": "2.0",
                "REDFISH_JITTER": "false",
            },
        ):
            try:
                config = get_retry_configuration()

                # Configuration should always be valid
                self.assertIn("stop", config)
                self.assertIn("wait", config)
                self.assertIn("retry", config)

                # Should be able to create a working retry decorator
                from tenacity import retry

                @retry(**config)
                def test_function():
                    return "success"

                result = test_function()
                self.assertEqual(result, "success")

            except Exception as e:
                self.fail(
                    f"Retry configuration failed with max_retries={max_retries}, "
                    f"initial_delay={initial_delay}, max_delay={max_delay}: {e}"
                )


if __name__ == "__main__":
    if not hypothesis_available:
        print(
            "Warning: Hypothesis library not available. Property-based tests will be skipped."
        )
    unittest.main()
