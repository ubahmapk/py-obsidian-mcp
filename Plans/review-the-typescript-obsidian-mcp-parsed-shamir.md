# Plan: Python port of obsidian-mcp

## Context

`/Users/jallen/github/obsidian-mcp` is a TypeScript MCP (stdio) server that gives an LLM client (e.g. Claude Desktop) read/write access to local Obsidian vaults via direct filesystem access — no Obsidian Local REST API plugin, no HTTP, no auth token. The goal is a functionally equivalent Python implementation at `/Users/jallen/github/py-obsidian-mcp` (currently empty), using the official Python `mcp` SDK, `uv` for packaging, and `pytest` for tests.

The TS source was read in full (`main.ts`, `server.ts`, all 11 `tools/*/index.ts`, all `utils/*.ts`, `resources/*.ts`, `prompts/list-vaults/index.ts`) rather than just summarized, so the plan below reflects verified behavior, not guesses. Several real issues were found in the TS original that this port deliberately fixes or intentionally does not replicate — see the Decisions table.

**Critical finding:** `utils/path.ts`'s `validateVaultPath()` calls `checkPathSafety()` — an `async` function — **without `await`**: `if (!checkPathSafety(vaultPath, targetPath)) throw ...`. A `Promise` object is always truthy, so `!Promise` is always `false` and the throw never fires. **The vault-containment check is a no-op in the shipped TS server** — every tool that relies on `validateVaultPath`/`safeJoinPath` for path-traversal protection is currently unprotected by it (other checks like `.md`-extension enforcement and explicit existence checks still apply, but the "stay inside the vault" guarantee does not). The Python port must implement this check as a plain synchronous function so this class of bug is structurally impossible.

**Platform scope (per user decision):** target macOS/Linux only. Drop Windows-specific path logic (drive letters, UNC paths, reserved device names, `wmic`/PowerShell probing) entirely rather than porting-and-skipping it.

## Python MCP SDK choice (revised — empirically verified against the actually-installed `mcp==2.0.0`)

The original recommendation below (low-level `Server`) was written from general SDK knowledge before installing the package. After `uv add mcp` and directly introspecting the installed 2.0.0 API (`inspect.signature`, live `add_tool`/`call_tool` calls), the real API differs materially, so the plan is corrected here rather than shipped wrong:

- `mcp==2.0.0` has **no `FastMCP` module** and **no decorator-style low-level `Server`** (`@server.list_tools()` etc. don't exist on `mcp.server.lowlevel.Server` in this version — handlers are constructor callables instead). The modern high-level surface is **`mcp.server.mcpserver.MCPServer`** (FastMCP's successor): `MCPServer("obsidian-mcp", version="0.1.0")`, `mcp.add_tool(fn, name=..., description=..., structured_output=False)`, `mcp.add_resource(resource)`, `mcp.add_prompt(prompt)`, `mcp.run(transport="stdio")`.
- **`add_tool(fn)` builds the wire JSON schema from `fn`'s individual flat parameters**, not from a single Pydantic-model parameter — verified empirically that a single `BaseModel` parameter produces an incorrectly-nested `{"args": {...}}` schema. **Every tool handler therefore takes flat keyword parameters** matching the TS zod schema's top-level fields 1:1 (`async def read_note(vault: str, filename: str, folder: str | None = None) -> ...`), and constructs an internal Pydantic model from those kwargs inside the handler body for strict validation and reusable business logic — the model is not the wire signature, just the internal validation/logic layer.
- **`structured_output=False` is required on every `add_tool()` call** — confirmed empirically that without it, the SDK auto-generates an `outputSchema` and returns `structuredContent` that TS never emits; `structured_output=False` suppresses both, matching TS.
- Confirmed empirically that the SDK's own argument dispatch is **lenient by default** (unknown keys silently dropped, not rejected) — matching TS's non-`.strict()` tools automatically. Internal `extra="forbid"` Pydantic validation should therefore only be added for the 5 tools that were actually `.strict()` in TS (`read-note`, `create-note`, `edit-note`, `move-note`, `create-directory`); `remove-tags`/`rename-tag` stay non-strict internally too, matching TS exactly (revises the earlier "make everything strict" call — that would have rejected calls the original server accepted, per advisor review).
- Known, accepted minor divergence: `Optional[X] = None` params generate `anyOf: [{type: X}, {type: "null"}]` in the schema, where TS zod `.optional()` just omits the property from `required` with no `anyOf`. Documented rather than papered over with a schema post-processor — revisit only if a real MCP client chokes on it in practice.
- `edit-note`'s discriminated union becomes flat params (`operation: Literal["append","prepend","replace","delete"]`, `content: str | None = None`, plus shared fields) — the wire schema loses zod's free "content required unless delete" enforcement, but the `Literal` still carries the enum, field descriptions carry the conditional-requirement guidance to the calling model, and the internal Pydantic union still enforces it in the handler body.
- Shared plumbing: one small `registry.py` helper (`validate(model_cls, **kwargs)`) wraps `model_cls(**kwargs)` and maps `pydantic.ValidationError` to the same error shape TS produced on `ZodError` — written once, called at the top of all 11 handler bodies, instead of duplicated 11 times.
- No tool `annotations` (`readOnlyHint`, `destructiveHint`, `title`) are set — TS never sets them either, so this is a deliberate parity choice, not an oversight.

