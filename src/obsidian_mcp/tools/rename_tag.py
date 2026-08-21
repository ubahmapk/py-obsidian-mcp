"""`rename-tag` tool. Ported from TS `tools/rename-tag/index.ts`."""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys

import anyio
from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, ConfigDict, Field, field_validator

from obsidian_mcp.registry import validate
from obsidian_mcp.utils.backup import create_vault_snapshot
from obsidian_mcp.utils.files import file_exists, get_all_markdown_files, safe_read_file
from obsidian_mcp.utils.frontmatter import parse_note, stringify_note
from obsidian_mcp.utils.line_classifier import TAG_PATTERN, iter_lines_with_context
from obsidian_mcp.utils.tags import normalize_tag
from obsidian_mcp.vault_resolver import VaultResolver

_TAG_CHARS_RE = re.compile(r"^[a-zA-Z0-9/]+$")
_INLINE_TAG_RE = re.compile(TAG_PATTERN)


class RenameTagInput(BaseModel):
    model_config = ConfigDict(extra="allow")

    vault: str = Field(..., min_length=1, description="Name of the vault containing the tags")
    old_tag: str = Field(..., min_length=1, description="The tag to rename (without #)")
    new_tag: str = Field(..., min_length=1, description="The new tag name (without #)")
    create_backup: bool = Field(True, description="Whether to create a backup before making changes")
    normalize: bool = Field(True, description="Whether to normalize tag names")
    batch_size: int = Field(50, ge=1, le=100, description="Number of files to process in each batch")

    @field_validator("old_tag", "new_tag")
    @classmethod
    def _valid_tag_chars(cls, value: str) -> str:
        if not _TAG_CHARS_RE.match(value):
            raise ValueError(
                "Tags must contain only letters, numbers, and forward slashes. Do not include the # symbol."
            )
        return value


def _update_frontmatter_tags(frontmatter: dict, old_tag: str, new_tag: str, normalize: bool) -> tuple[dict, list[tuple[str, str]]]:
    changes: list[tuple[str, str]] = []
    updated = dict(frontmatter)
    if not isinstance(frontmatter.get("tags"), list):
        return updated, changes

    normalized_old = normalize_tag(old_tag, normalize)
    normalized_new = normalize_tag(new_tag, normalize)
    updated_tags = []

    for tag in frontmatter["tags"]:
        normalized_tag = normalize_tag(tag, normalize)
        if normalized_tag == normalized_old or normalized_tag.startswith(normalized_old + "/"):
            new_value = re.sub(f"^{re.escape(normalized_old)}", normalized_new, normalized_tag)
            changes.append((normalized_tag, new_value))
            updated_tags.append(new_value)
        else:
            updated_tags.append(normalized_tag)

    updated["tags"] = sorted(set(updated_tags))
    return updated, changes


def _update_inline_tags(content: str, old_tag: str, new_tag: str, normalize: bool) -> tuple[str, list[tuple[str, str, int]]]:
    changes: list[tuple[str, str, int]] = []
    normalized_old = normalize_tag(old_tag, normalize)
    normalized_new = normalize_tag(new_tag, normalize)
    output_lines: list[str] = []

    for ctx in iter_lines_with_context(content):
        if ctx.skip:
            output_lines.append(ctx.text)
            continue

        def _replace(match: re.Match[str], _ctx=ctx) -> str:
            tag = match.group(0)[1:]
            normalized_tag = normalize_tag(tag, normalize)
            if normalized_tag == normalized_old or normalized_tag.startswith(normalized_old + "/"):
                new_value = re.sub(f"^{re.escape(normalized_old)}", normalized_new, normalized_tag)
                changes.append((normalized_tag, new_value, _ctx.line_no))
                return f"#{new_value}"
            return match.group(0)

        output_lines.append(_INLINE_TAG_RE.sub(_replace, ctx.text))

    return "\n".join(output_lines), changes


