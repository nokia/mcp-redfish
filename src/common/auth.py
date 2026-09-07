# Copyright 2025 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause

"""
MCP HTTP authentication providers.

Maps MCP_AUTH_MODE to FastMCP AuthProvider classes. No hand-rolled JWT
parsing or custom OAuth callback routes.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import Any
from urllib.parse import urlparse

from fastmcp.server.auth import (
    AuthProvider,
    OAuthProxy,
    RemoteAuthProvider,
    TokenVerifier,
)
from fastmcp.server.auth.oidc_proxy import OIDCProxy
from fastmcp.server.auth.providers.introspection import IntrospectionTokenVerifier
from fastmcp.server.auth.providers.jwt import JWTVerifier

from .auth_hardening import (
    HardenedTokenVerifier,
    SsrfSafeIntrospectionClient,
    TokenHardeningPolicy,
    configure_safe_provider_logging,
)
from .validation import (
    AuthConfigurationError,
    MCPAuthConfig,
    configured_proxy_env_var,
    effective_bind_host,
    effective_bind_port,
    effective_fastmcp_settings,
    host_origin_protection_for_run,
    is_loopback_bind,
    listen_scheme,
    warn_if_world_readable_key,
)

logger = logging.getLogger(__name__)
configure_safe_provider_logging()

HTTP_AUTH_DISABLED_WARNING = (
    "MCP HTTP authentication is disabled (MCP_HTTP_AUTH=false). "
    "Any client that can reach this MCP Server can call MCP tools using the "
    "configured Redfish credentials. Listening on FASTMCP_HOST={host} port {port}."
)

TLS_TERMINATED_CLEARTEXT_WARNING = (
    "MCP HTTP authentication is enabled but this MCP Server is listening in "
    "cleartext on FASTMCP_HOST={host} port {port} (MCP_TLS_TERMINATED=true). "
    "Bearer tokens are confidential only if a reverse proxy or mesh terminates "
    "TLS in front of this MCP Server."
)

HOST_ORIGIN_PROTECTION_DISABLED_WARNING = (
    "FastMCP HTTP Host/Origin protection is disabled "
    "(FASTMCP_HTTP_HOST_ORIGIN_PROTECTION=false). Browser and DNS-rebinding "
    "requests are not filtered; enable protection outside isolated testing."
)

PRIVATE_INTROSPECTION_WARNING = (
    "MCP_AUTH_INTROSPECTION_ALLOW_PRIVATE=true: introspection egress trusts "
    "private/internal DNS and routing. The Bearer token and introspection client "
    "credentials are sent to the configured HTTPS endpoint."
)

PRIVATE_JWKS_WARNING = (
    "MCP_AUTH_JWKS_ALLOW_PRIVATE=true: JWKS fetches trust private/internal DNS "
    "and routing, including loopback. Use this only for a private identity "
    "provider or local e2e."
)

REMOTE_SSE_WARNING = (
    "MCP_ALLOW_REMOTE_SSE=true: SSE is listening on non-loopback "
    "FASTMCP_HOST={host} port {port}. SSE has no Host/Origin protection. "
    "Prefer streamable-http for remote access."
)


def build_auth_provider(auth: MCPAuthConfig) -> AuthProvider | None:
    """Construct a FastMCP AuthProvider for the validated config, or None."""
    if auth.mode == "none":
        return None
    if auth.mode == "token":
        return _build_token_verifier(auth)
    if auth.mode == "remote_oauth":
        return _build_remote_oauth(auth)
    if auth.mode == "oauth_proxy":
        return _build_oauth_proxy(auth)
    if auth.mode == "oidc_proxy":
        return _build_oidc_proxy(auth)
    raise AuthConfigurationError(f"Unsupported MCP_AUTH_MODE: {auth.mode}")


def _build_token_verifier(auth: MCPAuthConfig) -> AuthProvider:
    # Bandit B105 reads "token_type" as a credential name; this is a verifier
    # name from MCP_AUTH_TOKEN_TYPE, not a secret. The inline suppression is
    # deliberately limited to the comparison below.
    if auth.token_type == "introspection":  # nosec B105
        inner = _construct(
            IntrospectionTokenVerifier,
            introspection_url=auth.introspection_url or "",
            client_id=auth.introspection_client_id or "",
            client_secret=auth.introspection_client_secret or "",
            client_auth_method=auth.introspection_auth_method,
            required_scopes=auth.required_scopes,
            http_client=SsrfSafeIntrospectionClient(
                allow_private=auth.introspection_allow_private
            ),
        )
        return HardenedTokenVerifier(
            inner,
            TokenHardeningPolicy(
                mode="introspection",
                expected_issuer=auth.introspection_issuer,
                expected_audience=auth.introspection_audience,
                allowed_token_types=tuple(auth.introspection_allowed_token_types),
            ),
        )

    kwargs: dict[str, Any] = {
        "issuer": auth.jwt_issuer,
        "audience": auth.jwt_audience,
        "required_scopes": auth.required_scopes,
    }
    if auth.jwt_algorithm:
        kwargs["algorithm"] = auth.jwt_algorithm
    if auth.jwt_jwks_uri:
        kwargs["jwks_uri"] = auth.jwt_jwks_uri
        kwargs["ssrf_safe"] = not auth.jwks_allow_private
    else:
        kwargs["public_key"] = auth.jwt_public_key
    inner = _construct(JWTVerifier, **kwargs)
    return HardenedTokenVerifier(
        inner,
        TokenHardeningPolicy(
            mode="jwt",
            leeway_seconds=auth.token_leeway_seconds,
        ),
    )


def _build_remote_oauth(auth: MCPAuthConfig) -> AuthProvider:
    return _construct(
        RemoteAuthProvider,
        token_verifier=_build_token_verifier(auth),
        authorization_servers=list(auth.authorization_servers or ()),
        base_url=auth.base_url or "",
        scopes_supported=auth.required_scopes,
    )


def _proxy_common_kwargs(auth: MCPAuthConfig) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "base_url": auth.base_url or "",
        "redirect_path": auth.redirect_path,
        "allowed_client_redirect_uris": auth.allowed_client_redirect_uris,
        "require_authorization_consent": auth.consent_for_fastmcp(),
    }
    if auth.jwt_signing_key:
        kwargs["jwt_signing_key"] = auth.jwt_signing_key
    storage = _build_client_storage(auth)
    if storage is not None:
        kwargs["client_storage"] = storage
    return kwargs


def _build_oauth_proxy(auth: MCPAuthConfig) -> AuthProvider:
    kwargs = _proxy_common_kwargs(auth)
    kwargs.update(
        {
            "upstream_authorization_endpoint": (
                auth.upstream_authorization_endpoint or ""
            ),
            "upstream_token_endpoint": auth.upstream_token_endpoint or "",
            "upstream_client_id": auth.client_id or "",
            "upstream_client_secret": auth.client_secret,
            # Advertise MCP_AUTH_REQUIRED_SCOPES to MCP clients (DCR). Upstream
            # access tokens may omit those names as JWT/introspection claims
            # (OIDC openid is an authorize scope, not necessarily a token claim).
            "token_verifier": _build_token_verifier(
                replace(auth, required_scopes=None)
            ),
            "forward_pkce": auth.forward_pkce,
        }
    )
    if auth.required_scopes:
        kwargs["valid_scopes"] = auth.required_scopes
    return _construct(OAuthProxy, **kwargs)


def _build_oidc_proxy(auth: MCPAuthConfig) -> AuthProvider:
    kwargs = _proxy_common_kwargs(auth)
    kwargs.update(
        {
            "config_url": auth.oidc_config_url or "",
            "client_id": auth.client_id or "",
            "client_secret": auth.client_secret,
            "verify_id_token": auth.oidc_verify_id_token,
            "token_leeway_seconds": auth.token_leeway_seconds,
            "jwks_allow_private": auth.jwks_allow_private,
        }
    )
    if auth.oidc_audience:
        kwargs["audience"] = auth.oidc_audience
    if auth.jwt_algorithm:
        kwargs["algorithm"] = auth.jwt_algorithm
    if auth.required_scopes:
        kwargs["required_scopes"] = auth.required_scopes
    return _construct(SsrfSafeOIDCProxy, **kwargs)


def _build_client_storage(auth: MCPAuthConfig) -> Any | None:
    """Return FastMCP client storage, or None for the default encrypted disk store."""
    if not auth.is_proxy_mode() or auth.storage_backend != "redis":
        return None
    try:
        from cryptography.fernet import Fernet
        from key_value.aio.stores.redis import RedisStore
        from key_value.aio.wrappers.encryption import FernetEncryptionWrapper
    except ImportError as e:
        raise AuthConfigurationError(
            "MCP_AUTH_STORAGE_BACKEND=redis requires the redis extra "
            "(py-key-value-aio[redis]). Install it or use the default encrypted "
            "disk store."
        ) from e
    return FernetEncryptionWrapper(
        key_value=RedisStore(url=auth.redis_url or ""),
        fernet=Fernet((auth.storage_encryption_key or "").encode()),
    )


class SsrfSafeOIDCProxy(OIDCProxy):
    """OIDCProxy that verifies JWKS with FastMCP SSRF protection."""

    def __init__(
        self,
        *,
        token_leeway_seconds: int = 60,
        jwks_allow_private: bool = False,
        **kwargs: Any,
    ) -> None:
        self.token_leeway_seconds = token_leeway_seconds
        self.jwks_allow_private = jwks_allow_private
        required_scopes = kwargs.get("required_scopes")
        verify_id_token = kwargs.get("verify_id_token", False)
        super().__init__(**kwargs)
        if required_scopes and not verify_id_token:
            # FastMCP only restores advertised scopes for verify_id_token=true.
            # Access-token verification still needs DCR/authorize scopes while
            # upstream JWT scope claims are validated separately (see
            # get_token_verifier).
            self.required_scopes = list(required_scopes)
            self.update_default_scopes(list(required_scopes))

    def _uses_alternate_verification(self) -> bool:
        """Always patch scopes from the upstream token response.

        Dex (and many IdPs) omit authorize scopes such as ``openid`` from JWT
        access-token claims. FastMCP only performs that patch when verifying an
        ID token; enable it for access-token verification too.
        """
        return True

    def get_token_verifier(
        self,
        *,
        algorithm: str | None = None,
        audience: str | None = None,
        required_scopes: list[str] | None = None,
        timeout_seconds: int | None = None,
    ) -> TokenVerifier:
        jwks_uri = getattr(self.oidc_config, "jwks_uri", None)
        issuer = getattr(self.oidc_config, "issuer", None)
        if not jwks_uri or not issuer:
            raise AuthConfigurationError(
                "OIDC discovery did not include jwks_uri and issuer. "
                "Use an identity provider that publishes JWKS, or MCP_AUTH_MODE=token "
                "with introspection."
            )
        if algorithm is not None and algorithm.strip().lower() == "none":
            raise AuthConfigurationError("MCP_AUTH_JWT_ALGORITHM none is not allowed")
        verifier_kwargs: dict[str, Any] = {
            "jwks_uri": str(jwks_uri),
            "issuer": str(issuer),
            "audience": audience,
            # MCP_AUTH_REQUIRED_SCOPES is for DCR/authorize, not upstream JWT
            # claims (OIDC openid is an authorize scope, not always on access tokens).
            "required_scopes": None,
            "ssrf_safe": not self.jwks_allow_private,
        }
        if algorithm:
            verifier_kwargs["algorithm"] = algorithm
        inner = _construct(JWTVerifier, **verifier_kwargs)
        return HardenedTokenVerifier(
            inner,
            TokenHardeningPolicy(
                mode="jwt",
                leeway_seconds=self.token_leeway_seconds,
            ),
        )


def _construct(verifier: Any, **kwargs: Any) -> AuthProvider:
    """Build a FastMCP verifier, reporting its own rejections as config errors.

    FastMCP validates combinations we cannot check ourselves (an HS* algorithm
    paired with a PEM public key, for example) and raises ValueError. That is a
    configuration mistake, so it must abort with a readable message rather than
    a traceback from provider construction.
    """
    try:
        return verifier(**kwargs)  # type: ignore[no-any-return]
    except AuthConfigurationError:
        raise
    except ValueError as e:
        raise AuthConfigurationError(
            f"{verifier.__name__} rejected the MCP_AUTH_* configuration "
            f"(error_type={type(e).__name__}). "
            "Check the selected algorithm, key format, and required fields."
        ) from e
    except Exception as e:
        raise AuthConfigurationError(
            f"{verifier.__name__} rejected the MCP_AUTH_* configuration "
            f"(error_type={type(e).__name__}). "
            "Check identity-provider URLs, credentials, and required fields."
        ) from e


def http_run_kwargs(auth: MCPAuthConfig) -> dict[str, Any]:
    """Kwargs passed to mcp.run() for HTTP transports."""
    host = effective_bind_host()
    kwargs: dict[str, Any] = {
        "host": host,
        "port": effective_bind_port(),
        "host_origin_protection": host_origin_protection_for_run(host),
    }
    if auth.has_in_process_tls():
        kwargs["uvicorn_config"] = {
            "ssl_certfile": auth.tls_certfile,
            "ssl_keyfile": auth.tls_keyfile,
        }
    return kwargs


def apply_provider(mcp: Any, auth: MCPAuthConfig) -> None:
    """Set FastMCP.auth from the current validated config."""
    mcp.auth = build_auth_provider(auth)


def _token_backend_label(auth: MCPAuthConfig) -> str:
    if not auth.is_real_mode():
        return "none"
    if auth.mode == "oidc_proxy":
        return "oidc"
    return auth.token_type


def _verification_source_label(auth: MCPAuthConfig) -> str:
    if not auth.is_real_mode():
        return "none"
    if auth.mode == "oidc_proxy":
        return "oidc_discovery"
    if auth.jwt_jwks_uri:
        return "jwks"
    if auth.jwt_public_key:
        return "public_key"
    if auth.token_type == "introspection":  # nosec B105
        return "introspection"
    return "none"


def _public_origin_for_logs(base_url: str | None) -> str:
    """Return scheme://host[:port] with no userinfo, path, or query."""
    if not base_url:
        return "none"
    parsed = urlparse(base_url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return "none"
    hostname = parsed.hostname
    host_label = f"[{hostname}]" if ":" in hostname else hostname
    netloc = f"{host_label}:{parsed.port}" if parsed.port else host_label
    return f"{parsed.scheme}://{netloc}"


def emit_startup_logs(
    transport: str,
    auth: MCPAuthConfig,
    host: str,
    port: int,
) -> None:
    """Log bind, scheme, mode, and warnings. Never log secrets."""
    scheme = listen_scheme(auth)
    auth_enabled = auth.http_auth and auth.is_real_mode()
    tls_source = (
        "mcp-server"
        if auth.has_in_process_tls()
        else "upstream"
        if auth.tls_terminated
        else "none"
    )
    token_backend = _token_backend_label(auth)
    verification_source = _verification_source_label(auth)
    idp_egress = (
        "private_trust"
        if auth.introspection_allow_private or auth.jwks_allow_private
        else "trusted_proxy"
        if auth.uses_ssrf_protected_fetch()
        and effective_fastmcp_settings().ssrf_trust_proxy
        else "validated"
        if auth.uses_ssrf_protected_fetch()
        else "none"
    )
    logger.info(
        "MCP Server HTTP configuration: transport=%s auth_enabled=%s "
        "auth_mode=%s token_backend=%s verification_source=%s idp_egress=%s "
        "bind=%s port=%s scheme=%s "
        "tls_source=%s host_origin_protection=%s required_scope_count=%d "
        "private_introspection=%s consent=%s storage=%s redirect_path=%s "
        "public_origin=%s",
        transport,
        auth_enabled,
        auth.mode,
        token_backend,
        verification_source,
        idp_egress,
        host,
        port,
        scheme,
        tls_source,
        host_origin_protection_for_run(host) if transport != "sse" else "unavailable",
        len(auth.required_scopes or ()),
        auth.introspection_allow_private,
        auth.require_consent if auth.is_proxy_mode() else "n/a",
        auth.storage_backend if auth.is_proxy_mode() else "n/a",
        auth.redirect_path if auth.is_proxy_mode() else "n/a",
        _public_origin_for_logs(auth.base_url),
    )

    if not auth.http_auth:
        logger.warning(HTTP_AUTH_DISABLED_WARNING.format(host=host, port=port))

    if transport != "sse" and host_origin_protection_for_run(host) is False:
        logger.warning(HOST_ORIGIN_PROTECTION_DISABLED_WARNING)

    if transport == "sse" and not is_loopback_bind(host) and auth.allow_remote_sse:
        logger.warning(REMOTE_SSE_WARNING.format(host=host, port=port))

    if (
        auth.is_real_mode()
        and not is_loopback_bind(host)
        and not auth.has_in_process_tls()
        and auth.tls_terminated
    ):
        logger.warning(TLS_TERMINATED_CLEARTEXT_WARNING.format(host=host, port=port))

    if auth.has_in_process_tls() and auth.tls_keyfile:
        warn_if_world_readable_key(auth.tls_keyfile)

    if (
        auth.is_real_mode()
        and auth.uses_ssrf_protected_fetch()
        and effective_fastmcp_settings().ssrf_trust_proxy
    ):
        # Name the variable, never its value: proxy URLs routinely carry
        # credentials, and this line goes to ordinary server logs.
        logger.warning(
            "FASTMCP_SSRF_TRUST_PROXY is enabled: identity provider egress is "
            "delegated to the proxy in %s. FastMCP skips its own DNS resolution "
            "and private-address blocklist for JWKS and OAuth metadata fetches, "
            "and does not consult NO_PROXY.",
            configured_proxy_env_var(),
        )

    if (
        auth.token_type == "introspection"  # nosec B105
        and auth.introspection_allow_private
    ):
        logger.warning(PRIVATE_INTROSPECTION_WARNING)

    if auth.jwks_allow_private and (auth.jwt_jwks_uri or auth.mode == "oidc_proxy"):
        logger.warning(PRIVATE_JWKS_WARNING)

    if auth.require_consent == "remember":
        logger.warning(
            "MCP_AUTH_REQUIRE_CONSENT=remember allows clients to skip repeated "
            "consent prompts."
        )
