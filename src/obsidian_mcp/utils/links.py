"""Vault-wide wikilink/markdown-link rewriting on note move/delete.

Ported from TS `utils/links.ts`, same-vault rename and delete-strikethrough cases
only. TS's cross-vault branches (`isMovedToOtherVault`/`isMovedFromOtherVault`) are
confirmed unreachable dead code -- no registered tool ever calls `updateVaultLinks`
with those parameters set (there's no cross-vault move tool), so they're
deliberately omitted here rather than ported unused.
"""

from __future__ import annotations

import os
import re

import anyio

from obsidian_mcp.utils.files import get_all_markdown_files
from obsidian_mcp.utils.path_safety import normalize_path


def _wikilink_re(name: str) -> re.Pattern[str]:
    return re.compile(rf"\[\[{re.escape(name)}(\|[^\]]*)?\]\]")


def _mdlink_re(name: str) -> re.Pattern[str]:
    return re.compile(rf"\[([^\]]*)\]\({re.escape(name)}\.md\)")


async def update_links_in_file(file_path: str, old_path: str, new_path: str | None) -> bool:
    """Rewrites links to `old_path` within a single file. Returns True if changed."""
    content = await anyio.Path(file_path).read_text(encoding="utf-8")

    old_name = os.path.splitext(os.path.basename(old_path))[0]

    if new_path is None:
        # Deletion: strike through the links.
        new_content = _wikilink_re(old_name).sub(rf"~~[[{old_name}\1]]~~", content)
        new_content = _mdlink_re(old_name).sub(rf"~~[\1]({old_name}.md)~~", new_content)
    else:
        new_name = os.path.splitext(os.path.basename(new_path))[0]
        new_content = _wikilink_re(old_name).sub(rf"[[{new_name}\1]]", content)
        new_content = _mdlink_re(old_name).sub(rf"[\1]({new_name}.md)", new_content)

    if new_content != content:
        await anyio.Path(file_path).write_text(new_content, encoding="utf-8")
        return True
    return False


async def update_vault_links(vault_path: str, old_path: str | None, new_path: str | None) -> int:
    """Rewrites links to `old_path` across every markdown file in the vault.

    Returns the number of files updated. Skips the destination file itself on a
    move/rename (rewriting its own filename-derived links would be a no-op anyway,
    but this matches the TS original's explicit skip).
    """
    if not old_path:
        return 0

    files = await get_all_markdown_files(vault_path)
    updated = 0

    # Normalize the destination the same way get_all_markdown_files normalizes the
    # walked file paths (forward slashes), so the skip comparison below matches on
    # Windows -- os.path.join would otherwise produce backslashes and never match.
    new_full_path = normalize_path(os.path.join(vault_path, new_path)) if new_path else None

    for file_path in files:
        if new_full_path and file_path == new_full_path:
            continue
        if await update_links_in_file(file_path, old_path, new_path):
            updated += 1

    return updated
