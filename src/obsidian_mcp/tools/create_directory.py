"""`create-directory` tool. Ported from TS `tools/create-directory/index.ts`.

TS's original implementation skipped the shared `validateVaultPath`/`safeJoinPath`
utilities here and used a weaker inline `startsWith` check with no symlink
resolution -- a confirmed inconsistency. This port routes through the shared
`validate_vault_path` like every other tool instead of replicating that weakness.
"""

from __future__ import annotations

import os

import anyio
from mcp.server.mcpserver import MCPServer
from mcp.shared.exceptions import MCPError
from mcp.types import INVALID_REQUEST
from pydantic import BaseModel, ConfigDict, Field, field_validator

from obsidian_mcp.registry import validate
from obsidian_mcp.utils.errors import handle_fs_error
from obsidian_mcp.utils.files import file_exists
from obsidian_mcp.utils.path_safety import validate_vault_path
from obsidian_mcp.vault_resolver import VaultResolver


class CreateDirectoryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vault: str = Field(..., min_length=1, description="Name of the vault where the directory should be created")
    path: str = Field(..., min_length=1, description="Path of the directory to create (relative to vault root)")
    recursive: bool = Field(True, description="Create parent directories if they don't exist")

    @field_validator("path")
    @classmethod
    def _relative(cls, value: str) -> str:
        if os.path.isabs(value):
            raise ValueError("Directory path must be relative to vault root")
        return value


def register(mcp: MCPServer, vaults: dict[str, str]) -> None:
    resolver = VaultResolver(vaults)

    async def create_directory(vault: str, path: str, recursive: bool = True) -> str:
        args = validate(CreateDirectoryInput, vault=vault, path=path, recursive=recursive)
        vault_path = resolver.resolve_vault(args.vault)

        full_path = os.path.join(vault_path, args.path)
        validate_vault_path(vault_path, full_path)

        try:
            if await file_exists(full_path):
                raise MCPError(INVALID_REQUEST, f"A directory already exists at: {full_path}")
            await anyio.Path(full_path).mkdir(parents=args.recursive, exist_ok=False)
        except OSError as exc:
            handle_fs_error(exc, "create directory")

        return f"Successfully created directory at: {full_path}"

    mcp.add_tool(
        create_directory,
        name="create-directory",
        description="Create a new directory in the specified vault",
        structured_output=False,
    )
