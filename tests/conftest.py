from __future__ import annotations

import os
from pathlib import Path

import pytest

from obsidian_mcp.server import build_server


@pytest.fixture
def vault_path(tmp_path: Path) -> str:
    """A realpath'd temp directory that looks like a real Obsidian vault.

    Realpath'd to avoid macOS's /var -> /private/var symlink mismatch, matching
    what cli.py does to every vault path at bootstrap (see path_safety.py's
    check_path_safety docstring for why the base path must already be resolved).
    """
    resolved = Path(os.path.realpath(tmp_path))
    obsidian_dir = resolved / ".obsidian"
    obsidian_dir.mkdir(parents=True, exist_ok=True)
    (obsidian_dir / "app.json").write_text("{}")
    return str(resolved)


@pytest.fixture
def mcp(vault_path: str):
    return build_server({"test": vault_path})
