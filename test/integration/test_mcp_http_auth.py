# Copyright 2025 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause

"""In-process MCP HTTP authentication tests (Phases 0–4)."""

from __future__ import annotations

import asyncio
import base64
import json
import socket
import threading
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx2 as httpx
import pytest
import uvicorn
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from fastmcp import Client
from fastmcp.client.auth import BearerAuth
from fastmcp.server.auth import OAuthProxy, RemoteAuthProvider
from fastmcp.server.auth.oidc_proxy import OIDCConfiguration
from fastmcp.server.auth.providers.introspection import IntrospectionTokenVerifier
from fastmcp.server.auth.providers.jwt import JWTVerifier, RSAKeyPair
from key_value.aio.stores.memory import MemoryStore
from pydantic import AnyHttpUrl

from src.common.auth import SsrfSafeOIDCProxy, build_auth_provider
from src.common.auth_hardening import HardenedTokenVerifier, TokenHardeningPolicy
from src.common.server import mcp
from src.common.validation import load_mcp_auth_config

from test.common.oidc_simulator import (
    AUDIENCE,
    CLIENT_ID,
    CLIENT_SECRET,
    HttpsOidcSimulator,
    complete_mcp_oauth_login,
)
from test.utils import clear_auth_env, write_self_signed_tls_pair

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


def test_phase2_remote_oauth_metadata_is_public_tools_are_not(
    restore_mcp_auth: None, start_http_server: Any
) -> None:
    keypair = RSAKeyPair.generate()
    mcp.auth = RemoteAuthProvider(
        token_verifier=HardenedTokenVerifier(
            JWTVerifier(
                public_key=keypair.public_key,
                issuer=JWT_ISSUER,
                audience=JWT_AUDIENCE,
            ),
            TokenHardeningPolicy(mode="jwt"),
        ),
        authorization_servers=[AnyHttpUrl("https://idp.example")],
        base_url="http://127.0.0.1:8000",
    )
    port = _free_port()
    start_http_server(port)
    metadata = httpx.get(
        f"http://127.0.0.1:{port}/.well-known/oauth-protected-resource/mcp"
    )
    assert metadata.status_code == 200
    body = metadata.json()
    assert "authorization_servers" in body

    url = f"http://127.0.0.1:{port}/mcp"

    async def _list(token: str | None) -> Any:
        auth = BearerAuth(token) if token else None
        async with Client(url, auth=auth) as client:
            with patch(
                "src.common.hosts.get_hosts", return_value=[{"address": "bmc-1"}]
            ):
                return await client.call_tool("list_servers")

    with pytest.raises(Exception):  # noqa: B017 - HTTP 401 / transport error
        asyncio.run(_list(None))
    token = keypair.create_token(issuer=JWT_ISSUER, audience=JWT_AUDIENCE)
    result = asyncio.run(_list(token))
    data = result.data if hasattr(result, "data") else None
    if data is None and result.content:
        data = json.loads(result.content[0].text)
    assert data == ["bmc-1"]


def test_phase3_oauth_proxy_metadata_is_public_tools_are_not(
    restore_mcp_auth: None, start_http_server: Any
) -> None:
    keypair = RSAKeyPair.generate()
    mcp.auth = OAuthProxy(
        upstream_authorization_endpoint="https://idp.example/authorize",
        upstream_token_endpoint="https://idp.example/token",
        upstream_client_id="client",
        upstream_client_secret="oauth-client-secret-value-not-for-logs",
        token_verifier=HardenedTokenVerifier(
            JWTVerifier(
                public_key=keypair.public_key,
                issuer=JWT_ISSUER,
                audience=JWT_AUDIENCE,
            ),
            TokenHardeningPolicy(mode="jwt"),
        ),
        base_url="http://127.0.0.1:8000",
        jwt_signing_key="abcdefghijklmnopqrstuvwxyz012345",
        require_authorization_consent=True,
        forward_pkce=True,
        allowed_client_redirect_uris=[
            "http://localhost:*",
            "http://127.0.0.1:*",
        ],
        client_storage=MemoryStore(),
    )
    port = _free_port()
    start_http_server(port)
    metadata = httpx.get(
        f"http://127.0.0.1:{port}/.well-known/oauth-authorization-server"
    )
    assert metadata.status_code == 200
    protected = httpx.get(
        f"http://127.0.0.1:{port}/.well-known/oauth-protected-resource/mcp"
    )
    assert protected.status_code == 200

    async def _list() -> None:
        async with Client(f"http://127.0.0.1:{port}/mcp") as client:
            await client.call_tool("list_servers")

    with pytest.raises(Exception):  # noqa: B017
        asyncio.run(_list())


