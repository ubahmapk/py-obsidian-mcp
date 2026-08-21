"""`obsidian-vault://` resource scheme.

Ported from TS `resources/resources.ts` -- the implementation that was actually
wired into `server.ts`. TS also had an orphaned near-duplicate at
`resources/vault/index.ts` (subtly missing the root-list special case, and never
imported by `server.ts`); this module is the single Python implementation, based
on the one that was actually live.
"""

from __future__ import annotations

import json
import os

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.resources import FunctionResource


def register(mcp: MCPServer, vaults: dict[str, str]) -> None:
    async def root() -> str:
        vault_list = [{"name": name, "path": path, "isAccessible": os.access(path, os.F_OK)} for name, path in vaults.items()]
        return json.dumps({"totalVaults": len(vaults), "vaults": vault_list}, indent=2)

    mcp.add_resource(
        FunctionResource.from_function(
            root,
            uri="obsidian-vault://",
            name="Available Vaults",
            description="List of all available Obsidian vaults and their access status",
            mime_type="application/json",
        )
    )

    for vault_name, vault_path in vaults.items():
        def make_vault_resource(name: str, path: str):
            async def read_vault() -> str:
                return json.dumps({"name": name, "path": path, "isAccessible": os.access(path, os.F_OK)}, indent=2)

            return read_vault

        mcp.add_resource(
            FunctionResource.from_function(
                make_vault_resource(vault_name, vault_path),
                uri=f"obsidian-vault://{vault_name}",
                name=vault_name,
                description=f"Access information for the {vault_name} vault",
                mime_type="application/json",
            )
        )
