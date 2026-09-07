# Copyright 2025 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause

"""HTTPS OpenID simulator speaks discovery, authorize, and token locally."""

from __future__ import annotations

import base64
import json
import socket
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
from fastmcp.server.auth.providers.jwt import RSAKeyPair

from test.common.oidc_simulator import (
    AUDIENCE,
    HttpsOidcSimulator,
    ssl_context_for_cert,
)
from test.utils import write_self_signed_tls_pair


def _jwt_claims(token: str) -> dict[str, object]:
    payload = token.split(".")[1]
    padded = payload + "=" * (-len(payload) % 4)
    return dict(json.loads(base64.urlsafe_b64decode(padded)))


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_https_oidc_simulator_issues_jwt_after_code_redirect(tmp_path: Path) -> None:
    certfile, keyfile = write_self_signed_tls_pair(str(tmp_path))
    keypair = RSAKeyPair.generate()
    with HttpsOidcSimulator(
        port=_free_port(),
        certfile=certfile,
        keyfile=keyfile,
        keypair=keypair,
    ) as idp:
        with httpx.Client(
            follow_redirects=False,
            trust_env=False,
            verify=ssl_context_for_cert(idp.certfile),
        ) as client:
            discovery = client.get(idp.discovery_url())
            assert discovery.status_code == 200
            body = discovery.json()
            assert body["issuer"] == idp.issuer
            assert body["authorization_endpoint"] == idp.authorization_endpoint()
            assert body["token_endpoint"] == idp.token_endpoint()
            assert body["jwks_uri"].endswith("/jwks")
            assert "RS256" in body["id_token_signing_alg_values_supported"]

            jwks = client.get(body["jwks_uri"])
            assert jwks.status_code == 200
            assert jwks.json()["keys"][0]["kty"] == "RSA"

            authorize = client.get(
                idp.authorization_endpoint(),
                params={
                    "response_type": "code",
                    "client_id": "mcp-redfish-e2e",
                    "redirect_uri": "http://127.0.0.1:9/callback",
                    "state": "txn-1",
                },
            )
            assert authorize.status_code == 302
            location = authorize.headers["location"]
            assert location.startswith("http://127.0.0.1:9/callback")
            code = parse_qs(urlparse(location).query)["code"][0]

            token = client.post(
                idp.token_endpoint(),
                data={"grant_type": "authorization_code", "code": code},
            )
            assert token.status_code == 200
            access_token = token.json()["access_token"]
            claims = _jwt_claims(access_token)
            assert claims["iss"] == idp.issuer
            assert claims["aud"] == AUDIENCE

            replay = client.post(
                idp.token_endpoint(),
                data={"grant_type": "authorization_code", "code": code},
            )
            assert replay.status_code == 400