## Project layout

```
py-obsidian-mcp/
  pyproject.toml
  README.md
  src/obsidian_mcp/
    __init__.py
    __main__.py            # `python -m obsidian_mcp`
    cli.py                 # arg parsing + vault bootstrap (~main.ts)
    server.py              # Server wiring, request handlers (~server.ts)
    types.py               # shared response dataclasses (~types.ts)
    registry.py            # tool registry/dispatch (~tool-factory.ts + schema.ts, simplified)
    vault_resolver.py      # name -> path resolution (~vault-resolver.ts)
    utils/
      path_safety.py       # normalize/validate/containment/overlap (~utils/path.ts)
      files.py             # get_all_markdown_files, ensure_directory, safe_read_file (~utils/files.ts)
      frontmatter.py       # parse_note/stringify_note (~part of utils/tags.ts)
      tags.py              # validate/normalize/extract/add/remove tag logic (~utils/tags.ts)
      line_classifier.py   # NEW: single shared code-block/HTML-comment line scanner
      links.py             # update_links_in_file/update_vault_links, same-vault cases only (~utils/links.ts)
      errors.py            # fs-error -> MCP error mapping (~utils/errors.ts)
      responses.py         # text-formatting helpers (~utils/responses.ts)
      backup.py            # NEW: unifies the 3 backup mechanisms into one module, 3 distinct functions
    tools/
      __init__.py           # TOOL registry list, mirrors main.ts's tool array
      read_note.py
      create_note.py
      edit_note.py
      delete_note.py
      move_note.py
      create_directory.py
      search_vault.py
      add_tags.py
      remove_tags.py
      rename_tag.py
      list_available_vaults.py
    resources.py            # single implementation (~resources/resources.ts; the actually-wired one)
    prompts/
      list_vaults.py        # (~prompts/list-vaults/index.ts)
  tests/
    conftest.py
    test_path_safety.py
    test_files.py
    test_frontmatter.py
    test_tags.py
    test_line_classifier.py
    test_links.py
    test_tools_read_create_edit.py
    test_tools_delete_move.py
    test_tools_tags.py
    test_tools_search.py
    test_resources_prompts.py
    test_cli_bootstrap.py
```

## Packaging

`uv`-managed `pyproject.toml`: `requires-python = ">=3.11"`. Dependencies: `mcp`, `pydantic>=2`, `pyyaml`. Dev deps: `pytest`, `pytest-asyncio`, `ruff`. Entry point: `[project.scripts] obsidian-mcp = "obsidian_mcp.cli:run"`, invoked the same way as the TS `npx obsidian-mcp <vault-path>...` (e.g. `uvx obsidian-mcp <path>` or a Claude Desktop config pointing at `uv run obsidian-mcp <path>`).

