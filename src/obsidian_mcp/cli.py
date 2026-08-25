"""CLI entry point and vault bootstrap validation, ported from TS `main.ts`.

Cross-platform (macOS, Linux, Windows). Platform-specific path rules live in
`obsidian_mcp.utils.path_safety`; this module stays separator-agnostic.
"""

from __future__ import annotations

import json
import os
import sys

import anyio
from mcp.shared.exceptions import MCPError
from mcp.types import INVALID_REQUEST

from obsidian_mcp.server import build_server
from obsidian_mcp.utils.path_safety import (
    check_local_path,
    check_path_overlap,
    check_suspicious_path,
    sanitize_vault_name,
)

MAX_VAULTS = 10

_HELP = f"""
Obsidian MCP Server - Multi-vault Support

Usage: obsidian-mcp <vault1_path> [vault2_path ...]

Requirements:
- Paths must point to valid Obsidian vaults (containing .obsidian directory)
- Vaults must be initialized in Obsidian at least once
- Paths must have read and write permissions
- Paths cannot overlap (one vault cannot be inside another)
- Each vault must be a separate directory
- Maximum {MAX_VAULTS} vaults can be connected at once

Security restrictions:
- Must be on a local filesystem (no network drives or mounts)
- Cannot point to system directories
- Hidden directories not allowed (except .obsidian)
- Cannot use the home directory root
- Cannot use symlinks that point outside their directory
"""


def _fatal(message: str, *, code: int = INVALID_REQUEST) -> None:
    """Prints a human message to stderr and a raw JSON-RPC error envelope to
    stdout (since stdout is the transport channel and a client may already be
    listening for a response), then exits with status 1.
    """
    print(f"Error: {message}", file=sys.stderr)
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "error": {"code": code, "message": message}, "id": None}))
    sys.exit(1)


def _validate_vault_path(raw_path: str) -> str:
    """Expands, normalizes, and validates a single vault path. Returns the
    resolved absolute (realpath'd) path, or calls `_fatal()` and exits.
    """
    expanded = os.path.expanduser(raw_path)
    # Strip trailing separators (both kinds, for Windows) without stripping a
    # bare drive/UNC root -- os.path.normpath already keeps a lone root's separator.
    normalized = os.path.normpath(expanded)
    if len(normalized) > 3:
        normalized = normalized.rstrip("/\\")
    absolute_path = os.path.realpath(normalized)

    if not os.path.isabs(absolute_path):
        _fatal(f"Vault path must be absolute: {raw_path}")

    suspicious_reason = check_suspicious_path(absolute_path)
    local_path_issue = check_local_path(absolute_path)

    if local_path_issue:
        _fatal(
            f"Invalid vault path ({local_path_issue}): {raw_path}\n"
            "For reliability and security reasons, vault paths must:\n"
            "- Be on a local filesystem\n"
            "- Not use network drives or mounts"
        )

    if suspicious_reason:
        _fatal(
            f"Invalid vault path ({suspicious_reason}): {raw_path}\n"
            "For security reasons, vault paths cannot:\n"
            "- Point to system directories\n"
            "- Use hidden directories (except .obsidian)\n"
            "- Point to the home directory root"
        )

    if not os.path.isdir(absolute_path):
        _fatal(f"Vault path must be a directory: {raw_path}")

    if not os.access(absolute_path, os.R_OK | os.W_OK):
        _fatal(f"No permission to access vault directory: {raw_path}")

    obsidian_config_path = os.path.join(absolute_path, ".obsidian")
    obsidian_app_config_path = os.path.join(obsidian_config_path, "app.json")

    if not os.path.isdir(obsidian_config_path):
        _fatal(
            f"Not a valid Obsidian vault ({raw_path})\n"
            "Missing or incomplete .obsidian configuration\n\n"
            "To fix this:\n"
            "1. Open Obsidian\n"
            '2. Click "Open folder as vault"\n'
            f"3. Select the directory: {absolute_path}\n"
            "4. Wait for Obsidian to initialize the vault\n"
            "5. Try running this command again"
        )

    if not os.access(obsidian_app_config_path, os.R_OK):
        _fatal(f"Invalid Obsidian vault configuration in {raw_path}\nMissing or unreadable .obsidian/app.json")

    return absolute_path


def _build_vault_map(vault_paths: list[str]) -> dict[str, str]:
    """Sanitizes vault names from directory basenames, de-duplicating with numeric suffixes."""
    vault_map: dict[str, str] = {}
    for path in vault_paths:
        raw_name = os.path.basename(path)
        name = sanitize_vault_name(raw_name)

        unique_name = name
        counter = 1
        while unique_name in vault_map:
            unique_name = f"{name}-{counter}"
            counter += 1

        vault_map[unique_name] = path

    return vault_map


async def _run_stdio(vaults: dict[str, str]) -> None:
    mcp = build_server(vaults)
    await mcp.run_stdio_async()


def run() -> None:
    vault_args = sys.argv[1:]

    if not vault_args:
        print(_HELP, file=sys.stderr)
        _fatal("No vault paths provided. Please provide at least one valid Obsidian vault path.")
        return

    if len(vault_args) > MAX_VAULTS:
        _fatal(
            f"Too many vaults specified ({len(vault_args)})\n"
            f"Maximum number of vaults allowed: {MAX_VAULTS}\n"
            "This limit helps prevent performance issues and resource exhaustion"
        )

    resolved_paths = [_validate_vault_path(p) for p in vault_args]

    try:
        check_path_overlap(resolved_paths)
    except MCPError as exc:
        _fatal(str(exc))

    vaults = _build_vault_map(resolved_paths)

    try:
        anyio.run(_run_stdio, vaults)
    except Exception as exc:  # noqa: BLE001 - top-level fatal handler, mirrors TS main()'s catch-all
        mcp_error = exc if isinstance(exc, MCPError) else MCPError(-32603, str(exc))
        print("\nFatal error starting server:", file=sys.stderr)
        print(str(mcp_error), file=sys.stderr)
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "error": {"code": -32603, "message": str(mcp_error)}, "id": None}))
        sys.exit(1)


if __name__ == "__main__":
    run()
