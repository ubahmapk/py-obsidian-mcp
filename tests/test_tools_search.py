from __future__ import annotations


async def test_search_vault_content_match(mcp):
    """ISC-23."""
    await mcp.call_tool("create-note", {"vault": "test", "filename": "note.md", "content": "hello world"})
    r = await mcp.call_tool("search-vault", {"vault": "test", "query": "hello", "search_type": "content"})
    assert "note.md" in r.content[0].text
    assert "1 match" in r.content[0].text


async def test_search_vault_filename_match(mcp):
    """ISC-23."""
    await mcp.call_tool("create-note", {"vault": "test", "filename": "meeting-notes.md", "content": "x"})
    r = await mcp.call_tool("search-vault", {"vault": "test", "query": "meeting", "search_type": "filename"})
    assert "meeting-notes.md" in r.content[0].text


async def test_search_vault_tag_search():
    """ISC-24 -- covered end-to-end via test_tools_tags.py's add-tags + this."""


async def test_search_vault_tag_query(mcp):
    await mcp.call_tool("create-note", {"vault": "test", "filename": "note.md", "content": "text"})
    await mcp.call_tool("add-tags", {"vault": "test", "files": ["note.md"], "tags": ["status/active"], "location": "content"})

    r = await mcp.call_tool("search-vault", {"vault": "test", "query": "tag:status/active"})
    assert "note.md" in r.content[0].text


async def test_search_vault_no_matches(mcp):
    await mcp.call_tool("create-note", {"vault": "test", "filename": "note.md", "content": "hello"})
    r = await mcp.call_tool("search-vault", {"vault": "test", "query": "nonexistent-string"})
    assert "No matches found" in r.content[0].text


async def test_search_vault_max_results_caps_output(mcp):
    """ISC-25: new capability, working max_results."""
    for i in range(5):
        await mcp.call_tool("create-note", {"vault": "test", "filename": f"note{i}.md", "content": "hello"})

    r = await mcp.call_tool("search-vault", {"vault": "test", "query": "hello", "search_type": "content", "max_results": 2})
    assert "Found 2 match" in r.content[0].text
    file_headers = [line for line in r.content[0].text.splitlines() if line.startswith("File: ")]
    assert len(file_headers) == 2
