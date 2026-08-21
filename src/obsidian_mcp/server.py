"""Server construction, mirroring TS `server.ts` (minus the rate limiter and
connection monitor -- see the plan's Decisions table for why those aren't ported).
"""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from obsidian_mcp import resources
from obsidian_mcp.prompts import list_vaults
from obsidian_mcp.tools import register_all


def build_server(vaults: dict[str, str]) -> MCPServer:
    if not vaults:
        raise ValueError("No vault configurations provided. At least one valid Obsidian vault is required.")

    mcp = MCPServer("obsidian-mcp", version="0.1.0")

    register_all(mcp, vaults)
    resources.register(mcp, vaults)
    list_vaults.register(mcp, vaults)

    return mcp
