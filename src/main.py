
# Copyright 2025 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause

"""
Main entry point for Redfish MCP server.
Handles SSDP discovery and MCP server startup.
"""

import os
import threading
import time
import logging
from common.discovery import SSDPDiscovery
from common.server import mcp
import tools.servers
import tools.get
from common.config import MCP_TRANSPORT



class RedfishMCPServer:
    """
    Main Redfish MCP server class. Handles SSDP discovery and MCP server startup.
    """
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.logger.info("Starting the RedfishMCPServer")
        self.discovery_enabled = os.environ.get("REDFISH_DISCOVERY_ENABLED", "false").lower() == "true"
        self.discovery_interval = int(os.environ.get("REDFISH_DISCOVERY_INTERVAL", "30"))
        self.discovery_thread = None
        if self.discovery_enabled:
            self.discovery_thread = threading.Thread(target=self._run_discovery, daemon=True)
            self.discovery_thread.start()

    def _run_discovery(self):
        """
        Periodically runs SSDP discovery in a background thread.
        """
        while True:
            try:
                discovery = SSDPDiscovery()
                hosts = discovery.discover()
                self.logger.info(f"[SSDP Discovery] Found hosts: {hosts}")
            except Exception as e:
                self.logger.error(f"[SSDP Discovery] Error: {e}")
            time.sleep(self.discovery_interval)

    def run(self):
        """
        Starts the MCP server with the configured transport.
        """
        try:
            mcp.run(transport=MCP_TRANSPORT)
        except Exception as e:
            self.logger.error(f"Error running mcp: {e}")

def main():
    """
    Main entry point for the Redfish MCP server.
    """
    # Configure logging to stderr
    log_level = os.getenv('MCP_REDFISH_LOG_LEVEL', 'INFO').upper()
    logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO), format='%(asctime)s %(levelname)s %(message)s')
    server = RedfishMCPServer()
    server.run()

if __name__ == "__main__":
    main()