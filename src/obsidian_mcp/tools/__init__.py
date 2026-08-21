"""Tool registration. Each module exposes a `register(mcp, vaults)` function."""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from obsidian_mcp.tools import (
    add_tags,
    create_directory,
    create_note,
    delete_note,
    edit_note,
    list_available_vaults,
    move_note,
    read_note,
    remove_tags,
    rename_tag,
    search_vault,
)

_MODULES = (
    read_note,
    create_note,
    edit_note,
    delete_note,
    move_note,
    create_directory,
    search_vault,
    add_tags,
    remove_tags,
    rename_tag,
    list_available_vaults,
)


def register_all(mcp: MCPServer, vaults: dict[str, str]) -> None:
    for module in _MODULES:
        module.register(mcp, vaults)
