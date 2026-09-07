# Copyright 2025 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause

"""Unit tests for Remote OAuth, OAuth Proxy, and OIDC Proxy construction."""

from __future__ import annotations

import logging
import types
from unittest.mock import MagicMock, patch

import pytest
from cryptography.fernet import Fernet
from fastmcp.server.auth import OAuthProxy, RemoteAuthProvider
from fastmcp.server.auth.oidc_proxy import OIDCConfiguration
from fastmcp.server.auth.providers.jwt import JWTVerifier, RSAKeyPair
from key_value.aio.stores.memory import MemoryStore
from key_value.aio.wrappers.encryption import FernetEncryptionWrapper

from src.common.auth import (
    PRIVATE_JWKS_WARNING,
    SsrfSafeOIDCProxy,
    _build_client_storage,
    build_auth_provider,
    emit_startup_logs,
)
from src.common.auth_hardening import HardenedTokenVerifier
from src.common.validation import (
    DEFAULT_ALLOWED_CLIENT_REDIRECT_URIS,
    AuthConfigurationError,
    load_mcp_auth_config,
    validate_auth_for_transport,
)

from test.utils import clear_auth_env

JWT_ISSUER = "https://issuer.example"
JWT_AUDIENCE = "mcp-redfish"
SIGNING_KEY = "abcdefghijklmnopqrstuvwxyz012345"
CLIENT_SECRET = "oauth-client-secret-value-not-for-logs"
BASE_URL = "http://127.0.0.1:8000"


@pytest.fixture
def auth_env(monkeypatch: pytest.MonkeyPatch):
    clear_auth_env()
    monkeypatch.setenv("MCP_TRANSPORT", "stdio")
    yield monkeypatch
    clear_auth_env()


@pytest.fixture
def rsa_public_key() -> str:
    return RSAKeyPair.generate().public_key


def _jwt_env(monkeypatch: pytest.MonkeyPatch, public_key: str) -> None:
    monkeypatch.setenv("MCP_AUTH_TOKEN_TYPE", "jwt")
    monkeypatch.setenv("MCP_AUTH_JWT_ISSUER", JWT_ISSUER)
    monkeypatch.setenv("MCP_AUTH_JWT_AUDIENCE", JWT_AUDIENCE)
    monkeypatch.setenv("MCP_AUTH_JWT_PUBLIC_KEY", public_key)


def _remote_oauth_env(monkeypatch: pytest.MonkeyPatch, public_key: str) -> None:
    _jwt_env(monkeypatch, public_key)
    monkeypatch.setenv("MCP_AUTH_MODE", "remote_oauth")
    monkeypatch.setenv(
        "MCP_AUTH_AUTHORIZATION_SERVERS",
        '["https://idp.example"]',
    )
    monkeypatch.setenv("MCP_AUTH_BASE_URL", BASE_URL)


def _oauth_proxy_env(monkeypatch: pytest.MonkeyPatch, public_key: str) -> None:
    _jwt_env(monkeypatch, public_key)
    monkeypatch.setenv("MCP_AUTH_MODE", "oauth_proxy")
    monkeypatch.setenv(
        "MCP_AUTH_UPSTREAM_AUTHORIZATION_ENDPOINT",
        "https://idp.example/authorize",
    )
    monkeypatch.setenv("MCP_AUTH_UPSTREAM_TOKEN_ENDPOINT", "https://idp.example/token")
    monkeypatch.setenv("MCP_AUTH_CLIENT_ID", "client")
    monkeypatch.setenv("MCP_AUTH_CLIENT_SECRET", CLIENT_SECRET)
    monkeypatch.setenv("MCP_AUTH_BASE_URL", BASE_URL)


def _oidc_proxy_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MCP_AUTH_MODE", "oidc_proxy")
    monkeypatch.setenv(
        "MCP_AUTH_OIDC_CONFIG_URL",
        "https://idp.example/.well-known/openid-configuration",
    )
    monkeypatch.setenv("MCP_AUTH_CLIENT_ID", "client")
    monkeypatch.setenv("MCP_AUTH_CLIENT_SECRET", CLIENT_SECRET)
    monkeypatch.setenv("MCP_AUTH_BASE_URL", BASE_URL)
    monkeypatch.setenv("MCP_AUTH_OIDC_AUDIENCE", JWT_AUDIENCE)


