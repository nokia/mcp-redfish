# Copyright 2025 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause

"""Tests for policy applied after FastMCP authenticates a token."""

from __future__ import annotations

import asyncio
import logging
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastmcp.server.auth import AccessToken, AuthProvider
from fastmcp.server.auth.ssrf import SSRFError, ValidatedURL

from src.common.auth_hardening import (
    HardenedTokenVerifier,
    SsrfSafeIntrospectionClient,
    TokenHardeningPolicy,
    configure_safe_provider_logging,
    harden_access_token,
)


def _token(**claims: object) -> AccessToken:
    return AccessToken(
        token="redacted-test-token",
        client_id="test-client",
        scopes=[],
        expires_at=None,
        claims=dict(claims),
    )


@pytest.mark.parametrize(
    "claims",
    [
        {},
        {"exp": None},
        {"exp": "tomorrow"},
        {"exp": 2_000, "nbf": 1_101},
        {"exp": 2_000, "iat": 1_101},
        {"exp": 2_000, "nbf": "later"},
    ],
)
def test_jwt_temporal_policy_rejects_invalid_claims(
    claims: dict[str, object],
) -> None:
    policy = TokenHardeningPolicy(mode="jwt", leeway_seconds=60)
    assert harden_access_token(_token(**claims), policy, now=1_000) is None


def test_jwt_temporal_policy_accepts_bounded_clock_skew() -> None:
    token = _token(exp=1_001, nbf=1_060, iat=1_060)
    policy = TokenHardeningPolicy(mode="jwt", leeway_seconds=60)
    assert harden_access_token(token, policy, now=1_000) is token


@pytest.mark.parametrize(
    "claims",
    [
        {
            "iss": "https://wrong.example",
            "aud": "mcp-redfish",
            "token_type": "Bearer",
        },
        {
            "iss": "https://issuer.example",
            "aud": "other-api",
            "token_type": "Bearer",
        },
        {
            "iss": "https://issuer.example",
            "aud": "mcp-redfish",
            "token_type": "refresh_token",
        },
        {
            "iss": "https://issuer.example",
            "aud": "mcp-redfish",
            "token_use": "refresh_token",
        },
        {"iss": "https://issuer.example", "aud": "mcp-redfish"},
    ],
)
def test_introspection_binding_rejects_wrong_or_missing_claims(
    claims: dict[str, object],
) -> None:
    policy = TokenHardeningPolicy(
        mode="introspection",
        expected_issuer="https://issuer.example",
        expected_audience="mcp-redfish",
    )
    assert harden_access_token(_token(**claims), policy) is None


def test_introspection_binding_accepts_audience_list_and_bearer() -> None:
    token = _token(
        iss="https://issuer.example",
        aud=["other-api", "mcp-redfish"],
        token_type="Bearer",
    )
    policy = TokenHardeningPolicy(
        mode="introspection",
        expected_issuer="https://issuer.example",
        expected_audience="mcp-redfish",
    )
    assert harden_access_token(token, policy) is token


class _AcceptingProvider(AuthProvider):
    def __init__(self, result: AccessToken) -> None:
        super().__init__()
        self.result = result

    async def verify_token(self, token: str) -> AccessToken | None:
        return self.result


def test_wrapper_applies_policy_after_inner_provider_accepts() -> None:
    inner = _AcceptingProvider(_token(exp=None))
    verifier = HardenedTokenVerifier(
        inner, TokenHardeningPolicy(mode="jwt", leeway_seconds=60)
    )
    assert asyncio.run(verifier.verify_token("never-logged")) is None


def test_introspection_client_stops_when_ssrf_validation_blocks() -> None:
    client = SsrfSafeIntrospectionClient(allow_private=False)
    with (
        patch(
            "src.common.auth_hardening.validate_url",
            AsyncMock(side_effect=SSRFError("blocked")),
        ),
        patch.object(client, "_post_target", AsyncMock()) as post,
        pytest.raises(httpx.RequestError, match="egress validation failed"),
    ):
        asyncio.run(client.post("https://127.0.0.1/introspect"))
    post.assert_not_awaited()


