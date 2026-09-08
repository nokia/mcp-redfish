#!/usr/bin/env python3
# Copyright 2025 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause

"""OAuth Proxy, OIDC Proxy, and Remote OAuth e2e against CNCF Dex.

Dex has no Dynamic Client Registration, so OAuth Proxy registers a fixed
app and lists authorize/token by hand. Current Dex access tokens are JWTs
with aud set to the client id; JWKS and RFC 7662 introspection both work.
OIDC Proxy uses discovery with ID-token or access-token verification.
Remote OAuth uses public protected-resource metadata and Dex JWT Bearer
tokens obtained directly from Dex (no MCP-client DCR). Loopback JWKS and
introspection need the warned private-trust flags. Cloud IdPs remain a
manual checklist.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx2
import pytest

from e2e.test_http_auth import (
    _SIGNING_KEY,
    _emulator_in_servers,
    _HttpMcpProcess,
    _list_servers,
    _proxy_home,
)
from test.common.oidc_simulator import complete_dex_login, complete_mcp_oauth_login

pytestmark = [pytest.mark.e2e, pytest.mark.idp]


def _dex_common_env(
    mcp_server_env: dict[str, str],
    dex_server: dict[str, str],
    tmp_path: Path,
) -> dict[str, str]:
    certfile = str(Path(__file__).parent / "certs" / "server.crt")
    mcp_port = dex_server["mcp_port"]
    env = dict(mcp_server_env)
    env.update(_proxy_home(tmp_path))
    env.update(
        {
            "MCP_AUTH_CLIENT_ID": dex_server["client_id"],
            "MCP_AUTH_CLIENT_SECRET": dex_server["client_secret"],
            "MCP_AUTH_BASE_URL": f"http://127.0.0.1:{mcp_port}",
            "MCP_AUTH_REQUIRE_CONSENT": "false",
            "MCP_AUTH_JWT_SIGNING_KEY": _SIGNING_KEY,
            "SSL_CERT_FILE": certfile,
            "REQUESTS_CA_BUNDLE": certfile,
            "MCP_REDFISH_LOG_LEVEL": "INFO",
        }
    )
    return env


def _dex_oidc_proxy_env(
    mcp_server_env: dict[str, str],
    dex_server: dict[str, str],
    tmp_path: Path,
    *,
    allow_private_jwks: bool,
    verify_id_token: bool = True,
) -> dict[str, str]:
    env = _dex_common_env(mcp_server_env, dex_server, tmp_path)
    env.update(
        {
            "MCP_AUTH_MODE": "oidc_proxy",
            "MCP_AUTH_OIDC_CONFIG_URL": dex_server["discovery_url"],
            "MCP_AUTH_OIDC_VERIFY_ID_TOKEN": "true" if verify_id_token else "false",
            "MCP_AUTH_REQUIRED_SCOPES": '["openid"]',
        }
    )
    if not verify_id_token:
        env["MCP_AUTH_OIDC_AUDIENCE"] = dex_server["client_id"]
    if allow_private_jwks:
        env["MCP_AUTH_JWKS_ALLOW_PRIVATE"] = "true"
    return env


def _dex_remote_oauth_env(
    mcp_server_env: dict[str, str],
    dex_server: dict[str, str],
    tmp_path: Path,
) -> dict[str, str]:
    certfile = str(Path(__file__).parent / "certs" / "server.crt")
    mcp_port = dex_server["mcp_port"]
    env = dict(mcp_server_env)
    env.update(_proxy_home(tmp_path))
    env.update(
        {
            "MCP_AUTH_MODE": "remote_oauth",
            "MCP_AUTH_TOKEN_TYPE": "jwt",
            "MCP_AUTH_JWT_JWKS_URI": dex_server["jwks_uri"],
            "MCP_AUTH_JWT_ISSUER": dex_server["issuer"],
            "MCP_AUTH_JWT_AUDIENCE": dex_server["client_id"],
            "MCP_AUTH_AUTHORIZATION_SERVERS": json.dumps([dex_server["issuer"]]),
            "MCP_AUTH_BASE_URL": f"http://127.0.0.1:{mcp_port}",
            "MCP_AUTH_JWKS_ALLOW_PRIVATE": "true",
            "SSL_CERT_FILE": certfile,
            "REQUESTS_CA_BUNDLE": certfile,
            "MCP_REDFISH_LOG_LEVEL": "INFO",
        }
    )
    return env


def _dex_oauth_proxy_jwt_env(
    mcp_server_env: dict[str, str],
    dex_server: dict[str, str],
    tmp_path: Path,
    *,
    allow_private_jwks: bool,
) -> dict[str, str]:
    env = _dex_common_env(mcp_server_env, dex_server, tmp_path)
    env.update(
        {
            "MCP_AUTH_MODE": "oauth_proxy",
            "MCP_AUTH_TOKEN_TYPE": "jwt",
            "MCP_AUTH_UPSTREAM_AUTHORIZATION_ENDPOINT": dex_server[
                "authorization_endpoint"
            ],
            "MCP_AUTH_UPSTREAM_TOKEN_ENDPOINT": dex_server["token_endpoint"],
            "MCP_AUTH_JWT_JWKS_URI": dex_server["jwks_uri"],
            "MCP_AUTH_JWT_ISSUER": dex_server["issuer"],
            "MCP_AUTH_JWT_AUDIENCE": dex_server["client_id"],
            "MCP_AUTH_REQUIRED_SCOPES": '["openid"]',
        }
    )
    if allow_private_jwks:
        env["MCP_AUTH_JWKS_ALLOW_PRIVATE"] = "true"
    return env


def _dex_oauth_proxy_introspection_env(
    mcp_server_env: dict[str, str],
    dex_server: dict[str, str],
    tmp_path: Path,
) -> dict[str, str]:
    env = _dex_common_env(mcp_server_env, dex_server, tmp_path)
    env.update(
        {
            "MCP_AUTH_MODE": "oauth_proxy",
            "MCP_AUTH_TOKEN_TYPE": "introspection",
            "MCP_AUTH_UPSTREAM_AUTHORIZATION_ENDPOINT": dex_server[
                "authorization_endpoint"
            ],
            "MCP_AUTH_UPSTREAM_TOKEN_ENDPOINT": dex_server["token_endpoint"],
            "MCP_AUTH_INTROSPECTION_URL": dex_server["introspection_endpoint"],
            "MCP_AUTH_INTROSPECTION_CLIENT_ID": dex_server["client_id"],
            "MCP_AUTH_INTROSPECTION_CLIENT_SECRET": dex_server["client_secret"],
            "MCP_AUTH_INTROSPECTION_ISSUER": dex_server["issuer"],
            "MCP_AUTH_INTROSPECTION_AUDIENCE": dex_server["client_id"],
            "MCP_AUTH_INTROSPECTION_ALLOW_PRIVATE": "true",
            "MCP_AUTH_REQUIRED_SCOPES": '["openid"]',
        }
    )
    return env


def test_oidc_proxy_dex_metadata_is_public_tools_need_token(
    mcp_server_env: dict[str, str],
    dex_server: dict[str, str],
    tmp_path: Path,
) -> None:
    mcp_port = int(dex_server["mcp_port"])
    env = _dex_oidc_proxy_env(
        mcp_server_env, dex_server, tmp_path, allow_private_jwks=False
    )
    server = _HttpMcpProcess(env, mcp_port)
    try:
        server.wait_ready()
        origin = f"http://127.0.0.1:{mcp_port}"
        with httpx2.Client(trust_env=False) as client:
            metadata = client.get(f"{origin}/.well-known/oauth-authorization-server")
            protected = client.get(f"{origin}/.well-known/oauth-protected-resource/mcp")
        assert metadata.status_code == 200
        assert protected.status_code == 200
        assert "authorization_servers" in protected.json()
        with pytest.raises(Exception):  # noqa: B017
            _list_servers(f"{origin}/mcp", None)
        stderr = server.stderr_text()
        assert "verification_source=oidc_discovery" in stderr
        assert dex_server["client_secret"] not in stderr
    finally:
        server.close()


def test_oidc_proxy_dex_jwks_ssrf_blocks_tools_on_loopback(
    mcp_server_env: dict[str, str],
    dex_server: dict[str, str],
    tmp_path: Path,
) -> None:
    certfile = str(Path(__file__).parent / "certs" / "server.crt")
    mcp_port = int(dex_server["mcp_port"])
    env = _dex_oidc_proxy_env(
        mcp_server_env, dex_server, tmp_path, allow_private_jwks=False
    )
    server = _HttpMcpProcess(env, mcp_port)
    try:
        server.wait_ready()
        origin = f"http://127.0.0.1:{mcp_port}"
        with pytest.raises(Exception):  # noqa: B017
            _list_servers(f"{origin}/mcp", None)
        token = complete_mcp_oauth_login(
            mcp_origin=origin, ca_file=certfile, scope="openid"
        )
        with pytest.raises(Exception):  # noqa: B017
            _list_servers(f"{origin}/mcp", token)
        stderr = server.stderr_text()
        assert "verification_source=oidc_discovery" in stderr
        assert dex_server["client_secret"] not in stderr
    finally:
        server.close()


def test_oidc_proxy_dex_login_lists_servers(
    mcp_server_env: dict[str, str],
    dex_server: dict[str, str],
    emulator_config: dict[str, str],
    tmp_path: Path,
) -> None:
    certfile = str(Path(__file__).parent / "certs" / "server.crt")
    mcp_port = int(dex_server["mcp_port"])
    env = _dex_oidc_proxy_env(
        mcp_server_env, dex_server, tmp_path, allow_private_jwks=True
    )
    server = _HttpMcpProcess(env, mcp_port)
    try:
        server.wait_ready()
        origin = f"http://127.0.0.1:{mcp_port}"
        url = f"{origin}/mcp"
        with pytest.raises(Exception):  # noqa: B017
            _list_servers(url, None)
        token = complete_mcp_oauth_login(
            mcp_origin=origin, ca_file=certfile, scope="openid"
        )
        servers = _list_servers(url, token)
        assert _emulator_in_servers(servers, emulator_config)
        stderr = server.stderr_text()
        assert "verification_source=oidc_discovery" in stderr
        assert "MCP_AUTH_JWKS_ALLOW_PRIVATE=true" in stderr
        assert dex_server["client_secret"] not in stderr
    finally:
        server.close()


def test_oidc_proxy_dex_access_token_login_lists_servers(
    mcp_server_env: dict[str, str],
    dex_server: dict[str, str],
    emulator_config: dict[str, str],
    tmp_path: Path,
) -> None:
    certfile = str(Path(__file__).parent / "certs" / "server.crt")
    mcp_port = int(dex_server["mcp_port"])
    env = _dex_oidc_proxy_env(
        mcp_server_env,
        dex_server,
        tmp_path,
        allow_private_jwks=True,
        verify_id_token=False,
    )
    server = _HttpMcpProcess(env, mcp_port)
    try:
        server.wait_ready()
        origin = f"http://127.0.0.1:{mcp_port}"
        url = f"{origin}/mcp"
        with pytest.raises(Exception):  # noqa: B017
            _list_servers(url, None)
        token = complete_mcp_oauth_login(
            mcp_origin=origin, ca_file=certfile, scope="openid"
        )
        servers = _list_servers(url, token)
        assert _emulator_in_servers(servers, emulator_config)
        stderr = server.stderr_text()
        assert "verification_source=oidc_discovery" in stderr
        assert "MCP_AUTH_JWKS_ALLOW_PRIVATE=true" in stderr
        assert dex_server["client_secret"] not in stderr
    finally:
        server.close()


def test_oauth_proxy_dex_jwks_ssrf_blocks_tools_on_loopback(
    mcp_server_env: dict[str, str],
    dex_server: dict[str, str],
    tmp_path: Path,
) -> None:
    certfile = str(Path(__file__).parent / "certs" / "server.crt")
    mcp_port = int(dex_server["mcp_port"])
    env = _dex_oauth_proxy_jwt_env(
        mcp_server_env, dex_server, tmp_path, allow_private_jwks=False
    )
    server = _HttpMcpProcess(env, mcp_port)
    try:
        server.wait_ready()
        origin = f"http://127.0.0.1:{mcp_port}"
        with pytest.raises(Exception):  # noqa: B017
            _list_servers(f"{origin}/mcp", None)
        token = complete_mcp_oauth_login(
            mcp_origin=origin, ca_file=certfile, scope="openid"
        )
        with pytest.raises(Exception):  # noqa: B017
            _list_servers(f"{origin}/mcp", token)
        stderr = server.stderr_text()
        assert "verification_source=jwks" in stderr
        assert dex_server["client_secret"] not in stderr
    finally:
        server.close()


def test_oauth_proxy_dex_jwt_login_lists_servers(
    mcp_server_env: dict[str, str],
    dex_server: dict[str, str],
    emulator_config: dict[str, str],
    tmp_path: Path,
) -> None:
    certfile = str(Path(__file__).parent / "certs" / "server.crt")
    mcp_port = int(dex_server["mcp_port"])
    env = _dex_oauth_proxy_jwt_env(
        mcp_server_env, dex_server, tmp_path, allow_private_jwks=True
    )
    server = _HttpMcpProcess(env, mcp_port)
    try:
        server.wait_ready()
        origin = f"http://127.0.0.1:{mcp_port}"
        url = f"{origin}/mcp"
        with pytest.raises(Exception):  # noqa: B017
            _list_servers(url, None)
        token = complete_mcp_oauth_login(
            mcp_origin=origin, ca_file=certfile, scope="openid"
        )
        servers = _list_servers(url, token)
        assert _emulator_in_servers(servers, emulator_config)
        stderr = server.stderr_text()
        assert "verification_source=jwks" in stderr
        assert "MCP_AUTH_JWKS_ALLOW_PRIVATE=true" in stderr
        assert dex_server["client_secret"] not in stderr
    finally:
        server.close()


def test_oauth_proxy_dex_introspection_login_lists_servers(
    mcp_server_env: dict[str, str],
    dex_server: dict[str, str],
    emulator_config: dict[str, str],
    tmp_path: Path,
) -> None:
    certfile = str(Path(__file__).parent / "certs" / "server.crt")
    mcp_port = int(dex_server["mcp_port"])
    env = _dex_oauth_proxy_introspection_env(mcp_server_env, dex_server, tmp_path)
    server = _HttpMcpProcess(env, mcp_port)
    try:
        server.wait_ready()
        origin = f"http://127.0.0.1:{mcp_port}"
        url = f"{origin}/mcp"
        with pytest.raises(Exception):  # noqa: B017
            _list_servers(url, None)
        token = complete_mcp_oauth_login(
            mcp_origin=origin, ca_file=certfile, scope="openid"
        )
        servers = _list_servers(url, token)
        assert _emulator_in_servers(servers, emulator_config)
        stderr = server.stderr_text()
        assert "verification_source=introspection" in stderr
        assert "MCP_AUTH_INTROSPECTION_ALLOW_PRIVATE=true" in stderr
        assert dex_server["client_secret"] not in stderr
    finally:
        server.close()


def test_remote_oauth_dex_metadata_and_bearer_lists_servers(
    mcp_server_env: dict[str, str],
    dex_server: dict[str, str],
    emulator_config: dict[str, str],
    tmp_path: Path,
) -> None:
    certfile = str(Path(__file__).parent / "certs" / "server.crt")
    mcp_port = int(dex_server["mcp_port"])
    env = _dex_remote_oauth_env(mcp_server_env, dex_server, tmp_path)
    server = _HttpMcpProcess(env, mcp_port)
    try:
        server.wait_ready()
        origin = f"http://127.0.0.1:{mcp_port}"
        url = f"{origin}/mcp"
        with httpx2.Client(trust_env=False) as client:
            protected = client.get(f"{origin}/.well-known/oauth-protected-resource/mcp")
        assert protected.status_code == 200
        assert "authorization_servers" in protected.json()
        with pytest.raises(Exception):  # noqa: B017
            _list_servers(url, None)
        dex_token = complete_dex_login(
            authorization_endpoint=dex_server["authorization_endpoint"],
            token_endpoint=dex_server["token_endpoint"],
            client_id=dex_server["client_id"],
            client_secret=dex_server["client_secret"],
            ca_file=certfile,
        )
        servers = _list_servers(url, dex_token)
        assert _emulator_in_servers(servers, emulator_config)
        stderr = server.stderr_text()
        assert "auth_mode=remote_oauth" in stderr
        assert "verification_source=jwks" in stderr
        assert "MCP_AUTH_JWKS_ALLOW_PRIVATE=true" in stderr
        assert dex_server["client_secret"] not in stderr
    finally:
        server.close()
