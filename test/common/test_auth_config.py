# Copyright 2025 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause

"""Unit tests for MCP HTTP authentication configuration."""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import patch

import pytest
from fastmcp.server.auth.providers.introspection import IntrospectionTokenVerifier
from fastmcp.server.auth.providers.jwt import JWTVerifier, RSAKeyPair

from src.common.auth import (
    HOST_ORIGIN_PROTECTION_DISABLED_WARNING,
    HTTP_AUTH_DISABLED_WARNING,
    PRIVATE_INTROSPECTION_WARNING,
    REMOTE_SSE_WARNING,
    TLS_TERMINATED_CLEARTEXT_WARNING,
    build_auth_provider,
    emit_startup_logs,
    http_run_kwargs,
)
from src.common.auth_hardening import HardenedTokenVerifier
from src.common.validation import (
    AuthConfigurationError,
    ConfigValidator,
    effective_bind_host,
    is_http_transport,
    is_loopback_bind,
    load_mcp_auth_config,
    validate_auth_for_transport,
)

from test.utils import clear_auth_env, write_self_signed_tls_pair

JWT_ISSUER = "https://issuer.example"
JWT_AUDIENCE = "mcp-redfish"
INTROSPECTION_SECRET = "introspection-client-secret-value"
INTROSPECTION_ISSUER = "https://introspection-issuer.example"
INTROSPECTION_AUDIENCE = "mcp-redfish"
SIGNING_KEY = "abcdefghijklmnopqrstuvwxyz012345"
HMAC_SECRET = "hmac-secret-must-be-at-least-32ch"
CLIENT_SECRET = "oauth-client-secret-value-not-for-logs"


@pytest.fixture
def auth_env(monkeypatch: pytest.MonkeyPatch):
    """Isolate MCP auth environment variables for each test."""
    clear_auth_env()
    monkeypatch.setenv("MCP_TRANSPORT", "stdio")
    yield monkeypatch
    clear_auth_env()


@pytest.fixture
def rsa_public_key() -> str:
    return RSAKeyPair.generate().public_key


def _token_env(monkeypatch: pytest.MonkeyPatch, public_key: str) -> None:
    monkeypatch.setenv("MCP_AUTH_MODE", "token")
    monkeypatch.setenv("MCP_AUTH_TOKEN_TYPE", "jwt")
    monkeypatch.setenv("MCP_AUTH_JWT_ISSUER", JWT_ISSUER)
    monkeypatch.setenv("MCP_AUTH_JWT_AUDIENCE", JWT_AUDIENCE)
    monkeypatch.setenv("MCP_AUTH_JWT_PUBLIC_KEY", public_key)


def _introspection_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MCP_AUTH_MODE", "token")
    monkeypatch.setenv("MCP_AUTH_TOKEN_TYPE", "introspection")
    monkeypatch.setenv("MCP_AUTH_INTROSPECTION_URL", "https://idp.example/introspect")
    monkeypatch.setenv("MCP_AUTH_INTROSPECTION_CLIENT_ID", "client")
    monkeypatch.setenv("MCP_AUTH_INTROSPECTION_CLIENT_SECRET", INTROSPECTION_SECRET)
    monkeypatch.setenv("MCP_AUTH_INTROSPECTION_ISSUER", INTROSPECTION_ISSUER)
    monkeypatch.setenv("MCP_AUTH_INTROSPECTION_AUDIENCE", INTROSPECTION_AUDIENCE)


def _jwks_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MCP_AUTH_MODE", "token")
    monkeypatch.setenv("MCP_AUTH_TOKEN_TYPE", "jwt")
    monkeypatch.setenv("MCP_AUTH_JWT_ISSUER", JWT_ISSUER)
    monkeypatch.setenv("MCP_AUTH_JWT_AUDIENCE", JWT_AUDIENCE)
    monkeypatch.setenv("MCP_AUTH_JWT_JWKS_URI", "https://idp.example/jwks")


def test_stdio_mode_none_starts(auth_env: pytest.MonkeyPatch) -> None:
    auth = validate_auth_for_transport("stdio")
    assert auth.mode == "none"
    assert build_auth_provider(auth) is None


def test_stdio_ignores_mcp_http_auth(auth_env: pytest.MonkeyPatch) -> None:
    auth_env.setenv("MCP_HTTP_AUTH", "false")
    auth = validate_auth_for_transport("stdio")
    assert auth.http_auth is True
    assert build_auth_provider(auth) is None


def test_http_default_auth_mode_none_rejected(auth_env: pytest.MonkeyPatch) -> None:
    with pytest.raises(AuthConfigurationError, match="require authentication"):
        validate_auth_for_transport("streamable-http")
    with pytest.raises(AuthConfigurationError, match="require authentication"):
        validate_auth_for_transport("sse")
    auth_env.setenv("MCP_TRANSPORT", "streamable-http")
    with pytest.raises(AuthConfigurationError, match="require authentication"):
        ConfigValidator.load_config()


