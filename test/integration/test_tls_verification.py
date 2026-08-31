# Copyright 2025 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause

"""
Self-contained TLS verification integration tests.
"""

import json
import os
import ssl
import sys
import tempfile
import threading
import unittest
import warnings
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from unittest.mock import patch

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from fastmcp.exceptions import ToolError
from tenacity import RetryError
from urllib3.exceptions import InsecureRequestWarning

# Patch sys.path to import from src
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src"))
)

from src.common.client import RedfishClient


class RogueRedfishServer:
    """Tiny HTTPS Redfish-like server with an untrusted, wrong-host certificate."""

    def __init__(self) -> None:
        self.login_bodies: list[dict[str, Any]] = []
        self._temp_dir = tempfile.TemporaryDirectory()
        cert_path, key_path = self._write_certificate(Path(self._temp_dir.name))

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler_class())
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certfile=cert_path, keyfile=key_path)
        self.server.socket = context.wrap_socket(self.server.socket, server_side=True)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def port(self) -> int:
        return self.server.server_port

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self._temp_dir.cleanup()

    def _handler_class(self):
        login_bodies = self.login_bodies

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_GET(self) -> None:
                if self.path.rstrip("/") != "/redfish/v1":
                    self.send_error(404)
                    return

                self._send_json(
                    200,
                    {
                        "@odata.id": "/redfish/v1/",
                        "@odata.type": "#ServiceRoot.v1_0_0.ServiceRoot",
                        "Id": "RootService",
                        "Name": "Rogue Redfish Service",
                        "SessionService": {"@odata.id": "/redfish/v1/SessionService"},
                    },
                )

            def do_POST(self) -> None:
                if self.path != "/redfish/v1/SessionService/Sessions":
                    self.send_error(404)
                    return

                content_length = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(content_length).decode("utf-8")
                login_bodies.append(json.loads(body))

                self._send_json(
                    201,
                    {"@odata.id": "/redfish/v1/SessionService/Sessions/1"},
                    {
                        "X-Auth-Token": "rogue-session-token",
                        "Location": "/redfish/v1/SessionService/Sessions/1",
                    },
                )

            def do_DELETE(self) -> None:
                if self.path != "/redfish/v1/SessionService/Sessions/1":
                    self.send_error(404)
                    return

                self.send_response(204)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, format: str, *args: Any) -> None:
                return

            def _send_json(
                self,
                status: int,
                payload: dict[str, Any],
                headers: dict[str, str] | None = None,
            ) -> None:
                body = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                if headers:
                    for name, value in headers.items():
                        self.send_header(name, value)
                self.end_headers()
                self.wfile.write(body)

        return Handler

    def _write_certificate(self, temp_dir: Path) -> tuple[str, str]:
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = issuer = x509.Name(
            [
                x509.NameAttribute(
                    NameOID.COMMON_NAME, "totally-not-the-real-bmc.invalid"
                )
            ]
        )
        certificate = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.now(UTC) - timedelta(minutes=1))
            .not_valid_after(datetime.now(UTC) + timedelta(days=1))
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), True)
            .add_extension(
                x509.SubjectAlternativeName(
                    [x509.DNSName("totally-not-the-real-bmc.invalid")]
                ),
                False,
            )
            .add_extension(
                x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), False
            )
            .sign(key, hashes.SHA256())
        )

        cert_path = temp_dir / "rogue-cert.pem"
        key_path = temp_dir / "rogue-key.pem"
        cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
        key_path.write_bytes(
            key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )
        return str(cert_path), str(key_path)


class TestTLSVerificationAgainstRogueServer(unittest.TestCase):
    def setUp(self) -> None:
        self.server = RogueRedfishServer()
        self.server.start()
        self.server_cfg = {
            "address": "127.0.0.1",
            "port": self.server.port,
            "username": "bmc-admin",
            "password": "SuperSecretBmcPassw0rd",
            "auth_method": "session",
        }
        self.common_cfg = type(
            "Config",
            (),
            {
                "REDFISH_CFG": {
                    "auth_method": "session",
                    "username": "",
                    "password": "",
                    "port": 443,
                    "tls_verify": True,
                    "tls_server_ca_cert": None,
                }
            },
        )()

    def tearDown(self) -> None:
        self.server.stop()

    @patch("redfish.rest.v1.time.sleep", return_value=None)
    def test_default_tls_verification_rejects_rogue_server(self, _mock_sleep) -> None:
        with self.assertRaises((RetryError, ToolError, ssl.SSLError)):
            RedfishClient(self.server_cfg, self.common_cfg)

        self.assertEqual(self.server.login_bodies, [])

    def test_explicit_tls_verification_opt_out_allows_rogue_server(self) -> None:
        insecure_server_cfg = self.server_cfg.copy()
        insecure_server_cfg["tls_verify"] = False

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", InsecureRequestWarning)
            client = RedfishClient(insecure_server_cfg, self.common_cfg)
            try:
                self.assertEqual(
                    self.server.login_bodies,
                    [
                        {
                            "UserName": "bmc-admin",
                            "Password": "SuperSecretBmcPassw0rd",
                        }
                    ],
                )
            finally:
                client.logout()


if __name__ == "__main__":
    unittest.main()
