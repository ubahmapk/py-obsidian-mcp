# obsidian-mcp (Python)

[![SLSA 3](https://slsa.dev/images/gh-badge-level3.svg)](https://slsa.dev)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/ubahmapk/py-obsidian-mcp/blob/main/LICENSE)
[![MCP Server](https://img.shields.io/badge/MCP-server-black?logo=modelcontextprotocol&logoColor=white)](https://modelcontextprotocol.io)
[![PyPI version](https://img.shields.io/pypi/v/py-obsidian-mcp)](https://pypi.org/project/py-obsidian-mcp/)
[![CI](https://github.com/ubahmapk/py-obsidian-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/ubahmapk/py-obsidian-mcp/actions/workflows/ci.yml)

A Python MCP (Model Context Protocol) server giving an LLM client (e.g. Claude Desktop) read/write access to local Obsidian vaults, via direct filesystem access — no Obsidian Local REST API plugin, no HTTP, no auth token required.

This is a Python port of [obsidian-mcp](https://github.com/StevenStavrakis/obsidian-mcp) (TypeScript), functionally equivalent with a few deliberate fixes and simplifications — see `Plans/review-the-typescript-obsidian-mcp-parsed-shamir.md` and `ISA.md` for the full rationale.

> **Warning**: This server has read/write access to your vault. Back up your notes (e.g. via git) before use.

## Requirements

- Python 3.11+
- [`uv`](https://docs.astral.sh/uv/)
- An Obsidian vault (a directory that has been opened by Obsidian at least once, i.e. contains a `.obsidian/app.json`)
- macOS or Linux (Windows is not supported — see ISA "Out of Scope")

## Install & run

The PyPI distribution is named `py-obsidian-mcp` (the `obsidian-mcp` name was already taken by an unrelated project) — the installed command is still `obsidian-mcp`.

```bash
uvx --from py-obsidian-mcp obsidian-mcp /path/to/your/vault [/path/to/another/vault ...]
# or: pip install py-obsidian-mcp && obsidian-mcp /path/to/your/vault
```

### From source (development)

```bash
uv sync
uv run obsidian-mcp /path/to/your/vault [/path/to/another/vault ...]
```

Vault names are auto-derived from each directory's basename (lowercased, non-alphanumeric characters become hyphens, duplicates get a numeric suffix). Up to 10 vaults; vault paths must not be nested inside one another.

## Claude Desktop configuration

Edit `claude_desktop_config.json` (macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "obsidian": {
      "command": "uvx",
      "args": ["--from", "py-obsidian-mcp", "obsidian-mcp", "/path/to/your/vault"]
    }
  }
}
```

Or, running from a local clone instead of the published package:

```json
{
  "mcpServers": {
    "obsidian": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/py-obsidian-mcp", "obsidian-mcp", "/path/to/your/vault"]
    }
  }
}
```

## Tools

`read-note`, `create-note`, `edit-note` (append/prepend/replace/delete), `delete-note` (soft-delete to `.trash/` by default), `move-note`, `create-directory`, `search-vault` (content/filename/tag search, with an optional `max_results`), `add-tags`, `remove-tags`, `rename-tag` (vault-wide, hierarchy-preserving), `list-available-vaults`.

Also exposes an `obsidian-vault://` resource scheme (vault listing/info) and a `list-vaults` prompt.

## Development

```bash
uv sync --all-extras
uv run pytest -q
uv run ruff check src tests
```

## Security notes

- Every tool validates that target paths stay within the vault (`src/obsidian_mcp/utils/path_safety.py`), including symlink-aware containment checks.
- The TypeScript original had a confirmed bug where this containment check was effectively a no-op (an async validation function was called without `await`). This port's path-safety functions are all synchronous, structurally preventing that class of bug.