def test_private_introspection_opt_in_uses_configured_https_target() -> None:
    client = SsrfSafeIntrospectionClient(allow_private=True)
    response = object()
    with patch.object(client, "_post_target", AsyncMock(return_value=response)) as post:
        result = asyncio.run(
            client.post(
                "https://keycloak.internal/introspect",
                data={"token": "not-logged"},
            )
        )
    assert result is response
    post.assert_awaited_once()


def test_introspection_client_pins_validated_ip_host_and_sni() -> None:
    client = SsrfSafeIntrospectionClient(allow_private=False)
    validated = ValidatedURL(
        original_url="https://idp.example/introspect",
        hostname="idp.example",
        port=443,
        path="/introspect",
        resolved_ips=["203.0.113.10"],
    )
    response = object()
    with (
        patch(
            "src.common.auth_hardening.validate_url",
            AsyncMock(return_value=validated),
        ),
        patch.object(client, "_post_target", AsyncMock(return_value=response)) as post,
    ):
        result = asyncio.run(client.post(validated.original_url))
    assert result is response
    assert post.await_args.args[0] == "https://203.0.113.10:443/introspect"
    assert post.await_args.kwargs["host_header"] == "idp.example"
    assert post.await_args.kwargs["sni_hostname"] == "idp.example"


def test_introspection_client_uses_explicit_validated_proxy() -> None:
    client = SsrfSafeIntrospectionClient(allow_private=False)
    validated = ValidatedURL(
        original_url="https://idp.example/introspect",
        hostname="idp.example",
        port=443,
        path="/introspect",
        resolved_ips=[],
        proxy_url="http://proxy.example:3128",
    )
    with (
        patch(
            "src.common.auth_hardening.validate_url",
            AsyncMock(return_value=validated),
        ),
        patch.object(client, "_post_target", AsyncMock(return_value=object())) as post,
    ):
        asyncio.run(client.post(validated.original_url))
    assert post.await_args.kwargs["proxy"] == "http://proxy.example:3128"


def test_policy_debug_log_uses_reason_code_without_claim_values(
    caplog: pytest.LogCaptureFixture,
) -> None:
    sensitive_issuer = "https://private-tenant.example"
    sensitive_audience = "confidential-service-name"
    token = _token(
        iss=sensitive_issuer,
        aud=sensitive_audience,
        token_type="Bearer",
    )
    policy = TokenHardeningPolicy(
        mode="introspection",
        expected_issuer="https://expected.example",
        expected_audience="mcp-redfish",
    )
    with caplog.at_level(logging.DEBUG, logger="src.common.auth_hardening"):
        assert harden_access_token(token, policy) is None
    assert "reason=introspection_issuer_mismatch" in caplog.text
    assert sensitive_issuer not in caplog.text
    assert sensitive_audience not in caplog.text
    assert token.token not in caplog.text


def test_fastmcp_provider_logs_are_sanitized(
    caplog: pytest.LogCaptureFixture,
) -> None:
    configure_safe_provider_logging()
    sensitive_client = "private-client-identity"
    sensitive_claim = "private-audience"
    provider_logger = logging.getLogger("fastmcp.server.auth.providers.jwt")
    with caplog.at_level(logging.WARNING, logger="fastmcp.server.auth.providers.jwt"):
        provider_logger.warning(
            "Bearer token rejected for client %s: audience mismatch %s",
            sensitive_client,
            sensitive_claim,
        )
    assert "JWT rejected by the FastMCP audience check." in caplog.text
    assert sensitive_client not in caplog.text
    assert sensitive_claim not in caplog.text


def test_fastmcp_introspection_response_body_is_not_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    configure_safe_provider_logging()
    sensitive_body = "client_secret=never-log-this"
    provider_logger = logging.getLogger("fastmcp.server.auth.providers.introspection")
    with caplog.at_level(
        logging.DEBUG, logger="fastmcp.server.auth.providers.introspection"
    ):
        provider_logger.debug(
            "Token introspection failed: HTTP %d - %s",
            500,
            sensitive_body,
        )
    assert "FastMCP token introspection event." in caplog.text
    assert sensitive_body not in caplog.text
