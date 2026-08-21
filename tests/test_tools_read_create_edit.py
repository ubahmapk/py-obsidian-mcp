from __future__ import annotations

import os

import pytest
from mcp.shared.exceptions import MCPError


async def test_create_note_then_read_it(mcp, vault_path):
    r = await mcp.call_tool("create-note", {"vault": "test", "filename": "note1", "content": "# Hello"})
    assert "Created file" in r.content[0].text
    assert os.path.exists(os.path.join(vault_path, "note1.md"))

    r = await mcp.call_tool("read-note", {"vault": "test", "filename": "note1.md"})
    assert "# Hello" in r.content[0].text


async def test_create_note_refuses_overwrite(mcp):
    await mcp.call_tool("create-note", {"vault": "test", "filename": "dup.md", "content": "a"})
    with pytest.raises(MCPError):
        await mcp.call_tool("create-note", {"vault": "test", "filename": "dup.md", "content": "b"})


async def test_create_note_creates_parent_folders(mcp, vault_path):
    await mcp.call_tool("create-note", {"vault": "test", "filename": "note.md", "folder": "journal/2024", "content": "x"})
    assert os.path.exists(os.path.join(vault_path, "journal", "2024", "note.md"))


async def test_read_note_rejects_path_separator_in_filename(mcp):
    with pytest.raises(MCPError):
        await mcp.call_tool("read-note", {"vault": "test", "filename": "folder/note.md"})


async def test_read_note_not_found(mcp):
    with pytest.raises(MCPError):
        await mcp.call_tool("read-note", {"vault": "test", "filename": "missing.md"})


async def test_edit_note_append(mcp, vault_path):
    await mcp.call_tool("create-note", {"vault": "test", "filename": "note.md", "content": "line1"})
    r = await mcp.call_tool("edit-note", {"vault": "test", "filename": "note.md", "operation": "append", "content": "line2"})
    assert "appended successfully" in r.content[0].text
    content = open(os.path.join(vault_path, "note.md")).read()
    assert "line1" in content and "line2" in content


async def test_edit_note_replace(mcp, vault_path):
    await mcp.call_tool("create-note", {"vault": "test", "filename": "note.md", "content": "old"})
    await mcp.call_tool("edit-note", {"vault": "test", "filename": "note.md", "operation": "replace", "content": "new"})
    content = open(os.path.join(vault_path, "note.md")).read()
    assert content == "new"


async def test_edit_note_delete_leaves_no_orphan_backup(mcp, vault_path):
    """ISC-15."""
    await mcp.call_tool("create-note", {"vault": "test", "filename": "note.md", "content": "x"})
    await mcp.call_tool("edit-note", {"vault": "test", "filename": "note.md", "operation": "delete"})

    assert not os.path.exists(os.path.join(vault_path, "note.md"))
    remaining = [f for f in os.listdir(vault_path) if f.endswith(".backup")]
    assert remaining == []


async def test_edit_note_restores_on_failure(mcp, vault_path, monkeypatch):
    """ISC-14: a simulated write failure mid-edit restores the original content."""
    await mcp.call_tool("create-note", {"vault": "test", "filename": "note.md", "content": "original"})

    import anyio

    original_write_text = anyio.Path.write_text
    call_count = {"n": 0}

    async def flaky_write_text(self, data, *args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise OSError("simulated disk failure")
        return await original_write_text(self, data, *args, **kwargs)

    monkeypatch.setattr(anyio.Path, "write_text", flaky_write_text)

    # the raw OSError is mapped to an MCPError by handle_fs_error, matching
    # TS's handleFsError -- the restore-on-failure behavior under test happens
    # regardless of how the error surfaces to the caller.
    with pytest.raises(MCPError):
        await mcp.call_tool("edit-note", {"vault": "test", "filename": "note.md", "operation": "replace", "content": "new"})

    content = open(os.path.join(vault_path, "note.md")).read()
    assert content == "original"
