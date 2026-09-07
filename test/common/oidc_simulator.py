# Copyright 2025 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause

"""In-process HTTPS OpenID simulator for proxy-mode tests.

This is a stand-in for a local identity provider, not GitHub, Azure, or Auth0.
It serves discovery, JWKS, authorization-code redirects, and JWT token
responses so OAuth/OIDC Proxy can be exercised without a browser or cloud IdP.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import ssl
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import TracebackType
from typing import Any, Self
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

import httpx2 as httpx
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from fastmcp.server.auth.providers.jwt import RSAKeyPair


def ssl_context_for_cert(ca_file: str) -> ssl.SSLContext:
    """Trust a single PEM certificate, typically the simulator's self-signed cert."""
    return ssl.create_default_context(cafile=ca_file)


CLIENT_ID = "mcp-redfish-e2e"
CLIENT_SECRET = "e2e-oidc-client-secret"
AUDIENCE = "mcp-redfish"
KID = "e2e-oidc"


def _b64url_uint(value: int) -> str:
    length = max(1, (value.bit_length() + 7) // 8)
    return base64.urlsafe_b64encode(value.to_bytes(length, "big")).rstrip(b"=").decode()


def _rsa_jwk(public_pem: str) -> dict[str, str]:
    public_key = load_pem_public_key(public_pem.encode())
    assert isinstance(public_key, RSAPublicKey)
    numbers = public_key.public_numbers()
    return {
        "kty": "RSA",
        "kid": KID,
        "use": "sig",
        "alg": "RS256",
        "n": _b64url_uint(numbers.n),
        "e": _b64url_uint(numbers.e),
    }


class HttpsOidcSimulator:
    """TLS identity-provider stub bound to 127.0.0.1."""

    def __init__(
        self,
        *,
        port: int,
        certfile: str,
        keyfile: str,
        keypair: RSAKeyPair,
        client_id: str = CLIENT_ID,
        client_secret: str = CLIENT_SECRET,
        audience: str = AUDIENCE,
    ) -> None:
        self.port = port
        self.certfile = certfile
        self.keyfile = keyfile
        self.keypair = keypair
        self.client_id = client_id
        self.client_secret = client_secret
        self.audience = audience
        self.origin = f"https://127.0.0.1:{port}"
        self.issuer = self.origin
        self._codes: set[str] = set()
        self._server = ThreadingHTTPServer(("127.0.0.1", port), self._handler())
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certfile, keyfile)
        self._server.socket = context.wrap_socket(self._server.socket, server_side=True)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def discovery_url(self) -> str:
        return f"{self.origin}/.well-known/openid-configuration"

    def authorization_endpoint(self) -> str:
        return f"{self.origin}/authorize"

    def token_endpoint(self) -> str:
        return f"{self.origin}/token"

    def start(self) -> None:
        self._thread.start()

    def wait_ready(self, timeout: float = 5.0) -> None:
        deadline = time.time() + timeout
        last_error: Exception | None = None
        while time.time() < deadline:
            try:
                response = httpx.get(
                    self.discovery_url(),
                    verify=ssl_context_for_cert(self.certfile),
                    trust_env=False,
                    timeout=0.5,
                )
                response.raise_for_status()
                return
            except Exception as exc:  # noqa: BLE001 - retry until timeout
                last_error = exc
                time.sleep(0.05)
        raise TimeoutError(f"HTTPS OIDC simulator did not become ready: {last_error}")

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=10)
        if self._thread.is_alive():
            raise RuntimeError("HTTPS OIDC simulator did not shut down")

    def __enter__(self) -> Self:
        self.start()
        self.wait_ready()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def _discovery(self) -> dict[str, Any]:
        return {
            "issuer": self.issuer,
            "authorization_endpoint": self.authorization_endpoint(),
            "token_endpoint": self.token_endpoint(),
            "jwks_uri": f"{self.origin}/jwks",
            "response_types_supported": ["code"],
            "subject_types_supported": ["public"],
            "id_token_signing_alg_values_supported": ["RS256"],
            "token_endpoint_auth_methods_supported": [
                "client_secret_basic",
                "client_secret_post",
            ],
            "code_challenge_methods_supported": ["S256"],
        }

    def _access_token(self) -> str:
        return self.keypair.create_token(
            subject="e2e-user",
            issuer=self.issuer,
            audience=self.audience,
            kid=KID,
        )

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        simulator = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: object) -> None:
                return

            def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
                parsed = urlparse(self.path)
                if parsed.path == "/.well-known/openid-configuration":
                    self._json(200, simulator._discovery())
                    return
                if parsed.path == "/jwks":
                    self._json(200, {"keys": [_rsa_jwk(simulator.keypair.public_key)]})
                    return
                if parsed.path == "/authorize":
                    query = parse_qs(parsed.query)
                    redirect_uri = (query.get("redirect_uri") or [""])[0]
                    state = (query.get("state") or [""])[0]
                    if not redirect_uri:
                        self._json(400, {"error": "invalid_request"})
                        return
                    code = secrets.token_urlsafe(24)
                    simulator._codes.add(code)
                    location = redirect_uri
                    separator = "&" if "?" in location else "?"
                    location = f"{location}{separator}{urlencode({'code': code, 'state': state})}"
                    self.send_response(302)
                    self.send_header("Location", location)
                    self.end_headers()
                    return
                self.send_error(404)

            def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
                parsed = urlparse(self.path)
                if parsed.path != "/token":
                    self.send_error(404)
                    return
                length = int(self.headers.get("Content-Length", "0"))
                form = parse_qs(self.rfile.read(length).decode())
                code = (form.get("code") or [""])[0]
                if code not in simulator._codes:
                    self._json(400, {"error": "invalid_grant"})
                    return
                simulator._codes.remove(code)
                token = simulator._access_token()
                self._json(
                    200,
                    {
                        "access_token": token,
                        "id_token": token,
                        "token_type": "Bearer",
                        "expires_in": 3600,
                        "scope": "openid",
                    },
                )

            def _json(self, status: int, payload: dict[str, Any]) -> None:
                body = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        return Handler


