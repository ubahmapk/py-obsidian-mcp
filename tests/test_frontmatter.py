from __future__ import annotations

import pytest
from mcp.shared.exceptions import MCPError

from obsidian_mcp.utils.frontmatter import ParsedNote, parse_note, stringify_note


def test_parse_note_without_frontmatter():
    parsed = parse_note("just content\nmore lines")
    assert parsed.has_frontmatter is False
    assert parsed.frontmatter == {}
    assert parsed.content == "just content\nmore lines"


def test_parse_note_with_frontmatter():
    content = "---\ntags:\n  - a\n  - b\n---\nbody text"
    parsed = parse_note(content)
    assert parsed.has_frontmatter is True
    assert parsed.frontmatter == {"tags": ["a", "b"]}
    assert parsed.content == "body text"


def test_parse_note_normalizes_crlf():
    content = "---\r\ntitle: x\r\n---\r\nbody"
    parsed = parse_note(content)
    assert parsed.has_frontmatter is True
    assert parsed.frontmatter == {"title": "x"}


def test_parse_note_invalid_yaml_raises():
    content = "---\n[invalid: yaml: here\n---\nbody"
    with pytest.raises(MCPError):
        parse_note(content)


def test_stringify_note_roundtrip():
    parsed = ParsedNote(frontmatter={"tags": ["a"]}, content="body text", has_frontmatter=True)
    result = stringify_note(parsed)
    reparsed = parse_note(result)
    assert reparsed.frontmatter == {"tags": ["a"]}
    # stringify_note inserts a blank line after the closing "---" for
    # readability, and the parse regex only consumes one "\n" after it, so a
    # leading "\n" survives into the reparsed body -- matches the TS original's
    # parseNote/stringifyNote pairing exactly, not a bug.
    assert reparsed.content.strip() == "body text"


def test_stringify_note_no_frontmatter_returns_content_only():
    parsed = ParsedNote(frontmatter={}, content="just body", has_frontmatter=False)
    assert stringify_note(parsed) == "just body"
