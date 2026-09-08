#!/usr/bin/env python3
# Copyright 2025 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause

"""HTTP MCP e2e tests: unauthenticated lab mode, local JWT Bearer, and introspection.

Cloud identity providers are out of automated e2e. OAuth/OIDC Proxy and Remote
OAuth Dex coverage is in e2e/test_dex_auth.py. See docs/MCP_AUTH.md and
docs/MCP_AUTH_MANUAL_IDP.md.
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

import httpx2
import pytest
from fastmcp import Client
from fastmcp.client.auth import BearerAuth
from fastmcp.server.auth.providers.jwt import RSAKeyPair

JWT_ISSUER = "https://mcp-redfish.example"
JWT_AUDIENCE = "mcp-redfish"

_HTTP_AUTH_ENV_KEYS = {
    "MCP_HTTP_AUTH",
    "MCP_ALLOW_REMOTE_SSE",
    "MCP_TLS_TERMINATED",
    "MCP_TLS_CERTFILE",
    "MCP_TLS_KEYFILE",
    "HTTP_PROXY",
    "http_proxy",
    "HTTPS_PROXY",
    "https_proxy",
    "ALL_PROXY",
    "all_proxy",
}


def _clear_http_auth_env(environ: dict[str, str]) -> None:
    """Remove inherited settings that could change an HTTP auth scenario."""
    for key in list(environ):
        if (
            key in _HTTP_AUTH_ENV_KEYS
            or key.startswith("MCP_AUTH_")
            or key.startswith("FASTMCP_")
        ):
            environ.pop(key, None)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


class _HttpMcpProcess:
    def __init__(
        self, env: dict[str, str], port: int, bind_host: str = "127.0.0.1"
    ) -> None:
        self.port = port
        self._stderr = tempfile.NamedTemporaryFile(
            mode="w+", prefix="mcp-redfish-http-e2e-", suffix=".log"
        )
        merged = os.environ.copy()
        _clear_http_auth_env(merged)
        merged.update(env)
        merged["MCP_TRANSPORT"] = "streamable-http"
        merged["FASTMCP_HOST"] = bind_host
        merged["FASTMCP_PORT"] = str(port)
        merged["FASTMCP_SHOW_SERVER_BANNER"] = "false"
        self._proc = subprocess.Popen(
            [sys.executable, "-m", "src.main"],
            cwd=_project_root(),
            env=merged,
            stdout=subprocess.DEVNULL,
            stderr=self._stderr,
            text=True,
        )

    def wait_ready(self) -> None:
        deadline = time.time() + 20
        while time.time() < deadline:
            if self._proc.poll() is not None:
                raise RuntimeError(
                    f"MCP HTTP server exited {self._proc.returncode}: {self.stderr_text()}"
                )
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=0.2):
                    return
            except OSError:
                time.sleep(0.1)
        raise TimeoutError(self.stderr_text())

    def stderr_text(self) -> str:
        self._stderr.flush()
        self._stderr.seek(0)
        return self._stderr.read()

    def close(self) -> None:
        if self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                self._proc.wait(timeout=5)
        self._stderr.close()


class _IntrospectionHandler(BaseHTTPRequestHandler):
    received_tokens: list[str] = []

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
        length = int(self.headers.get("Content-Length", "0"))
        form = parse_qs(self.rfile.read(length).decode())
        token = form.get("token", [""])[0]
        self.received_tokens.append(token)

        if token == "redirect-token":
            self.send_response(302)
            self.send_header("Location", "/unexpected-redirect")
            self.end_headers()
            return
        if token == "oversized-token":
            body = b"x" * (300 * 1024)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except BrokenPipeError:
                pass
            return

        payload: dict[str, object]
        if token == "active-token":
            payload = {
                "active": True,
                "client_id": "e2e-client",
                "iss": JWT_ISSUER,
                "aud": JWT_AUDIENCE,
                "token_type": "Bearer",
            }
        elif token == "wrong-audience":
            payload = {
                "active": True,
                "iss": JWT_ISSUER,
                "aud": "other-api",
                "token_type": "Bearer",
            }
        elif token == "refresh-token":
            payload = {
                "active": True,
                "iss": JWT_ISSUER,
                "aud": JWT_AUDIENCE,
                "token_type": "refresh_token",
            }
        else:
            payload = {"active": False}

        body = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


class _HttpsIntrospectionServer:
    def __init__(self, port: int) -> None:
        cert_dir = Path(__file__).parent / "certs"
        self.certfile = cert_dir / "server.crt"
        self.keyfile = cert_dir / "server.key"
        self.port = port
        self._server = ThreadingHTTPServer(("127.0.0.1", port), _IntrospectionHandler)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(self.certfile, self.keyfile)
        self._server.socket = context.wrap_socket(self._server.socket, server_side=True)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def start(self) -> None:
        _IntrospectionHandler.received_tokens.clear()
        self._thread.start()

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=10)
        if self._thread.is_alive():
            raise RuntimeError("HTTPS introspection test server did not shut down")


@pytest.fixture
def http_port() -> int:
    return _free_port()


@pytest.fixture
def http_unauth_server(
    mcp_server_env: dict[str, str], http_port: int
) -> Iterator[_HttpMcpProcess]:
    env = dict(mcp_server_env)
    env["MCP_HTTP_AUTH"] = "false"
    server = _HttpMcpProcess(env, http_port)
    try:
        server.wait_ready()
        yield server
    finally:
        server.close()


@pytest.fixture
def jwt_keypair() -> RSAKeyPair:
    return RSAKeyPair.generate()


@pytest.fixture
def https_introspection_server() -> Iterator[_HttpsIntrospectionServer]:
    server = _HttpsIntrospectionServer(_free_port())
    server.start()
    try:
        yield server
    finally:
        server.close()


@pytest.fixture
def http_jwt_server(
    mcp_server_env: dict[str, str], http_port: int, jwt_keypair: RSAKeyPair
) -> Iterator[_HttpMcpProcess]:
    env = dict(mcp_server_env)
    env["MCP_AUTH_MODE"] = "token"
    env["MCP_AUTH_TOKEN_TYPE"] = "jwt"
    env["MCP_AUTH_JWT_ISSUER"] = JWT_ISSUER
    env["MCP_AUTH_JWT_AUDIENCE"] = JWT_AUDIENCE
    env["MCP_AUTH_JWT_PUBLIC_KEY"] = jwt_keypair.public_key
    server = _HttpMcpProcess(env, http_port)
    try:
        server.wait_ready()
        yield server
    finally:
        server.close()


@pytest.mark.e2e
def test_http_auth_disabled_lists_servers_and_warns(
    http_unauth_server: _HttpMcpProcess, emulator_config: dict[str, str]
) -> None:
    url = f"http://127.0.0.1:{http_unauth_server.port}/mcp"

    async def _call() -> list[str]:
        async with Client(url) as client:
            result = await client.call_tool("list_servers")
            data = result.data
            if data is None and result.content:
                import json

                data = json.loads(result.content[0].text)
            return list(data)

    servers = asyncio.run(_call())
    assert emulator_config["host"] in servers or any(
        emulator_config["host"] in str(item) for item in servers
    )
    stderr = http_unauth_server.stderr_text()
    assert "MCP HTTP authentication is disabled (MCP_HTTP_AUTH=false)" in stderr
    assert "Any client that can reach this MCP Server can call MCP tools" in stderr


@pytest.mark.e2e
def test_http_jwt_requires_bearer_and_lists_servers(
    http_jwt_server: _HttpMcpProcess,
    jwt_keypair: RSAKeyPair,
    emulator_config: dict[str, str],
) -> None:
    url = f"http://127.0.0.1:{http_jwt_server.port}/mcp"
    token = jwt_keypair.create_token(issuer=JWT_ISSUER, audience=JWT_AUDIENCE)

    async def _unauthenticated() -> None:
        async with Client(url) as client:
            await client.call_tool("list_servers")

    with pytest.raises(Exception):  # noqa: B017 - 401 / transport failure
        asyncio.run(_unauthenticated())

    async def _authenticated() -> list[str]:
        async with Client(url, auth=BearerAuth(token)) as client:
            result = await client.call_tool("list_servers")
            data = result.data
            if data is None and result.content:
                import json

                data = json.loads(result.content[0].text)
            return list(data)

    servers = asyncio.run(_authenticated())
    assert emulator_config["host"] in servers or any(
        emulator_config["host"] in str(item) for item in servers
    )


@pytest.mark.e2e
def test_https_introspection_egress_and_binding(
    mcp_server_env: dict[str, str],
    https_introspection_server: _HttpsIntrospectionServer,
    emulator_config: dict[str, str],
) -> None:
    endpoint = f"https://127.0.0.1:{https_introspection_server.port}/introspect"
    base_env = dict(mcp_server_env)
    base_env.update(
        {
            "MCP_AUTH_MODE": "token",
            "MCP_AUTH_TOKEN_TYPE": "introspection",
            "MCP_AUTH_INTROSPECTION_URL": endpoint,
            "MCP_AUTH_INTROSPECTION_CLIENT_ID": "mcp-redfish-e2e",
            "MCP_AUTH_INTROSPECTION_CLIENT_SECRET": "e2e-introspection-secret",
            "MCP_AUTH_INTROSPECTION_ISSUER": JWT_ISSUER,
            "MCP_AUTH_INTROSPECTION_AUDIENCE": JWT_AUDIENCE,
            "SSL_CERT_FILE": str(https_introspection_server.certfile),
        }
    )

    blocked_server = _HttpMcpProcess(base_env, _free_port())
    try:
        blocked_server.wait_ready()

        async def _blocked() -> None:
            async with Client(
                f"http://127.0.0.1:{blocked_server.port}/mcp",
                auth=BearerAuth("active-token"),
            ) as client:
                await client.call_tool("list_servers")

        with pytest.raises(Exception):  # noqa: B017 - expected HTTP 401
            asyncio.run(_blocked())
        assert _IntrospectionHandler.received_tokens == []
    finally:
        blocked_server.close()

    allowed_env = dict(base_env)
    allowed_env["MCP_AUTH_INTROSPECTION_ALLOW_PRIVATE"] = "true"
    allowed_server = _HttpMcpProcess(allowed_env, _free_port())
    try:
        allowed_server.wait_ready()
        url = f"http://127.0.0.1:{allowed_server.port}/mcp"

        async def _list(token: str) -> list[str]:
            async with Client(url, auth=BearerAuth(token)) as client:
                result = await client.call_tool("list_servers")
                data = result.data
                if data is None and result.content:
                    data = json.loads(result.content[0].text)
                return list(data)

        servers = asyncio.run(_list("active-token"))
        assert emulator_config["host"] in servers or any(
            emulator_config["host"] in str(item) for item in servers
        )
        for token in (
            "inactive-token",
            "wrong-audience",
            "refresh-token",
            "redirect-token",
            "oversized-token",
        ):
            with pytest.raises(Exception):  # noqa: B017 - expected HTTP 401
                asyncio.run(_list(token))

        assert set(_IntrospectionHandler.received_tokens) == {
            "active-token",
            "inactive-token",
            "wrong-audience",
            "refresh-token",
            "redirect-token",
            "oversized-token",
        }
        stderr = allowed_server.stderr_text()
        assert "MCP_AUTH_INTROSPECTION_ALLOW_PRIVATE=true" in stderr
        assert "e2e-introspection-secret" not in stderr
    finally:
        allowed_server.close()


@pytest.mark.e2e
def test_non_loopback_host_origin_guard_precedes_authentication(
    mcp_server_env: dict[str, str], jwt_keypair: RSAKeyPair
) -> None:
    port = _free_port()
    env = dict(mcp_server_env)
    env.update(
        {
            "MCP_AUTH_MODE": "token",
            "MCP_AUTH_TOKEN_TYPE": "jwt",
            "MCP_AUTH_JWT_ISSUER": JWT_ISSUER,
            "MCP_AUTH_JWT_AUDIENCE": JWT_AUDIENCE,
            "MCP_AUTH_JWT_PUBLIC_KEY": jwt_keypair.public_key,
            "MCP_TLS_TERMINATED": "true",
            "FASTMCP_HTTP_ALLOWED_HOSTS": '["allowed.example"]',
        }
    )
    server = _HttpMcpProcess(env, port, bind_host="0.0.0.0")
    try:
        server.wait_ready()
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "host-origin-e2e", "version": "1"},
            },
        }
        with httpx2.Client(trust_env=False) as client:
            wrong_host = client.post(
                f"http://127.0.0.1:{port}/mcp",
                headers={"Host": "evil.example"},
                json=payload,
            )
            wrong_origin = client.post(
                f"http://127.0.0.1:{port}/mcp",
                headers={
                    "Host": "allowed.example",
                    "Origin": "https://evil.example",
                },
                json=payload,
            )
            reaches_auth = client.post(
                f"http://127.0.0.1:{port}/mcp",
                headers={"Host": "allowed.example"},
                json=payload,
            )

        assert wrong_host.status_code == 421
        assert wrong_origin.status_code == 403
        assert reaches_auth.status_code == 401
    finally:
        server.close()


_SIGNING_KEY = "abcdefghijklmnopqrstuvwxyz012345"


def _emulator_in_servers(servers: list[str], emulator_config: dict[str, str]) -> bool:
    return emulator_config["host"] in servers or any(
        emulator_config["host"] in str(item) for item in servers
    )


def _list_servers(url: str, token: str | None) -> list[str]:
    async def _call() -> list[str]:
        auth = BearerAuth(token) if token else None
        async with Client(url, auth=auth) as client:
            result = await client.call_tool("list_servers")
            data = result.data
            if data is None and result.content:
                data = json.loads(result.content[0].text)
            return list(data)

    return asyncio.run(_call())


def _proxy_home(tmp_path: Path) -> dict[str, str]:
    home = tmp_path / "fastmcp-home"
    home.mkdir()
    return {"HOME": str(home), "XDG_DATA_HOME": str(home)}
