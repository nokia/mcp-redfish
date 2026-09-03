# Copyright 2025 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause

"""
Configuration loader for MCP Redfish client.
Loads settings from environment variables with validation.
"""

import logging
from typing import Any

from dotenv import load_dotenv

from .validation import (
    ConfigurationError,
    MCPConfig,
    RedfishConfig,
    fatal_configuration_error,
    load_validated_config,
)

logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Load and validate configuration.
#
# There is no fallback parser. A configuration this module cannot validate
# aborts the process instead of starting with guessed values: a server that
# silently substitutes defaults for a rejected transport, host list, or auth
# setting is indistinguishable from a correctly configured one.
REDFISH_CONFIG: RedfishConfig
MCP_CONFIG: MCPConfig
try:
    REDFISH_CONFIG, MCP_CONFIG = load_validated_config()
except ConfigurationError as error:
    raise fatal_configuration_error(error) from None

# Legacy compatibility - maintain the old REDFISH_CFG format
REDFISH_CFG: dict[str, Any] = {
    "hosts": [
        {
            "address": host.address,
            "port": host.port,
            "username": host.username,
            "password": host.password,
            "auth_method": host.auth_method,
            "tls_server_ca_cert": host.tls_server_ca_cert,
            "tls_verify": host.tls_verify,
        }
        for host in REDFISH_CONFIG.hosts
    ],
    "port": REDFISH_CONFIG.port,
    "auth_method": REDFISH_CONFIG.auth_method,
    "username": REDFISH_CONFIG.username,
    "password": REDFISH_CONFIG.password,
    "tls_server_ca_cert": REDFISH_CONFIG.tls_server_ca_cert,
    "tls_verify": REDFISH_CONFIG.tls_verify,
}

# Legacy compatibility - maintain the old MCP_TRANSPORT variable
MCP_TRANSPORT = MCP_CONFIG.transport

logger.info("Configuration validated and loaded successfully")
