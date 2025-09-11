# Copyright 2025 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause

"""
Configuration loader for MCP Redfish client.
Loads settings from environment variables with validation.
"""

import json
import logging
import os
import warnings
from typing import Any

from dotenv import load_dotenv

from .validation import (
    ConfigurationError,
    MCPConfig,
    RedfishConfig,
    load_validated_config,
)

logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Load and validate configuration
try:
    REDFISH_CONFIG: RedfishConfig
    MCP_CONFIG: MCPConfig
    REDFISH_CONFIG, MCP_CONFIG = load_validated_config()

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
            }
            for host in REDFISH_CONFIG.hosts
        ],
        "port": REDFISH_CONFIG.port,
        "auth_method": REDFISH_CONFIG.auth_method,
        "username": REDFISH_CONFIG.username,
        "password": REDFISH_CONFIG.password,
        "tls_server_ca_cert": REDFISH_CONFIG.tls_server_ca_cert,
    }

    # Legacy compatibility - maintain the old MCP_TRANSPORT variable
    MCP_TRANSPORT = MCP_CONFIG.transport

    logger.info("Configuration validated and loaded successfully")

except ConfigurationError as e:
    logger.error(f"Configuration validation failed: {e}")

    # Issue deprecation warning
    warnings.warn(
        "Falling back to legacy configuration parsing. This behavior is deprecated and will be removed in a future version. "
        "Please ensure your environment variables are properly formatted and all required values are provided. "
        "See the documentation for the expected configuration format.",
        DeprecationWarning,
        stacklevel=2,
    )
    logger.warning(
        "DEPRECATION WARNING: Using legacy configuration parsing. Please update your configuration to use the new validated format."
    )

    logger.info("Falling back to legacy configuration loading...")

    # Parse hosts as JSON, handle errors gracefully
    hosts_env = os.getenv("REDFISH_HOSTS", '[{"address": "127.0.0.1"}]')
    hosts: list[dict[str, Any]]
    try:
        hosts = json.loads(hosts_env)
        if not isinstance(hosts, list):
            raise ValueError("REDFISH_HOSTS must be a JSON list")
    except Exception as e:
        logger.error(f"Failed to parse REDFISH_HOSTS: {e}")
        hosts = [{"address": "127.0.0.1"}]

    # Reassign variables for legacy fallback
    MCP_TRANSPORT = os.getenv("MCP_TRANSPORT", "stdio")  # type: ignore[assignment]
    REDFISH_CFG = {
        "hosts": hosts,
        "port": int(os.getenv("REDFISH_PORT", 443)),
        "auth_method": os.getenv("REDFISH_AUTH_METHOD", "session"),
        "username": os.getenv("REDFISH_USERNAME", ""),
        "password": os.getenv("REDFISH_PASSWORD", ""),
        "tls_server_ca_cert": os.getenv("REDFISH_SERVER_CA_CERT", None),
    }

    # Reset config objects for compatibility
    REDFISH_CONFIG = None  # type: ignore[assignment]
    MCP_CONFIG = None  # type: ignore[assignment]