## Tools (11, 1:1 with TS, each a Pydantic model + async handler)

All models use `model_config = ConfigDict(extra="forbid")` (matches/extends zod `.strict()` — apply consistently even to the 3 TS tools that weren't strict, since there's no compatibility reason to keep them loose).

1. **read-note** `{vault, filename, folder?}` — filename must not contain path separators; `.md` auto-appended; returns content + formatted footer via `responses.py`.
2. **create-note** `{vault, filename, content, folder?}` — creates parent dirs, refuses to overwrite.
3. **edit-note** — Pydantic discriminated union on `operation`: `delete` (no `content` field at all) vs `append|prepend|replace` (`content: str = Field(min_length=1)`). Uses the new `backup.py` `edit_safety_backup()` context manager instead of TS's sidecar-file + `setTimeout` pattern (see Decisions).
4. **delete-note** `{vault, path, reason?, permanent?=false}` — default soft-delete via `backup.py`'s `soft_delete_to_trash()` (moves into `.trash/` with real YAML frontmatter metadata, not hand-built strings); `permanent=true` unlinks directly; both paths call `links.py`'s delete-strikethrough rewrite first.
5. **move-note** `{vault, source, destination}` — validate/create dest dir/rename, then same-vault link rewrite via `links.py`.
6. **create-directory** `{vault, path, recursive?=true}` — **routed through the shared `path_safety.validate_vault_path`**, fixing the TS inconsistency where this one tool used a weaker inline check.
7. **search-vault** `{vault, query, path?, caseSensitive?=false, searchType?}` — `tag:`-prefixed queries do hashtag search via `tags.py`; otherwise substring search per line. Add real, working `max_results`/pagination params (TS declared these in its type but never implemented them) — default behavior (no limit) unchanged unless a caller opts in.
8. **add-tags** `{vault, files[], tags[], location?, normalize?, position?}` — frontmatter array merge and/or inline `#tag` append/prepend.
9. **remove-tags** `{vault, files[], tags[], options:{location, normalize, preserveChildren, patterns[]}}` — hierarchical + wildcard removal, skips code blocks/HTML comments via `line_classifier.py`.
10. **rename-tag** `{vault, oldTag, newTag, createBackup?=true, normalize?=true, batchSize?=50}` — vault-wide batched rename preserving hierarchy, optional full snapshot via `backup.py`'s `create_vault_snapshot()`, best-effort patch of `.obsidian/search.json`.
11. **list-available-vaults** — no args.

**Not ported:** `manage-tags` — implemented in TS but never registered (confirmed dead code); `add-tags`/`remove-tags` already cover it, so it's omitted rather than carried forward as an unreachable third code path.

## Utils — key logic to replicate/fix

