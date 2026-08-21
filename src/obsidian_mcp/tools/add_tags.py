"""`add-tags` tool. Ported from TS `tools/add-tags/index.ts`."""

from __future__ import annotations

import os
from typing import Literal

import anyio
from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, ConfigDict, Field, field_validator

from obsidian_mcp.registry import validate
from obsidian_mcp.utils.files import file_exists, safe_read_file
from obsidian_mcp.utils.frontmatter import parse_note, stringify_note
from obsidian_mcp.utils.path_safety import validate_vault_path
from obsidian_mcp.utils.responses import TagOperationResult, format_tag_result
from obsidian_mcp.utils.tags import (
    TagChange,
    add_tags_to_frontmatter,
    normalize_tag,
    validate_tag,
)
from obsidian_mcp.vault_resolver import VaultResolver


class AddTagsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vault: str = Field(..., min_length=1, description="Name of the vault containing the notes")
    files: list[str] = Field(..., min_length=1, description="Array of note filenames to process (must have .md extension)")
    tags: list[str] = Field(..., min_length=1, description="Array of tags to add (e.g., 'status/active', 'project/docs')")
    location: Literal["frontmatter", "content", "both"] = Field("both", description="Where to add tags")
    normalize: bool = Field(True, description="Whether to normalize tag format")
    position: Literal["start", "end"] = Field("end", description="Where to add inline tags in content")

    @field_validator("files")
    @classmethod
    def _md_extension(cls, value: list[str]) -> list[str]:
        if not all(f.endswith(".md") for f in value):
            raise ValueError("All files must have .md extension")
        return value

    @field_validator("tags")
    @classmethod
    def _valid_tags(cls, value: list[str]) -> list[str]:
        if not all(validate_tag(t) for t in value):
            raise ValueError("Invalid tag format. Tags must contain only letters, numbers, and forward slashes for hierarchy.")
        return value


def register(mcp: MCPServer, vaults: dict[str, str]) -> None:
    resolver = VaultResolver(vaults)

    async def add_tags(
        vault: str,
        files: list[str],
        tags: list[str],
        location: Literal["frontmatter", "content", "both"] = "both",
        normalize: bool = True,
        position: Literal["start", "end"] = "end",
    ) -> str:
        args = validate(AddTagsInput, vault=vault, files=files, tags=tags, location=location, normalize=normalize, position=position)
        vault_path = resolver.resolve_vault(args.vault)

        details: dict[str, list[TagChange]] = {}
        failed_items: list[tuple[str, str]] = []
        success_count = 0

        for filename in args.files:
            full_path = os.path.join(vault_path, filename)
            details[filename] = []

            try:
                validate_vault_path(vault_path, full_path)

                if not await file_exists(full_path):
                    failed_items.append((filename, "File not found"))
                    continue

                content = await safe_read_file(full_path)
                if content is None:
                    failed_items.append((filename, "Failed to read file"))
                    continue

                parsed = parse_note(content)
                modified = False

                if args.location != "content":
                    updated_frontmatter = add_tags_to_frontmatter(parsed.frontmatter, args.tags, args.normalize)
                    if updated_frontmatter != parsed.frontmatter:
                        parsed.frontmatter = updated_frontmatter
                        parsed.has_frontmatter = True
                        modified = True
                        for tag in args.tags:
                            details[filename].append(TagChange(tag=normalize_tag(tag, args.normalize) if args.normalize else tag, location="frontmatter"))

                if args.location != "frontmatter":
                    tag_string = " ".join(f"#{normalize_tag(tag, args.normalize) if args.normalize else tag}" for tag in args.tags if validate_tag(tag))
                    if tag_string:
                        stripped = parsed.content.strip()
                        parsed.content = f"{tag_string}\n\n{stripped}" if args.position == "start" else f"{stripped}\n\n{tag_string}"
                        modified = True
                        for tag in args.tags:
                            details[filename].append(TagChange(tag=normalize_tag(tag, args.normalize) if args.normalize else tag, location="content"))

                if modified:
                    updated_content = stringify_note(parsed)
                    await anyio.Path(full_path).write_text(updated_content, encoding="utf-8")
                    success_count += 1
            except Exception as exc:  # noqa: BLE001 - mirrors TS's per-file catch-and-continue
                failed_items.append((filename, str(exc)))

        success = not failed_items
        message = f"Successfully added tags to {success_count} files" if success else f"Completed with {len(failed_items)} errors"

        result = TagOperationResult(
            success=success,
            message=message,
            total_count=len(args.files),
            success_count=success_count,
            details=details,
            failed_items=failed_items,
        )
        return format_tag_result(result)

    mcp.add_tool(
        add_tags,
        name="add-tags",
        description=(
            "Add tags to notes in frontmatter and/or content.\n\n"
            "Examples:\n"
            "- Add to both locations: { \"files\": [\"note.md\"], \"tags\": [\"status/active\"] }\n"
            "- Add to frontmatter only: { \"files\": [\"note.md\"], \"tags\": [\"project/docs\"], \"location\": \"frontmatter\" }\n"
            "- Add to start of content: { \"files\": [\"note.md\"], \"tags\": [\"type/meeting\"], \"location\": \"content\", \"position\": \"start\" }"
        ),
        structured_output=False,
    )
