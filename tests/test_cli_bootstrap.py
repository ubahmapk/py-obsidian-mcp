from __future__ import annotations

import os

import pytest

from obsidian_mcp import cli


def _make_vault(base: str, name: str) -> str:
    vault = os.path.join(base, name)
    os.makedirs(os.path.join(vault, ".obsidian"))
    with open(os.path.join(vault, ".obsidian", "app.json"), "w") as f:
        f.write("{}")
    return vault


def test_validate_vault_path_accepts_real_vault(tmp_path):
    base = os.path.realpath(tmp_path)
    vault = _make_vault(base, "vault")
    resolved = cli._validate_vault_path(vault)
    assert resolved == vault


def test_validate_vault_path_rejects_missing_obsidian_dir(tmp_path):
    """ISC-35."""
    base = os.path.realpath(tmp_path)
    not_a_vault = os.path.join(base, "not-a-vault")
    os.makedirs(not_a_vault)

    with pytest.raises(SystemExit):
        cli._validate_vault_path(not_a_vault)


def test_validate_vault_path_rejects_missing_app_json(tmp_path):
    base = os.path.realpath(tmp_path)
    vault = os.path.join(base, "vault")
    os.makedirs(os.path.join(vault, ".obsidian"))
    # no app.json written

    with pytest.raises(SystemExit):
        cli._validate_vault_path(vault)


def test_validate_vault_path_rejects_nonexistent_directory(tmp_path):
    base = os.path.realpath(tmp_path)
    with pytest.raises(SystemExit):
        cli._validate_vault_path(os.path.join(base, "does-not-exist"))


def test_build_vault_map_dedupes_with_numeric_suffix(tmp_path):
    """ISC-37."""
    base = os.path.realpath(tmp_path)
    vault_a = _make_vault(base, "Work")
    os.makedirs(os.path.join(base, "other"))
    vault_b = _make_vault(os.path.join(base, "other"), "Work")  # same basename "Work"

    vault_map = cli._build_vault_map([vault_a, vault_b])
    assert vault_map == {"work": vault_a, "work-1": vault_b}


def test_max_vaults_cap_enforced(tmp_path, monkeypatch, capsys):
    """ISC-36."""
    base = os.path.realpath(tmp_path)
    paths = [_make_vault(base, f"vault{i}") for i in range(cli.MAX_VAULTS + 1)]

    monkeypatch.setattr("sys.argv", ["obsidian-mcp", *paths])
    with pytest.raises(SystemExit) as exc_info:
        cli.run()
    assert exc_info.value.code == 1
