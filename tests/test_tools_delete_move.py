from __future__ import annotations

import os

import pytest
from mcp.shared.exceptions import MCPError


async def test_delete_note_soft_delete_default(mcp, vault_path):
    """ISC-16."""
    await mcp.call_tool("create-note", {"vault": "test", "filename": "note.md", "content": "x"})
    r = await mcp.call_tool("delete-note", {"vault": "test", "path": "note.md", "reason": "cleanup"})
    assert "trash" in r.content[0].text.lower()
    assert not os.path.exists(os.path.join(vault_path, "note.md"))

    trash_dir = os.path.join(vault_path, ".trash")
    entries = os.listdir(trash_dir)
    assert len(entries) == 1
    content = open(os.path.join(trash_dir, entries[0])).read()
    assert "trash_metadata" in content
    assert "cleanup" in content


async def test_delete_note_permanent(mcp, vault_path):
    """ISC-17."""
    await mcp.call_tool("create-note", {"vault": "test", "filename": "note.md", "content": "x"})
    await mcp.call_tool("delete-note", {"vault": "test", "path": "note.md", "permanent": True})

    assert not os.path.exists(os.path.join(vault_path, "note.md"))
    trash_dir = os.path.join(vault_path, ".trash")
    assert not os.path.exists(trash_dir) or os.listdir(trash_dir) == []


async def test_delete_note_strikes_through_links(mcp, vault_path):
    """ISC-18."""
    await mcp.call_tool("create-note", {"vault": "test", "filename": "target.md", "content": "x"})
    await mcp.call_tool("create-note", {"vault": "test", "filename": "referrer.md", "content": "See [[target]] here"})

    await mcp.call_tool("delete-note", {"vault": "test", "path": "target.md"})

    content = open(os.path.join(vault_path, "referrer.md")).read()
    assert "~~[[target]]~~" in content


async def test_delete_note_not_found(mcp):
    with pytest.raises(MCPError):
        await mcp.call_tool("delete-note", {"vault": "test", "path": "missing.md"})


async def test_move_note_rejects_existing_destination(mcp):
    """ISC-19."""
    await mcp.call_tool("create-note", {"vault": "test", "filename": "a.md", "content": "a"})
    await mcp.call_tool("create-note", {"vault": "test", "filename": "b.md", "content": "b"})
    with pytest.raises(MCPError):
        await mcp.call_tool("move-note", {"vault": "test", "source": "a.md", "destination": "b.md"})


async def test_move_note_rewrites_links(mcp, vault_path):
    """ISC-20. Link rewriting is name-based (matching TS): a same-basename
    folder-only move is a no-op for wikilinks, since `[[target]]` stays valid
    regardless of which folder the note lives in. This test exercises an actual
    rename (basename change), which is what triggers a rewrite."""
    await mcp.call_tool("create-note", {"vault": "test", "filename": "target.md", "content": "x"})
    await mcp.call_tool("create-note", {"vault": "test", "filename": "referrer.md", "content": "See [[target]] and [link](target.md)"})

    await mcp.call_tool("move-note", {"vault": "test", "source": "target.md", "destination": "renamed.md"})

    assert os.path.exists(os.path.join(vault_path, "renamed.md"))
    content = open(os.path.join(vault_path, "referrer.md")).read()
    assert "[[renamed]]" in content
    assert "[link](renamed.md)" in content
    assert "[[target]]" not in content
    assert "[link](target.md)" not in content


async def test_create_directory_via_shared_validator_rejects_traversal(mcp):
    """ISC-21: create-directory is routed through the shared path validator."""
    with pytest.raises(MCPError):
        await mcp.call_tool("create-directory", {"vault": "test", "path": "../../etc/evil"})


async def test_create_directory_rejects_existing(mcp, vault_path):
    """ISC-22."""
    os.makedirs(os.path.join(vault_path, "existing"))
    with pytest.raises(MCPError):
        await mcp.call_tool("create-directory", {"vault": "test", "path": "existing"})


async def test_create_directory_creates_recursively(mcp, vault_path):
    await mcp.call_tool("create-directory", {"vault": "test", "path": "a/b/c"})
    assert os.path.isdir(os.path.join(vault_path, "a", "b", "c"))
