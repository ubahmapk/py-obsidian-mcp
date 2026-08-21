"""Tag validation, normalization, and frontmatter/inline manipulation.

Ported from TS `utils/tags.ts`. Code-block/HTML-comment detection delegates to
`line_classifier.py` instead of re-implementing the scan three times (TS
duplicates it in `extractTags`, `removeInlineTags`, and `rename-tag`'s
`updateInlineTags`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from mcp.shared.exceptions import MCPError
from mcp.types import INVALID_PARAMS

from obsidian_mcp.utils.line_classifier import TAG_PATTERN, iter_lines_with_context

_TAG_RE = re.compile(r"^[a-zA-Z0-9]+(/[a-zA-Z0-9]+)*$")
_INLINE_TAG_RE = re.compile(TAG_PATTERN)
_CAMEL_RE = re.compile(r"([a-z0-9])([A-Z])")


@dataclass(frozen=True)
class TagChange:
    tag: str
    location: str  # "frontmatter" | "content"
    line: int | None = None
    context: str | None = None


def is_parent_tag(parent_tag: str, child_tag: str) -> bool:
    return child_tag.startswith(parent_tag + "/")


def matches_tag_pattern(pattern: str, tag: str) -> bool:
    """Glob-style `*` wildcard matching, hierarchical via `/`."""
    regex_pattern = pattern.replace("*", ".*").replace("/", r"\/")
    return re.match(f"^{regex_pattern}$", tag) is not None


def get_related_tags(tag: str, all_tags: list[str]) -> tuple[list[str], list[str]]:
    """Returns (parents, children) of `tag` among `all_tags`."""
    parents: list[str] = []
    parts = tag.split("/")
    current = ""
    for part in parts[:-1]:
        current = f"{current}/{part}" if current else part
        parents.append(current)

    children = [other for other in all_tags if is_parent_tag(tag, other)]
    return parents, children


def validate_tag(tag: str) -> bool:
    """Allows tag, tag/subtag; disallows empty or special characters other than '/'."""
    tag = tag.lstrip("#") if tag.startswith("#") else tag
    tag = re.sub(r"^#", "", tag)
    if not tag:
        return False
    return _TAG_RE.match(tag) is not None


def normalize_tag(tag: str, normalize: bool = True) -> str:
    """camelCase/PascalCase -> kebab-case, per hierarchy segment."""
    tag = re.sub(r"^#", "", tag)
    if not normalize:
        return tag
    return "/".join(_CAMEL_RE.sub(r"\1-\2", part).lower() for part in tag.split("/"))


def extract_tags(content: str) -> list[str]:
    """All hashtags in `content`, skipping fenced code blocks and HTML comments."""
    tags: set[str] = set()
    for ctx in iter_lines_with_context(content):
        if ctx.skip:
            continue
        for match in _INLINE_TAG_RE.finditer(ctx.text):
            tags.add(match.group(0)[1:])
    return list(tags)


def add_tags_to_frontmatter(
    frontmatter: dict[str, Any], new_tags: list[str], normalize: bool = True
) -> dict[str, Any]:
    """Merges new_tags into frontmatter['tags'], validating and de-duplicating."""
    updated = dict(frontmatter)
    existing_tags: set[str] = set(frontmatter.get("tags") or []) if isinstance(frontmatter.get("tags"), list) else set()

    for tag in new_tags:
        if not validate_tag(tag):
            raise MCPError(INVALID_PARAMS, f"Invalid tag format: {tag}")
        existing_tags.add(normalize_tag(tag, normalize))

    updated["tags"] = sorted(existing_tags)
    return updated


@dataclass
class TagRemovalReport:
    removed: list[TagChange]
    preserved: list[TagChange]


def remove_tags_from_frontmatter(
    frontmatter: dict[str, Any],
    tags_to_remove: list[str],
    normalize: bool = True,
    preserve_children: bool = False,
    patterns: list[str] | None = None,
) -> tuple[dict[str, Any], TagRemovalReport]:
    """Removes matching tags (direct, pattern, or hierarchical) from frontmatter['tags']."""
    patterns = patterns or []
    updated = dict(frontmatter)
    existing_tags: list[str] = list(frontmatter.get("tags") or []) if isinstance(frontmatter.get("tags"), list) else []

    removed: list[TagChange] = []
    preserved: list[TagChange] = []
    kept: list[str] = []

    for tag in existing_tags:
        normalized_tag = normalize_tag(tag, normalize)
        should_remove = False
        for remove_tag in tags_to_remove:
            if normalize_tag(remove_tag, normalize) == normalized_tag:
                should_remove = True
                break
            if any(matches_tag_pattern(pattern, normalized_tag) for pattern in patterns):
                should_remove = True
                break
            if not preserve_children and is_parent_tag(remove_tag, normalized_tag):
                should_remove = True
                break

        if should_remove:
            removed.append(TagChange(tag=normalized_tag, location="frontmatter"))
        else:
            preserved.append(TagChange(tag=normalized_tag, location="frontmatter"))
            kept.append(normalized_tag)

    updated["tags"] = sorted(kept)
    return updated, TagRemovalReport(removed=removed, preserved=preserved)


def remove_inline_tags(
    content: str,
    tags_to_remove: list[str],
    normalize: bool = True,
    preserve_children: bool = False,
    patterns: list[str] | None = None,
) -> tuple[str, TagRemovalReport]:
    """Removes matching inline #tags from content, skipping code blocks/HTML comments."""
    patterns = patterns or []
    removed: list[TagChange] = []
    preserved: list[TagChange] = []
    output_lines: list[str] = []

    for ctx in iter_lines_with_context(content):
        if ctx.skip:
            if not ctx.is_fence_marker:
                for match in _INLINE_TAG_RE.finditer(ctx.text):
                    preserved.append(
                        TagChange(tag=match.group(0)[1:], location="content", line=ctx.line_no, context=ctx.text.strip())
                    )
            output_lines.append(ctx.text)
            continue

        def _replace(match: re.Match[str], _ctx=ctx) -> str:
            # _ctx defaulted to the current loop value: _replace is only ever
            # invoked synchronously by .sub() within this same iteration, but the
            # default-argument binding makes that explicit rather than relying on
            # closure-over-loop-variable timing.
            tag = match.group(0)[1:]
            normalized_tag = normalize_tag(tag, normalize)
            should_remove = False
            for remove_tag in tags_to_remove:
                if normalize_tag(remove_tag, normalize) == normalized_tag:
                    should_remove = True
                    break
                if any(matches_tag_pattern(pattern, normalized_tag) for pattern in patterns):
                    should_remove = True
                    break
                if not preserve_children and is_parent_tag(remove_tag, normalized_tag):
                    should_remove = True
                    break

            if should_remove:
                removed.append(TagChange(tag=normalized_tag, location="content", line=_ctx.line_no, context=_ctx.text.strip()))
                return ""
            preserved.append(TagChange(tag=normalized_tag, location="content", line=_ctx.line_no, context=_ctx.text.strip()))
            return match.group(0)

        output_lines.append(_INLINE_TAG_RE.sub(_replace, ctx.text))

    collapsed: list[str] = []
    for line in output_lines:
        if line.strip() == "" and collapsed and collapsed[-1].strip() == "":
            continue
        collapsed.append(line)

    return "\n".join(collapsed), TagRemovalReport(removed=removed, preserved=preserved)
