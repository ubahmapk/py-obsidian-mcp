"""`read-note` tool. Ported from TS `tools/read-note/index.ts`."""

from __future__ import annotations

import os

import anyio
from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, ConfigDict, Field, field_validator

from obsidian_mcp.registry import validate
from obsidian_mcp.utils.errors import create_note_not_found_error, handle_fs_error
from obsidian_mcp.utils.files import file_exists
from obsidian_mcp.utils.path_safety import (
    ensure_markdown_extension,
    validate_vault_path,
)
from obsidian_mcp.utils.responses import FileOperationResult, format_file_result
from obsidian_mcp.vault_resolver import VaultResolver


class ReadNoteInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vault: str = Field(..., min_length=1, description="Name of the vault containing the note")
    filename: str = Field(
        ...,
        min_length=1,
        description="Just the note name without any path separators (e.g. 'my-note.md', NOT 'folder/my-note.md')",
    )
    folder: str | None = Field(None, description="Optional subfolder path relative to vault root")

    @field_validator("filename")
    @classmethod
    def _no_path_separators(cls, value: str) -> str:
        if "/" in value or "\\" in value:
            raise ValueError("Filename cannot contain path separators - use the 'folder' parameter for paths instead")
        return value

    @field_validator("folder")
    @classmethod
    def _folder_relative(cls, value: str | None) -> str | None:
        if value and os.path.isabs(value):
            raise ValueError("Folder must be a relative path")
        return value


def register(mcp: MCPServer, vaults: dict[str, str]) -> None:
    resolver = VaultResolver(vaults)

    async def read_note(vault: str, filename: str, folder: str | None = None) -> str:
        args = validate(ReadNoteInput, vault=vault, filename=filename, folder=folder)
        vault_path = resolver.resolve_vault(args.vault)

        sanitized_filename = ensure_markdown_extension(args.filename)
        full_path = os.path.join(vault_path, args.folder, sanitized_filename) if args.folder else os.path.join(
            vault_path, sanitized_filename
        )
        validate_vault_path(vault_path, full_path)

        try:
            if not await file_exists(full_path):
                raise create_note_not_found_error(args.filename)
            content = await anyio.Path(full_path).read_text(encoding="utf-8")
        except OSError as exc:
            handle_fs_error(exc, "read note")
            raise  # unreachable, handle_fs_error always raises

        result = FileOperationResult(success=True, message="Note read successfully", operation="edit", path=full_path)
        return f"{content}\n\n{format_file_result(result)}"

    mcp.add_tool(
        read_note,
        name="read-note",
        description=(
            "Read the content of an existing note in the vault.\n\n"
            "Examples:\n"
            "- Root note: { \"vault\": \"vault1\", \"filename\": \"note.md\" }\n"
            "- Subfolder note: { \"vault\": \"vault1\", \"filename\": \"note.md\", \"folder\": \"journal/2024\" }\n"
            "- INCORRECT: { \"filename\": \"journal/2024/note.md\" } (don't put path in filename)"
        ),
        structured_output=False,
    )