def test_only_stdio_escapes_the_http_auth_rules(
    auth_env: pytest.MonkeyPatch,
) -> None:
    """Any non-stdio transport inherits the HTTP fail-closed rules.

    FastMCP also accepts "http" as a transport name, so an allowlist of
    ("streamable-http", "sse") would let that value skip auth entirely.
    """
    assert not is_http_transport("stdio")
    for transport in ("http", "streamable-http", "sse", "unknown-future-transport"):
        assert is_http_transport(transport)
        with pytest.raises(AuthConfigurationError, match="require authentication"):
            validate_auth_for_transport(transport)


def test_non_loopback_tls_rule_applies_to_http_transport_name(
    auth_env: pytest.MonkeyPatch, rsa_public_key: str
) -> None:
    """The cleartext-Bearer refusal is not tied to the transport spelling."""
    _token_env(auth_env, rsa_public_key)
    auth_env.setenv("FASTMCP_HOST", "0.0.0.0")
    with pytest.raises(AuthConfigurationError, match="MCP_TLS_"):
        validate_auth_for_transport("http")


def test_http_auth_false_mode_none_accepted(auth_env: pytest.MonkeyPatch) -> None:
    auth_env.setenv("MCP_HTTP_AUTH", "false")
    auth = validate_auth_for_transport("streamable-http")
    assert auth.mode == "none"
    assert auth.http_auth is False


def test_http_auth_false_real_mode_rejected(
    auth_env: pytest.MonkeyPatch, rsa_public_key: str
) -> None:
    _token_env(auth_env, rsa_public_key)
    auth_env.setenv("MCP_HTTP_AUTH", "false")
    with pytest.raises(AuthConfigurationError, match="contradicts"):
        validate_auth_for_transport("streamable-http")


