"""Note frontmatter parsing, ported from TS `utils/tags.ts` (parseNote/stringifyNote).

Hand-rolled with PyYAML rather than the `python-frontmatter` package: that
package's delimiter detection is more permissive than the TS original (which
requires content to *start* with `---\\n`, no leading blank lines, `\\n`-only),
and using it would create subtle, silent behavior drift from a real Obsidian
vault edited by the original TS server. A `\\r\\n` -> `\\n` normalization pass is
added as a portability nicety beyond TS, not a behavior gap.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import yaml
from mcp.shared.exceptions import MCPError
from mcp.types import INVALID_PARAMS

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)


@dataclass
class ParsedNote:
    frontmatter: dict[str, Any] = field(default_factory=dict)
    content: str = ""
    has_frontmatter: bool = False


def parse_note(content: str) -> ParsedNote:
    """Splits note content into frontmatter dict + body."""
    normalized = content.replace("\r\n", "\n")
    match = _FRONTMATTER_RE.match(normalized)

    if not match:
        return ParsedNote(frontmatter={}, content=content, has_frontmatter=False)

    try:
        frontmatter = yaml.safe_load(match.group(1))
    except yaml.YAMLError as exc:
        raise MCPError(INVALID_PARAMS, "Invalid frontmatter YAML format") from exc

    return ParsedNote(frontmatter=frontmatter or {}, content=match.group(2), has_frontmatter=True)


def stringify_note(parsed: ParsedNote) -> str:
    """Recombines frontmatter + body into note text."""
    if not parsed.has_frontmatter or not parsed.frontmatter:
        return parsed.content

    frontmatter_str = yaml.safe_dump(parsed.frontmatter, sort_keys=False).strip()
    return f"---\n{frontmatter_str}\n---\n\n{parsed.content.strip()}"