def _fake_oidc_config() -> OIDCConfiguration:
    return OIDCConfiguration.model_validate(
        {
            "strict": False,
            "issuer": "https://idp.example",
            "authorization_endpoint": "https://idp.example/authorize",
            "token_endpoint": "https://idp.example/token",
            "jwks_uri": "https://idp.example/jwks",
        }
    )


def test_remote_oauth_provider_wraps_hardened_jwt(
    auth_env: pytest.MonkeyPatch, rsa_public_key: str
) -> None:
    _remote_oauth_env(auth_env, rsa_public_key)
    provider = build_auth_provider(load_mcp_auth_config())
    assert isinstance(provider, RemoteAuthProvider)
    assert isinstance(provider.token_verifier, HardenedTokenVerifier)
    assert isinstance(provider.token_verifier.inner, JWTVerifier)
    assert provider.token_verifier.inner.issuer == JWT_ISSUER
    assert provider.token_verifier.inner.audience == JWT_AUDIENCE
    assert str(provider.authorization_servers[0]).rstrip("/") == "https://idp.example"


def test_remote_oauth_http_jwks_rejected(
    auth_env: pytest.MonkeyPatch,
) -> None:
    auth_env.setenv("MCP_AUTH_MODE", "remote_oauth")
    auth_env.setenv("MCP_AUTH_JWT_ISSUER", JWT_ISSUER)
    auth_env.setenv("MCP_AUTH_JWT_AUDIENCE", JWT_AUDIENCE)
    auth_env.setenv("MCP_AUTH_JWT_JWKS_URI", "http://idp.example/jwks")
    auth_env.setenv("MCP_AUTH_AUTHORIZATION_SERVERS", '["https://idp.example"]')
    auth_env.setenv("MCP_AUTH_BASE_URL", BASE_URL)
    with pytest.raises(AuthConfigurationError, match="HTTPS"):
        load_mcp_auth_config()


def test_oauth_proxy_defaults_consent_pkce_and_redirects(
    auth_env: pytest.MonkeyPatch, rsa_public_key: str
) -> None:
    _oauth_proxy_env(auth_env, rsa_public_key)
    auth = load_mcp_auth_config()
    assert auth.require_consent == "true"
    assert auth.forward_pkce is True
    assert auth.allowed_client_redirect_uris == list(
        DEFAULT_ALLOWED_CLIENT_REDIRECT_URIS
    )
    with patch("src.common.auth.OAuthProxy", autospec=True) as proxy_cls:
        proxy_cls.return_value = MagicMock(spec=OAuthProxy)
        build_auth_provider(auth)
    kwargs = proxy_cls.call_args.kwargs
    assert kwargs["require_authorization_consent"] is True
    assert kwargs["forward_pkce"] is True
    assert kwargs["allowed_client_redirect_uris"] == list(
        DEFAULT_ALLOWED_CLIENT_REDIRECT_URIS
    )
    assert isinstance(kwargs["token_verifier"], HardenedTokenVerifier)
    assert "valid_scopes" not in kwargs


def test_oauth_proxy_required_scopes_are_dcr_not_jwt_claims(
    auth_env: pytest.MonkeyPatch, rsa_public_key: str
) -> None:
    _oauth_proxy_env(auth_env, rsa_public_key)
    auth_env.setenv("MCP_AUTH_REQUIRED_SCOPES", '["openid"]')
    with patch("src.common.auth.OAuthProxy", autospec=True) as proxy_cls:
        proxy_cls.return_value = MagicMock(spec=OAuthProxy)
        build_auth_provider(load_mcp_auth_config())
    kwargs = proxy_cls.call_args.kwargs
    assert kwargs["valid_scopes"] == ["openid"]
    assert kwargs["token_verifier"].required_scopes == []


def test_oauth_proxy_constructs_with_test_storage(
    auth_env: pytest.MonkeyPatch, rsa_public_key: str
) -> None:
    _oauth_proxy_env(auth_env, rsa_public_key)
    with patch("src.common.auth._build_client_storage", return_value=MemoryStore()):
        provider = build_auth_provider(load_mcp_auth_config())
    assert isinstance(provider, OAuthProxy)
    assert provider._require_authorization_consent is True
    assert provider._forward_pkce is True


