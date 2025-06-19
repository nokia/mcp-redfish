# Copyright 2025 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause

import sys

from common.server import mcp
import tools.endpoints
import tools.get
from common.config import MCP_TRANSPORT


class RedfishMCPServer:
    def __init__(self):
        print("Starting the RedfishMCPServer", file=sys.stderr)

    def run(self):
        try:
            mcp.run(transport=MCP_TRANSPORT)
        except Exception as e:
            print(f"Error running mcp: {e}", file=sys.stderr)

def main():
    server = RedfishMCPServer()
    server.run()

if __name__ == "__main__":
    main()