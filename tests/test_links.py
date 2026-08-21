from __future__ import annotations

import os

from obsidian_mcp.utils.links import update_links_in_file, update_vault_links


async def test_update_links_in_file_rename_wikilink(tmp_path):
    base = os.path.realpath(tmp_path)
    referencing = os.path.join(base, "ref.md")
    with open(referencing, "w") as f:
        f.write("See [[old-note]] and [[old-note|alias]] for more.")

    changed = await update_links_in_file(referencing, "old-note.md", "new-note.md")
    assert changed is True

    content = open(referencing).read()
    assert "[[new-note]]" in content
    assert "[[new-note|alias]]" in content
    assert "old-note" not in content


async def test_update_links_in_file_rename_markdown_link(tmp_path):
    base = os.path.realpath(tmp_path)
    referencing = os.path.join(base, "ref.md")
    with open(referencing, "w") as f:
        f.write("See [my note](old-note.md) for more.")

    await update_links_in_file(referencing, "old-note.md", "new-note.md")
    content = open(referencing).read()
    assert "[my note](new-note.md)" in content


async def test_update_links_in_file_delete_strikethrough(tmp_path):
    base = os.path.realpath(tmp_path)
    referencing = os.path.join(base, "ref.md")
    with open(referencing, "w") as f:
        f.write("See [[old-note]] for more.")

    changed = await update_links_in_file(referencing, "old-note.md", None)
    assert changed is True
    content = open(referencing).read()
    assert "~~[[old-note]]~~" in content


async def test_update_links_in_file_no_change_returns_false(tmp_path):
    base = os.path.realpath(tmp_path)
    referencing = os.path.join(base, "ref.md")
    with open(referencing, "w") as f:
        f.write("No links here.")

    assert await update_links_in_file(referencing, "old-note.md", "new-note.md") is False


async def test_update_vault_links_updates_multiple_files_and_skips_destination(tmp_path):
    base = os.path.realpath(tmp_path)
    with open(os.path.join(base, "a.md"), "w") as f:
        f.write("[[old-note]]")
    with open(os.path.join(base, "b.md"), "w") as f:
        f.write("no link")
    # the destination file itself, pre-populated as if the move already happened
    with open(os.path.join(base, "new-note.md"), "w") as f:
        f.write("[[old-note]] should not be rewritten here")

    updated = await update_vault_links(base, "old-note.md", "new-note.md")
    assert updated == 1  # only a.md changes; new-note.md (the destination) is skipped

    assert "[[new-note]]" in open(os.path.join(base, "a.md")).read()
    assert "[[old-note]]" in open(os.path.join(base, "new-note.md")).read()
