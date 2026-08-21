# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-08-21

Initial release: a Python port of [obsidian-mcp](https://github.com/StevenStavrakis/obsidian-mcp) (TypeScript), functionally equivalent with a few deliberate fixes and simplifications.

### Added

- MCP stdio server (`mcp` SDK) exposing 11 tools: `read-note`, `create-note`, `edit-note` (append/prepend/replace/delete), `delete-note` (soft-delete to `.trash/` by default), `move-note`, `create-directory`, `search-vault` (content/filename/tag search), `add-tags`, `remove-tags`, `rename-tag` (vault-wide, hierarchy-preserving), `list-available-vaults`.
- `obsidian-vault://` resource scheme (vault listing and per-vault info).
- `list-vaults` prompt.
- `search-vault` gains a working `max_results` parameter — the TS original declared this field but never implemented it.
- Multi-vault CLI bootstrap with the same path-safety validation pipeline as the TS original (suspicious-path checks, local-filesystem checks, `.obsidian/app.json` verification, overlap/duplicate detection, vault name sanitization with numeric-suffix dedup, `MAX_VAULTS=10` cap).
- Full pytest suite (101 tests), including new coverage the TS original never had for tag and link logic.

### Fixed

- **Path-traversal validation bug**: the TS original's `validateVaultPath()` called an `async` `checkPathSafety()` without `await`, so the containment check silently never threw (`!Promise` is always falsy in JS). This port's `path_safety.py` is fully synchronous, making that bug class structurally impossible rather than individually patched.
- **Dead hierarchical tag-removal branch**: TS's `removeTagsFromFrontmatter` guarded its parent/child removal check behind a map that only ever populated non-null values when `preserveChildren` was `true`, so removing a parent tag never actually removed its children in frontmatter (the equivalent inline-content check worked fine). This port uses the same direct check the inline path already got right.

### Changed / not ported (deliberate)

- **Not ported**: the `manage-tags` tool (implemented in TS but never registered — confirmed dead code; `add-tags`/`remove-tags` already cover it), TS's `RateLimiter` and `ConnectionMonitor` (the latter's own heartbeat reset the idle clock it was meant to enforce, making it self-defeating by construction), cross-vault link-rewrite branches (unreachable — no cross-vault move tool exists), and Windows-specific path validation (macOS/Linux only).
- **Simplified**: network-drive detection uses `os.path.ismount()` plus a known-mount-prefix denylist instead of shelling out to `df`/`wmic`/PowerShell on every startup.
- **Consolidated**: a shared `line_classifier.py` replaces three independent copies of the same code-block/HTML-comment line-scanning logic in TS; a new `backup.py` unifies three previously-scattered backup mechanisms (per-file edit safety backup, `.trash/` soft delete, vault-wide snapshot before a bulk rename) into one module while preserving their distinct behaviors.

[Unreleased]: https://github.com/ubahmapk/py-obsidian-mcp/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/ubahmapk/py-obsidian-mcp/releases/tag/v0.1.0