def test_oidc_proxy_uses_discovery_and_ssrf_safe_jwks(
    auth_env: pytest.MonkeyPatch,
) -> None:
    _oidc_proxy_env(auth_env)
    with (
        patch.object(
            SsrfSafeOIDCProxy,
            "get_oidc_configuration",
            return_value=_fake_oidc_config(),
        ),
        patch("src.common.auth._build_client_storage", return_value=MemoryStore()),
    ):
        provider = build_auth_provider(load_mcp_auth_config())
    assert isinstance(provider, SsrfSafeOIDCProxy)
    assert provider._require_authorization_consent is True
    assert isinstance(provider._token_validator, HardenedTokenVerifier)
    assert isinstance(provider._token_validator.inner, JWTVerifier)
    assert provider._token_validator.inner.ssrf_safe is True
    assert provider._token_validator.inner.jwks_uri == "https://idp.example/jwks"
    assert provider._token_validator.inner.audience == JWT_AUDIENCE


def test_oidc_proxy_jwks_allow_private_disables_ssrf(
    auth_env: pytest.MonkeyPatch,
) -> None:
    _oidc_proxy_env(auth_env)
    auth_env.setenv("MCP_AUTH_JWKS_ALLOW_PRIVATE", "true")
    with (
        patch.object(
            SsrfSafeOIDCProxy,
            "get_oidc_configuration",
            return_value=_fake_oidc_config(),
        ),
        patch("src.common.auth._build_client_storage", return_value=MemoryStore()),
    ):
        provider = build_auth_provider(load_mcp_auth_config())
    assert isinstance(provider, SsrfSafeOIDCProxy)
    assert provider.jwks_allow_private is True
    assert provider._token_validator.inner.ssrf_safe is False


