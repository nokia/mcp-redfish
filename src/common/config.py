# Copyright 2025 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause

"""
Configuration loader for MCP Redfish client.
Loads settings from environment variables, with sensible defaults.
"""

import os
import json
import logging
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()

MCP_TRANSPORT = os.getenv('MCP_TRANSPORT', 'stdio')

# Parse hosts as JSON, handle errors gracefully
hosts_env = os.getenv('REDFISH_HOSTS', '[{"address": "127.0.0.1"}]')
try:
    hosts = json.loads(hosts_env)
    if not isinstance(hosts, list):
        raise ValueError("REDFISH_HOSTS must be a JSON list")
except Exception as e:
    logger.error(f"Failed to parse REDFISH_HOSTS: {e}")
    hosts = [{"address": "127.0.0.1"}]

REDFISH_CFG = {
    "hosts": hosts,
    "port": int(os.getenv('REDFISH_PORT', 443)),
    "auth_method": os.getenv('REDFISH_AUTH_METHOD', 'session'),
    "username": os.getenv('REDFISH_USERNAME', ""),
    "password": os.getenv('REDFISH_PASSWORD', ''),
    "tls_server_ca_cert": os.getenv('REDFISH_SERVER_CA_CERT', None)
}
