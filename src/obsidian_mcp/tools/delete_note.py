"""`delete-note` tool. Ported from TS `tools/delete-note/index.ts`."""

from __future__ import annotations

import os

import anyio
from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, ConfigDict, Field, field_validator

from obsidian_mcp.registry import validate
from obsidian_mcp.utils.backup import soft_delete_to_trash
from obsidian_mcp.utils.errors import create_note_not_found_error, handle_fs_error
from obsidian_mcp.utils.files import file_exists
from obsidian_mcp.utils.links import update_vault_links
from obsidian_mcp.utils.path_safety import (
    ensure_markdown_extension,
    validate_vault_path,
)
from obsidian_mcp.vault_resolver import VaultResolver


class DeleteNoteInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vault: str = Field(..., min_length=1, description="Name of the vault containing the note")
    path: str = Field(..., min_length=1, description="Path of the note relative to vault root (e.g., 'folder/note.md')")
    reason: str | None = Field(None, description="Optional reason for deletion (stored in trash metadata)")
    permanent: bool = Field(False, description="Whether to permanently delete instead of moving to trash")

    @field_validator("path")
    @classmethod
    def _path_relative(cls, value: str) -> str:
        if os.path.isabs(value):
            raise ValueError("Path must be relative to vault root")
        return value


def register(mcp: MCPServer, vaults: dict[str, str]) -> None:
    resolver = VaultResolver(vaults)

    async def delete_note(vault: str, path: str, reason: str | None = None, permanent: bool = False) -> str:
        args = validate(DeleteNoteInput, vault=vault, path=path, reason=reason, permanent=permanent)
        vault_path = resolver.resolve_vault(args.vault)

        note_path = ensure_markdown_extension(args.path)
        full_path = os.path.join(vault_path, note_path)
        validate_vault_path(vault_path, full_path)

        if not await file_exists(full_path):
            raise create_note_not_found_error(note_path)

        try:
            updated_files = await update_vault_links(vault_path, note_path, None)

            if args.permanent:
                await anyio.Path(full_path).unlink()
                plural = "" if updated_files == 1 else "s"
                return f'Permanently deleted note "{note_path}"\nUpdated {updated_files} file{plural} with broken links'

            trash_name = await soft_delete_to_trash(vault_path, note_path, args.reason)
            plural = "" if updated_files == 1 else "s"
            return f'Moved note "{note_path}" to trash as "{trash_name}"\nUpdated {updated_files} file{plural} with broken links'
        except OSError as exc:
            handle_fs_error(exc, "delete note")
            raise  # unreachable

    mcp.add_tool(
        delete_note,
        name="delete-note",
        description="Delete a note, moving it to .trash by default or permanently deleting if specified",
        structured_output=False,
    )