def test_oidc_jwks_allow_private_warns(
    auth_env: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _oidc_proxy_env(auth_env)
    auth_env.setenv("MCP_AUTH_JWKS_ALLOW_PRIVATE", "true")
    auth = load_mcp_auth_config()
    with caplog.at_level(logging.WARNING, logger="src.common.auth"):
        emit_startup_logs("streamable-http", auth, "127.0.0.1", 8000)
    assert PRIVATE_JWKS_WARNING in caplog.text
    assert CLIENT_SECRET not in caplog.text


def test_oidc_proxy_constructor_kwargs(
    auth_env: pytest.MonkeyPatch,
) -> None:
    _oidc_proxy_env(auth_env)
    auth_env.setenv("MCP_AUTH_OIDC_VERIFY_ID_TOKEN", "true")
    auth = load_mcp_auth_config()
    with patch("src.common.auth.SsrfSafeOIDCProxy", autospec=True) as proxy_cls:
        proxy_cls.return_value = MagicMock(spec=SsrfSafeOIDCProxy)
        build_auth_provider(auth)
    kwargs = proxy_cls.call_args.kwargs
    assert kwargs["require_authorization_consent"] is True
    assert kwargs["verify_id_token"] is True
    assert kwargs["config_url"].startswith("https://")
    assert kwargs["audience"] == JWT_AUDIENCE
    assert kwargs["jwks_allow_private"] is False
    assert "forward_pkce" not in kwargs


def test_oidc_http_discovery_url_rejected(auth_env: pytest.MonkeyPatch) -> None:
    _oidc_proxy_env(auth_env)
    auth_env.setenv(
        "MCP_AUTH_OIDC_CONFIG_URL",
        "http://idp.example/.well-known/openid-configuration",
    )
    with pytest.raises(AuthConfigurationError, match="HTTPS"):
        load_mcp_auth_config()


def test_oidc_forward_pkce_false_rejected(auth_env: pytest.MonkeyPatch) -> None:
    _oidc_proxy_env(auth_env)
    auth_env.setenv("MCP_AUTH_FORWARD_PKCE", "false")
    with pytest.raises(AuthConfigurationError, match="FORWARD_PKCE"):
        validate_auth_for_transport("streamable-http")


def test_unsafe_redirect_uri_rejected(
    auth_env: pytest.MonkeyPatch, rsa_public_key: str
) -> None:
    _oauth_proxy_env(auth_env, rsa_public_key)
    auth_env.setenv(
        "MCP_AUTH_ALLOWED_CLIENT_REDIRECT_URIS",
        '["javascript:alert(1)"]',
    )
    with pytest.raises(AuthConfigurationError, match="unsafe URI scheme"):
        load_mcp_auth_config()


def test_redis_storage_requires_fernet_key(
    auth_env: pytest.MonkeyPatch, rsa_public_key: str
) -> None:
    _oauth_proxy_env(auth_env, rsa_public_key)
    auth_env.setenv("MCP_AUTH_STORAGE_BACKEND", "redis")
    auth_env.setenv("MCP_AUTH_REDIS_URL", "redis://127.0.0.1:6379/0")
    with pytest.raises(AuthConfigurationError, match="STORAGE_ENCRYPTION_KEY"):
        load_mcp_auth_config()


def test_redis_storage_wraps_store_in_fernet(
    auth_env: pytest.MonkeyPatch, rsa_public_key: str
) -> None:
    _oauth_proxy_env(auth_env, rsa_public_key)
    key = Fernet.generate_key().decode()
    auth_env.setenv("MCP_AUTH_STORAGE_BACKEND", "redis")
    auth_env.setenv("MCP_AUTH_REDIS_URL", "rediss://redis.example:6379/0")
    auth_env.setenv("MCP_AUTH_STORAGE_ENCRYPTION_KEY", key)
    auth = load_mcp_auth_config()
    fake_mod = types.ModuleType("key_value.aio.stores.redis")

    class _Store(MemoryStore):
        def __init__(self, *, url: str) -> None:
            super().__init__()
            self.url = url

    fake_mod.RedisStore = _Store  # type: ignore[attr-defined]
    with patch.dict("sys.modules", {"key_value.aio.stores.redis": fake_mod}):
        wrapped = _build_client_storage(auth)
    assert isinstance(wrapped, FernetEncryptionWrapper)
    assert wrapped.key_value.url == "rediss://redis.example:6379/0"


def test_storage_backend_rejected_for_token_mode(
    auth_env: pytest.MonkeyPatch, rsa_public_key: str
) -> None:
    _jwt_env(auth_env, rsa_public_key)
    auth_env.setenv("MCP_AUTH_MODE", "token")
    auth_env.setenv("MCP_AUTH_STORAGE_BACKEND", "redis")
    with pytest.raises(AuthConfigurationError, match="only valid for"):
        load_mcp_auth_config()


def test_loopback_http_base_url_accepted(
    auth_env: pytest.MonkeyPatch, rsa_public_key: str
) -> None:
    _remote_oauth_env(auth_env, rsa_public_key)
    auth_env.setenv("MCP_AUTH_BASE_URL", "http://127.0.0.1:8000")
    assert load_mcp_auth_config().base_url == "http://127.0.0.1:8000"


def test_non_loopback_http_base_url_rejected(
    auth_env: pytest.MonkeyPatch, rsa_public_key: str
) -> None:
    _remote_oauth_env(auth_env, rsa_public_key)
    auth_env.setenv("MCP_AUTH_BASE_URL", "http://mcp.example.com")
    with pytest.raises(AuthConfigurationError, match="loopback"):
        load_mcp_auth_config()


def test_oidc_audience_required_when_verifying_access_tokens(
    auth_env: pytest.MonkeyPatch,
) -> None:
    _oidc_proxy_env(auth_env)
    auth_env.delenv("MCP_AUTH_OIDC_AUDIENCE", raising=False)
    with pytest.raises(AuthConfigurationError, match="OIDC_AUDIENCE"):
        load_mcp_auth_config()


def test_oidc_audience_optional_when_verifying_id_token(
    auth_env: pytest.MonkeyPatch,
) -> None:
    _oidc_proxy_env(auth_env)
    auth_env.delenv("MCP_AUTH_OIDC_AUDIENCE", raising=False)
    auth_env.setenv("MCP_AUTH_OIDC_VERIFY_ID_TOKEN", "true")
    auth = load_mcp_auth_config()
    assert auth.oidc_audience is None
    assert auth.oidc_verify_id_token is True


def test_oidc_algorithm_none_rejected(auth_env: pytest.MonkeyPatch) -> None:
    _oidc_proxy_env(auth_env)
    auth_env.setenv("MCP_AUTH_JWT_ALGORITHM", "none")
    with pytest.raises(AuthConfigurationError, match="none is not allowed"):
        load_mcp_auth_config()


def test_oauth_proxy_http_upstream_urls_rejected(
    auth_env: pytest.MonkeyPatch, rsa_public_key: str
) -> None:
    _oauth_proxy_env(auth_env, rsa_public_key)
    auth_env.setenv(
        "MCP_AUTH_UPSTREAM_AUTHORIZATION_ENDPOINT", "http://idp.example/authorize"
    )
    with pytest.raises(AuthConfigurationError, match="HTTPS"):
        load_mcp_auth_config()

    auth_env.setenv(
        "MCP_AUTH_UPSTREAM_AUTHORIZATION_ENDPOINT", "https://idp.example/authorize"
    )
    auth_env.setenv("MCP_AUTH_UPSTREAM_TOKEN_ENDPOINT", "http://idp.example/token")
    with pytest.raises(AuthConfigurationError, match="HTTPS"):
        load_mcp_auth_config()


def test_unrestricted_redirect_host_rejected(
    auth_env: pytest.MonkeyPatch, rsa_public_key: str
) -> None:
    _oauth_proxy_env(auth_env, rsa_public_key)
    auth_env.setenv("MCP_AUTH_ALLOWED_CLIENT_REDIRECT_URIS", '["https://*"]')
    with pytest.raises(AuthConfigurationError, match="unrestricted host pattern"):
        load_mcp_auth_config()


def test_proxy_secrets_not_logged(
    auth_env: pytest.MonkeyPatch,
    rsa_public_key: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _oauth_proxy_env(auth_env, rsa_public_key)
    signing_key = SIGNING_KEY
    redis_secret = "redis-password-not-for-logs"
    encryption_key = Fernet.generate_key().decode()
    auth_env.setenv("MCP_AUTH_JWT_SIGNING_KEY", signing_key)
    auth_env.setenv("MCP_AUTH_STORAGE_BACKEND", "redis")
    auth_env.setenv(
        "MCP_AUTH_REDIS_URL", f"rediss://user:{redis_secret}@redis.example:6379/0"
    )
    auth_env.setenv("MCP_AUTH_STORAGE_ENCRYPTION_KEY", encryption_key)
    auth_env.setenv("REDFISH_PASSWORD", "bmc-super-secret-password")
    with caplog.at_level(logging.DEBUG):
        auth = load_mcp_auth_config()
        with (
            patch("src.common.auth.OAuthProxy", autospec=True) as proxy_cls,
            patch("src.common.auth._build_client_storage", return_value=MemoryStore()),
        ):
            proxy_cls.return_value = MagicMock(spec=OAuthProxy)
            build_auth_provider(auth)
        emit_startup_logs("streamable-http", auth, "127.0.0.1", 8000)
    assert CLIENT_SECRET not in caplog.text
    assert signing_key not in caplog.text
    assert redis_secret not in caplog.text
    assert encryption_key not in caplog.text
    assert "bmc-super-secret-password" not in caplog.text


def test_oidc_startup_summary_names_discovery_without_secrets(
    auth_env: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _oidc_proxy_env(auth_env)
    auth_env.setenv(
        "MCP_AUTH_BASE_URL", "https://mcp.example.com:8443/path?secret=never-log-this"
    )
    auth = load_mcp_auth_config()
    with caplog.at_level(logging.INFO, logger="src.common.auth"):
        emit_startup_logs("streamable-http", auth, "127.0.0.1", 8000)
    assert "token_backend=oidc" in caplog.text
    assert "verification_source=oidc_discovery" in caplog.text
    assert "consent=true" in caplog.text
    assert "storage=disk" in caplog.text
    assert "redirect_path=/auth/callback" in caplog.text
    assert "public_origin=https://mcp.example.com:8443" in caplog.text
    assert "never-log-this" not in caplog.text
    assert CLIENT_SECRET not in caplog.text
    assert JWT_AUDIENCE not in caplog.text
