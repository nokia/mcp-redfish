# Copyright 2025 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause

"""
Tools module for MCP Redfish server.
Imports all tool modules to register them with the MCP server.
"""

# Import all tool modules to register them with MCP
from . import (
    get,  # noqa: F401
    servers,  # noqa: F401
)
