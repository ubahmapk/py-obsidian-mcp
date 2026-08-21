"""`search-vault` tool. Ported from TS `tools/search-vault/index.ts`.

Adds a working `max_results` parameter -- TS declared `SearchOptions.maxResults`
in its type but never implemented it. Default (unlimited) behavior is unchanged
unless a caller opts in, so this is a pure addition, not a breaking change.
"""

from __future__ import annotations

import os
from typing import Literal

import anyio
from mcp.server.mcpserver import MCPServer
from mcp.shared.exceptions import MCPError
from mcp.types import INTERNAL_ERROR
from pydantic import BaseModel, ConfigDict, Field

from obsidian_mcp.registry import validate
from obsidian_mcp.utils.errors import handle_fs_error
from obsidian_mcp.utils.files import get_all_markdown_files
from obsidian_mcp.utils.path_safety import normalize_path, safe_join_path
from obsidian_mcp.utils.responses import (
    SearchMatch,
    SearchOperationResult,
    SearchResult,
    format_search_result,
)
from obsidian_mcp.utils.tags import extract_tags, matches_tag_pattern, normalize_tag
from obsidian_mcp.vault_resolver import VaultResolver


class SearchVaultInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vault: str = Field(..., min_length=1, description="Name of the vault to search in")
    query: str = Field(..., min_length=1, description="Search query. Use tag: prefix for tag search")
    path: str | None = Field(None, description="Optional subfolder path within the vault to limit search scope")
    case_sensitive: bool = Field(False, description="Whether to perform case-sensitive search")
    search_type: Literal["content", "filename", "both"] = Field("content", description="Type of search to perform")
    max_results: int | None = Field(None, ge=1, description="Optional cap on the number of matches returned")


def _is_tag_search(query: str) -> bool:
    return query.startswith("tag:")


async def _search_filenames(vault_path: str, query: str, path: str | None, case_sensitive: bool) -> list[SearchResult]:
    try:
        search_dir = safe_join_path(vault_path, path) if path else vault_path
        files = await get_all_markdown_files(vault_path, search_dir)
        results: list[SearchResult] = []
        search_query = query if case_sensitive else query.lower()

        for file_path in files:
            relative_path = os.path.relpath(file_path, vault_path)
            search_target = relative_path if case_sensitive else relative_path.lower()
            if search_query in search_target:
                results.append(SearchResult(file=relative_path, matches=[SearchMatch(line=0, text=f"Filename match: {relative_path}")]))
        return results
    except MCPError:
        raise
    except OSError as exc:
        handle_fs_error(exc, "search filenames")
        raise  # unreachable


async def _search_content(vault_path: str, query: str, path: str | None, case_sensitive: bool) -> list[SearchResult]:
    try:
        search_dir = safe_join_path(vault_path, path) if path else vault_path
        files = await get_all_markdown_files(vault_path, search_dir)
        results: list[SearchResult] = []
        is_tag_query = _is_tag_search(query)
        normalized_tag_query = normalize_tag(query[4:]) if is_tag_query else ""

        for file_path in files:
            try:
                content = await anyio.Path(file_path).read_text(encoding="utf-8")
            except OSError:
                continue

            lines = content.split("\n")
            matches: list[SearchMatch] = []

            if is_tag_query:
                for index, line in enumerate(lines):
                    line_tags = extract_tags(line)
                    if any(
                        normalize_tag(tag) == normalized_tag_query or matches_tag_pattern(normalized_tag_query, normalize_tag(tag))
                        for tag in line_tags
                    ):
                        matches.append(SearchMatch(line=index + 1, text=line.strip()))
            else:
                search_query = query if case_sensitive else query.lower()
                for index, line in enumerate(lines):
                    search_line = line if case_sensitive else line.lower()
                    if search_query in search_line:
                        matches.append(SearchMatch(line=index + 1, text=line.strip()))

            if matches:
                results.append(SearchResult(file=os.path.relpath(file_path, vault_path), matches=matches))

        return results
    except MCPError:
        raise
    except OSError as exc:
        handle_fs_error(exc, "search content")
        raise  # unreachable


async def _search_vault(
    vault_path: str,
    query: str,
    path: str | None,
    case_sensitive: bool,
    search_type: Literal["content", "filename", "both"],
    max_results: int | None,
) -> SearchOperationResult:
    normalized_vault_path = normalize_path(vault_path)
    results: list[SearchResult] = []
    errors: list[str] = []

    if search_type in ("filename", "both"):
        try:
            results.extend(await _search_filenames(normalized_vault_path, query, path, case_sensitive))
        except MCPError as exc:
            errors.append(f"Filename search error: {exc}")
        except Exception as exc:  # noqa: BLE001 - mirrors TS's catch-all-and-continue
            errors.append(f"Filename search failed: {exc}")

    if search_type in ("content", "both"):
        try:
            results.extend(await _search_content(normalized_vault_path, query, path, case_sensitive))
        except MCPError as exc:
            errors.append(f"Content search error: {exc}")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Content search failed: {exc}")

    if max_results is not None:
        results = results[:max_results]

    total_matches = sum(len(r.matches) for r in results)

    if results and errors:
        return SearchOperationResult(
            results=results,
            total_matches=total_matches,
            matched_files=len(results),
            message="Search completed with warnings:\n" + "\n".join(errors),
        )

    if not results and errors:
        raise MCPError(INTERNAL_ERROR, "Search failed:\n" + "\n".join(errors))

    return SearchOperationResult(results=results, total_matches=total_matches, matched_files=len(results))


def register(mcp: MCPServer, vaults: dict[str, str]) -> None:
    resolver = VaultResolver(vaults)

    async def search_vault(
        vault: str,
        query: str,
        path: str | None = None,
        case_sensitive: bool = False,
        search_type: Literal["content", "filename", "both"] = "content",
        max_results: int | None = None,
    ) -> str:
        args = validate(
            SearchVaultInput,
            vault=vault,
            query=query,
            path=path,
            case_sensitive=case_sensitive,
            search_type=search_type,
            max_results=max_results,
        )
        vault_path = resolver.resolve_vault(args.vault)
        result = await _search_vault(
            vault_path, args.query, args.path, args.case_sensitive, args.search_type, args.max_results
        )
        return format_search_result(result)

    mcp.add_tool(
        search_vault,
        name="search-vault",
        description=(
            "Search for specific content within vault notes (NOT for listing available vaults - "
            "use the list-vaults prompt for that).\n\n"
            "This tool searches through note contents and filenames for specific text or tags:\n"
            "- Content search: { \"vault\": \"vault1\", \"query\": \"hello world\", \"search_type\": \"content\" }\n"
            "- Filename search: { \"vault\": \"vault2\", \"query\": \"meeting-notes\", \"search_type\": \"filename\" }\n"
            "- Search both: { \"vault\": \"vault1\", \"query\": \"project\", \"search_type\": \"both\" }\n"
            "- Tag search: { \"vault\": \"vault2\", \"query\": \"tag:status/active\" }\n"
            "- Search in subfolder: { \"vault\": \"vault1\", \"query\": \"hello\", \"path\": \"journal/2024\" }\n\n"
            "Note: To get a list of available vaults, use the list-vaults prompt instead of this search tool."
        ),
        structured_output=False,
    )