- **`path_safety.py`**: **entirely synchronous** port of `checkPathCharacters`/`checkSuspiciousPath`/`normalizePath`/`checkPathSafety`/`validateVaultPath`/`safeJoinPath`/`sanitizeVaultName`/`isParentPath`/`checkPathOverlap`, Unix-only (drop all Windows branches per platform-scope decision). This is a deliberate design choice, not just "fix the one bug": the only work these functions do is `os.path.realpath`/`os.stat` on local disk (the network-drive check already rejects non-local mounts, so there's no slow I/O here to justify async), and making the whole module sync removes the async/await boundary entirely — there's no Promise/coroutine object a caller could fail to await, so this class of bug (TS's `validateVaultPath` checking an unawaited `Promise<boolean>`, which is always truthy and never throws) is structurally impossible rather than just individually fixed. Tool handlers remain `async def` per the MCP SDK and call these sync functions directly — trivial and safe for microsecond-scale local syscalls. Network-drive detection: replace the `df`/`wmic`/PowerShell shell-out-with-timeout with `os.path.ismount()` + a known-mount-prefix denylist (`/net/`, `/mnt/`, `/media/`, `/Volumes/`) — no subprocess calls at startup.
- **`files.py`**: stays **async** (`async def`), unlike `path_safety.py` — `get_all_markdown_files` does a recursive walk over the whole vault (potentially thousands of files), which legitimately benefits from not blocking the event loop, especially since `search-vault` and `rename-tag` depend on it and could run long on large vaults. Covers `get_all_markdown_files` (recursive, skips dot-dirs, continues past per-entry errors), `ensure_directory`, `file_exists`, `safe_read_file`.
- **`frontmatter.py`**: hand-rolled with `PyYAML`, deliberately matching the TS regex behavior (`^---\n...\n---\n...$`) rather than using the looser `python-frontmatter` package, plus a `\r\n`→`\n` normalization pass before matching (a portability nicety, not a behavior gap).
- **`tags.py`**: `validate_tag` (`^[a-zA-Z0-9]+(/[a-zA-Z0-9]+)*$`), `normalize_tag` (camelCase/PascalCase→kebab per segment), hierarchical/wildcard matching, frontmatter add/remove, inline add/remove — delegates code-block/comment detection to `line_classifier.py` instead of re-implementing it (TS duplicates this logic 3 times independently: `extractTags`, `removeInlineTags`, and again inside `rename-tag`).
- **`line_classifier.py`** (new): single shared per-line state machine for code-block/HTML-comment detection, with its known limitation (not a real parser; doesn't handle nested/malformed fences or comments) documented in the docstring and preserved intentionally for behavior parity.
- **`links.py`**: same-vault rename rewrite (`[[wikilink]]`, `[[wikilink|alias]]`, `[text](file.md)`) and delete-strikethrough only. TS's cross-vault move branches (`isMovedToOtherVault`/`isMovedFromOtherVault`) are confirmed unreachable — no registered tool ever calls them (there's no cross-vault move tool) — so they're omitted, with a code comment noting why.
- **`errors.py`**: `handle_fs_error` mapping `OSError.errno` (`ENOENT`/`EACCES`/`EEXIST`/`ENOSPC`) to MCP errors with the same friendly messages as TS.
- **`responses.py`**: direct ports of the file/tag/search/batch text-formatting helpers — several tools' output shape depends on these exactly, so they're unit-tested directly.
- **`backup.py`** (new, unifies 3 previously-separate/inconsistent TS mechanisms into one module while keeping 3 distinct behaviors — they serve different purposes and shouldn't be collapsed into one mechanism):
  - `edit_safety_backup(path)`: an async context manager — copy before entry, delete on clean exit, restore-then-delete on exception. Replaces `edit-note`'s TS pattern of a timestamp-suffixed backup file plus a detached `setTimeout(5000)` cleanup that can outlive process exit and leak stray `.backup` files. The "5-second recovery window" for delete is intentionally dropped — a synchronous restore-on-failure block removes the failure window it was protecting against, and if a delete-specific grace/undo window is ever wanted, `.trash/`-based soft delete (already `delete-note`'s own pattern) is the correct primitive for that, not a bolt-on timer in a different tool.
  - `soft_delete_to_trash(vault_path, note_path, reason=None)`: used by `delete-note`; builds frontmatter via real `yaml.safe_dump` instead of TS's hand-built string (fixes fragility with special characters in `reason`).
  - `create_vault_snapshot(vault_path)`: used by `rename-tag`; full `.md`-tree copy to `.backup/vault-backup-<timestamp>/`.

## Vault resolution & bootstrap

- `vault_resolver.py`: `VaultResolver(vaults: dict[str, str])` with `resolve_vault(name)` raising a clear "unknown vault, available: [...]" error. Drop TS's commented-out/unused `resolveDualVaults`.
- `cli.py`: `argparse` with `nargs="+"` for vault paths. Validation order matches TS: expand `~`, normalize, absolutize, run suspicious-path + local-mount checks, must be a directory with R/W access, verify `.obsidian/app.json` exists and is readable, cap at 10 vaults (`MAX_VAULTS`), reject overlapping/nested paths (`check_path_overlap`), then `sanitize_vault_name` + numeric-suffix dedup to build the final `name -> path` dict.
- **Fatal-error protocol preserved**: on any pre-transport validation failure, print the human message to stderr *and* write a raw JSON-RPC error envelope (`{"jsonrpc":"2.0","error":{...},"id":null}`) to stdout before `sys.exit(1)`, since stdout is the transport channel and a client may already be listening for a response.
- **Not ported**: `RateLimiter` (global-per-RPC-method budget, not real per-client protection), `ConnectionMonitor` (confirmed self-defeating in TS — its own 30s heartbeat resets the idle clock it's supposed to enforce, so the 5-minute idle timeout can never fire). A local stdio server's lifecycle is already owned by the parent client process. Port the 5MB message-size cap only if the installed `mcp` SDK version doesn't already bound frame size (verify during implementation).

## Resources & Prompt

- `resources.py`: single implementation of the `obsidian-vault://` scheme (root → JSON list of `{name, path, isAccessible}`; `obsidian-vault://<name>` → one vault's info). TS has two duplicate/inconsistent implementations (`resources/resources.ts`, actually wired into `server.ts`, vs. an orphaned `resources/vault/index.ts` missing the root-list case) — port only the one that was actually live.
- `prompts/list_vaults.py`: the canned two-turn exchange nudging the model toward vault discovery instead of misusing `search-vault`.

## Testing

- `pytest` + `pytest-asyncio` (tool handlers are async). `conftest.py` provides a `tmp_path`-based fake-vault fixture (creates `.obsidian/app.json`).
- Port `path.test.ts`'s cases into `test_path_safety.py`, plus new containment/overlap cases exercising the fixed async-bug behavior.
- **New coverage the TS project never had** (zero tests existed for tags/links logic): `test_tags.py` (validate/normalize edge cases, hierarchical/wildcard removal matrix), `test_links.py` (wikilink/alias/markdown-link rewrite, delete-strikethrough), `test_line_classifier.py` (including the known false-positive case, captured as an accepted-limitation regression test).
- `test_cli_bootstrap.py`: valid vault, missing `.obsidian`, overlapping paths, >10 vaults, duplicate-name suffix dedup.
- `test_tools_*.py`: black-box tests per tool against a fixture vault, asserting filesystem side effects and exact response text (locks in `responses.py` formatting).
- `test_resources_prompts.py`: root/per-vault resource shapes, prompt message shape.

## Key decisions vs. TS (deviations, with reasoning)

| Area | TS behavior | Python decision |
|---|---|---|
| **`validateVaultPath` async bug** | `checkPathSafety` is `async`, called without `await` in `validateVaultPath` → the containment check never throws (confirmed via source read) | Implement as plain sync functions — bug is structurally impossible |
| Platform scope | Windows + Unix branches throughout `path.ts` | Unix/macOS-Linux only, per user decision — drop Windows branches entirely |
| `manage-tags` tool | Implemented, never registered — dead code | Not ported; `add-tags`/`remove-tags` cover it |
| Resources | Two duplicate implementations, one orphaned | One `resources.py`, based on the one actually wired into `server.ts` |
| `create-directory` path check | Skips shared validator, weaker inline check | Routed through the shared `validate_vault_path` like every other tool |
| Network-drive detection | Shells out to `df`/`wmic`/PowerShell with 5s timeout, fails closed | `os.path.ismount()` + known-prefix denylist, no subprocess calls |
| Rate limiting | Global budget keyed by RPC method name, not per-client | Not ported |
| Connection monitor | Self-defeating: heartbeat resets its own idle clock | Not ported; stdio lifecycle owned by parent client |
| 3x duplicated code-block/comment scanner | Independently reimplemented 3 times | Single shared `line_classifier.py` |
| 3 inconsistent backup mechanisms | Separate ad hoc patterns per tool | One `backup.py` module, 3 distinct functions/behaviors preserved (not merged into one mechanism) |
| edit-note delete "5s recovery window" | Detached `setTimeout`, can leak `.backup` files past process exit | Dropped in favor of synchronous try/restore/finally; `.trash/` soft-delete is the correct recovery primitive if wanted |
| Cross-vault link-rewrite branches | Implemented but unreachable (no cross-vault move tool exists) | Omitted, with a code comment explaining why |
| `search-vault` unused `maxResults`/pagination fields | Declared in TS types, never implemented | Implemented for real in Python; default (unlimited) behavior unchanged |
| Frontmatter parsing | Strict TS regex, `\n`-only | Hand-rolled with PyYAML matching the strict regex, plus `\r\n` normalization |
| Schema strictness | 3 of 11 tools not `.strict()` in TS | All Pydantic models use `extra="forbid"` |

## Verification

1. `uv sync` to install deps; `uv run pytest` — all unit tests (path safety, tags, links, line classifier, frontmatter, per-tool black-box tests, CLI bootstrap) should pass, including a specific regression test proving `validate_vault_path` actually rejects a path-traversal attempt (`../../etc/passwd`-style) end to end, since this exact case was silently broken in the TS original.
2. Point the server at a real (or scratch) Obsidian vault: `uv run obsidian-mcp <vault-path>` and confirm clean startup (no `.obsidian/app.json` → expect the fatal-error stdout/stderr protocol to fire correctly).
3. Use `mcp`'s dev inspector (`mcp dev` / `mcp-inspector` equivalent to the TS project's `bunx @modelcontextprotocol/inspector`) to call each of the 11 tools interactively: read/create/edit/delete/move a note, create a directory, search by content/filename/tag, add/remove/rename tags, list vaults — confirm responses match the documented format and that filesystem side effects (backups created/cleaned, `.trash/` entries, link rewrites) are correct.
4. Wire into a real Claude Desktop `claude_desktop_config.json` pointing at `uv run obsidian-mcp <vault-path>` and manually exercise a few tools through an actual conversation to confirm end-to-end behavior matches the TS server's UX.

---

## Follow-up (2026-08-21): Windows support tracking issue

Not a code-planning task — this is a single administrative action: file a GitHub issue on `ubahmapk/py-obsidian-mcp` tracking Windows support as a future feature request, no code changes.

**Issue content** (based on the difficulty assessment given to the user):
- **Title**: `Add Windows support`
- **Body**: summarizes that the port is currently macOS/Linux-only by deliberate scoping decision (see "Platform scope" row in the Decisions table above), and that adding it is estimated as roughly a half-day to a day of focused work, concentrated entirely in `src/obsidian_mcp/utils/path_safety.py` and the CLI bootstrap validation in `src/obsidian_mcp/cli.py`:
  - `check_path_characters`: Windows path-length limit (260 vs current 4096), reserved device names (`CON`/`PRN`/`AUX`/`NUL`/`COM1-9`/`LPT1-9`), invalid characters (`<>:"|?*`), drive-letter-root and UNC/device-path rejection.
  - `normalize_path`: preserve UNC paths and drive letters, a Windows system-directory denylist, consistent backslash handling.
  - Network-drive detection: needs a Windows equivalent to the current `os.path.ismount()` + mount-prefix denylist approach — likely a simple UNC/mapped-drive-letter heuristic rather than a `pywin32` dependency, to avoid a platform-conditional dependency for marginal benefit (consistent with the existing decision to avoid shelling out to `df`/`wmic`).
  - Needs real Windows testing (GitHub Actions `windows-latest` runner, or a real machine) — the main risk is symlink/realpath containment-check behavior against NTFS junctions/reparse points, not the mechanical regex porting.
  - Everything else (all 11 tools, tag/link/frontmatter logic, resources, MCP server wiring) needs no changes — already platform-agnostic via `os.path`/`anyio.Path`.
- **Labels**: `enhancement` (create if it doesn't already exist on the repo).

No implementation, no file edits to the source tree — just `gh issue create` against the already-existing public repo.
