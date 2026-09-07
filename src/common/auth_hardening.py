# Copyright 2025 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause

"""Post-verification token policy and SSRF-safe introspection HTTP.

FastMCP remains responsible for JWT signature/JWKS verification and RFC 7662
processing. This module only validates claims FastMCP has already authenticated
and supplies a hardened HTTP client for the credential-bearing introspection
POST.
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass
from typing import Any, Literal

import httpx
from fastmcp.server.auth import AccessToken, AuthProvider
from fastmcp.server.auth.auth import TokenVerifier
from fastmcp.server.auth.ssrf import format_ip_for_url, validate_url
from starlette.routing import Route

logger = logging.getLogger(__name__)


class _SafeProviderLogFilter(logging.Filter):
    """Remove token-derived values from FastMCP provider log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = str(record.msg).casefold()
        if record.name.endswith(".jwt"):
            if "expired" in message:
                safe_message = "JWT rejected by the FastMCP expiration check."
            elif "issuer" in message:
                safe_message = "JWT rejected by the FastMCP issuer check."
            elif "audience" in message:
                safe_message = "JWT rejected by the FastMCP audience check."
            elif "scope" in message:
                safe_message = "JWT rejected by the FastMCP scope check."
            else:
                safe_message = "FastMCP JWT verification event."
        elif record.name.endswith(".introspection"):
            if "active=false" in message:
                safe_message = "Token introspection reported an inactive token."
            elif "expired" in message:
                safe_message = "Token introspection reported an expired token."
            else:
                safe_message = "FastMCP token introspection event."
        elif record.name.endswith(".ssrf"):
            safe_message = "FastMCP identity-provider egress security event."
        elif record.name.endswith(".oidc_proxy"):
            if record.levelno >= logging.WARNING or any(
                marker in message for marker in ("fail", "error", "unable", "invalid")
            ):
                safe_message = "FastMCP OIDC discovery failed."
            else:
                safe_message = "FastMCP OIDC discovery event."
        elif record.name.endswith(".oauth_proxy") or ".oauth_proxy." in record.name:
            if any(
                marker in message
                for marker in ("fail", "error", "denied", "invalid", "reject")
            ):
                safe_message = "FastMCP OAuth proxy rejected a request."
            else:
                safe_message = "FastMCP OAuth proxy event."
        else:
            return True

        record.msg = safe_message
        record.args = ()
        return True


def configure_safe_provider_logging() -> None:
    """Install idempotent filters on FastMCP auth-provider loggers."""
    for name in (
        "fastmcp.server.auth.providers.jwt",
        "fastmcp.server.auth.providers.introspection",
        "fastmcp.server.auth.ssrf",
        "fastmcp.server.auth.oidc_proxy",
        "fastmcp.server.auth.oauth_proxy",
        "fastmcp.server.auth.oauth_proxy.proxy",
    ):
        provider_logger = logging.getLogger(name)
        if not any(
            isinstance(item, _SafeProviderLogFilter) for item in provider_logger.filters
        ):
            provider_logger.addFilter(_SafeProviderLogFilter())


def _reject(reason: str) -> None:
    """Log a stable reason code without logging token-derived values."""
    logger.debug("MCP Bearer token rejected by policy: reason=%s", reason)


@dataclass(frozen=True)
class TokenHardeningPolicy:
    """Additional policy applied after FastMCP authenticates a token."""

    mode: Literal["jwt", "introspection"]
    leeway_seconds: int = 60
    expected_issuer: str | None = None
    expected_audience: str | None = None
    allowed_token_types: tuple[str, ...] = ("bearer", "access_token")