def test_http_auth_false_warning_text(
    auth_env: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    auth_env.setenv("MCP_HTTP_AUTH", "false")
    auth = validate_auth_for_transport("streamable-http")
    with caplog.at_level(logging.WARNING, logger="src.common.auth"):
        emit_startup_logs("streamable-http", auth, "127.0.0.1", 8000)
    expected = HTTP_AUTH_DISABLED_WARNING.format(host="127.0.0.1", port=8000)
    assert expected in caplog.text


def test_auth_plus_loopback_without_tls_accepted(
    auth_env: pytest.MonkeyPatch, rsa_public_key: str
) -> None:
    _token_env(auth_env, rsa_public_key)
    auth = validate_auth_for_transport("streamable-http", bind_host="127.0.0.1")
    assert auth.mode == "token"


@pytest.mark.parametrize("host", ["::1", "::ffff:127.0.0.1"])
def test_loopback_detection_ipv6(
    auth_env: pytest.MonkeyPatch, rsa_public_key: str, host: str
) -> None:
    assert is_loopback_bind(host)
    _token_env(auth_env, rsa_public_key)
    auth_env.setenv("FASTMCP_HOST", host)
    validate_auth_for_transport("streamable-http")


def test_bracketed_ipv6_loopback_is_normalized(
    auth_env: pytest.MonkeyPatch, rsa_public_key: str
) -> None:
    assert is_loopback_bind("[::1]")
    _token_env(auth_env, rsa_public_key)
    auth_env.setenv("FASTMCP_HOST", "[::1]")
    auth = validate_auth_for_transport("streamable-http")
    assert http_run_kwargs(auth)["host"] == "::1"


def test_localhost_is_not_loopback_for_tls_rule(
    auth_env: pytest.MonkeyPatch, rsa_public_key: str
) -> None:
    assert not is_loopback_bind("localhost")
    _token_env(auth_env, rsa_public_key)
    auth_env.setenv("FASTMCP_HOST", "localhost")
    with pytest.raises(AuthConfigurationError, match="MCP_TLS_"):
        validate_auth_for_transport("streamable-http")


def test_non_loopback_without_tls_or_flag_rejected(
    auth_env: pytest.MonkeyPatch, rsa_public_key: str
) -> None:
    _token_env(auth_env, rsa_public_key)
    auth_env.setenv("FASTMCP_HOST", "0.0.0.0")
    with pytest.raises(AuthConfigurationError, match="MCP_TLS_"):
        validate_auth_for_transport("streamable-http")


def test_non_loopback_tls_terminated_accepted(
    auth_env: pytest.MonkeyPatch,
    rsa_public_key: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _token_env(auth_env, rsa_public_key)
    auth_env.setenv("FASTMCP_HOST", "0.0.0.0")
    auth_env.setenv("MCP_TLS_TERMINATED", "true")
    auth_env.setenv("FASTMCP_HTTP_ALLOWED_HOSTS", '["mcp.example.com"]')
    auth = validate_auth_for_transport("streamable-http")
    with caplog.at_level(logging.WARNING, logger="src.common.auth"):
        emit_startup_logs("streamable-http", auth, "0.0.0.0", 8000)
    expected = TLS_TERMINATED_CLEARTEXT_WARNING.format(host="0.0.0.0", port=8000)
    assert expected in caplog.text


def test_non_loopback_cert_key_starts_without_proxy_warning(
    auth_env: pytest.MonkeyPatch,
    rsa_public_key: str,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    cert, key = write_self_signed_tls_pair(str(tmp_path))
    _token_env(auth_env, rsa_public_key)
    auth_env.setenv("FASTMCP_HOST", "0.0.0.0")
    auth_env.setenv("MCP_TLS_CERTFILE", cert)
    auth_env.setenv("MCP_TLS_KEYFILE", key)
    auth_env.setenv("FASTMCP_HTTP_ALLOWED_HOSTS", '["mcp.example.com"]')
    auth = validate_auth_for_transport("streamable-http")
    kwargs = http_run_kwargs(auth)
    assert kwargs["uvicorn_config"]["ssl_certfile"] == cert
    assert kwargs["uvicorn_config"]["ssl_keyfile"] == key
    with caplog.at_level(logging.WARNING, logger="src.common.auth"):
        emit_startup_logs("streamable-http", auth, "0.0.0.0", 8000)
    assert "MCP_TLS_TERMINATED=true" not in caplog.text


def test_only_one_of_cert_key_rejected(
    auth_env: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cert, _key = write_self_signed_tls_pair(str(tmp_path))
    auth_env.setenv("MCP_TLS_CERTFILE", cert)
    with pytest.raises(AuthConfigurationError, match="both be set"):
        load_mcp_auth_config()


def test_missing_tls_file_rejected(
    auth_env: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    missing_cert = str(tmp_path / "missing.crt")
    missing_key = str(tmp_path / "missing.key")
    auth_env.setenv("MCP_TLS_CERTFILE", missing_cert)
    auth_env.setenv("MCP_TLS_KEYFILE", missing_key)
    with pytest.raises(AuthConfigurationError, match="does not exist"):
        load_mcp_auth_config()


def test_unreadable_tls_file_rejected(
    auth_env: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cert, key = write_self_signed_tls_pair(str(tmp_path))
    auth_env.setenv("MCP_TLS_CERTFILE", cert)
    auth_env.setenv("MCP_TLS_KEYFILE", key)
    with (
        patch("src.common.validation.os.access", return_value=False),
        pytest.raises(AuthConfigurationError, match="not readable"),
    ):
        load_mcp_auth_config()


def test_tls_terminated_and_certs_allowed(
    auth_env: pytest.MonkeyPatch, rsa_public_key: str, tmp_path: Path
) -> None:
    cert, key = write_self_signed_tls_pair(str(tmp_path))
    _token_env(auth_env, rsa_public_key)
    auth_env.setenv("FASTMCP_HOST", "0.0.0.0")
    auth_env.setenv("MCP_TLS_TERMINATED", "true")
    auth_env.setenv("MCP_TLS_CERTFILE", cert)
    auth_env.setenv("MCP_TLS_KEYFILE", key)
    auth_env.setenv("FASTMCP_HTTP_ALLOWED_HOSTS", '["mcp.example.com"]')
    auth = validate_auth_for_transport("streamable-http")
    assert auth.has_in_process_tls()


def test_unset_fastmcp_host_is_loopback(auth_env: pytest.MonkeyPatch) -> None:
    auth_env.delenv("FASTMCP_HOST", raising=False)
    assert effective_bind_host() == "127.0.0.1"
    kwargs = http_run_kwargs(load_mcp_auth_config())
    assert kwargs["host"] == "127.0.0.1"


def test_empty_fastmcp_host_is_loopback(auth_env: pytest.MonkeyPatch) -> None:
    auth_env.setenv("FASTMCP_HOST", "")
    assert effective_bind_host() == "127.0.0.1"


def test_set_fastmcp_host_passthrough(
    auth_env: pytest.MonkeyPatch,
) -> None:
    auth_env.setenv("FASTMCP_HOST", "0.0.0.0")
    auth_env.setenv("MCP_HTTP_AUTH", "false")
    auth_env.setenv("FASTMCP_HTTP_ALLOWED_HOSTS", '["mcp.example.com"]')
    assert effective_bind_host() == "0.0.0.0"
    auth = validate_auth_for_transport("streamable-http")
    assert http_run_kwargs(auth)["host"] == "0.0.0.0"


def test_jwt_missing_issuer_rejected(
    auth_env: pytest.MonkeyPatch, rsa_public_key: str
) -> None:
    auth_env.setenv("MCP_AUTH_MODE", "token")
    auth_env.setenv("MCP_AUTH_JWT_AUDIENCE", JWT_AUDIENCE)
    auth_env.setenv("MCP_AUTH_JWT_PUBLIC_KEY", rsa_public_key)
    with pytest.raises(AuthConfigurationError, match="MCP_AUTH_JWT_ISSUER"):
        load_mcp_auth_config()


def test_jwt_missing_audience_rejected(
    auth_env: pytest.MonkeyPatch, rsa_public_key: str
) -> None:
    auth_env.setenv("MCP_AUTH_MODE", "token")
    auth_env.setenv("MCP_AUTH_JWT_ISSUER", JWT_ISSUER)
    auth_env.setenv("MCP_AUTH_JWT_PUBLIC_KEY", rsa_public_key)
    with pytest.raises(AuthConfigurationError, match="MCP_AUTH_JWT_AUDIENCE"):
        load_mcp_auth_config()


def test_jwt_algorithm_none_rejected(
    auth_env: pytest.MonkeyPatch, rsa_public_key: str
) -> None:
    _token_env(auth_env, rsa_public_key)
    auth_env.setenv("MCP_AUTH_JWT_ALGORITHM", "none")
    with pytest.raises(AuthConfigurationError, match="none is not allowed"):
        load_mcp_auth_config()


def test_http_jwks_url_rejected(auth_env: pytest.MonkeyPatch) -> None:
    auth_env.setenv("MCP_AUTH_MODE", "token")
    auth_env.setenv("MCP_AUTH_JWT_ISSUER", JWT_ISSUER)
    auth_env.setenv("MCP_AUTH_JWT_AUDIENCE", JWT_AUDIENCE)
    auth_env.setenv("MCP_AUTH_JWT_JWKS_URI", "http://idp.example/jwks")
    with pytest.raises(AuthConfigurationError, match="HTTPS"):
        load_mcp_auth_config()


def test_hmac_secret_too_short_rejected(auth_env: pytest.MonkeyPatch) -> None:
    auth_env.setenv("MCP_AUTH_MODE", "token")
    auth_env.setenv("MCP_AUTH_JWT_ISSUER", JWT_ISSUER)
    auth_env.setenv("MCP_AUTH_JWT_AUDIENCE", JWT_AUDIENCE)
    auth_env.setenv("MCP_AUTH_JWT_ALGORITHM", "HS256")
    auth_env.setenv("MCP_AUTH_JWT_PUBLIC_KEY", "short")
    with pytest.raises(AuthConfigurationError, match="at least 32"):
        load_mcp_auth_config()


def test_private_key_rejected_as_public_key(auth_env: pytest.MonkeyPatch) -> None:
    keypair = RSAKeyPair.generate()
    auth_env.setenv("MCP_AUTH_MODE", "token")
    auth_env.setenv("MCP_AUTH_JWT_ISSUER", JWT_ISSUER)
    auth_env.setenv("MCP_AUTH_JWT_AUDIENCE", JWT_AUDIENCE)
    auth_env.setenv("MCP_AUTH_JWT_PUBLIC_KEY", keypair.private_key.get_secret_value())
    with pytest.raises(AuthConfigurationError, match="private key"):
        load_mcp_auth_config()


def test_fastmcp_server_auth_rejected(auth_env: pytest.MonkeyPatch) -> None:
    auth_env.setenv("FASTMCP_SERVER_AUTH", "JWTVerifier")
    with pytest.raises(AuthConfigurationError, match="FASTMCP_SERVER_AUTH"):
        load_mcp_auth_config()


def test_fastmcp_server_auth_prefix_rejected(auth_env: pytest.MonkeyPatch) -> None:
    auth_env.setenv("FASTMCP_SERVER_AUTH_JWT_PUBLIC_KEY", "secret")
    with pytest.raises(AuthConfigurationError, match="FASTMCP_SERVER_AUTH"):
        load_mcp_auth_config()


def test_stdio_ignores_malformed_and_unimplemented_auth(
    auth_env: pytest.MonkeyPatch,
) -> None:
    auth_env.setenv("MCP_AUTH_MODE", "oauth_proxy")
    auth_env.setenv("MCP_HTTP_AUTH", "not-a-boolean")
    auth_env.setenv("FASTMCP_SERVER_AUTH", "JWTVerifier")
    assert validate_auth_for_transport("stdio").mode == "none"
    _redfish, mcp_config = ConfigValidator.load_config()
    assert mcp_config.transport == "stdio"
    assert mcp_config.auth is not None
    assert mcp_config.auth.mode == "none"


@pytest.mark.parametrize("proxy_var", ["HTTPS_PROXY", "https_proxy", "ALL_PROXY"])
def test_ssrf_trust_proxy_accepted_with_a_proxy(
    auth_env: pytest.MonkeyPatch, proxy_var: str
) -> None:
    """An enterprise proxy is the only route to the IdP in some networks."""
    _jwks_env(auth_env)
    auth_env.setenv("FASTMCP_SSRF_TRUST_PROXY", "true")
    auth_env.setenv(proxy_var, "http://corp-proxy.example:3128")
    assert load_mcp_auth_config().mode == "token"


def test_ssrf_trust_proxy_without_a_proxy_rejected(
    auth_env: pytest.MonkeyPatch,
) -> None:
    """FastMCP would refuse every fetch, but only at the first verification."""
    _jwks_env(auth_env)
    auth_env.setenv("FASTMCP_SSRF_TRUST_PROXY", "true")
    for name in ("HTTPS_PROXY", "https_proxy", "ALL_PROXY", "all_proxy"):
        auth_env.delenv(name, raising=False)
    with pytest.raises(AuthConfigurationError, match="neither HTTPS_PROXY"):
        load_mcp_auth_config()


def test_ssrf_trust_proxy_ignored_without_auth(auth_env: pytest.MonkeyPatch) -> None:
    """No verifier is built in mode=none, so no IdP fetch ever happens."""
    auth_env.setenv("FASTMCP_SSRF_TRUST_PROXY", "true")
    assert load_mcp_auth_config().mode == "none"


def test_ssrf_trust_proxy_warns_without_leaking_the_proxy_url(
    auth_env: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Proxy URLs carry credentials; the log must name the variable only."""
    _jwks_env(auth_env)
    auth_env.setenv("FASTMCP_SSRF_TRUST_PROXY", "true")
    auth_env.setenv("HTTPS_PROXY", "http://user:s3cret@corp-proxy.example:3128")
    auth = load_mcp_auth_config()
    with caplog.at_level(logging.WARNING, logger="src.common.auth"):
        emit_startup_logs("streamable-http", auth, "127.0.0.1", 8000)
    assert "FASTMCP_SSRF_TRUST_PROXY is enabled" in caplog.text
    assert "HTTPS_PROXY" in caplog.text
    assert "s3cret" not in caplog.text
    assert "corp-proxy.example" not in caplog.text


@pytest.mark.parametrize(
    "variable",
    ["FASTMCP_HTTP_ALLOWED_HOSTS", "FASTMCP_HTTP_ALLOWED_ORIGINS"],
)
def test_wildcard_host_origin_allowlist_rejected(
    auth_env: pytest.MonkeyPatch, variable: str
) -> None:
    """A wildcard would disable the DNS-rebinding guard on HTTP."""
    auth_env.setenv("MCP_HTTP_AUTH", "false")
    auth_env.setenv(variable, '["*"]')
    with pytest.raises(AuthConfigurationError, match=variable):
        validate_auth_for_transport("streamable-http")


@pytest.mark.parametrize(
    "variable",
    ["FASTMCP_HTTP_ALLOWED_HOSTS", "FASTMCP_HTTP_ALLOWED_ORIGINS"],
)
def test_explicit_host_origin_allowlist_accepted(
    auth_env: pytest.MonkeyPatch, variable: str
) -> None:
    auth_env.setenv("MCP_HTTP_AUTH", "false")
    auth_env.setenv(variable, '["mcp.example.com"]')
    assert validate_auth_for_transport("streamable-http").mode == "none"


def test_wildcard_allowlist_ignored_on_stdio(auth_env: pytest.MonkeyPatch) -> None:
    """stdio opens no listener, so the Host/Origin guard does not apply."""
    auth_env.setenv("FASTMCP_HTTP_ALLOWED_ORIGINS", '["*"]')
    assert validate_auth_for_transport("stdio").mode == "none"


def test_unparseable_fastmcp_setting_rejected(auth_env: pytest.MonkeyPatch) -> None:
    """FastMCP's own settings errors surface as configuration errors."""
    auth_env.setenv("MCP_HTTP_AUTH", "false")
    auth_env.setenv("FASTMCP_HTTP_ALLOWED_ORIGINS", "*")
    with pytest.raises(AuthConfigurationError, match="Invalid FASTMCP_"):
        validate_auth_for_transport("streamable-http")


def test_hs_algorithm_with_pem_key_reported_as_config_error(
    auth_env: pytest.MonkeyPatch, rsa_public_key: str
) -> None:
    """FastMCP rejects this pairing; it must read as config, not a traceback."""
    _token_env(auth_env, rsa_public_key)
    auth_env.setenv("MCP_AUTH_JWT_ALGORITHM", "HS256")
    with pytest.raises(AuthConfigurationError, match="rejected the MCP_AUTH_"):
        build_auth_provider(load_mcp_auth_config())


def test_http_introspection_url_rejected(auth_env: pytest.MonkeyPatch) -> None:
    auth_env.setenv("MCP_AUTH_MODE", "token")
    auth_env.setenv("MCP_AUTH_TOKEN_TYPE", "introspection")
    auth_env.setenv("MCP_AUTH_INTROSPECTION_URL", "http://idp.example/introspect")
    auth_env.setenv("MCP_AUTH_INTROSPECTION_CLIENT_ID", "client")
    auth_env.setenv("MCP_AUTH_INTROSPECTION_CLIENT_SECRET", INTROSPECTION_SECRET)
    with pytest.raises(AuthConfigurationError, match="HTTPS"):
        load_mcp_auth_config()


def test_jwt_provider_kwargs(auth_env: pytest.MonkeyPatch, rsa_public_key: str) -> None:
    _token_env(auth_env, rsa_public_key)
    provider = build_auth_provider(load_mcp_auth_config())
    assert isinstance(provider, HardenedTokenVerifier)
    assert isinstance(provider.inner, JWTVerifier)
    assert provider.inner.issuer == JWT_ISSUER
    assert provider.inner.audience == JWT_AUDIENCE


def test_jwks_provider_sets_ssrf_safe(auth_env: pytest.MonkeyPatch) -> None:
    auth_env.setenv("MCP_AUTH_MODE", "token")
    auth_env.setenv("MCP_AUTH_JWT_ISSUER", JWT_ISSUER)
    auth_env.setenv("MCP_AUTH_JWT_AUDIENCE", JWT_AUDIENCE)
    auth_env.setenv("MCP_AUTH_JWT_JWKS_URI", "https://idp.example/jwks")
    provider = build_auth_provider(load_mcp_auth_config())
    assert isinstance(provider, HardenedTokenVerifier)
    assert isinstance(provider.inner, JWTVerifier)
    assert provider.inner.jwks_uri == "https://idp.example/jwks"
    assert provider.inner.ssrf_safe is True


def test_introspection_provider(
    auth_env: pytest.MonkeyPatch,
) -> None:
    _introspection_env(auth_env)
    provider = build_auth_provider(load_mcp_auth_config())
    assert isinstance(provider, HardenedTokenVerifier)
    assert isinstance(provider.inner, IntrospectionTokenVerifier)
    assert provider.inner.introspection_url == "https://idp.example/introspect"
    assert provider.inner.client_id == "client"
    assert provider.inner.client_secret == INTROSPECTION_SECRET


def test_consent_false_off_loopback_rejected(
    auth_env: pytest.MonkeyPatch, rsa_public_key: str
) -> None:
    _token_env(auth_env, rsa_public_key)
    auth_env.setenv("MCP_AUTH_MODE", "oauth_proxy")
    auth_env.setenv(
        "MCP_AUTH_UPSTREAM_AUTHORIZATION_ENDPOINT",
        "https://idp.example/authorize",
    )
    auth_env.setenv("MCP_AUTH_UPSTREAM_TOKEN_ENDPOINT", "https://idp.example/token")
    auth_env.setenv("MCP_AUTH_CLIENT_ID", "client")
    auth_env.setenv("MCP_AUTH_CLIENT_SECRET", CLIENT_SECRET)
    auth_env.setenv("MCP_AUTH_JWT_SIGNING_KEY", SIGNING_KEY)
    auth_env.setenv("MCP_AUTH_BASE_URL", "https://mcp.example.com")
    auth_env.setenv("MCP_AUTH_REQUIRE_CONSENT", "false")
    auth_env.setenv("FASTMCP_HOST", "0.0.0.0")
    auth_env.setenv("MCP_TLS_TERMINATED", "true")
    auth_env.setenv("FASTMCP_HTTP_ALLOWED_HOSTS", '["mcp.example.com"]')
    with pytest.raises(AuthConfigurationError, match="not allowed off-loopback"):
        validate_auth_for_transport("streamable-http")


def test_proxy_signing_key_required_off_loopback(
    auth_env: pytest.MonkeyPatch, rsa_public_key: str
) -> None:
    _token_env(auth_env, rsa_public_key)
    auth_env.setenv("MCP_AUTH_MODE", "oauth_proxy")
    auth_env.setenv(
        "MCP_AUTH_UPSTREAM_AUTHORIZATION_ENDPOINT",
        "https://idp.example/authorize",
    )
    auth_env.setenv("MCP_AUTH_UPSTREAM_TOKEN_ENDPOINT", "https://idp.example/token")
    auth_env.setenv("MCP_AUTH_CLIENT_ID", "client")
    auth_env.setenv("MCP_AUTH_CLIENT_SECRET", CLIENT_SECRET)
    auth_env.setenv("MCP_AUTH_BASE_URL", "https://mcp.example.com")
    auth_env.setenv("FASTMCP_HOST", "0.0.0.0")
    auth_env.setenv("MCP_TLS_TERMINATED", "true")
    auth_env.setenv("FASTMCP_HTTP_ALLOWED_HOSTS", '["mcp.example.com"]')
    with pytest.raises(AuthConfigurationError, match="JWT_SIGNING_KEY"):
        validate_auth_for_transport("streamable-http")


def test_empty_redirect_uris_off_loopback_rejected(
    auth_env: pytest.MonkeyPatch, rsa_public_key: str
) -> None:
    _token_env(auth_env, rsa_public_key)
    auth_env.setenv("MCP_AUTH_MODE", "oauth_proxy")
    auth_env.setenv(
        "MCP_AUTH_UPSTREAM_AUTHORIZATION_ENDPOINT",
        "https://idp.example/authorize",
    )
    auth_env.setenv("MCP_AUTH_UPSTREAM_TOKEN_ENDPOINT", "https://idp.example/token")
    auth_env.setenv("MCP_AUTH_CLIENT_ID", "client")
    auth_env.setenv("MCP_AUTH_CLIENT_SECRET", CLIENT_SECRET)
    auth_env.setenv("MCP_AUTH_JWT_SIGNING_KEY", SIGNING_KEY)
    auth_env.setenv("MCP_AUTH_BASE_URL", "https://mcp.example.com")
    auth_env.setenv("MCP_AUTH_ALLOWED_CLIENT_REDIRECT_URIS", "[]")
    auth_env.setenv("FASTMCP_HOST", "0.0.0.0")
    auth_env.setenv("MCP_TLS_TERMINATED", "true")
    auth_env.setenv("FASTMCP_HTTP_ALLOWED_HOSTS", '["mcp.example.com"]')
    with pytest.raises(AuthConfigurationError, match="must not be empty"):
        validate_auth_for_transport("streamable-http")


def test_static_token_rejected(auth_env: pytest.MonkeyPatch) -> None:
    auth_env.setenv("MCP_AUTH_MODE", "static_token")
    with pytest.raises(AuthConfigurationError, match="static_token"):
        load_mcp_auth_config()


def test_remote_oauth_requires_authorization_servers(
    auth_env: pytest.MonkeyPatch, rsa_public_key: str
) -> None:
    _token_env(auth_env, rsa_public_key)
    auth_env.setenv("MCP_AUTH_MODE", "remote_oauth")
    auth_env.setenv("MCP_AUTH_BASE_URL", "https://mcp.example.com")
    with pytest.raises(AuthConfigurationError, match="AUTHORIZATION_SERVERS"):
        load_mcp_auth_config()


def test_debug_token_verifier_never_constructed() -> None:
    auth_source = Path("src/common/auth.py").read_text(encoding="utf-8")
    validation_source = Path("src/common/validation.py").read_text(encoding="utf-8")
    main_source = Path("src/main.py").read_text(encoding="utf-8")
    server_source = Path("src/common/server.py").read_text(encoding="utf-8")
    combined = auth_source + validation_source + main_source + server_source
    assert "DebugTokenVerifier" not in combined


def test_secrets_not_logged(
    auth_env: pytest.MonkeyPatch,
    rsa_public_key: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _token_env(auth_env, rsa_public_key)
    auth_env.setenv("MCP_AUTH_TOKEN_TYPE", "introspection")
    auth_env.setenv("MCP_AUTH_INTROSPECTION_URL", "https://idp.example/introspect")
    auth_env.setenv("MCP_AUTH_INTROSPECTION_CLIENT_ID", "client")
    auth_env.setenv("MCP_AUTH_INTROSPECTION_CLIENT_SECRET", INTROSPECTION_SECRET)
    auth_env.setenv("MCP_AUTH_INTROSPECTION_ISSUER", INTROSPECTION_ISSUER)
    auth_env.setenv("MCP_AUTH_INTROSPECTION_AUDIENCE", INTROSPECTION_AUDIENCE)
    auth_env.setenv("REDFISH_PASSWORD", "bmc-super-secret-password")
    with caplog.at_level(logging.DEBUG):
        auth = load_mcp_auth_config()
        build_auth_provider(auth)
        emit_startup_logs("streamable-http", auth, "127.0.0.1", 8000)
        ConfigValidator.load_config()
    assert INTROSPECTION_SECRET not in caplog.text
    assert "bmc-super-secret-password" not in caplog.text
    assert rsa_public_key not in caplog.text


def test_auth_error_aborts_config_load(
    auth_env: pytest.MonkeyPatch,
) -> None:
    auth_env.setenv("FASTMCP_SERVER_AUTH", "JWTVerifier")
    auth_env.setenv("MCP_TRANSPORT", "streamable-http")
    with pytest.raises(AuthConfigurationError):
        ConfigValidator.load_config()


def test_host_origin_protection_default(auth_env: pytest.MonkeyPatch) -> None:
    auth_env.setenv("MCP_HTTP_AUTH", "false")
    kwargs = http_run_kwargs(validate_auth_for_transport("streamable-http"))
    assert kwargs["host_origin_protection"] == "auto"
    assert "uvicorn_config" not in kwargs


def test_oauth_proxy_ignored_on_stdio(
    auth_env: pytest.MonkeyPatch, rsa_public_key: str
) -> None:
    _token_env(auth_env, rsa_public_key)
    auth_env.setenv("MCP_AUTH_MODE", "oauth_proxy")
    auth_env.setenv(
        "MCP_AUTH_UPSTREAM_AUTHORIZATION_ENDPOINT",
        "https://idp.example/authorize",
    )
    auth_env.setenv("MCP_AUTH_UPSTREAM_TOKEN_ENDPOINT", "https://idp.example/token")
    auth_env.setenv("MCP_AUTH_CLIENT_ID", "client")
    auth_env.setenv("MCP_AUTH_CLIENT_SECRET", CLIENT_SECRET)
    auth_env.setenv("MCP_AUTH_BASE_URL", "http://127.0.0.1:8000")
    assert validate_auth_for_transport("stdio").mode == "none"
    _redfish, mcp_config = ConfigValidator.load_config()
    assert mcp_config.auth is not None
    assert mcp_config.auth.mode == "none"


def test_jwt_algorithm_passed_through(
    auth_env: pytest.MonkeyPatch, rsa_public_key: str
) -> None:
    _token_env(auth_env, rsa_public_key)
    auth_env.setenv("MCP_AUTH_JWT_ALGORITHM", "RS384")
    provider = build_auth_provider(load_mcp_auth_config())
    assert isinstance(provider, HardenedTokenVerifier)
    assert isinstance(provider.inner, JWTVerifier)
    assert provider.inner.algorithm == "RS384"


@pytest.mark.parametrize(
    ("variable", "value"),
    [
        ("FASTMCP_HTTP_ALLOWED_HOSTS", '["*.*"]'),
        ("FASTMCP_HTTP_ALLOWED_HOSTS", '["?.example.com"]'),
        ("FASTMCP_HTTP_ALLOWED_ORIGINS", '["https://[abc].example.com"]'),
    ],
)
def test_host_origin_patterns_rejected(
    auth_env: pytest.MonkeyPatch, variable: str, value: str
) -> None:
    auth_env.setenv("MCP_HTTP_AUTH", "false")
    auth_env.setenv(variable, value)
    with pytest.raises(AuthConfigurationError, match="metacharacters"):
        validate_auth_for_transport("streamable-http")


def test_non_loopback_defaults_to_strict_and_requires_allowed_hosts(
    auth_env: pytest.MonkeyPatch,
) -> None:
    auth_env.setenv("MCP_HTTP_AUTH", "false")
    auth_env.setenv("FASTMCP_HOST", "0.0.0.0")
    with pytest.raises(AuthConfigurationError, match="ALLOWED_HOSTS"):
        validate_auth_for_transport("streamable-http")

    auth_env.setenv("FASTMCP_HTTP_ALLOWED_HOSTS", '["mcp.example.com"]')
    auth = validate_auth_for_transport("streamable-http")
    assert http_run_kwargs(auth)["host_origin_protection"] is True


def test_non_loopback_sse_requires_explicit_break_glass(
    auth_env: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    auth_env.setenv("MCP_HTTP_AUTH", "false")
    auth_env.setenv("FASTMCP_HOST", "0.0.0.0")
    with pytest.raises(AuthConfigurationError, match="MCP_ALLOW_REMOTE_SSE"):
        validate_auth_for_transport("sse")

    auth_env.setenv("MCP_ALLOW_REMOTE_SSE", "true")
    auth = validate_auth_for_transport("sse")
    with caplog.at_level(logging.WARNING, logger="src.common.auth"):
        emit_startup_logs("sse", auth, "0.0.0.0", 8000)
    assert REMOTE_SSE_WARNING.format(host="0.0.0.0", port=8000) in caplog.text


def test_loopback_sse_does_not_require_break_glass(
    auth_env: pytest.MonkeyPatch,
) -> None:
    auth_env.setenv("MCP_HTTP_AUTH", "false")
    assert validate_auth_for_transport("sse").mode == "none"


def test_explicitly_disabled_host_origin_protection_warns(
    auth_env: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    auth_env.setenv("MCP_HTTP_AUTH", "false")
    auth_env.setenv("FASTMCP_HOST", "0.0.0.0")
    auth_env.setenv("FASTMCP_HTTP_HOST_ORIGIN_PROTECTION", "false")
    auth = validate_auth_for_transport("streamable-http")
    with caplog.at_level(logging.WARNING, logger="src.common.auth"):
        emit_startup_logs("streamable-http", auth, "0.0.0.0", 8000)
    assert HOST_ORIGIN_PROTECTION_DISABLED_WARNING in caplog.text


def test_blank_boolean_uses_secure_default(auth_env: pytest.MonkeyPatch) -> None:
    auth_env.setenv("MCP_HTTP_AUTH", "  ")
    assert load_mcp_auth_config().http_auth is True


def test_whitespace_only_issuer_is_rejected(
    auth_env: pytest.MonkeyPatch, rsa_public_key: str
) -> None:
    _token_env(auth_env, rsa_public_key)
    auth_env.setenv("MCP_AUTH_JWT_ISSUER", "   ")
    with pytest.raises(AuthConfigurationError, match="JWT_ISSUER"):
        load_mcp_auth_config()


def test_static_key_jwt_ignores_unrelated_ssrf_proxy_setting(
    auth_env: pytest.MonkeyPatch, rsa_public_key: str
) -> None:
    _token_env(auth_env, rsa_public_key)
    auth_env.setenv("FASTMCP_SSRF_TRUST_PROXY", "true")
    for name in ("HTTPS_PROXY", "https_proxy", "ALL_PROXY", "all_proxy"):
        auth_env.delenv(name, raising=False)
    assert load_mcp_auth_config().mode == "token"


def test_introspection_requires_resource_binding(
    auth_env: pytest.MonkeyPatch,
) -> None:
    _introspection_env(auth_env)
    auth_env.delenv("MCP_AUTH_INTROSPECTION_AUDIENCE")
    with pytest.raises(AuthConfigurationError, match="INTROSPECTION_AUDIENCE"):
        load_mcp_auth_config()


def test_private_introspection_opt_in_warns(
    auth_env: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _introspection_env(auth_env)
    auth_env.setenv("MCP_AUTH_INTROSPECTION_ALLOW_PRIVATE", "true")
    auth = load_mcp_auth_config()
    with caplog.at_level(logging.WARNING, logger="src.common.auth"):
        emit_startup_logs("streamable-http", auth, "127.0.0.1", 8000)
    assert PRIVATE_INTROSPECTION_WARNING in caplog.text
    assert INTROSPECTION_SECRET not in caplog.text


def test_startup_summary_is_useful_without_logging_sensitive_values(
    auth_env: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _introspection_env(auth_env)
    auth_env.setenv("MCP_AUTH_REQUIRED_SCOPES", '["private:scope"]')
    auth_env.setenv("MCP_AUTH_INTROSPECTION_ALLOW_PRIVATE", "true")
    auth_env.setenv(
        "MCP_AUTH_BASE_URL", "https://private.example/?secret=never-log-this"
    )
    auth = load_mcp_auth_config()
    with caplog.at_level(logging.INFO, logger="src.common.auth"):
        emit_startup_logs("streamable-http", auth, "127.0.0.1", 8000)

    assert "token_backend=introspection" in caplog.text
    assert "verification_source=introspection" in caplog.text
    assert "idp_egress=private_trust" in caplog.text
    assert "tls_source=none" in caplog.text
    assert "host_origin_protection=auto" in caplog.text
    assert "required_scope_count=1" in caplog.text
    assert "private_introspection=True" in caplog.text
    assert INTROSPECTION_SECRET not in caplog.text
    assert INTROSPECTION_ISSUER not in caplog.text
    assert INTROSPECTION_AUDIENCE not in caplog.text
    assert "private:scope" not in caplog.text
    assert "never-log-this" not in caplog.text
