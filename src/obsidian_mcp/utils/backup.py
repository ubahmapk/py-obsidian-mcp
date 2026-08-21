"""Unified backup/safety module.

TS spread three inconsistent backup mechanisms across three separate tool files:
a per-file `.backup` sidecar for `edit-note`, a `.trash/` mover for `delete-note`,
and a `.backup/vault-backup-<timestamp>/` snapshot for `rename-tag`. This module
gives them one home while keeping three distinct *behaviors* -- they serve
genuinely different purposes and shouldn't be collapsed into one mechanism.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import anyio
import yaml

from obsidian_mcp.utils.errors import handle_fs_error
from obsidian_mcp.utils.files import (
    ensure_directory,
    file_exists,
    get_all_markdown_files,
)


def _timestamp() -> str:
    return datetime.now(UTC).isoformat().replace(":", "-").replace(".", "-")


@asynccontextmanager
async def edit_safety_backup(path: str) -> AsyncIterator[None]:
    """Backs up `path` before a mutation; restores it if the block raises.

    Replaces TS `edit-note`'s timestamp-suffixed backup file plus a detached
    `setTimeout(5000)` cleanup, which could outlive process exit and leak stray
    `.backup` files. This is a proper try/restore/finally block instead: no
    orphaned backups, and no "5 second recovery window" to protect (a synchronous
    restore-on-failure removes the failure window that window was compensating
    for). If a delete-specific grace/undo window is ever wanted, `.trash/`-based
    soft delete (see `soft_delete_to_trash`) is the correct primitive for that,
    not a bolt-on timer inside a different tool.
    """
    backup_path = f"{path}.{_timestamp()}.backup"
    had_original = await file_exists(path)
    if had_original:
        await anyio.Path(path).parent.mkdir(parents=True, exist_ok=True)
        content = await anyio.Path(path).read_bytes()
        await anyio.Path(backup_path).write_bytes(content)

    try:
        yield
    except Exception:
        if had_original:
            try:
                content = await anyio.Path(backup_path).read_bytes()
                await anyio.Path(path).write_bytes(content)
            except OSError:
                pass
        raise
    finally:
        if had_original and await file_exists(backup_path):
            try:
                await anyio.Path(backup_path).unlink()
            except OSError:
                pass


async def soft_delete_to_trash(vault_path: str, note_path: str, reason: str | None = None) -> str:
    """Moves a note into `<vault>/.trash/` with YAML frontmatter metadata.

    Returns the trash entry's filename. Real `yaml.safe_dump` is used for the
    metadata block (TS hand-built the YAML string, which was fragile with special
    characters in `reason`).
    """
    trash_dir = os.path.join(vault_path, ".trash")
    await ensure_directory(trash_dir)

    timestamp = datetime.now(UTC).isoformat().replace(":", "-").replace(".", "-")
    base_name = os.path.splitext(os.path.basename(note_path))[0]
    trash_name = f"{base_name}_{timestamp}.md"
    trash_file_path = os.path.join(trash_dir, trash_name)

    full_source_path = os.path.join(vault_path, note_path)

    try:
        content = await anyio.Path(full_source_path).read_text(encoding="utf-8")

        metadata: dict[str, str] = {"original_path": note_path, "deleted_at": datetime.now(UTC).isoformat()}
        if reason:
            metadata["reason"] = reason

        frontmatter_str = yaml.safe_dump({"trash_metadata": metadata}, sort_keys=False).strip()
        content_with_metadata = f"---\n{frontmatter_str}\n---\n\n{content}"

        await anyio.Path(trash_file_path).write_text(content_with_metadata, encoding="utf-8")
        await anyio.Path(full_source_path).unlink()
    except OSError as exc:
        handle_fs_error(exc, "move note to trash")

    return trash_name


async def create_vault_snapshot(vault_path: str) -> str:
    """Copies every markdown file in the vault to `.backup/vault-backup-<timestamp>/`."""
    timestamp = datetime.now(UTC).isoformat().replace(":", "-").replace(".", "-")
    backup_dir = os.path.join(vault_path, ".backup")
    backup_path = os.path.join(backup_dir, f"vault-backup-{timestamp}")

    await anyio.Path(backup_dir).mkdir(parents=True, exist_ok=True)

    files = await get_all_markdown_files(vault_path)
    for file_path in files:
        relative_path = os.path.relpath(file_path, vault_path)
        backup_file = os.path.join(backup_path, relative_path)
        await anyio.Path(backup_file).parent.mkdir(parents=True, exist_ok=True)
        content = await anyio.Path(file_path).read_bytes()
        await anyio.Path(backup_file).write_bytes(content)

    return backup_path
