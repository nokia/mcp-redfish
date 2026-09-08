# Copyright 2025 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause

"""
Test utilities and helper functions for mcp-redfish test suite.
"""

import json
import os
from typing import Any
from unittest.mock import MagicMock


def create_mock_redfish_response(data: dict[str, Any], status: int = 200) -> MagicMock:
    """Create a mock Redfish response object."""
    mock_response = MagicMock()
    mock_response.status = status
    mock_response.dict = data
    return mock_response


def create_mock_redfish_client(response_data: dict[str, Any] = None) -> MagicMock:
    """Create a mock Redfish client with configurable response."""
    if response_data is None:
        response_data = {"mock": "data"}

    mock_client = MagicMock()
    mock_client.login.return_value = None
    mock_client.logout.return_value = None
    mock_client.cafile = None
    mock_client.get.return_value = create_mock_redfish_response(response_data)
    return mock_client


def extract_call_tool_result(result) -> Any:
    """
    Extract data from CallToolResult or return direct result.

    This helper handles the different ways MCP tools can return data
    depending on the test context and FastMCP version.
    """
    if hasattr(result, "structured_content") and result.structured_content is not None:
        return result.structured_content
    if hasattr(result, "data") and result.data is not None:
        return result.data
    if hasattr(result, "content") and result.content:
        return json.loads(result.content[0].text)
    if isinstance(result, list) and result and hasattr(result[0], "text"):
        return json.loads(result[0].text)
    # FastMCP 4 omits content for empty list results.
    if (
        hasattr(result, "content")
        and hasattr(result, "is_error")
        and not result.is_error
        and not result.content
    ):
        return []
    return result


def create_host_config(address: str, **kwargs) -> dict[str, str]:
    """Create a host configuration dictionary with optional parameters."""
    config = {"address": address}
    config.update(kwargs)
    return config


def create_multiple_hosts(
    addresses: list[str], **common_config
) -> list[dict[str, str]]:
    """Create multiple host configurations with common settings."""
    return [create_host_config(addr, **common_config) for addr in addresses]


def write_self_signed_tls_pair(
    directory: str, common_name: str = "127.0.0.1"
) -> tuple[str, str]:
    """Write a self-signed server certificate and key; return (cert_path, key_path)."""
    from datetime import UTC, datetime, timedelta
    from pathlib import Path

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    san: list[x509.GeneralName]
    try:
        import ipaddress

        san = [x509.IPAddress(ipaddress.ip_address(common_name))]
    except ValueError:
        san = [x509.DNSName(common_name)]

    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(UTC) - timedelta(minutes=1))
        .not_valid_after(datetime.now(UTC) + timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName(san), False)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), False)
        .sign(key, hashes.SHA256())
    )

    cert_path = Path(directory) / "server.crt"
    key_path = Path(directory) / "server.key"
    cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    return str(cert_path), str(key_path)


AUTH_ENV_KEYS = (
    "MCP_AUTH_MODE",
    "MCP_HTTP_AUTH",
    "MCP_ALLOW_REMOTE_SSE",
    "MCP_TLS_TERMINATED",
    "MCP_TLS_CERTFILE",
    "MCP_TLS_KEYFILE",
    "MCP_AUTH_TOKEN_TYPE",
    "MCP_AUTH_TOKEN_LEEWAY_SECONDS",
    "MCP_AUTH_REQUIRED_SCOPES",
    "MCP_AUTH_BASE_URL",
    "MCP_AUTH_JWT_JWKS_URI",
    "MCP_AUTH_JWT_ISSUER",
    "MCP_AUTH_JWT_AUDIENCE",
    "MCP_AUTH_JWT_ALGORITHM",
    "MCP_AUTH_JWT_PUBLIC_KEY",
    "MCP_AUTH_INTROSPECTION_URL",
    "MCP_AUTH_INTROSPECTION_CLIENT_ID",
    "MCP_AUTH_INTROSPECTION_CLIENT_SECRET",
    "MCP_AUTH_INTROSPECTION_AUTH_METHOD",
    "MCP_AUTH_INTROSPECTION_ISSUER",
    "MCP_AUTH_INTROSPECTION_AUDIENCE",
    "MCP_AUTH_INTROSPECTION_ALLOWED_TOKEN_TYPES",
    "MCP_AUTH_INTROSPECTION_ALLOW_PRIVATE",
    "MCP_AUTH_JWKS_ALLOW_PRIVATE",
    "MCP_AUTH_AUTHORIZATION_SERVERS",
    "MCP_AUTH_UPSTREAM_AUTHORIZATION_ENDPOINT",
    "MCP_AUTH_UPSTREAM_TOKEN_ENDPOINT",
    "MCP_AUTH_OIDC_CONFIG_URL",
    "MCP_AUTH_OIDC_AUDIENCE",
    "MCP_AUTH_CLIENT_ID",
    "MCP_AUTH_CLIENT_SECRET",
    "MCP_AUTH_JWT_SIGNING_KEY",
    "MCP_AUTH_STORAGE_ENCRYPTION_KEY",
    "MCP_AUTH_ALLOWED_CLIENT_REDIRECT_URIS",
    "MCP_AUTH_REQUIRE_CONSENT",
    "MCP_AUTH_FORWARD_PKCE",
    "MCP_AUTH_REDIRECT_PATH",
    "FASTMCP_HOST",
    "FASTMCP_PORT",
    "FASTMCP_SERVER_AUTH",
    "FASTMCP_HTTP_HOST_ORIGIN_PROTECTION",
    # FastMCP-native settings the validator now reads. A developer with any of
    # these exported would otherwise get different results than CI.
    "FASTMCP_SSRF_TRUST_PROXY",
    "FASTMCP_HTTP_ALLOWED_HOSTS",
    "FASTMCP_HTTP_ALLOWED_ORIGINS",
    "HTTPS_PROXY",
    "https_proxy",
    "ALL_PROXY",
    "all_proxy",
)


def clear_auth_env(environ: dict[str, str] | None = None) -> None:
    """Remove MCP auth/TLS/bind env vars from os.environ or a mapping."""
    target = os.environ if environ is None else environ
    for key in list(target):
        if (
            key in AUTH_ENV_KEYS
            or key.startswith("FASTMCP_SERVER_AUTH_")
            or key.startswith("MCP_AUTH_")
        ):
            target.pop(key, None)


class MockEnvironment:
    """Context manager for temporarily setting environment variables in tests."""

    def __init__(self, env_vars: dict[str, str]):
        self.env_vars = env_vars
        self.original_values = {}

    def __enter__(self):
        for key, value in self.env_vars.items():
            self.original_values[key] = os.environ.get(key)
            os.environ[key] = value
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        for key in self.env_vars:
            original_value = self.original_values[key]
            if original_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = original_value