def _numeric_date(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _audience_matches(value: Any, expected: str) -> bool:
    if isinstance(value, str):
        return value == expected
    if isinstance(value, list):
        return expected in value
    return False


def _temporal_claims_valid(
    claims: dict[str, Any], *, now: float, leeway_seconds: int
) -> bool:
    """Require expiry and enforce not-before/issued-at with bounded skew."""
    exp = _numeric_date(claims.get("exp"))
    if exp is None:
        _reject("jwt_exp_missing_or_invalid")
        return False
    if exp <= now:
        _reject("jwt_expired")
        return False

    if "nbf" in claims:
        nbf = _numeric_date(claims["nbf"])
        if nbf is None:
            _reject("jwt_nbf_invalid")
            return False
        if nbf > now + leeway_seconds:
            _reject("jwt_not_yet_valid")
            return False

    if "iat" in claims:
        iat = _numeric_date(claims["iat"])
        if iat is None:
            _reject("jwt_iat_invalid")
            return False
        if iat > now + leeway_seconds:
            _reject("jwt_iat_in_future")
            return False

    return True


def harden_access_token(
    token: AccessToken | None,
    policy: TokenHardeningPolicy,
    *,
    now: float | None = None,
) -> AccessToken | None:
    """Return an authenticated token only when project policy also accepts it."""
    if token is None:
        _reject("core_verification_failed")
        return None

    claims = token.claims
    if policy.mode == "jwt":
        if not _temporal_claims_valid(
            claims,
            now=time.time() if now is None else now,
            leeway_seconds=policy.leeway_seconds,
        ):
            return None
        return token

    if claims.get("iss") != policy.expected_issuer:
        _reject("introspection_issuer_mismatch")
        return None
    if not policy.expected_audience or not _audience_matches(
        claims.get("aud"), policy.expected_audience
    ):
        _reject("introspection_audience_mismatch")
        return None

    type_claim_seen = False
    token_use = claims.get("token_use")
    if token_use is not None:
        type_claim_seen = True
        if not isinstance(token_use, str) or token_use.casefold() != "access_token":
            _reject("introspection_token_use_not_access_token")
            return None

    token_type = claims.get("token_type")
    if token_type is not None:
        type_claim_seen = True
        if (
            not isinstance(token_type, str)
            or token_type.casefold() not in policy.allowed_token_types
        ):
            _reject("introspection_token_type_not_allowed")
            return None

    if not type_claim_seen:
        _reject("introspection_token_type_missing")
        return None
    return token


class HardenedTokenVerifier(TokenVerifier):
    """Compose an official FastMCP provider with project claim policy."""

    def __init__(self, inner: AuthProvider, policy: TokenHardeningPolicy) -> None:
        super().__init__(
            base_url=inner.base_url,
            required_scopes=inner.required_scopes,
            resource_base_url=getattr(inner, "resource_base_url", None),
        )
        self.inner = inner
        self.policy = policy

    @property
    def scopes_supported(self) -> list[str]:
        inner_scopes = getattr(self.inner, "scopes_supported", None)
        if inner_scopes is not None:
            return list(inner_scopes)
        return self.required_scopes or []

    async def verify_token(self, token: str) -> AccessToken | None:
        verified = await self.inner.verify_token(token)
        return harden_access_token(verified, self.policy)

    def set_mcp_path(self, mcp_path: str | None) -> None:
        super().set_mcp_path(mcp_path)
        self.inner.set_mcp_path(mcp_path)

    def get_routes(self, mcp_path: str | None = None) -> list[Route]:
        return self.inner.get_routes(mcp_path)


class SsrfSafeIntrospectionClient:
    """Minimal httpx-compatible client used by IntrospectionTokenVerifier."""

    def __init__(
        self,
        *,
        allow_private: bool,
        timeout_seconds: float = 10.0,
        max_response_bytes: int = 256 * 1024,
    ) -> None:
        self.allow_private = allow_private
        self.timeout_seconds = timeout_seconds
        self.max_response_bytes = max_response_bytes

    async def post(
        self,
        url: str,
        data: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        if self.allow_private:
            logger.debug("Token introspection request uses explicit private-IdP trust.")
            return await self._post_target(url, data=data, headers=headers)

        logger.debug("Validating token introspection egress destination.")
        try:
            validated = await validate_url(url)
        except Exception as error:
            logger.debug(
                "Token introspection egress validation failed: error_type=%s",
                type(error).__name__,
            )
            raise httpx.RequestError(
                "Token introspection egress validation failed"
            ) from None
        if not validated.resolved_ips:
            logger.debug("Token introspection request uses an explicit proxy.")
            return await self._post_target(
                validated.original_url,
                data=data,
                headers=headers,
                proxy=validated.proxy_url,
            )

        last_error: httpx.RequestError | None = None
        logger.debug(
            "Token introspection destination validated: target_count=%d",
            len(validated.resolved_ips),
        )
        for ip in validated.resolved_ips:
            target = f"https://{format_ip_for_url(ip)}:{validated.port}{validated.path}"
            try:
                return await self._post_target(
                    target,
                    data=data,
                    headers=headers,
                    host_header=(
                        validated.hostname
                        if validated.port == 443
                        else f"{validated.hostname}:{validated.port}"
                    ),
                    sni_hostname=validated.hostname,
                )
            except httpx.RequestError as error:
                logger.debug(
                    "Token introspection target failed: error_type=%s",
                    type(error).__name__,
                )
                last_error = error

        if last_error is not None:
            raise last_error
        raise httpx.RequestError("No validated introspection target was available")

    async def _post_target(
        self,
        url: str,
        *,
        data: dict[str, str] | None,
        headers: dict[str, str] | None,
        host_header: str | None = None,
        sni_hostname: str | None = None,
        proxy: str | None = None,
    ) -> httpx.Response:
        request_headers = {
            key: value
            for key, value in (headers or {}).items()
            if key.casefold() != "host"
        }
        if host_header is not None:
            request_headers["Host"] = host_header
        extensions = (
            {"sni_hostname": sni_hostname} if sni_hostname is not None else None
        )
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout_seconds),
            follow_redirects=False,
            verify=True,
            proxy=proxy,
            trust_env=True,
        ) as client:
            async with client.stream(
                "POST",
                url,
                data=data,
                headers=request_headers,
                extensions=extensions,
            ) as response:
                content = bytearray()
                async for chunk in response.aiter_bytes():
                    content.extend(chunk)
                    if len(content) > self.max_response_bytes:
                        logger.debug(
                            "Token introspection response rejected: reason=size_limit"
                        )
                        raise httpx.HTTPError(
                            "Introspection response exceeded the size limit"
                        )
                response_content = (
                    bytes(content) if response.status_code == 200 else b""
                )
                logger.debug(
                    "Token introspection endpoint response: status=%d",
                    response.status_code,
                )
                return httpx.Response(
                    response.status_code,
                    headers=response.headers,
                    content=response_content,
                    request=response.request,
                )
