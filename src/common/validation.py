# Copyright 2025 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause

"""
Configuration validation module for MCP Redfish server.
Provides schema validation and error handling for environment variables.
"""

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Literal

from redfish.rest.v1 import AuthMethod

logger = logging.getLogger(__name__)

# Official MCP transport types as defined in FastMCP
MCPTransportType = Literal["stdio", "streamable-http", "sse"]
VALID_MCP_TRANSPORTS = ["stdio", "streamable-http", "sse"]


@dataclass
class HostConfig:
    """Configuration for a single Redfish host."""

    address: str
    port: int | None = None
    username: str | None = None
    password: str | None = None
    auth_method: str | None = None
    tls_server_ca_cert: str | None = None

    def __post_init__(self) -> None:
        """Validate host configuration after initialization."""
        if not self.address:
            raise ValueError("Host address cannot be empty")

        if self.port is not None and (self.port < 1 or self.port > 65535):
            raise ValueError(f"Port must be between 1 and 65535, got: {self.port}")

        if self.auth_method and self.auth_method not in (
            AuthMethod.BASIC,
            AuthMethod.SESSION,
        ):
            raise ValueError(
                f"Invalid auth_method: {self.auth_method}. Must be one of: {AuthMethod.BASIC}, {AuthMethod.SESSION}"
            )


@dataclass
class RedfishConfig:
    """Complete Redfish configuration."""

    hosts: list[HostConfig] = field(default_factory=list)
    port: int = 443
    auth_method: str = AuthMethod.SESSION
    username: str = ""
    password: str = ""
    tls_server_ca_cert: str | None = None
    discovery_enabled: bool = False
    discovery_interval: int = 30

    def __post_init__(self) -> None:
        """Validate Redfish configuration after initialization."""
        if self.port < 1 or self.port > 65535:
            raise ValueError(f"Port must be between 1 and 65535, got: {self.port}")

        if self.auth_method not in (AuthMethod.BASIC, AuthMethod.SESSION):
            raise ValueError(
                f"Invalid auth_method: {self.auth_method}. Must be one of: {AuthMethod.BASIC}, {AuthMethod.SESSION}"
            )

        if self.discovery_interval < 1:
            raise ValueError(
                f"Discovery interval must be positive, got: {self.discovery_interval}"
            )

        if not self.hosts:
            logger.warning("No Redfish hosts configured")


@dataclass
class MCPConfig:
    """MCP server configuration."""

    transport: MCPTransportType = "stdio"
    log_level: str = "INFO"

    def __post_init__(self) -> None:
        """Validate MCP configuration after initialization."""
        if self.transport not in VALID_MCP_TRANSPORTS:
            raise ValueError(
                f"Invalid transport: {self.transport}. Must be one of: {VALID_MCP_TRANSPORTS}"
            )

        valid_log_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if self.log_level.upper() not in valid_log_levels:
            raise ValueError(
                f"Invalid log_level: {self.log_level}. Must be one of: {valid_log_levels}"
            )

        self.log_level = self.log_level.upper()


class ConfigurationError(Exception):
    """Raised when configuration validation fails."""

    pass


class ConfigValidator:
    """Validates and loads configuration from environment variables."""

    @staticmethod
    def parse_hosts(hosts_json: str) -> list[HostConfig]:
        """Parse and validate hosts from JSON string."""
        try:
            hosts_data = json.loads(hosts_json)
        except json.JSONDecodeError as e:
            raise ConfigurationError(f"Invalid JSON in REDFISH_HOSTS: {e}") from e

        if not isinstance(hosts_data, list):
            raise ConfigurationError("REDFISH_HOSTS must be a JSON array")

        hosts = []
        for i, host_data in enumerate(hosts_data):
            if not isinstance(host_data, dict):
                raise ConfigurationError(f"Host {i} must be a JSON object")

            try:
                host = HostConfig(**host_data)
                hosts.append(host)
            except (TypeError, ValueError) as e:
                raise ConfigurationError(
                    f"Invalid host configuration at index {i}: {e}"
                ) from e

        return hosts

    @staticmethod
    def get_env_bool(key: str, default: bool = False) -> bool:
        """Get boolean value from environment variable."""
        value = os.getenv(key, str(default)).lower()
        return value in ("true", "1", "yes", "on")

    @staticmethod
    def get_env_int(
        key: str, default: int, min_val: int | None = None, max_val: int | None = None
    ) -> int:
        """Get integer value from environment variable with optional bounds checking."""
        try:
            value = int(os.getenv(key, str(default)))
        except ValueError:
            raise ConfigurationError(
                f"Environment variable {key} must be an integer"
            ) from None

        if min_val is not None and value < min_val:
            raise ConfigurationError(
                f"Environment variable {key} must be >= {min_val}, got: {value}"
            )

        if max_val is not None and value > max_val:
            raise ConfigurationError(
                f"Environment variable {key} must be <= {max_val}, got: {value}"
            )

        return value

    @classmethod
    def load_config(cls) -> tuple[RedfishConfig, MCPConfig]:
        """Load and validate complete configuration from environment variables."""
        try:
            # Parse hosts
            hosts_json = os.getenv("REDFISH_HOSTS", '[{"address": "127.0.0.1"}]')
            hosts = cls.parse_hosts(hosts_json)

            # Build Redfish configuration
            redfish_config = RedfishConfig(
                hosts=hosts,
                port=cls.get_env_int("REDFISH_PORT", 443, 1, 65535),
                auth_method=os.getenv("REDFISH_AUTH_METHOD", AuthMethod.SESSION),
                username=os.getenv("REDFISH_USERNAME", ""),
                password=os.getenv("REDFISH_PASSWORD", ""),
                tls_server_ca_cert=os.getenv("REDFISH_SERVER_CA_CERT"),
                discovery_enabled=cls.get_env_bool("REDFISH_DISCOVERY_ENABLED", False),
                discovery_interval=cls.get_env_int("REDFISH_DISCOVERY_INTERVAL", 30, 1),
            )

            # Build MCP configuration
            transport_str = os.getenv("MCP_TRANSPORT", "stdio")
            if transport_str not in VALID_MCP_TRANSPORTS:
                raise ConfigurationError(
                    f"Invalid transport: {transport_str}. Must be one of: {VALID_MCP_TRANSPORTS}"
                )
            mcp_config = MCPConfig(
                transport=transport_str,  # type: ignore[arg-type]
                log_level=os.getenv("MCP_REDFISH_LOG_LEVEL", "INFO"),
            )

            logger.info(
                f"Configuration loaded successfully: {len(redfish_config.hosts)} hosts, transport: {mcp_config.transport}"
            )
            return redfish_config, mcp_config

        except Exception as e:
            if isinstance(e, ConfigurationError):
                raise
            else:
                raise ConfigurationError(f"Failed to load configuration: {e}") from e


def load_validated_config() -> tuple[RedfishConfig, MCPConfig]:
    """Load and validate configuration, with user-friendly error messages."""
    try:
        return ConfigValidator.load_config()
    except ConfigurationError as e:
        logger.error(f"Configuration error: {e}")
        logger.error("Please check your environment variables and .env file")
        raise
    except Exception as e:
        logger.error(f"Unexpected error loading configuration: {e}")
        raise ConfigurationError(
            "Failed to load configuration due to unexpected error"
        ) from e
