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
from typing import Any

from fastmcp.server.auth import AuthProvider
from fastmcp.server.auth.providers.introspection import IntrospectionTokenVerifier
from fastmcp.server.auth.providers.jwt import JWTVerifier

from .auth_hardening import (
    HardenedTokenVerifier,
    SsrfSafeIntrospectionClient,
    TokenHardeningPolicy,
    configure_safe_provider_logging,
)
from .validation import (
    IMPLEMENTED_MCP_AUTH_MODES,
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

REMOTE_SSE_WARNING = (
    "MCP_ALLOW_REMOTE_SSE=true: SSE is listening on non-loopback "
    "FASTMCP_HOST={host} port {port}. SSE has no Host/Origin protection. "
    "Prefer streamable-http for remote access."
)


def build_auth_provider(auth: MCPAuthConfig) -> AuthProvider | None:
    """Construct a FastMCP AuthProvider for the validated config, or None."""
    if auth.mode == "none":
        return None
    if auth.mode not in IMPLEMENTED_MCP_AUTH_MODES:
        raise AuthConfigurationError(
            f"MCP_AUTH_MODE={auth.mode} is not implemented in this release. "
            "Use MCP_AUTH_MODE=token, or see docs/MCP_AUTH_PLAN.md for later phases."
        )
    if auth.mode == "token":
        return _build_token_verifier(auth)
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
        kwargs["ssrf_safe"] = True
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


def _construct(verifier: Any, **kwargs: Any) -> AuthProvider:
    """Build a FastMCP verifier, reporting its own rejections as config errors.

    FastMCP validates combinations we cannot check ourselves (an HS* algorithm
    paired with a PEM public key, for example) and raises ValueError. That is a
    configuration mistake, so it must abort with a readable message rather than
    a traceback from provider construction.
    """
    try:
        return verifier(**kwargs)  # type: ignore[no-any-return]
    except ValueError as e:
        raise AuthConfigurationError(
            f"{verifier.__name__} rejected the MCP_AUTH_* configuration. "
            "Check the selected algorithm, key format, and required fields."
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
    token_backend = auth.token_type if auth.is_real_mode() else "none"
    is_introspection = auth.token_type == "introspection"  # nosec B105
    verification_source = (
        "jwks"
        if auth.jwt_jwks_uri
        else "public_key"
        if auth.jwt_public_key
        else "introspection"
        if is_introspection and auth.is_real_mode()
        else "none"
    )
    idp_egress = (
        "private_trust"
        if auth.introspection_allow_private
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
        "private_introspection=%s",
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

    if auth.require_consent == "remember":
        logger.warning(
            "MCP_AUTH_REQUIRE_CONSENT=remember allows clients to skip repeated "
            "consent prompts."
        )
