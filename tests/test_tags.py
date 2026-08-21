from __future__ import annotations

import pytest
from mcp.shared.exceptions import MCPError

from obsidian_mcp.utils.tags import (
    add_tags_to_frontmatter,
    extract_tags,
    matches_tag_pattern,
    normalize_tag,
    remove_inline_tags,
    remove_tags_from_frontmatter,
    validate_tag,
)


@pytest.mark.parametrize(
    ("tag", "expected"),
    [
        ("project", True),
        ("work/active", True),
        ("tasks/2024/q1", True),
        ("", False),
        ("#project", True),  # leading # stripped before validation
        ("has space", False),
        ("has-dash", False),
    ],
)
def test_validate_tag(tag, expected):
    assert validate_tag(tag) is expected


@pytest.mark.parametrize(
    ("tag", "expected"),
    [
        ("ProjectActive", "project-active"),
        ("work/ActiveNow", "work/active-now"),
        ("already-kebab", "already-kebab"),
    ],
)
def test_normalize_tag(tag, expected):
    assert normalize_tag(tag) == expected


def test_normalize_tag_disabled():
    assert normalize_tag("ProjectActive", normalize=False) == "ProjectActive"


def test_matches_tag_pattern_wildcard():
    assert matches_tag_pattern("status/*", "status/active") is True
    assert matches_tag_pattern("status/*", "other/active") is False


def test_extract_tags_skips_code_block():
    # Note: the tag pattern (matching TS) doesn't include '-' in the character
    # class, same as validate_tag's allowed charset -- realistic tags here.
    content = "#realtag\n```\n#faketag\n```\n#anotherreal"
    tags = extract_tags(content)
    assert set(tags) == {"realtag", "anotherreal"}


def test_extract_tags_skips_html_comment():
    content = "<!--\n#hidden\n-->\n#visible"
    assert extract_tags(content) == ["visible"]


def test_add_tags_to_frontmatter_dedup_and_sort():
    result = add_tags_to_frontmatter({"tags": ["b"]}, ["a", "b"])
    assert result["tags"] == ["a", "b"]


def test_add_tags_to_frontmatter_invalid_tag_raises():
    with pytest.raises(MCPError):
        add_tags_to_frontmatter({}, ["not a tag!"])


def test_remove_tags_from_frontmatter_direct_match():
    updated, report = remove_tags_from_frontmatter({"tags": ["a", "b"]}, ["a"])
    assert updated["tags"] == ["b"]
    assert [c.tag for c in report.removed] == ["a"]
    assert [c.tag for c in report.preserved] == ["b"]


def test_remove_tags_from_frontmatter_hierarchical_removes_children():
    updated, _report = remove_tags_from_frontmatter({"tags": ["work", "work/active"]}, ["work"])
    assert updated["tags"] == []


def test_remove_tags_from_frontmatter_preserve_children():
    updated, _report = remove_tags_from_frontmatter(
        {"tags": ["work", "work/active"]}, ["work"], preserve_children=True
    )
    assert updated["tags"] == ["work/active"]


def test_remove_tags_from_frontmatter_pattern_match():
    # The real remove-tags tool schema always requires >=1 entry in `tags`
    # (matching TS's zod .min(1)), so a pattern-only call always pairs with at
    # least one (possibly non-matching) tag -- "nonexistent" here.
    updated, _report = remove_tags_from_frontmatter(
        {"tags": ["status/active", "status/done"]}, ["nonexistent"], patterns=["status/*"]
    )
    assert updated["tags"] == []


def test_remove_inline_tags_direct_and_preserved():
    content = "text #remove and #keep"
    new_content, report = remove_inline_tags(content, ["remove"])
    assert "#remove" not in new_content
    assert "#keep" in new_content
    assert [c.tag for c in report.removed] == ["remove"]
    assert [c.tag for c in report.preserved] == ["keep"]


def test_remove_inline_tags_skips_code_block():
    content = "```\n#remove\n```\ntext #remove"
    new_content, report = remove_inline_tags(content, ["remove"])
    assert new_content.count("#remove") == 1  # only the fenced one survives
    assert len(report.removed) == 1
