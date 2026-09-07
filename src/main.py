# Copyright 2025 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause

"""
Main entry point for Redfish MCP server.
Handles SSDP discovery and MCP server startup.
"""

import logging
import os
import sys
import threading
import time
import warnings

from . import tools  # noqa: F401 - Import tools to register them with MCP server
from .common.config import MCP_CONFIG, MCP_TRANSPORT, REDFISH_CONFIG
from .common.discovery import SSDPDiscovery
from .common.logging_utils import configure_sensitive_data_filter
from .common.server import mcp
from .common.validation import (
    ConfigurationError,
    effective_bind_host,
    effective_bind_port,
    fatal_configuration_error,
    is_http_transport,
    validate_auth_for_transport,
)

logger = logging.getLogger(__name__)

_PYTHON_3_13_DEPRECATION_MESSAGE = (
    "Python 3.13 support is deprecated and will be removed in a future release. "
    "Python 3.14 or later is recommended and fully supported. "
    "See docs/PYTHON_RUNTIME.md for details."
)


def _safe_traceback_locations(error: BaseException) -> str:
    """Return call locations without exception messages or local values."""
    locations: list[str] = []
    traceback = error.__traceback__
    while traceback is not None:
        frame = traceback.tb_frame
        locations.append(
            f"{frame.f_code.co_filename}:{traceback.tb_lineno}:{frame.f_code.co_name}"
        )
        traceback = traceback.tb_next
    return " <- ".join(locations) or "unavailable"


def _warn_deprecated_python_runtime() -> None:
    """Warn when running on a Python version scheduled for removal."""
    if sys.version_info < (3, 14):
        warnings.warn(
            _PYTHON_3_13_DEPRECATION_MESSAGE,
            FutureWarning,
            stacklevel=2,
        )
        logger.warning(_PYTHON_3_13_DEPRECATION_MESSAGE)


class RedfishMCPServer:
    """
    Main Redfish MCP server class. Handles SSDP discovery and MCP server startup.
    """

    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)
        self.logger.info("Starting the RedfishMCPServer")
        self.discovery_enabled = (
            os.environ.get("REDFISH_DISCOVERY_ENABLED", "false").lower() == "true"
        )
        self.discovery_interval = int(
            os.environ.get("REDFISH_DISCOVERY_INTERVAL", "30")
        )
        self.discovery_thread = None
        if self.discovery_enabled:
            self.discovery_thread = threading.Thread(
                target=self._run_discovery, daemon=True
            )
            self.discovery_thread.start()

    def _run_discovery(self) -> None:
        """
        Periodically runs SSDP discovery in a background thread.
        """
        while True:
            try:
                discovery = SSDPDiscovery()
                hosts = discovery.discover()
                self.logger.info(f"[SSDP Discovery] Found hosts: {hosts}")
            except Exception as e:
                self.logger.error(
                    "[SSDP Discovery] failed: error_type=%s", type(e).__name__
                )
                self.logger.debug(
                    "[SSDP Discovery] failure locations: %s",
                    _safe_traceback_locations(e),
                )
            time.sleep(self.discovery_interval)

    def run(self) -> None:
        """
        Starts the MCP server with the configured transport.
        """
        try:
            if not is_http_transport(MCP_TRANSPORT):
                self.logger.info(
                    "MCP Server transport starting: transport=stdio "
                    "http_authentication=not_applicable"
                )
                mcp.run(transport=MCP_TRANSPORT)
                return

            from .common.auth import apply_provider, emit_startup_logs, http_run_kwargs

            configured_auth = (
                MCP_CONFIG.auth if MCP_CONFIG.transport == MCP_TRANSPORT else None
            )
            auth = validate_auth_for_transport(MCP_TRANSPORT, configured_auth)
            apply_provider(mcp, auth)
            host = effective_bind_host()
            port = effective_bind_port()
            emit_startup_logs(MCP_TRANSPORT, auth, host, port)
            mcp.run(transport=MCP_TRANSPORT, **http_run_kwargs(auth))
        except ConfigurationError as e:
            # AuthConfigurationError is a ConfigurationError. Report through the
            # shared helper so a rule re-checked here reads exactly as it does
            # when the same rule rejects the configuration during import.
            raise fatal_configuration_error(e) from None
        except SystemExit:
            raise
        except Exception as e:
            # A server that failed to start must not report success: a
            # supervisor or Kubernetes would otherwise treat this MCP Server as
            # healthy and never restart it.
            self.logger.error(
                "MCP Server failed to start: error_type=%s", type(e).__name__
            )
            self.logger.debug(
                "MCP Server startup failure locations: %s",
                _safe_traceback_locations(e),
            )
            sys.exit(1)


def main() -> None:
    """
    Main entry point for the Redfish MCP server.
    """
    # Configure logging to stderr
    log_level = os.getenv("MCP_REDFISH_LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(message)s",
    )
    configure_sensitive_data_filter()
    logger.info(
        "MCP Server configuration: transport=%s log_level=%s "
        "redfish_target_count=%d discovery_enabled=%s",
        MCP_TRANSPORT,
        log_level,
        len(REDFISH_CONFIG.hosts),
        REDFISH_CONFIG.discovery_enabled,
    )
    _warn_deprecated_python_runtime()
    server = RedfishMCPServer()
    server.run()


if __name__ == "__main__":
    main()
