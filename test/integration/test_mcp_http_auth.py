# Copyright 2025 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause

"""In-process MCP HTTP authentication tests (Phase 0 + Phase 1)."""

from __future__ import annotations

import asyncio
import base64
import json
import socket
import threading
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import uvicorn
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from fastmcp import Client
from fastmcp.client.auth import BearerAuth
from fastmcp.server.auth.providers.introspection import IntrospectionTokenVerifier
from fastmcp.server.auth.providers.jwt import JWTVerifier, RSAKeyPair

from src.common.auth_hardening import HardenedTokenVerifier, TokenHardeningPolicy
from src.common.server import mcp

JWT_ISSUER = "https://issuer.example"
JWT_AUDIENCE = "mcp-redfish"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _base64url_uint(value: int) -> str:
    length = max(1, (value.bit_length() + 7) // 8)
    return base64.urlsafe_b64encode(value.to_bytes(length, "big")).rstrip(b"=").decode()


def _jwks_bytes(keypair: RSAKeyPair, kid: str) -> bytes:
    public_key = load_pem_public_key(keypair.public_key.encode())
    assert isinstance(public_key, RSAPublicKey)
    numbers = public_key.public_numbers()
    return json.dumps(
        {
            "keys": [
                {
                    "kty": "RSA",
                    "kid": kid,
                    "use": "sig",
                    "alg": "RS256",
                    "n": _base64url_uint(numbers.n),
                    "e": _base64url_uint(numbers.e),
                }
            ]
        }
    ).encode()


def _wait_for_port(host: str, port: int, timeout: float = 10.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.05)
    raise TimeoutError(f"Port {host}:{port} did not open")


class _HttpServer:
    def __init__(self, port: int, path: str = "/mcp") -> None:
        self.port = port
        self.path = path
        self._thread: threading.Thread | None = None
        self._error: BaseException | None = None
        self._server: uvicorn.Server | None = None

    def start(self) -> None:
        def _run() -> None:
            try:
                app = mcp.http_app(
                    path=self.path,
                    transport="streamable-http",
                    host_origin_protection=False,
                )
                config = uvicorn.Config(
                    app,
                    host="127.0.0.1",
                    port=self.port,
                    log_level="error",
                )
                self._server = uvicorn.Server(config)
                self._server.run()
            except BaseException as exc:  # noqa: BLE001 - capture thread errors
                self._error = exc

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()
        _wait_for_port("127.0.0.1", self.port)
        if self._error is not None:
            raise self._error

    def close(self) -> None:
        if self._server is not None:
            self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout=10)
            if self._thread.is_alive():
                raise RuntimeError("MCP HTTP test server did not shut down")


@pytest.fixture
def restore_mcp_auth():
    previous = mcp.auth
    yield
    mcp.auth = previous


@pytest.fixture
def start_http_server():
    servers: list[_HttpServer] = []

    def _start(port: int, path: str = "/mcp") -> _HttpServer:
        server = _HttpServer(port, path)
        server.start()
        servers.append(server)
        return server

    yield _start

    for server in reversed(servers):
        server.close()


def test_phase0_http_without_auth_can_list_servers(
    restore_mcp_auth: None, start_http_server: Any
) -> None:
    mcp.auth = None
    port = _free_port()
    start_http_server(port)

    async def _call() -> Any:
        async with Client(f"http://127.0.0.1:{port}/mcp") as client:
            with patch(
                "src.common.hosts.get_hosts", return_value=[{"address": "bmc-1"}]
            ):
                return await client.call_tool("list_servers")

    result = asyncio.run(_call())
    data = result.data if hasattr(result, "data") else None
    if data is None and result.content:
        import json

        data = json.loads(result.content[0].text)
    assert data == ["bmc-1"]


