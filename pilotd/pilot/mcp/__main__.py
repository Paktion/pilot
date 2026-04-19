"""
MCP entry: ``python -m pilot.mcp``.

Stdio JSON-RPC server with 4 fail-closed tools. Transport proxies to the
same Unix socket the SwiftUI app uses — the MCP server is just a second
client, with its own permission filter.

Register with Claude Code:

    claude mcp add --transport stdio pilot -- python -m pilot.mcp
"""

from __future__ import annotations

import logging
import sys

from pilot import prompts
from pilot.mcp.server import MCPServer


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    # Populate env from .env if present (MCP servers inherit env from the
    # launching client, which may not include our local .env).
    prompts.load_env()
    server = MCPServer()
    try:
        server.serve()
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
