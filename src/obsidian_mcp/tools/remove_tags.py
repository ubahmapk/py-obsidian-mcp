"""`remove-tags` tool. Ported from TS `tools/remove-tags/index.ts`.

TS's `options` sub-schema was not `.strict()`, unlike most other tools -- this
internal model stays non-strict too (`extra="allow"`), matching TS exactly rather
than blanket-strictening every tool (see the SDK Addendum's advisor-reviewed
decision on per-tool strictness parity).
"""

from __future__ import annotations

import os
import re
from typing import Literal

import anyio
from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, ConfigDict, Field, field_validator

from obsidian_mcp.registry import validate
from obsidian_mcp.utils.files import file_exists, safe_read_file
from obsidian_mcp.utils.frontmatter import parse_note, stringify_note
from obsidian_mcp.utils.path_safety import validate_vault_path
from obsidian_mcp.utils.tags import (
    TagChange,
    remove_inline_tags,
    remove_tags_from_frontmatter,
)
from obsidian_mcp.vault_resolver import VaultResolver

_TAG_CHARS_RE = re.compile(r"^[a-zA-Z0-9/]+$")


class RemoveTagsOptions(BaseModel):
    model_config = ConfigDict(extra="allow")

    location: Literal["frontmatter", "content", "both"] = Field("both", description="Where to remove tags from")
    normalize: bool = Field(True, description="Whether to normalize tag format")
    preserve_children: bool = Field(False, description="Whether to preserve child tags when removing parent tags")
    patterns: list[str] = Field(default_factory=list, description="Tag patterns to match for removal (supports * wildcard)")


class RemoveTagsInput(BaseModel):
    model_config = ConfigDict(extra="allow")

    vault: str = Field(..., min_length=1, description="Name of the vault containing the notes")
    files: list[str] = Field(..., min_length=1, description="Array of note filenames to process (must have .md extension)")
    tags: list[str] = Field(..., min_length=1, description="Array of tags to remove (without # symbol)")
    options: RemoveTagsOptions = Field(default_factory=RemoveTagsOptions)

    @field_validator("files")
    @classmethod
    def _md_extension(cls, value: list[str]) -> list[str]:
        if not all(f.endswith(".md") for f in value):
            raise ValueError("All files must have .md extension")
        return value

    @field_validator("tags")
    @classmethod
    def _valid_tags(cls, value: list[str]) -> list[str]:
        if not all(_TAG_CHARS_RE.match(t) for t in value):
            raise ValueError(
                "Tags must contain only letters, numbers, and forward slashes. Do not include the # symbol."
            )
        return value


def _format_changes_block(label: str, changes: list[TagChange]) -> str:
    by_key: dict[str, set[str]] = {}
    for change in changes:
        key = f"{change.location} (line {change.line})" if change.line else change.location
        by_key.setdefault(key, set()).add(change.tag)

    lines = [f"  {label}:"]
    for key, tags in by_key.items():
        lines.append(f"    {key}: {', '.join(sorted(tags))}")
    return "\n".join(lines)


def register(mcp: MCPServer, vaults: dict[str, str]) -> None:
    resolver = VaultResolver(vaults)

    async def remove_tags(
        vault: str,
        files: list[str],
        tags: list[str],
        options: RemoveTagsOptions | None = None,
    ) -> str:
        args = validate(RemoveTagsInput, vault=vault, files=files, tags=tags, options=options or RemoveTagsOptions())
        vault_path = resolver.resolve_vault(args.vault)
        opts = args.options

        success_files: list[str] = []
        errors: list[tuple[str, str]] = []
        details: dict[str, tuple[list[TagChange], list[TagChange]]] = {}

        for filename in args.files:
            full_path = os.path.join(vault_path, filename)

            try:
                validate_vault_path(vault_path, full_path)

                if not await file_exists(full_path):
                    errors.append((filename, "File not found"))
                    continue

                content = await safe_read_file(full_path)
                if content is None:
                    errors.append((filename, "Failed to read file"))
                    continue

                parsed = parse_note(content)
                modified = False
                removed: list[TagChange] = []
                preserved: list[TagChange] = []

                if opts.location != "content":
                    updated_frontmatter, report = remove_tags_from_frontmatter(
                        parsed.frontmatter, args.tags, opts.normalize, opts.preserve_children, opts.patterns
                    )
                    removed.extend(report.removed)
                    preserved.extend(report.preserved)
                    if updated_frontmatter != parsed.frontmatter:
                        parsed.frontmatter = updated_frontmatter
                        modified = True

                if opts.location != "frontmatter":
                    new_content, report = remove_inline_tags(
                        parsed.content, args.tags, opts.normalize, opts.preserve_children, opts.patterns
                    )
                    removed.extend(report.removed)
                    preserved.extend(report.preserved)
                    if new_content != parsed.content:
                        parsed.content = new_content
                        modified = True

                details[filename] = (removed, preserved)

                if modified:
                    updated_content = stringify_note(parsed)
                    await anyio.Path(full_path).write_text(updated_content, encoding="utf-8")
                    success_files.append(filename)
            except Exception as exc:  # noqa: BLE001 - mirrors TS's per-file catch-and-continue
                errors.append((filename, str(exc)))

        message_parts: list[str] = []
        if success_files:
            message_parts.append(f"Successfully processed tags in: {', '.join(success_files)}\n")

        for filename, (removed, preserved) in details.items():
            if removed or preserved:
                message_parts.append(f"Changes in {filename}:")
                if removed:
                    message_parts.append(_format_changes_block("Removed tags", removed))
                if preserved:
                    message_parts.append(_format_changes_block("Preserved tags", preserved))
                message_parts.append("")

        if errors:
            message_parts.append("Errors:")
            for filename, error in errors:
                message_parts.append(f"  {filename}: {error}")

        return "\n".join(message_parts).strip()

    mcp.add_tool(
        remove_tags,
        name="remove-tags",
        description=(
            "Remove tags from notes in frontmatter and/or content.\n\n"
            "Examples:\n"
            "- Simple: { \"files\": [\"note.md\"], \"tags\": [\"project\", \"status\"] }\n"
            "- With hierarchy: { \"files\": [\"note.md\"], \"tags\": [\"work/active\", \"priority/high\"] }\n"
            "- With options: { \"files\": [\"note.md\"], \"tags\": [\"status\"], \"options\": { \"location\": \"frontmatter\" } }\n"
            "- Pattern matching: { \"files\": [\"note.md\"], \"options\": { \"patterns\": [\"status/*\"] } }\n"
            "- INCORRECT: { \"tags\": [\"#project\"] } (don't include # symbol)"
        ),
        structured_output=False,
    )
