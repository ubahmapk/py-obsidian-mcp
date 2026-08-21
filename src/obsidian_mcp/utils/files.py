"""Async filesystem helpers, mirroring TS `utils/files.ts`.

Kept async (unlike `path_safety.py`) because `get_all_markdown_files` does a real
recursive walk over the whole vault, which can be slow on large vaults and
legitimately benefits from not blocking the event loop.
"""

from __future__ import annotations

import sys

import anyio
from mcp.shared.exceptions import MCPError
from mcp.types import INVALID_REQUEST

from obsidian_mcp.utils.path_safety import normalize_path, safe_join_path


async def get_all_markdown_files(vault_path: str, directory: str | None = None) -> list[str]:
    """Recursively collects all .md files under `directory` (default: vault_path).

    Skips dot-directories (hidden dirs, including `.trash`/`.backup`) and continues
    past per-entry errors rather than aborting the whole walk.
    """
    directory = directory if directory is not None else vault_path
    normalized_vault_path = normalize_path(vault_path)
    normalized_dir = normalize_path(directory)

    if not (normalized_dir == normalized_vault_path or normalized_dir.startswith(normalized_vault_path + "/")):
        raise MCPError(INVALID_REQUEST, f"Search directory must be within vault: {directory}")

    try:
        entries = [entry async for entry in anyio.Path(normalized_dir).iterdir()]
    except FileNotFoundError as exc:
        raise MCPError(INVALID_REQUEST, f"Directory not found: {directory}") from exc
    except OSError as exc:
        raise MCPError(INVALID_REQUEST, f"Failed to read directory {directory}: {exc}") from exc

    files: list[str] = []
    for entry in entries:
        try:
            full_path = safe_join_path(normalized_dir, entry.name)
            is_dir = await entry.is_dir()
            if is_dir:
                if not entry.name.startswith("."):
                    files.extend(await get_all_markdown_files(normalized_vault_path, full_path))
            elif entry.name.endswith(".md"):
                files.append(full_path)
        except (MCPError, OSError) as exc:
            print(f"Skipping {entry.name}: {exc}", file=sys.stderr)

    return files


async def ensure_directory(dir_path: str) -> None:
    """Creates a directory (and parents) if it doesn't already exist."""
    normalized_path = normalize_path(dir_path)
    try:
        await anyio.Path(normalized_path).mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise MCPError(INVALID_REQUEST, f"Failed to create directory {dir_path}: {exc}") from exc


async def file_exists(file_path: str) -> bool:
    """True if the given path exists (and is accessible)."""
    normalized_path = normalize_path(file_path)
    return await anyio.Path(normalized_path).exists()


async def safe_read_file(file_path: str) -> str | None:
    """Reads a file's text content, returning None if it doesn't exist."""
    normalized_path = normalize_path(file_path)
    try:
        return await anyio.Path(normalized_path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise MCPError(INVALID_REQUEST, f"Failed to read file {file_path}: {exc}") from exc
