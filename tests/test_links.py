from __future__ import annotations

import os
from pathlib import Path

from obsidian_mcp.utils.links import update_links_in_file, update_vault_links


async def test_update_links_in_file_rename_wikilink(tmp_path):
    base = os.path.realpath(tmp_path)
    referencing = os.path.join(base, "ref.md")
    Path(referencing).write_text("See [[old-note]] and [[old-note|alias]] for more.")

    changed = await update_links_in_file(referencing, "old-note.md", "new-note.md")
    assert changed is True

    content = Path(referencing).read_text()
    assert "[[new-note]]" in content
    assert "[[new-note|alias]]" in content
    assert "old-note" not in content


async def test_update_links_in_file_rename_markdown_link(tmp_path):
    base = os.path.realpath(tmp_path)
    referencing = os.path.join(base, "ref.md")
    Path(referencing).write_text("See [my note](old-note.md) for more.")

    await update_links_in_file(referencing, "old-note.md", "new-note.md")
    content = Path(referencing).read_text()
    assert "[my note](new-note.md)" in content


async def test_update_links_in_file_delete_strikethrough(tmp_path):
    base = os.path.realpath(tmp_path)
    referencing = os.path.join(base, "ref.md")
    Path(referencing).write_text("See [[old-note]] for more.")

    changed = await update_links_in_file(referencing, "old-note.md", None)
    assert changed is True
    content = Path(referencing).read_text()
    assert "~~[[old-note]]~~" in content


async def test_update_links_in_file_no_change_returns_false(tmp_path):
    base = os.path.realpath(tmp_path)
    referencing = os.path.join(base, "ref.md")
    Path(referencing).write_text("No links here.")

    assert await update_links_in_file(referencing, "old-note.md", "new-note.md") is False


async def test_update_vault_links_updates_multiple_files_and_skips_destination(tmp_path):
    base = os.path.realpath(tmp_path)
    Path(os.path.join(base, "a.md")).write_text("[[old-note]]")
    Path(os.path.join(base, "b.md")).write_text("no link")
    # the destination file itself, pre-populated as if the move already happened
    Path(os.path.join(base, "new-note.md")).write_text("[[old-note]] should not be rewritten here")

    updated = await update_vault_links(base, "old-note.md", "new-note.md")
    assert updated == 1  # only a.md changes; new-note.md (the destination) is skipped

    assert "[[new-note]]" in Path(os.path.join(base, "a.md")).read_text()
    assert "[[old-note]]" in Path(os.path.join(base, "new-note.md")).read_text()
