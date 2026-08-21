"""`create-note` tool. Ported from TS `tools/create-note/index.ts`."""

from __future__ import annotations

import os

import anyio
from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, ConfigDict, Field, field_validator

from obsidian_mcp.registry import validate
from obsidian_mcp.utils.errors import create_note_exists_error, handle_fs_error
from obsidian_mcp.utils.files import ensure_directory, file_exists
from obsidian_mcp.utils.path_safety import (
    ensure_markdown_extension,
    validate_vault_path,
)
from obsidian_mcp.utils.responses import FileOperationResult, format_file_result
from obsidian_mcp.vault_resolver import VaultResolver


class CreateNoteInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vault: str = Field(..., min_length=1, description="Name of the vault to create the note in")
    filename: str = Field(
        ...,
        min_length=1,
        description="Just the note name without any path separators. Will add .md extension if missing",
    )
    content: str = Field(..., min_length=1, description="Content of the note in markdown format")
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

    async def create_note(vault: str, filename: str, content: str, folder: str | None = None) -> str:
        args = validate(CreateNoteInput, vault=vault, filename=filename, content=content, folder=folder)
        vault_path = resolver.resolve_vault(args.vault)

        sanitized_filename = ensure_markdown_extension(args.filename)
        note_path = (
            os.path.join(vault_path, args.folder, sanitized_filename)
            if args.folder
            else os.path.join(vault_path, sanitized_filename)
        )
        validate_vault_path(vault_path, note_path)

        try:
            await ensure_directory(os.path.dirname(note_path))
            if await file_exists(note_path):
                raise create_note_exists_error(note_path)
            await anyio.Path(note_path).write_text(args.content, encoding="utf-8")
        except OSError as exc:
            handle_fs_error(exc, "create note")

        result = FileOperationResult(success=True, message="Note created successfully", operation="create", path=note_path)
        return format_file_result(result)

    mcp.add_tool(
        create_note,
        name="create-note",
        description=(
            "Create a new note in the specified vault with markdown content.\n\n"
            "Examples:\n"
            "- Root note: { \"vault\": \"vault1\", \"filename\": \"note.md\" }\n"
            "- Subfolder note: { \"vault\": \"vault2\", \"filename\": \"note.md\", \"folder\": \"journal/2024\" }\n"
            "- INCORRECT: { \"filename\": \"journal/2024/note.md\" } (don't put path in filename)"
        ),
        structured_output=False,
    )
