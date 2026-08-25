---
task: "Port TypeScript obsidian-mcp server to Python"
project: py-obsidian-mcp
effort: E3
effort_source: classifier
phase: complete
progress: 38/38
mode: interactive
started: 2026-08-21T13:30:00-07:00
updated: 2026-08-21T19:00:00-07:00
---

## Problem

`/Users/jallen/github/py-obsidian-mcp` is empty. The reference implementation, `/Users/jallen/github/obsidian-mcp` (TypeScript), gives an LLM client stdio-based read/write access to local Obsidian vaults, but there is no Python equivalent, and the TS original has a confirmed security bug (`validateVaultPath` calls the async `checkPathSafety` without `await`, so the vault-containment check never throws — path-traversal protection is a no-op in the shipped server) plus several inconsistencies (dead `manage-tags` tool, duplicate resource implementations, `create-directory` skipping shared path validation, a self-defeating connection-monitor heartbeat, zero tests for tag/link logic).

## Vision

A developer runs `uv run obsidian-mcp <vault-path>` and it just works with Claude Desktop exactly like the TS version did — same 11 tools, same prompt, same resource scheme — except the path-traversal bug is structurally impossible (sync validation, no async footgun), the dead/duplicate code is gone, and the previously-untested tag/link logic has real coverage.

## Out of Scope

- ~~Windows support~~ — **now in scope and implemented** (issue #1): drive letters, UNC paths, reserved device names, and a Windows system-directory denylist are handled in `path_safety.py` via runtime platform dispatch. Network-drive detection is a UNC heuristic only (no `wmic`/PowerShell probing, no `pywin32`) — mapped network drive *letters* are not detected, a deliberate tradeoff consistent with dropping the Unix `df` shell-out.
- The `manage-tags` tool — confirmed dead code in TS (never registered); `add-tags`/`remove-tags` already cover it.
- Cross-vault link rewriting (`isMovedToOtherVault`/`isMovedFromOtherVault` branches) — confirmed unreachable in TS, no tool ever exercises them.
- `RateLimiter` and `ConnectionMonitor` subsystems — the rate limiter is a global per-RPC-method budget (not real per-client protection) and the connection monitor's own heartbeat resets the idle clock it's supposed to enforce, making it self-defeating by construction.
- Obsidian Local REST API plugin / HTTP transport / any auth-token mechanism — the server is direct-filesystem-only, stdio-only, exactly like the TS original.
- Non-markdown vault content (images, PDFs, attachments) — invisible to this server, same as TS.

## Constraints

- Must use the official Python `mcp` SDK, stdio transport, matching the TS server's JSON-RPC method surface (`tools/list`, `tools/call`, `resources/list`, `resources/read`, `prompts/list`, `prompts/get`). (Revised after empirical SDK verification: the installed `mcp==2.0.0` has no low-level decorator API in the form originally assumed — uses `mcp.server.mcpserver.MCPServer` instead. See the plan's "SDK Addendum" section.)
- Must use Pydantic v2 models (`extra="forbid"`) for every tool's input schema, generating `inputSchema` via `model_json_schema()`.
- Path-safety functions (`check_path_safety`, `validate_vault_path`, `safe_join_path`) must be synchronous — no async/await boundary in the containment-check call chain, so the TS bug class is structurally impossible.
- Packaging via `uv` + `pyproject.toml`, `requires-python = ">=3.11"`, entry point `obsidian-mcp`.
- All 11 registered TS tools must have functionally equivalent Python tools with matching input shape and response text formatting.

## Goal

`uv run pytest` passes with tests covering path safety (including a path-traversal-rejection regression test), tag/link logic, and all 11 tools; `uv run obsidian-mcp <vault-path>` starts cleanly against a real `.obsidian`-containing directory and each tool is callable via the MCP dev inspector with correct filesystem side effects and response text.

## Criteria

