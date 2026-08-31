# Copyright 2025 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause

"""
Tests for legacy configuration fallback behavior.
"""

import importlib
import os
import sys
import unittest
from unittest.mock import patch

# Patch sys.path to import from src
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src"))
)

from src.common.validation import ConfigurationError

from test.utils import MockEnvironment


class TestConfigFallback(unittest.TestCase):
    def test_legacy_fallback_invalid_tls_verify_defaults_to_enabled(self):
        """Test invalid TLS verification values fail closed in legacy fallback."""
        env_vars = {
            "REDFISH_HOSTS": '[{"address": "test.example.com"}]',
            "REDFISH_TLS_VERIFY": "definitely-not-a-bool",
        }

        with MockEnvironment(env_vars):
            import src.common.config as config

            with patch(
                "src.common.config.load_validated_config",
                side_effect=ConfigurationError("forced fallback"),
            ):
                with self.assertWarns(DeprecationWarning):
                    reloaded_config = importlib.reload(config)

        self.assertTrue(reloaded_config.REDFISH_CFG["tls_verify"])


if __name__ == "__main__":
    unittest.main()