def test_phase4_oidc_proxy_metadata_is_public_tools_are_not(
    restore_mcp_auth: None, start_http_server: Any
) -> None:
    oidc_config = OIDCConfiguration.model_validate(
        {
            "strict": False,
            "issuer": "https://idp.example",
            "authorization_endpoint": "https://idp.example/authorize",
            "token_endpoint": "https://idp.example/token",
            "jwks_uri": "https://idp.example/jwks",
        }
    )
    with patch.object(
        SsrfSafeOIDCProxy, "get_oidc_configuration", return_value=oidc_config
    ):
        mcp.auth = SsrfSafeOIDCProxy(
            config_url="https://idp.example/.well-known/openid-configuration",
            client_id="client",
            client_secret="oauth-client-secret-value-not-for-logs",
            base_url="http://127.0.0.1:8000",
            audience=JWT_AUDIENCE,
            jwt_signing_key="abcdefghijklmnopqrstuvwxyz012345",
            require_authorization_consent=True,
            allowed_client_redirect_uris=[
                "http://localhost:*",
                "http://127.0.0.1:*",
            ],
            client_storage=MemoryStore(),
            verify_id_token=False,
        )
    port = _free_port()
    start_http_server(port)
    metadata = httpx.get(
        f"http://127.0.0.1:{port}/.well-known/oauth-authorization-server"
    )
    assert metadata.status_code == 200
    protected = httpx.get(
        f"http://127.0.0.1:{port}/.well-known/oauth-protected-resource/mcp"
    )
    assert protected.status_code == 200

    async def _list() -> None:
        async with Client(f"http://127.0.0.1:{port}/mcp") as client:
            await client.call_tool("list_servers")

    with pytest.raises(Exception):  # noqa: B017
        asyncio.run(_list())


SIGNING_KEY = "abcdefghijklmnopqrstuvwxyz012345"


def _start_simulator(tmp_path: Any, keypair: RSAKeyPair) -> HttpsOidcSimulator:
    certfile, keyfile = write_self_signed_tls_pair(str(tmp_path))
    return HttpsOidcSimulator(
        port=_free_port(),
        certfile=certfile,
        keyfile=keyfile,
        keypair=keypair,
        audience=AUDIENCE,
    )


