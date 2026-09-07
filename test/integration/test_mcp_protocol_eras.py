# Copyright 2025 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause

"""MCP protocol-era compatibility over Streamable HTTP (legacy and 2026-07-28)."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import patch

import pytest
from fastmcp import Client
from fastmcp.client.auth import BearerAuth
from fastmcp.server.auth.providers.jwt import JWTVerifier, RSAKeyPair

from src.common.auth_hardening import HardenedTokenVerifier, TokenHardeningPolicy
from src.common.server import mcp

from test.integration.conftest import (
    JWT_AUDIENCE,
    JWT_ISSUER,
    PROTOCOL_CONNECT_MODES,
    free_port,
)
from test.utils import extract_call_tool_result


def _jwt_auth_provider(keypair: RSAKeyPair) -> HardenedTokenVerifier:
    return HardenedTokenVerifier(
        JWTVerifier(
            public_key=keypair.public_key,
            issuer=JWT_ISSUER,
            audience=JWT_AUDIENCE,
            required_scopes=["mcp:read"],
        ),
        TokenHardeningPolicy(mode="jwt", leeway_seconds=60),
    )


async def _list_servers(
    url: str,
    *,
    connect_mode: str,
    token: str | None,
    hosts: list[dict[str, str]],
) -> Any:
    auth = BearerAuth(token) if token else None
    async with Client(url, auth=auth, mode=connect_mode) as client:
        with patch("src.common.hosts.get_hosts", return_value=hosts):
            return await client.call_tool("list_servers")


@pytest.mark.integration
@pytest.mark.parametrize("connect_mode", PROTOCOL_CONNECT_MODES)
def test_list_servers_with_jwt_across_protocol_eras(
    connect_mode: str,
    restore_mcp_auth: None,
    start_http_server: Any,
) -> None:
    keypair = RSAKeyPair.generate()
    mcp.auth = _jwt_auth_provider(keypair)
    port = free_port()
    start_http_server(port)
    url = f"http://127.0.0.1:{port}/mcp"
    token = keypair.create_token(
        issuer=JWT_ISSUER, audience=JWT_AUDIENCE, scopes=["mcp:read"]
    )

    result = asyncio.run(
        _list_servers(
            url,
            connect_mode=connect_mode,
            token=token,
            hosts=[{"address": "bmc-1"}],
        )
    )
    assert extract_call_tool_result(result) == ["bmc-1"]


@pytest.mark.integration
@pytest.mark.parametrize("connect_mode", PROTOCOL_CONNECT_MODES)
def test_list_servers_empty_across_protocol_eras(
    connect_mode: str,
    restore_mcp_auth: None,
    start_http_server: Any,
) -> None:
    keypair = RSAKeyPair.generate()
    mcp.auth = _jwt_auth_provider(keypair)
    port = free_port()
    start_http_server(port)
    url = f"http://127.0.0.1:{port}/mcp"
    token = keypair.create_token(
        issuer=JWT_ISSUER, audience=JWT_AUDIENCE, scopes=["mcp:read"]
    )

    result = asyncio.run(
        _list_servers(
            url,
            connect_mode=connect_mode,
            token=token,
            hosts=[],
        )
    )
    assert extract_call_tool_result(result) == []


@pytest.mark.integration
@pytest.mark.parametrize("connect_mode", PROTOCOL_CONNECT_MODES)
def test_unauthenticated_request_rejected_across_protocol_eras(
    connect_mode: str,
    restore_mcp_auth: None,
    start_http_server: Any,
) -> None:
    keypair = RSAKeyPair.generate()
    mcp.auth = _jwt_auth_provider(keypair)
    port = free_port()
    start_http_server(port)
    url = f"http://127.0.0.1:{port}/mcp"

    with pytest.raises(Exception):  # noqa: B017 - HTTP 401 / transport error
        asyncio.run(
            _list_servers(
                url,
                connect_mode=connect_mode,
                token=None,
                hosts=[{"address": "bmc-1"}],
            )
        )


@pytest.mark.integration
@pytest.mark.parametrize("connect_mode", PROTOCOL_CONNECT_MODES)
def test_http_without_auth_list_servers_across_protocol_eras(
    connect_mode: str,
    restore_mcp_auth: None,
    start_http_server: Any,
) -> None:
    mcp.auth = None
    port = free_port()
    start_http_server(port)
    url = f"http://127.0.0.1:{port}/mcp"

    result = asyncio.run(
        _list_servers(
            url,
            connect_mode=connect_mode,
            token=None,
            hosts=[{"address": "bmc-1"}],
        )
    )
    assert extract_call_tool_result(result) == ["bmc-1"]
