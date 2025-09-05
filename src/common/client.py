# Copyright 2025 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause

import redfish
from redfish.rest.v1 import AuthMethod
from fastmcp.exceptions import ToolError, ValidationError

class RedfishClient:
    def __init__(self, server_cfg, common_cfg):
        self.server_cfg = server_cfg
        self.common_cfg = common_cfg
        self.client = None
        self._setup_client()

    def _setup_client(self):
        auth_method = self.server_cfg.get("auth_method") or self.common_cfg.REDFISH_CFG.get("auth_method")
        if auth_method not in (AuthMethod.BASIC, AuthMethod.SESSION):
            raise ValidationError(f"Invalid auth_method: {auth_method}. Allowed values: {AuthMethod.BASIC}, {AuthMethod.SESSION}")
        username = self.server_cfg.get("username") or self.common_cfg.REDFISH_CFG.get("username")
        password = self.server_cfg.get("password") or self.common_cfg.REDFISH_CFG.get("password")
        port = self.server_cfg.get("port") or self.common_cfg.REDFISH_CFG.get("port", 443)
        base_url = f"https://{self.server_cfg.get('address')}:{port}"
        try:
            self.client = redfish.redfish_client(base_url=base_url, username=username, password=password, default_prefix="/redfish/v1")
        except Exception as e:
            raise ToolError(f"Failed to create Redfish client: {e}")
        ca_cert = self.server_cfg.get("tls_server_ca_cert") or self.common_cfg.REDFISH_CFG.get("tls_server_ca_cert")
        if ca_cert:
            self.client.cafile = ca_cert
        try:
            self.client.login(auth=auth_method)
        except Exception as e:
            raise ToolError(f"Redfish login failed: {e}")

    def get(self, resource_path):
        try:
            response = self.client.get(resource_path)
        except Exception as e:
            raise ToolError(f"Redfish GET request failed: {e}")
        return response

    def logout(self):
        if self.client:
            try:
                self.client.logout()
            except Exception:
                pass
