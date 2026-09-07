# Copyright 2025 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause

"""Shared fixtures for in-process MCP HTTP integration tests."""

from __future__ import annotations

import socket
import threading
import time

import pytest
import uvicorn

from src.common.server import mcp

JWT_ISSUER = "https://issuer.example"
JWT_AUDIENCE = "mcp-redfish"

PROTOCOL_CONNECT_MODES = ("legacy", "auto", "2026-07-28")


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_for_port(host: str, port: int, timeout: float = 10.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.05)
    raise TimeoutError(f"Port {host}:{port} did not open")


class HttpMcpServer:
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
        wait_for_port("127.0.0.1", self.port)
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
    servers: list[HttpMcpServer] = []

    def _start(port: int, path: str = "/mcp") -> HttpMcpServer:
        server = HttpMcpServer(port, path)
        server.start()
        servers.append(server)
        return server

    yield _start

    for server in reversed(servers):
        server.close()