- [x] ISC-1: `pyproject.toml` exists with `requires-python = ">=3.11"` and `[project.scripts] obsidian-mcp` entry point
- [x] ISC-2: `uv sync` completes without error
- [x] ISC-3: `path_safety.py` exports `check_path_safety`/`validate_vault_path` as plain `def` (not `async def`)
- [x] ISC-4: Regression test proves `validate_vault_path` rejects a `../../etc/passwd`-style traversal attempt
- [x] ISC-5: Regression test proves `validate_vault_path` accepts a legitimate in-vault path
- [x] ISC-6: `sanitize_vault_name` test matrix matches TS behavior (lowercase, non-alnum→hyphen, trim, `unnamed-vault` fallback)
- [x] ISC-7: `check_path_overlap` rejects duplicate vault paths
- [x] ISC-8: `check_path_overlap` rejects nested/parent-child vault paths
- [x] ISC-9: `read-note` tool reads content and appends `.md` automatically
- [x] ISC-10: `read-note` rejects a `filename` containing a path separator
- [x] ISC-11: `create-note` refuses to overwrite an existing note
- [x] ISC-12: `create-note` creates missing parent directories
- [x] ISC-13: `edit-note` Pydantic model is a discriminated union on `operation` (`delete` has no `content` field; `append|prepend|replace` require non-empty `content`)
- [x] ISC-14: `edit-note` append/prepend/replace restores original content on a simulated write failure
- [x] ISC-15: `edit-note` delete operation removes the file and leaves no orphaned backup file after the call returns
- [x] ISC-16: `delete-note` default (non-permanent) moves the note into `.trash/` with YAML frontmatter `trash_metadata`
- [x] ISC-17: `delete-note` with `permanent=true` unlinks the file directly (no `.trash/` entry)
- [x] ISC-18: `delete-note` strikes through `[[wikilink]]` references to the deleted note elsewhere in the vault
- [x] ISC-19: `move-note` rejects a move to an already-existing destination
- [x] ISC-20: `move-note` rewrites `[[wikilink]]` and `[text](file.md)` references vault-wide after a move
- [x] ISC-21: `create-directory` is routed through the shared `validate_vault_path` (not a weaker inline check)
- [x] ISC-22: `create-directory` rejects creation of an already-existing directory
- [x] ISC-23: `search-vault` substring search matches TS behavior for `searchType=content|filename|both`
- [x] ISC-24: `search-vault` `tag:` prefix triggers hashtag search with normalization/wildcard matching
- [x] ISC-25: `search-vault` supports a working `max_results` parameter (new capability, TS declared but never implemented this)
- [x] ISC-26: `add-tags` adds to YAML frontmatter array and/or inline `#tag` per `location`/`position`
- [x] ISC-27: `remove-tags` hierarchical removal removes children unless `preserveChildren=true`
- [x] ISC-28: `remove-tags` skips tags inside fenced code blocks and HTML comments via `line_classifier.py`
- [x] ISC-29: `rename-tag` preserves hierarchy (`work` → `newTag` also renames `work/active` → `newTag/active`)
- [x] ISC-30: `rename-tag` with `createBackup=true` produces a `.backup/vault-backup-<timestamp>/` snapshot
- [x] ISC-31: `list-available-vaults` returns the configured vault names with no arguments
- [x] ISC-32: `resources.py` root `obsidian-vault://` URI lists all vaults as `{name, path, isAccessible}[]`
- [x] ISC-33: `resources.py` per-vault `obsidian-vault://<name>` URI returns that vault's info
- [x] ISC-34: `list-vaults` prompt returns a 2-message exchange with no arguments required
- [x] ISC-35: CLI bootstrap rejects a vault path missing `.obsidian/app.json`
- [x] ISC-36: CLI bootstrap caps at `MAX_VAULTS=10` and rejects an 11th vault path
- [x] ISC-37: CLI bootstrap deduplicates same-basename vaults with numeric suffixes (`-1`, `-2`, ...)
- [x] ISC-38: Anti: `manage-tags` is not registered as a callable tool in `list_tools` output

## Test Strategy

| ISC | Type | Check | Threshold | Tool |
|-----|------|-------|-----------|------|
| ISC-1,2 | packaging | `uv sync` / `cat pyproject.toml` | exit 0 / fields present | Bash |
| ISC-3 | static | `inspect.iscoroutinefunction` on the two functions | both `False` | pytest |
| ISC-4,5,7,8 | unit | pytest assertions in `test_path_safety.py` | pass | pytest |
| ISC-6 | unit | pytest parametrized matrix | pass | pytest |
| ISC-9..ISC-31 | unit/integration | per-tool pytest against `tmp_path` fixture vault | pass, exact response text | pytest |
| ISC-32..34 | integration | direct call of resource/prompt handlers | pass | pytest |
| ISC-35..37 | integration | `cli.py` bootstrap function against `tmp_path` fixtures | pass/raises as expected | pytest |
| ISC-38 | static | `list_tools()` output does not contain `manage-tags` | absent | pytest |

## Features

| Name | Description | Satisfies | Depends On | Parallelizable |
|------|-------------|-----------|------------|----------------|
| packaging | pyproject.toml, uv setup, entry point | ISC-1,2 | — | no |
| path_safety | sync path validation module | ISC-3..8 | packaging | no |
| utils | files, frontmatter, tags, line_classifier, links, errors, responses, backup | ISC-14..30 (support) | path_safety | yes |
| tools | 11 tool modules + Pydantic models | ISC-9..31 | utils | yes |
| resources_prompts | resources.py, prompts/list_vaults.py | ISC-32..34 | utils | yes |
| cli_server | cli.py bootstrap + server.py wiring | ISC-35..38 | tools, resources_prompts | no |
| tests | full pytest suite | all | all above | no |

## Decisions