def test_phase1_jwt_bearer_success_and_failures(
    restore_mcp_auth: None, start_http_server: Any
) -> None:
    keypair = RSAKeyPair.generate()
    mcp.auth = HardenedTokenVerifier(
        JWTVerifier(
            public_key=keypair.public_key,
            issuer=JWT_ISSUER,
            audience=JWT_AUDIENCE,
            required_scopes=["mcp:read"],
        ),
        TokenHardeningPolicy(mode="jwt", leeway_seconds=60),
    )
    port = _free_port()
    start_http_server(port)
    url = f"http://127.0.0.1:{port}/mcp"
    good = keypair.create_token(
        issuer=JWT_ISSUER, audience=JWT_AUDIENCE, scopes=["mcp:read"]
    )
    wrong_aud = keypair.create_token(issuer=JWT_ISSUER, audience="someone-else")
    wrong_issuer = keypair.create_token(
        issuer="https://wrong-issuer.example",
        audience=JWT_AUDIENCE,
        scopes=["mcp:read"],
    )
    expired = keypair.create_token(
        issuer=JWT_ISSUER,
        audience=JWT_AUDIENCE,
        scopes=["mcp:read"],
        expires_in_seconds=-120,
    )
    future_nbf = keypair.create_token(
        issuer=JWT_ISSUER,
        audience=JWT_AUDIENCE,
        scopes=["mcp:read"],
        additional_claims={"nbf": int(time.time()) + 3600},
    )
    no_exp = keypair.create_token(
        issuer=JWT_ISSUER,
        audience=JWT_AUDIENCE,
        scopes=["mcp:read"],
        additional_claims={"exp": None},
    )
    wrong_scope = keypair.create_token(
        issuer=JWT_ISSUER,
        audience=JWT_AUDIENCE,
        scopes=["other"],
    )

    async def _list(token: str | None) -> Any:
        auth = BearerAuth(token) if token else None
        async with Client(url, auth=auth) as client:
            with patch(
                "src.common.hosts.get_hosts", return_value=[{"address": "bmc-1"}]
            ):
                return await client.call_tool("list_servers")

    result = asyncio.run(_list(good))
    data = result.data
    if data is None and result.content:
        import json

        data = json.loads(result.content[0].text)
    assert data == ["bmc-1"]

    with pytest.raises(Exception):  # noqa: B017 - HTTP 401 / transport error
        asyncio.run(_list(None))
    with pytest.raises(Exception):  # noqa: B017
        asyncio.run(_list(wrong_aud))
    with pytest.raises(Exception):  # noqa: B017
        asyncio.run(_list(wrong_issuer))
    with pytest.raises(Exception):  # noqa: B017
        asyncio.run(_list(expired))
    with pytest.raises(Exception):  # noqa: B017
        asyncio.run(_list(future_nbf))
    with pytest.raises(Exception):  # noqa: B017
        asyncio.run(_list(no_exp))
    with pytest.raises(Exception):  # noqa: B017
        asyncio.run(_list(wrong_scope))
    with pytest.raises(Exception):  # noqa: B017
        asyncio.run(_list("not-a-jwt"))


def test_phase1_introspection_active_and_inactive(
    restore_mcp_auth: None, start_http_server: Any
) -> None:
    class _Response:
        def __init__(self, payload: dict[str, Any]) -> None:
            self.status_code = 200
            self._payload = payload

        def json(self) -> dict[str, Any]:
            return self._payload

    class _Client:
        async def post(
            self,
            url: str,
            data: dict[str, str] | None = None,
            headers: dict | None = None,
        ) -> _Response:
            token = (data or {}).get("token")
            if token == "active-token":
                return _Response(
                    {
                        "active": True,
                        "client_id": "mcp-client",
                        "iss": JWT_ISSUER,
                        "aud": JWT_AUDIENCE,
                        "token_type": "Bearer",
                    }
                )
            if token == "wrong-audience":
                return _Response(
                    {
                        "active": True,
                        "iss": JWT_ISSUER,
                        "aud": "other-api",
                        "token_type": "Bearer",
                    }
                )
            if token == "refresh-token":
                return _Response(
                    {
                        "active": True,
                        "iss": JWT_ISSUER,
                        "aud": JWT_AUDIENCE,
                        "token_type": "refresh_token",
                    }
                )
            return _Response({"active": False})

    verifier = HardenedTokenVerifier(
        IntrospectionTokenVerifier(
            introspection_url="https://idp.example/introspect",
            client_id="client",
            client_secret="super-secret-introspection-value",
            http_client=_Client(),  # type: ignore[arg-type]
        ),
        TokenHardeningPolicy(
            mode="introspection",
            expected_issuer=JWT_ISSUER,
            expected_audience=JWT_AUDIENCE,
        ),
    )
    mcp.auth = verifier
    port = _free_port()
    start_http_server(port)
    url = f"http://127.0.0.1:{port}/mcp"

    async def _list(token: str) -> Any:
        async with Client(url, auth=BearerAuth(token)) as client:
            with patch(
                "src.common.hosts.get_hosts", return_value=[{"address": "bmc-1"}]
            ):
                return await client.call_tool("list_servers")

    result = asyncio.run(_list("active-token"))
    data = result.data or json.loads(result.content[0].text)
    assert data == ["bmc-1"]
    for token in ("revoked-token", "wrong-audience", "refresh-token"):
        with pytest.raises(Exception):  # noqa: B017
            asyncio.run(_list(token))


