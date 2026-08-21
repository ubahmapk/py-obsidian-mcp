"""`move-note` tool. Ported from TS `tools/move-note/index.ts`."""

from __future__ import annotations

import os

import anyio
from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, ConfigDict, Field, field_validator

from obsidian_mcp.registry import validate
from obsidian_mcp.utils.errors import (
    create_note_exists_error,
    create_note_not_found_error,
    handle_fs_error,
)
from obsidian_mcp.utils.files import ensure_directory, file_exists
from obsidian_mcp.utils.links import update_vault_links
from obsidian_mcp.utils.path_safety import (
    ensure_markdown_extension,
    validate_vault_path,
)
from obsidian_mcp.vault_resolver import VaultResolver


class MoveNoteInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vault: str = Field(..., min_length=1, description="Name of the vault containing the note")
    source: str = Field(..., min_length=1, description="Source path of the note relative to vault root")
    destination: str = Field(..., min_length=1, description="Destination path relative to vault root")

    @field_validator("source", "destination")
    @classmethod
    def _relative(cls, value: str) -> str:
        if os.path.isabs(value):
            raise ValueError("Path must be relative to the vault root")
        return value


def register(mcp: MCPServer, vaults: dict[str, str]) -> None:
    resolver = VaultResolver(vaults)

    async def move_note(vault: str, source: str, destination: str) -> str:
        args = validate(MoveNoteInput, vault=vault, source=source, destination=destination)
        vault_path = resolver.resolve_vault(args.vault)

        source_rel = ensure_markdown_extension(args.source)
        destination_rel = ensure_markdown_extension(args.destination)
        full_source_path = os.path.join(vault_path, source_rel)
        full_dest_path = os.path.join(vault_path, destination_rel)

        validate_vault_path(vault_path, full_source_path)
        validate_vault_path(vault_path, full_dest_path)

        try:
            if not await file_exists(full_source_path):
                raise create_note_not_found_error(source_rel)
            if await file_exists(full_dest_path):
                raise create_note_exists_error(destination_rel)

            await ensure_directory(os.path.dirname(full_dest_path))
            await anyio.Path(full_source_path).rename(full_dest_path)

            updated_files = await update_vault_links(vault_path, source_rel, destination_rel)
            plural = "" if updated_files == 1 else "s"
            return f'Successfully moved note from "{source_rel}" to "{destination_rel}"\nUpdated links in {updated_files} file{plural}'
        except OSError as exc:
            handle_fs_error(exc, "move note")
            raise  # unreachable

    mcp.add_tool(
        move_note,
        name="move-note",
        description="Move/rename a note while preserving links",
        structured_output=False,
    )
