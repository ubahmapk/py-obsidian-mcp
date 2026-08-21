"""`edit-note` tool. Ported from TS `tools/edit-note/index.ts`.

TS modeled this as a zod discriminated union on `operation`. The installed SDK
derives the wire schema from flat function parameters, so the wire shape here is
flat (`operation: Literal[...]`, `content: str | None`) -- see the SDK Addendum in
the plan file. The internal validation below reconstructs the TS discriminated
union in Python (two Pydantic models, dispatched on `operation`), so the
conditional "content required unless delete" rule is still enforced -- just
inside the handler body instead of at the wire schema level.
"""

from __future__ import annotations

import os
from typing import Literal

import anyio
from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, ConfigDict, Field, field_validator

from obsidian_mcp.registry import validate
from obsidian_mcp.utils.backup import edit_safety_backup
from obsidian_mcp.utils.errors import create_note_not_found_error, handle_fs_error
from obsidian_mcp.utils.files import file_exists
from obsidian_mcp.utils.path_safety import (
    ensure_markdown_extension,
    validate_vault_path,
)
from obsidian_mcp.utils.responses import FileOperationResult, format_file_result
from obsidian_mcp.vault_resolver import VaultResolver


class _SharedFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vault: str = Field(..., min_length=1, description="Name of the vault containing the note")
    filename: str = Field(..., min_length=1, description="Just the note name without any path separators")
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


class EditNoteDeleteInput(_SharedFields):
    operation: Literal["delete"]


class EditNoteMutateInput(_SharedFields):
    operation: Literal["append", "prepend", "replace"]
    content: str = Field(..., min_length=1, description="New content to add/prepend/replace")


def register(mcp: MCPServer, vaults: dict[str, str]) -> None:
    resolver = VaultResolver(vaults)

    async def edit_note(
        vault: str,
        filename: str,
        operation: Literal["append", "prepend", "replace", "delete"],
        content: str | None = None,
        folder: str | None = None,
    ) -> str:
        if operation == "delete":
            args: EditNoteDeleteInput | EditNoteMutateInput = validate(
                EditNoteDeleteInput, vault=vault, filename=filename, folder=folder, operation=operation
            )
        else:
            if content is None:
                raise ValueError("content is required for append/prepend/replace operations")
            args = validate(
                EditNoteMutateInput, vault=vault, filename=filename, folder=folder, operation=operation, content=content
            )

        vault_path = resolver.resolve_vault(args.vault)
        sanitized_filename = ensure_markdown_extension(args.filename)
        full_path = (
            os.path.join(vault_path, args.folder, sanitized_filename)
            if args.folder
            else os.path.join(vault_path, sanitized_filename)
        )
        validate_vault_path(vault_path, full_path)

        if not await file_exists(full_path):
            raise create_note_not_found_error(args.filename)

        async with edit_safety_backup(full_path):
            try:
                if args.operation == "delete":
                    await anyio.Path(full_path).unlink()
                    return format_file_result(
                        FileOperationResult(success=True, message="Note deleted successfully", operation="delete", path=full_path)
                    )

                existing_content = await anyio.Path(full_path).read_text(encoding="utf-8")
                if args.operation == "append":
                    new_content = existing_content.strip() + (("\n\n" + args.content) if existing_content.strip() else args.content)
                elif args.operation == "prepend":
                    new_content = args.content + (("\n\n" + existing_content.strip()) if existing_content.strip() else "")
                else:
                    new_content = args.content

                await anyio.Path(full_path).write_text(new_content, encoding="utf-8")
                return format_file_result(
                    FileOperationResult(
                        success=True, message=f"Note {args.operation}ed successfully", operation="edit", path=full_path
                    )
                )
            except OSError as exc:
                handle_fs_error(exc, f"{args.operation} note")
                raise  # unreachable

    mcp.add_tool(
        edit_note,
        name="edit-note",
        description=(
            "Edit an existing note in the specified vault.\n\n"
            "There is a limited and discrete list of supported operations:\n"
            "- append: Appends content to the end of the note\n"
            "- prepend: Prepends content to the beginning of the note\n"
            "- replace: Replaces the entire content of the note\n"
            "- delete: Deletes the note (do not provide content for this operation)\n\n"
            "`content` is required for append/prepend/replace and must be omitted for delete.\n\n"
            "Examples:\n"
            "- Root note: { \"vault\": \"vault1\", \"filename\": \"note.md\", \"operation\": \"append\", \"content\": \"new content\" }\n"
            "- Subfolder note: { \"vault\": \"vault2\", \"filename\": \"note.md\", \"folder\": \"journal/2024\", \"operation\": \"append\", \"content\": \"new content\" }\n"
            "- INCORRECT: { \"filename\": \"journal/2024/note.md\" } (don't put path in filename)"
        ),
        structured_output=False,
    )
