from __future__ import annotations

import os

import pytest
from mcp.shared.exceptions import MCPError

from obsidian_mcp.utils import path_safety as ps


def test_check_path_safety_and_containment_are_sync_not_async():
    """ISC-3: containment functions are plain sync functions, not coroutines --
    this is what makes the TS async-without-await bug class structurally
    impossible here (see module docstring in path_safety.py)."""
    import inspect

    assert not inspect.iscoroutinefunction(ps.check_path_safety)
    assert not inspect.iscoroutinefunction(ps.validate_vault_path)
    assert not inspect.iscoroutinefunction(ps.safe_join_path)


def test_validate_vault_path_rejects_traversal(tmp_path):
    """ISC-4: regression test for the TS path-traversal vulnerability."""
    vault = os.path.join(os.path.realpath(tmp_path), "vault")
    os.makedirs(vault)
    outside = os.path.join(os.path.realpath(tmp_path), "outside")
    os.makedirs(outside)

    traversal_path = os.path.join(vault, "..", "outside", "secret.md")

    with pytest.raises(MCPError):
        ps.validate_vault_path(vault, traversal_path)


def test_validate_vault_path_accepts_legitimate_path(tmp_path):
    """ISC-5."""
    vault = os.path.join(os.path.realpath(tmp_path), "vault")
    os.makedirs(vault)

    # does not exist yet -- falls back to parent-directory containment check
    ps.validate_vault_path(vault, os.path.join(vault, "note.md"))

    # exists
    existing = os.path.join(vault, "existing.md")
    with open(existing, "w") as f:
        f.write("hi")
    ps.validate_vault_path(vault, existing)


def test_validate_vault_path_rejects_symlink_escape(tmp_path):
    vault = os.path.join(os.path.realpath(tmp_path), "vault")
    os.makedirs(vault)
    outside = os.path.join(os.path.realpath(tmp_path), "outside")
    os.makedirs(outside)
    with open(os.path.join(outside, "secret.md"), "w") as f:
        f.write("secret")

    symlink_path = os.path.join(vault, "escape.md")
    os.symlink(os.path.join(outside, "secret.md"), symlink_path)

    with pytest.raises(MCPError):
        ps.validate_vault_path(vault, symlink_path)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("My Vault!!", "my-vault"),
        ("   ", "unnamed-vault"),
        ("Work_Notes 2024", "work-notes-2024"),
        ("--already--hyphenated--", "already-hyphenated"),
        ("", "unnamed-vault"),
    ],
)
def test_sanitize_vault_name(raw, expected):
    assert ps.sanitize_vault_name(raw) == expected


def test_is_parent_path():
    assert ps.is_parent_path("/a/b", "/a/b/c") is True
    assert ps.is_parent_path("/a/b", "/a/c") is False
    # Identical paths are trivially "contained" (relpath == "") -- matches the TS
    # original; check_path_overlap separately catches exact duplicates first via
    # a set, so this doesn't affect overlap detection in practice.
    assert ps.is_parent_path("/a/b", "/a/b") is True


def test_check_path_overlap_rejects_duplicates(tmp_path):
    """ISC-7."""
    vault = os.path.join(os.path.realpath(tmp_path), "vault")
    with pytest.raises(MCPError):
        ps.check_path_overlap([vault, vault])


def test_check_path_overlap_rejects_nested_paths(tmp_path):
    """ISC-8."""
    vault = os.path.join(os.path.realpath(tmp_path), "vault")
    nested = os.path.join(vault, "sub")
    with pytest.raises(MCPError):
        ps.check_path_overlap([vault, nested])


def test_check_path_overlap_accepts_sibling_paths(tmp_path):
    base = os.path.realpath(tmp_path)
    vault_a = os.path.join(base, "vault-a")
    vault_b = os.path.join(base, "vault-b")
    ps.check_path_overlap([vault_a, vault_b])  # should not raise


def test_check_path_characters_rejects_relative_components():
    assert ps.check_path_characters("/a/../b") is not None


def test_check_path_characters_rejects_root():
    assert ps.check_path_characters("/") is not None


def test_check_suspicious_path_rejects_hidden_dir():
    assert ps.check_suspicious_path("/home/user/.config/vault") is not None


def test_check_suspicious_path_allows_dot_obsidian_component():
    # .obsidian itself is fine as a component; the vault path passed in doesn't
    # include it (it's a subdirectory the CLI checks separately), but a path
    # that merely contains ".obsidian" as one segment among others should not
    # be flagged as "hidden" on that basis alone.
    assert ps.check_suspicious_path("/home/user/vault/.obsidian") is None


def test_check_suspicious_path_rejects_system_dir():
    assert ps.check_suspicious_path("/etc/vault") is not None


def test_check_suspicious_path_rejects_home_root():
    assert ps.check_suspicious_path(os.path.expanduser("~")) is not None


def test_normalize_path_rejects_empty():
    with pytest.raises(MCPError):
        ps.normalize_path("")


def test_ensure_markdown_extension_adds_suffix():
    assert ps.ensure_markdown_extension("note").endswith("note.md")
    assert ps.ensure_markdown_extension("note.md").endswith("note.md")