def _proxy_simulator_env(
    monkeypatch: pytest.MonkeyPatch,
    *,
    mode: str,
    mcp_port: int,
    idp: HttpsOidcSimulator,
    public_key: str | None = None,
) -> None:
    clear_auth_env()
    monkeypatch.setenv("MCP_TRANSPORT", "streamable-http")
    monkeypatch.setenv("FASTMCP_HOST", "127.0.0.1")
    monkeypatch.setenv("MCP_AUTH_MODE", mode)
    monkeypatch.setenv("MCP_AUTH_CLIENT_ID", CLIENT_ID)
    monkeypatch.setenv("MCP_AUTH_CLIENT_SECRET", CLIENT_SECRET)
    monkeypatch.setenv("MCP_AUTH_BASE_URL", f"http://127.0.0.1:{mcp_port}")
    monkeypatch.setenv("MCP_AUTH_REQUIRE_CONSENT", "false")
    monkeypatch.setenv("MCP_AUTH_JWT_SIGNING_KEY", SIGNING_KEY)
    monkeypatch.setenv("SSL_CERT_FILE", idp.certfile)
    monkeypatch.setenv("REQUESTS_CA_BUNDLE", idp.certfile)
    if mode == "oauth_proxy":
        if public_key is None:
            raise AssertionError("oauth_proxy simulator tests require a public key")
        monkeypatch.setenv("MCP_AUTH_TOKEN_TYPE", "jwt")
        monkeypatch.setenv("MCP_AUTH_JWT_ISSUER", idp.issuer)
        monkeypatch.setenv("MCP_AUTH_JWT_AUDIENCE", idp.audience)
        monkeypatch.setenv("MCP_AUTH_JWT_PUBLIC_KEY", public_key)
        monkeypatch.setenv(
            "MCP_AUTH_UPSTREAM_AUTHORIZATION_ENDPOINT",
            idp.authorization_endpoint(),
        )
        monkeypatch.setenv("MCP_AUTH_UPSTREAM_TOKEN_ENDPOINT", idp.token_endpoint())
        return
    monkeypatch.setenv("MCP_AUTH_OIDC_CONFIG_URL", idp.discovery_url())
    monkeypatch.setenv("MCP_AUTH_OIDC_AUDIENCE", idp.audience)


def _call_list_servers(url: str, token: str | None) -> Any:
    async def _list() -> Any:
        auth = BearerAuth(token) if token else None
        async with Client(url, auth=auth) as client:
            with patch(
                "src.common.hosts.get_hosts", return_value=[{"address": "bmc-1"}]
            ):
                return await client.call_tool("list_servers")

    return asyncio.run(_list())


def test_oauth_proxy_login_against_https_simulator(
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
    restore_mcp_auth: None,
    start_http_server: Any,
) -> None:
    keypair = RSAKeyPair.generate()
    mcp_port = _free_port()
    with _start_simulator(tmp_path, keypair) as idp:
        _proxy_simulator_env(
            monkeypatch,
            mode="oauth_proxy",
            mcp_port=mcp_port,
            idp=idp,
            public_key=keypair.public_key,
        )
        with patch("src.common.auth._build_client_storage", return_value=MemoryStore()):
            mcp.auth = build_auth_provider(load_mcp_auth_config())
        start_http_server(mcp_port)
        origin = f"http://127.0.0.1:{mcp_port}"
        url = f"{origin}/mcp"
        with pytest.raises(Exception):  # noqa: B017
            _call_list_servers(url, None)
        token = complete_mcp_oauth_login(mcp_origin=origin, ca_file=idp.certfile)
        result = _call_list_servers(url, token)
        data = result.data if hasattr(result, "data") else None
        if data is None and result.content:
            data = json.loads(result.content[0].text)
        assert data == ["bmc-1"]


def test_oidc_proxy_discovers_simulator_and_protects_tools(
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
    restore_mcp_auth: None,
    start_http_server: Any,
) -> None:
    keypair = RSAKeyPair.generate()
    mcp_port = _free_port()
    with _start_simulator(tmp_path, keypair) as idp:
        _proxy_simulator_env(
            monkeypatch,
            mode="oidc_proxy",
            mcp_port=mcp_port,
            idp=idp,
        )
        with patch("src.common.auth._build_client_storage", return_value=MemoryStore()):
            provider = build_auth_provider(load_mcp_auth_config())
        assert isinstance(provider, SsrfSafeOIDCProxy)
        mcp.auth = provider
        start_http_server(mcp_port)
        origin = f"http://127.0.0.1:{mcp_port}"
        metadata = httpx.get(f"{origin}/.well-known/oauth-authorization-server")
        assert metadata.status_code == 200
        with pytest.raises(Exception):  # noqa: B017
            _call_list_servers(f"{origin}/mcp", None)
        token = complete_mcp_oauth_login(mcp_origin=origin, ca_file=idp.certfile)
        with pytest.raises(Exception):  # noqa: B017
            _call_list_servers(f"{origin}/mcp", token)
