# Copyright 2025 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause

import urllib
from dotenv import load_dotenv
import os
import json

load_dotenv()

MCP_TRANSPORT = os.getenv('MCP_TRANSPORT', 'stdio')

REDFISH_CFG = {"hosts": os.getenv('REDFISH_HOSTS', '[{"address": "127.0.0.1"}]'),
             "port": int(os.getenv('REDFISH_PORT', 443)),
             "username": os.getenv('REDFISH_USERNAME', ""),
             "password": os.getenv('REDFISH_PASSWORD',''),
             "tls_server_ca_cert": os.getenv('REDFISH_SERVER_CA_CERT', None)}

def get_hosts():
    """Get the list of hosts from the REDFISH_CFG."""
    hosts = REDFISH_CFG.get("hosts", [])
    if isinstance(hosts, str):
        try:
            hosts = json.loads(hosts)
        except json.JSONDecodeError:
            hosts = []
    return hosts