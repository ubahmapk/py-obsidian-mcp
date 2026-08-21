"""Text-formatting helpers for tool responses, ported from TS `utils/responses.ts`."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from obsidian_mcp.utils.tags import TagChange

_OPERATION_TEXT = {"create": "Created", "edit": "Modified", "delete": "Deleted", "move": "Moved"}


@dataclass
class FileOperationResult:
    success: bool
    message: str
    operation: Literal["create", "edit", "delete", "move"]
    path: str


def format_file_result(result: FileOperationResult) -> str:
    return f"{_OPERATION_TEXT[result.operation]} file: {result.path}\n{result.message}"


@dataclass
class TagOperationResult:
    success: bool
    message: str
    total_count: int
    success_count: int
    details: dict[str, list[TagChange]]
    failed_items: list[tuple[str, str]] = field(default_factory=list)


def _format_tag_changes(changes: list[TagChange]) -> str:
    by_location: dict[str, set[str]] = {}
    for change in changes:
        by_location.setdefault(change.location, set()).add(change.tag)
    return "\n".join(f"  {location}: {', '.join(sorted(tags))}" for location, tags in by_location.items())


def format_tag_result(result: TagOperationResult) -> str:
    parts = [result.message, f"\nProcessed {result.total_count} files: {result.success_count} modified"]

    for filename, changes in result.details.items():
        if changes:
            parts.append(f"\nChanges in {filename}:")
            parts.append(_format_tag_changes(changes))

    if result.failed_items:
        parts.append("\nErrors:")
        for item, error in result.failed_items:
            parts.append(f"  {item}: {error}")

    return "\n".join(parts)


@dataclass
class SearchMatch:
    line: int
    text: str


@dataclass
class SearchResult:
    file: str
    matches: list[SearchMatch] = field(default_factory=list)


@dataclass
class SearchOperationResult:
    results: list[SearchResult]
    total_matches: int
    matched_files: int
    message: str = "Search completed successfully"


def format_search_result(result: SearchOperationResult) -> str:
    parts = [f"Found {result.total_matches} match{'' if result.total_matches == 1 else 'es'} in {result.matched_files} file{'' if result.matched_files == 1 else 's'}"]

    if not result.results:
        return "No matches found."

    filename_matches = [r for r in result.results if any(m.line == 0 for m in r.matches)]
    content_matches = [r for r in result.results if any(m.line != 0 for m in r.matches)]

    if filename_matches:
        parts.append("\nFilename matches:")
        for result_item in filename_matches:
            parts.append(f"  {result_item.file}")

    if content_matches:
        parts.append("\nContent matches:")
        for result_item in content_matches:
            parts.append(f"\nFile: {result_item.file}")
            for match in result_item.matches:
                if match.line != 0:
                    parts.append(f"  Line {match.line}: {match.text}")

    return "\n".join(parts)
