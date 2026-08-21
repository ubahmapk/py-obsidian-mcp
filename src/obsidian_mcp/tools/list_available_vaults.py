"""`list-available-vaults` tool. Ported from TS `tools/list-available-vaults/index.ts`."""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer


def register(mcp: MCPServer, vaults: dict[str, str]) -> None:
    async def list_available_vaults() -> str:
        if not vaults:
            return "No vaults are currently available"
        lines = ["Available vaults:"] + [f"  - {name}" for name in vaults]
        return "\n".join(lines)

    mcp.add_tool(
        list_available_vaults,
        name="list-available-vaults",
        description="Lists all available vaults that can be used with other tools",
        structured_output=False,
    )
