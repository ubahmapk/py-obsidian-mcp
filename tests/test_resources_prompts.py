from __future__ import annotations

import json


async def test_root_resource_lists_all_vaults(mcp, vault_path):
    """ISC-32."""
    result = await mcp.read_resource("obsidian-vault://")
    payload = json.loads(result[0].content)
    assert payload["totalVaults"] == 1
    assert payload["vaults"][0]["name"] == "test"
    assert payload["vaults"][0]["path"] == vault_path
    assert payload["vaults"][0]["isAccessible"] is True


async def test_per_vault_resource(mcp, vault_path):
    """ISC-33."""
    result = await mcp.read_resource("obsidian-vault://test")
    payload = json.loads(result[0].content)
    assert payload["name"] == "test"
    assert payload["path"] == vault_path


async def test_list_vaults_prompt_no_args_required(mcp):
    """ISC-34."""
    prompts = await mcp.list_prompts()
    prompt = next(p for p in prompts if p.name == "list-vaults")
    assert prompt.arguments in (None, [])

    result = await mcp.get_prompt("list-vaults", {})
    assert len(result.messages) == 2
    assert result.messages[0].role == "user"
    assert "test" in result.messages[0].content.text
    assert result.messages[1].role == "assistant"


async def test_manage_tags_is_not_registered(mcp):
    """ISC-38 (Anti-criterion): manage-tags must not exist as a callable tool."""
    tools = await mcp.list_tools()
    names = {t.name for t in tools}
    assert "manage-tags" not in names
    assert len(names) == 11
