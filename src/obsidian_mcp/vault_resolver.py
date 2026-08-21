"""Resolves a vault name to its filesystem path. Ported from TS `utils/vault-resolver.ts`."""

from __future__ import annotations

from mcp.shared.exceptions import MCPError
from mcp.types import INVALID_PARAMS


class VaultResolver:
    def __init__(self, vaults: dict[str, str]) -> None:
        if not vaults:
            raise ValueError("At least one vault is required")
        self._vaults = vaults

    def resolve_vault(self, vault_name: str) -> str:
        vault_path = self._vaults.get(vault_name)
        if vault_path is None:
            available = ", ".join(self._vaults.keys())
            raise MCPError(INVALID_PARAMS, f"Unknown vault: {vault_name}. Available vaults: {available}")
        return vault_path

    def get_available_vaults(self) -> list[str]:
        return list(self._vaults.keys())
