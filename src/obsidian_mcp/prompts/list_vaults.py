"""`list-vaults` prompt. Ported from TS `prompts/list-vaults/index.ts`.

A canned two-turn exchange nudging the calling model toward vault discovery
instead of misusing `search-vault` to enumerate vaults.
"""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.prompts import Prompt
from mcp.server.mcpserver.prompts.base import AssistantMessage, UserMessage


def register(mcp: MCPServer, vaults: dict[str, str]) -> None:
    async def list_vaults() -> list[UserMessage | AssistantMessage]:
        vault_list = "\n".join(f"- {name}" for name in vaults)
        return [
            UserMessage(
                f"The following Obsidian vaults are available:\n{vault_list}\n\n"
                "You can use these vault names when working with tools. For example, to create a "
                "note in the first vault, use that vault's name in the create-note tool's arguments."
            ),
            AssistantMessage(
                "I see the available vaults. I'll use these vault names when working with tools "
                "that require a vault parameter. For searching within vault contents, I'll use the "
                "search-vault tool with the appropriate vault name."
            ),
        ]

    mcp.add_prompt(
        Prompt.from_function(
            list_vaults,
            name="list-vaults",
            description="Show available Obsidian vaults. Use this prompt to discover which vaults you can work with.",
        )
    )
