from __future__ import annotations

from obsidian_mcp.utils.line_classifier import iter_lines_with_context


def test_fence_marker_lines_are_always_skipped():
    content = "```\ncode #tag1\n```\ntext #tag2"
    ctxs = iter_lines_with_context(content)
    assert ctxs[0].is_fence_marker and ctxs[0].skip
    assert ctxs[1].in_code_block and ctxs[1].skip
    assert ctxs[2].is_fence_marker and ctxs[2].skip
    assert not ctxs[3].skip


def test_html_comment_toggles_per_occurrence():
    content = "<!-- start\n#hidden\nend -->\n#visible"
    ctxs = iter_lines_with_context(content)
    assert ctxs[0].in_html_comment and ctxs[0].skip
    assert ctxs[1].in_html_comment and ctxs[1].skip
    assert ctxs[2].in_html_comment is False  # closes on this line, matches TS's non-matched-pair toggle
    assert not ctxs[3].skip


def test_known_limitation_same_line_open_and_close_comment():
    """Documents the accepted limitation: TS toggles per-occurrence, not per matched
    pair, so a same-line `<!-- x -->` opens then immediately closes -- correct in
    this case, but nested/malformed constructs on other lines can still confuse it.
    This is intentional parity with TS, not a bug to fix."""
    content = "<!-- inline --> #tag"
    ctxs = iter_lines_with_context(content)
    assert ctxs[0].in_html_comment is False
    assert not ctxs[0].skip
