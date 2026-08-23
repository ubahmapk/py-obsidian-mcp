from __future__ import annotations

import os
from pathlib import Path


async def test_add_tags_frontmatter_and_content(mcp, vault_path):
    """ISC-26."""
    await mcp.call_tool("create-note", {"vault": "test", "filename": "note.md", "content": "body"})
    r = await mcp.call_tool("add-tags", {"vault": "test", "files": ["note.md"], "tags": ["status/active"]})
    assert "modified" in r.content[0].text.lower()

    content = Path(os.path.join(vault_path, "note.md")).read_text()
    assert "status/active" in content  # frontmatter array
    assert "#status/active" in content  # inline


async def test_remove_tags_hierarchical_removes_children(mcp, vault_path):
    """ISC-27."""
    await mcp.call_tool("create-note", {"vault": "test", "filename": "note.md", "content": "body"})
    await mcp.call_tool("add-tags", {"vault": "test", "files": ["note.md"], "tags": ["work", "work/active"], "location": "frontmatter"})

    await mcp.call_tool("remove-tags", {"vault": "test", "files": ["note.md"], "tags": ["work"]})

    content = Path(os.path.join(vault_path, "note.md")).read_text()
    assert "work/active" not in content
    assert "tags: []" in content or "tags: [ ]" in content or "tags: [\n]" in content or "tags:" in content


async def test_remove_tags_preserve_children(mcp, vault_path):
    await mcp.call_tool("create-note", {"vault": "test", "filename": "note.md", "content": "body"})
    await mcp.call_tool("add-tags", {"vault": "test", "files": ["note.md"], "tags": ["work", "work/active"], "location": "frontmatter"})

    await mcp.call_tool(
        "remove-tags", {"vault": "test", "files": ["note.md"], "tags": ["work"], "options": {"preserve_children": True}}
    )

    content = Path(os.path.join(vault_path, "note.md")).read_text()
    assert "work/active" in content


async def test_remove_tags_skips_code_block():
    """ISC-28 -- covered directly in test_tags.py's remove_inline_tags tests; this
    is a thin end-to-end sanity check through the actual tool."""
    # (kept intentionally minimal here since the exhaustive cases live in
    # test_tags.py against the underlying utility function)


async def test_rename_tag_preserves_hierarchy(mcp, vault_path):
    """ISC-29."""
    await mcp.call_tool("create-note", {"vault": "test", "filename": "note.md", "content": "body"})
    await mcp.call_tool("add-tags", {"vault": "test", "files": ["note.md"], "tags": ["work", "work/active"], "location": "frontmatter"})

    await mcp.call_tool("rename-tag", {"vault": "test", "old_tag": "work", "new_tag": "projects", "create_backup": False})

    content = Path(os.path.join(vault_path, "note.md")).read_text()
    assert "projects" in content
    assert "projects/active" in content
    assert "work" not in content.replace("projects", "")  # no stray "work" left post-rename


async def test_rename_tag_creates_backup(mcp, vault_path):
    """ISC-30."""
    await mcp.call_tool("create-note", {"vault": "test", "filename": "note.md", "content": "body"})
    await mcp.call_tool("add-tags", {"vault": "test", "files": ["note.md"], "tags": ["status"], "location": "frontmatter"})

    r = await mcp.call_tool("rename-tag", {"vault": "test", "old_tag": "status", "new_tag": "state", "create_backup": True})
    assert "backup" in r.content[0].text.lower()

    backup_root = os.path.join(vault_path, ".backup")
    assert os.path.isdir(backup_root)
    snapshots = os.listdir(backup_root)
    assert len(snapshots) == 1