def complete_dex_login(
    *,
    authorization_endpoint: str,
    token_endpoint: str,
    client_id: str,
    client_secret: str,
    ca_file: str,
    redirect_uri: str = "http://127.0.0.1:9/callback",
    scope: str = "openid",
) -> str:
    """Finish Dex mock-connector authorize flow; return the upstream access token."""
    state = secrets.token_urlsafe(16)
    with httpx.Client(
        follow_redirects=False,
        trust_env=False,
        verify=ssl_context_for_cert(ca_file),
        timeout=30.0,
    ) as client:
        location = _follow_until_redirect(
            client,
            authorization_endpoint,
            params={
                "response_type": "code",
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "scope": scope,
                "state": state,
            },
            stop_prefix=redirect_uri,
        )
        returned = parse_qs(urlparse(location).query)
        code = (returned.get("code") or [""])[0]
        if not code:
            raise RuntimeError(f"Dex login did not return a code: {location}")
        token_response = client.post(
            token_endpoint,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": client_id,
                "client_secret": client_secret,
            },
        )
        token_response.raise_for_status()
        access_token = token_response.json().get("access_token")
        if not access_token:
            raise RuntimeError("Dex token response did not include access_token")
        return str(access_token)


def complete_mcp_oauth_login(
    *,
    mcp_origin: str,
    ca_file: str,
    redirect_uri: str = "http://127.0.0.1:9/callback",
    scope: str | None = None,
) -> str:
    """Register a DCR client, finish the proxy redirect chain, return the MCP access token."""
    verifier = secrets.token_urlsafe(64)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    state = secrets.token_urlsafe(16)
    registration_body: dict[str, Any] = {
        "redirect_uris": [redirect_uri],
        "client_name": "mcp-redfish-oidc-simulator",
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
    }
    if scope:
        registration_body["scope"] = scope
    with httpx.Client(
        follow_redirects=False,
        trust_env=False,
        verify=ssl_context_for_cert(ca_file),
        timeout=30.0,
    ) as client:
        metadata = client.get(f"{mcp_origin}/.well-known/oauth-authorization-server")
        metadata.raise_for_status()
        as_meta = metadata.json()
        registration = client.post(
            as_meta["registration_endpoint"],
            json=registration_body,
        )
        registration.raise_for_status()
        client_id = registration.json()["client_id"]
        authorize_url = as_meta["authorization_endpoint"]
        params = {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        if scope:
            params["scope"] = scope
        location = _follow_until_redirect(
            client,
            authorize_url,
            params=params,
            stop_prefix=redirect_uri,
        )
        returned = parse_qs(urlparse(location).query)
        code = (returned.get("code") or [""])[0]
        if not code:
            raise RuntimeError(f"OAuth login did not return a code: {location}")
        token_response = client.post(
            as_meta["token_endpoint"],
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": client_id,
                "code_verifier": verifier,
            },
        )
        token_response.raise_for_status()
        access_token = token_response.json().get("access_token")
        if not access_token:
            raise RuntimeError("OAuth token response did not include access_token")
        return str(access_token)


def _follow_until_redirect(
    client: httpx.Client,
    url: str,
    *,
    params: dict[str, str],
    stop_prefix: str,
    max_hops: int = 12,
) -> str:
    response = client.get(url, params=params)
    for _ in range(max_hops):
        if response.status_code not in (301, 302, 303, 307, 308):
            raise RuntimeError(
                f"OAuth redirect chain stopped at HTTP {response.status_code}: "
                f"{response.text[:400]}"
            )
        location = response.headers.get("location")
        if not location:
            raise RuntimeError("OAuth redirect was missing a Location header")
        location = urljoin(str(response.url), location)
        if location.startswith(stop_prefix):
            return location
        response = client.get(location)
    raise RuntimeError("OAuth redirect chain exceeded the hop limit")