async def _update_saved_searches(vault_path: str, old_tag: str, new_tag: str, normalize: bool) -> None:
    search_config_path = os.path.join(vault_path, ".obsidian", "search.json")
    if not await file_exists(search_config_path):
        return

    try:
        raw = await anyio.Path(search_config_path).read_text(encoding="utf-8")
        config = json.loads(raw)
        normalized_old = normalize_tag(old_tag, normalize)
        normalized_new = normalize_tag(new_tag, normalize)
        modified = False

        for search in config.get("savedSearches", []):
            query = search.get("query")
            if not isinstance(query, str):
                continue
            updated_query = re.sub(rf"tag:{re.escape(normalized_old)}(/\S*)?", rf"tag:{normalized_new}\1", query)
            updated_query = re.sub(rf"#{re.escape(normalized_old)}(/\S*)?", rf"#{normalized_new}\1", updated_query)
            if updated_query != query:
                search["query"] = updated_query
                modified = True

        if modified:
            await anyio.Path(search_config_path).write_text(json.dumps(config, indent=2), encoding="utf-8")
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Error updating saved searches: {exc}", file=sys.stderr)


async def _process_file(file_path: str, old_tag: str, new_tag: str, normalize: bool) -> tuple[str, list[str]]:
    content = await safe_read_file(file_path)
    if content is None:
        raise OSError("File not found or cannot be read")

    parsed = parse_note(content)
    updated_frontmatter, frontmatter_changes = _update_frontmatter_tags(parsed.frontmatter, old_tag, new_tag, normalize)
    updated_content, content_changes = _update_inline_tags(parsed.content, old_tag, new_tag, normalize)

    summaries: list[str] = []
    if frontmatter_changes or content_changes:
        parsed.frontmatter = updated_frontmatter
        parsed.content = updated_content
        await anyio.Path(file_path).write_text(stringify_note(parsed), encoding="utf-8")

        if frontmatter_changes:
            joined = ", ".join(f"{o} -> {n}" for o, n in frontmatter_changes)
            summaries.append(f"  frontmatter: {joined}")
        for old, new, line in content_changes:
            summaries.append(f"  content (line {line}): {old} -> {new}")

    return file_path, summaries


def register(mcp: MCPServer, vaults: dict[str, str]) -> None:
    resolver = VaultResolver(vaults)

    async def rename_tag(
        vault: str,
        old_tag: str,
        new_tag: str,
        create_backup: bool = True,
        normalize: bool = True,
        batch_size: int = 50,
    ) -> str:
        args = validate(
            RenameTagInput,
            vault=vault,
            old_tag=old_tag,
            new_tag=new_tag,
            create_backup=create_backup,
            normalize=normalize,
            batch_size=batch_size,
        )
        vault_path = resolver.resolve_vault(args.vault)

        backup_path: str | None = None
        if args.create_backup:
            backup_path = await create_vault_snapshot(vault_path)

        files = await get_all_markdown_files(vault_path)
        successful: dict[str, list[str]] = {}
        failed: list[tuple[str, str]] = []

        for start in range(0, len(files), args.batch_size):
            batch = files[start : start + args.batch_size]
            batch_results = await asyncio.gather(
                *(_process_file(f, args.old_tag, args.new_tag, args.normalize) for f in batch), return_exceptions=True
            )
            for file_path, outcome in zip(batch, batch_results):
                if isinstance(outcome, Exception):
                    failed.append((file_path, str(outcome)))
                else:
                    _, summaries = outcome
                    if summaries:
                        successful[file_path] = summaries

        await _update_saved_searches(vault_path, args.old_tag, args.new_tag, args.normalize)

        parts: list[str] = []
        if backup_path:
            parts.append(f"Created backup at: {backup_path}\n")

        if successful:
            total_locations = sum(len(v) for v in successful.values())
            parts.append(f"Successfully renamed tags in {total_locations} locations:\n")
            for file_path, summaries in successful.items():
                parts.append(f"{file_path}:")
                parts.extend(summaries)
                parts.append("")

        if failed:
            parts.append("Errors:")
            for file_path, error in failed:
                parts.append(f"  {file_path}: {error}")

        return "\n".join(parts).strip()

    mcp.add_tool(
        rename_tag,
        name="rename-tag",
        description=(
            "Safely renames tags throughout the vault while preserving hierarchies.\n\n"
            "Examples:\n"
            "- Simple rename: { \"old_tag\": \"project\", \"new_tag\": \"projects\" }\n"
            "- Rename with hierarchy: { \"old_tag\": \"work/active\", \"new_tag\": \"projects/current\" }\n"
            "- With options: { \"old_tag\": \"status\", \"new_tag\": \"state\", \"normalize\": true, \"create_backup\": true }\n"
            "- INCORRECT: { \"old_tag\": \"#project\" } (don't include # symbol)"
        ),
        structured_output=False,
    )
