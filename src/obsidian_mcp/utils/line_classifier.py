"""Shared per-line code-block/HTML-comment state scanner.

TS duplicated this exact line-scanning pattern three times independently
(`extractTags`, `removeInlineTags`, and `rename-tag`'s `updateInlineTags`). This
module is the single Python implementation all of them delegate to.

This is a pragmatic scanner, not a real markdown/HTML parser: it toggles
`in_code_block` on any line whose trimmed text starts with ``` and toggles
`in_html_comment` independently on the presence of `<!--`/`-->` per line (not
matched pairs). It will misclassify nested/malformed fences or comments, same as
the TS original -- this is a known, accepted limitation, not a bug to "fix" later.
"""

from __future__ import annotations

from dataclasses import dataclass

TAG_PATTERN = r"(?<!`)#[a-zA-Z0-9][a-zA-Z0-9/]*(?!`)"


@dataclass(frozen=True)
class LineContext:
    text: str
    line_no: int  # 1-indexed
    in_code_block: bool
    in_html_comment: bool
    is_fence_marker: bool = False

    @property
    def skip(self) -> bool:
        """True if tags on this line should be left alone entirely.

        Fence-marker lines (```) are always skipped, matching TS's `continue` on
        the fence line itself. Non-fence lines are skipped while inside a code
        block or HTML comment.
        """
        return self.is_fence_marker or self.in_code_block or self.in_html_comment


def iter_lines_with_context(content: str) -> list[LineContext]:
    """Splits content into lines, tagging each with code-block/comment state."""
    contexts: list[LineContext] = []
    in_code_block = False
    in_html_comment = False

    for index, line in enumerate(content.split("\n")):
        if line.strip().startswith("```"):
            in_code_block = not in_code_block
            contexts.append(LineContext(line, index + 1, in_code_block, in_html_comment, is_fence_marker=True))
            continue

        if "<!--" in line:
            in_html_comment = True
        if "-->" in line:
            in_html_comment = False

        contexts.append(LineContext(line, index + 1, in_code_block, in_html_comment))

    return contexts