- 2026-08-21: macOS/Linux only, dropping all Windows-specific path logic — explicit user decision, avoids porting complexity for a platform not used in this environment.
- 2026-08-21: `path_safety.py` made entirely synchronous (not just fixing the one bug) — removes the async/await boundary that caused the TS vulnerability, so the bug class is structurally impossible rather than individually patched. `files.py` stays async since `get_all_markdown_files` does a real recursive vault walk that benefits from not blocking the event loop.
- 2026-08-21: `manage-tags` not ported — confirmed dead code in TS (never registered in `main.ts`); `add-tags`/`remove-tags` already cover its functionality.
- 2026-08-21: Fixed a real bug found while writing tests: TS's `removeTagsFromFrontmatter` hierarchical-removal branch (`relatedTagsMap.get(removeTag)?.parents.includes(...)`) is dead code — the map only stores non-null values when `preserveChildren` is true, so the `!preserveChildren` branch always reads `null` and the check never fires. Hierarchical frontmatter tag removal never actually worked in the TS original, even though `removeInlineTags`' equivalent check (`isParentTag(removeTag, normalizedTag)`, unconditional) works correctly. Since ISC-27 requires hierarchical removal to actually work and the tool's own documented behavior promises it, the Python port uses the same direct `is_parent_tag()` check the inline implementation already gets right, instead of replicating the dead branch.
- 2026-08-21: Forge (GPT-5.4 via codex CLI) was unavailable in this environment (codex not installed) and Anvil's Moonshot API key wasn't configured either — both declined/were skipped rather than silently falling back to Claude-family code under another agent's name. Implementation was hand-written directly by the primary agent instead, using the same TS source + verified SDK facts that would have briefed either delegate. Documented as a show-your-math exception to the E3 delegation floor.

## Verification

- ISC-1,2: `pyproject.toml` contains `requires-python = ">=3.11"` and `[project.scripts] obsidian-mcp = "obsidian_mcp.cli:run"`; `uv sync` and `uv run pytest` both exit 0 (see below).
- ISC-3: `test_check_path_safety_and_containment_are_sync_not_async` in `test_path_safety.py` asserts `inspect.iscoroutinefunction` is `False` for `check_path_safety`/`validate_vault_path`/`safe_join_path` — passes.
- ISC-4: `test_validate_vault_path_rejects_traversal` constructs a `vault/../outside/secret.md` traversal and asserts `MCPError` is raised — passes. Also manually verified end-to-end via `mcp.call_tool("read-note", {..., "folder": "../../../etc"})` raising `MCPError` (not silently succeeding).
- ISC-5, 6, 7, 8: corresponding `test_path_safety.py` tests pass (legitimate-path acceptance, `sanitize_vault_name` matrix, duplicate/nested overlap rejection).
- ISC-9..31: one or more tests per tool in `test_tools_read_create_edit.py`, `test_tools_delete_move.py`, `test_tools_tags.py`, `test_tools_search.py` — all pass. Additionally manually verified end-to-end against a real fixture vault via direct `mcp.call_tool(...)` calls covering create/read/edit/add-tags/search/tag-search/rename-tag/move/mkdir/delete, all producing correct filesystem side effects and response text (captured in-session).
- ISC-32..34: `test_resources_prompts.py` — root and per-vault resource reads, and the `list-vaults` prompt's 2-message, no-argument shape all pass.
- ISC-35..37: `test_cli_bootstrap.py` — missing `.obsidian`, missing `app.json`, nonexistent directory, `MAX_VAULTS` cap, and name-dedup-with-suffix all pass.
- ISC-38 (Anti): `test_manage_tags_is_not_registered` asserts `"manage-tags"` is absent from `list_tools()` and exactly 11 tools are registered — passes. Also confirmed live over real stdio JSON-RPC (`tools/list` returned exactly the 11 expected names).
- Full suite: `uv run pytest -q` → **101 passed**. `uv run ruff check src tests` → clean (remaining findings are accepted test-style items, documented inline).
- Live protocol verification (beyond unit tests): started `uv run obsidian-mcp /tmp/test-vault` as a real subprocess, sent `initialize` over stdin, received a correct `InitializeResult` with `serverInfo.name == "obsidian-mcp"` and `capabilities.{tools,resources,prompts}` present; sent `tools/list` and received the correct 11 tool names with clean stderr.
- CLI fatal-error protocol: `uv run obsidian-mcp` (no args) printed the help text + human error to stderr and wrote a well-formed `{"jsonrpc":"2.0","error":{...},"id":null}` envelope to stdout, exit code 1 — matches the TS original's pre-transport error contract.

## Re-read check

- "Review the TypeScript obsidian-mcp project... Create a plan to implement a functionally equivalent MCP service in python" → ✓ addressed: TS source fully read, plan written and approved, implementation built and tested.
- User's clarifying question on async-vs-sync path validation → ✓ addressed: `path_safety.py` made fully synchronous, explained in-session and in the plan's SDK Addendum / Decisions.
- User's approval "Thanks for the explanation - good to begin" → ✓ addressed: proceeded to full implementation, all 11 tools + utils + tests + packaging delivered and verified.