def test_custom_streamable_http_path_stays_authenticated(
    restore_mcp_auth: None, start_http_server: Any
) -> None:
    keypair = RSAKeyPair.generate()
    mcp.auth = HardenedTokenVerifier(
        JWTVerifier(
            public_key=keypair.public_key,
            issuer=JWT_ISSUER,
            audience=JWT_AUDIENCE,
        ),
        TokenHardeningPolicy(mode="jwt"),
    )
    port = _free_port()
    start_http_server(port, path="/custom")

    async def _call_without_token() -> None:
        async with Client(f"http://127.0.0.1:{port}/custom") as client:
            await client.call_tool("list_servers")

    with pytest.raises(Exception):  # noqa: B017
        asyncio.run(_call_without_token())


def test_jwks_verification_fetches_new_key_on_rotation() -> None:
    first = RSAKeyPair.generate()
    second = RSAKeyPair.generate()
    verifier = HardenedTokenVerifier(
        JWTVerifier(
            jwks_uri="https://idp.example/jwks",
            issuer=JWT_ISSUER,
            audience=JWT_AUDIENCE,
            ssrf_safe=True,
        ),
        TokenHardeningPolicy(mode="jwt"),
    )
    first_token = first.create_token(
        issuer=JWT_ISSUER, audience=JWT_AUDIENCE, kid="first"
    )
    second_token = second.create_token(
        issuer=JWT_ISSUER, audience=JWT_AUDIENCE, kid="second"
    )
    with patch(
        "fastmcp.server.auth.providers.jwt.ssrf_safe_fetch",
        new=AsyncMock(
            side_effect=[_jwks_bytes(first, "first"), _jwks_bytes(second, "second")]
        ),
    ) as fetch:
        assert asyncio.run(verifier.verify_token(first_token)) is not None
        assert asyncio.run(verifier.verify_token(second_token)) is not None
    assert fetch.await_count == 2


@patch("src.common.hosts.get_hosts")
@patch("redfish.redfish_client")
def test_mcp_bearer_not_copied_to_redfish_headers(
    mock_redfish_client: MagicMock,
    mock_get_hosts: MagicMock,
    restore_mcp_auth: None,
    start_http_server: Any,
) -> None:
    mock_get_hosts.return_value = [
        {"address": "host1", "username": "bmc-user", "password": "bmc-password"}
    ]
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.dict = {"Id": "1"}
    mock_response.getheaders.return_value = [("Content-Type", "application/json")]
    instance = MagicMock()
    instance.login.return_value = None
    instance.cafile = None
    instance.get.return_value = mock_response
    instance.logout.return_value = None
    mock_redfish_client.return_value = instance

    keypair = RSAKeyPair.generate()
    bearer = keypair.create_token(issuer=JWT_ISSUER, audience=JWT_AUDIENCE)
    mcp.auth = HardenedTokenVerifier(
        JWTVerifier(
            public_key=keypair.public_key,
            issuer=JWT_ISSUER,
            audience=JWT_AUDIENCE,
        ),
        TokenHardeningPolicy(mode="jwt"),
    )
    port = _free_port()
    start_http_server(port)

    async def _call() -> None:
        async with Client(
            f"http://127.0.0.1:{port}/mcp", auth=BearerAuth(bearer)
        ) as client:
            await client.call_tool(
                "get_resource_data",
                {"url": "https://host1/redfish/v1/Systems/1"},
            )

    asyncio.run(_call())
    kwargs = mock_redfish_client.call_args.kwargs
    assert kwargs["username"] == "bmc-user"
    assert kwargs["password"] == "bmc-password"
    assert "Authorization" not in kwargs
    for value in kwargs.values():
        assert "Bearer" not in str(value)
        assert bearer not in str(value)
