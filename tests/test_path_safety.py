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


# --------------------------------------------------------------------------- #
# Windows path rules.
#
# The pure-string helpers (_check_windows_path_characters, _normalize_windows_path,
# _check_windows_local_path) are host-independent (they use `ntpath`), so these
# tests run on every OS and are the primary safety net for the ported win32 logic.
# Realpath/symlink/junction containment behaviour is genuinely OS-dependent and is
# covered separately by the `os.name == "nt"` gated tests below (verified in CI on a
# windows-latest runner).
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "path",
    [
        r"C:\Users\me\Vault",
        r"D:\Notes",
        "C:/Users/me/Vault",  # forward slashes are also valid on Windows
        r"\\server\share\Vault",  # UNC
    ],
)
def test_check_windows_path_characters_accepts_valid(path):
    assert ps._check_windows_path_characters(path) is None


@pytest.mark.parametrize(
    ("path", "fragment"),
    [
        (r"C:\Users\me\CON", "reserved"),
        (r"C:\Users\me\con.md", "reserved"),  # reserved + extension
        (r"C:\Users\me\LPT1\notes", "reserved"),
        (r"C:\Users\me\COM9.txt", "reserved"),
        (r"C:\Users\me\bad<name", "not allowed on Windows"),
        (r'C:\Users\me\bad"name', "not allowed on Windows"),
        (r"C:\Users\me\pipe|name", "not allowed on Windows"),
        (r"C:\Users\me\star*name", "not allowed on Windows"),
        (r"C:\Users\me\alt:stream", "not allowed on Windows"),  # ADS colon mid-path
        ("C:\\", "drive root"),
        ("C:", "drive root"),
        (r"\\.\C:\dev", "Device paths"),
        (r"C:\Users\me\..\escape", "relative components"),
        ("C:\\" + "a" * 300, "maximum length"),
    ],
)
def test_check_windows_path_characters_rejects(path, fragment):
    result = ps._check_windows_path_characters(path)
    assert result is not None
    assert fragment.lower() in result.lower()


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (r"C:\Users\me\Vault", "C:/Users/me/Vault"),
        (r"C:\Users\me\sub\..\Vault", "C:/Users/me/Vault"),
        (r"\\server\share\Vault", "//server/share/Vault"),
        ("C:/Users/me/Vault", "C:/Users/me/Vault"),
    ],
)
def test_normalize_windows_path_preserves_drive_and_unc(raw, expected):
    assert ps._normalize_windows_path(raw) == expected


@pytest.mark.parametrize(
    "path",
    [r"\\server\share\Vault", "//server/share/Vault"],
)
def test_check_windows_local_path_rejects_unc(path):
    assert ps._check_windows_local_path(path) is not None


@pytest.mark.parametrize(
    "path",
    [r"C:\Users\me\Vault", "C:/Users/me/Vault", r"D:\Notes"],
)
def test_check_windows_local_path_accepts_local_drive(path):
    assert ps._check_windows_local_path(path) is None


@pytest.mark.parametrize(
    "path",
    [
        r"C:\Windows\System32",
        r"c:\program files\app",  # case-insensitive
        "C:/ProgramData/x",  # separator-agnostic
        r"C:\Program Files (x86)\app",
    ],
)
def test_check_suspicious_path_rejects_windows_system_dirs(path):
    result = ps.check_suspicious_path(path)
    assert result is not None
    assert "system directory" in result.lower()


@pytest.mark.skipif(os.name != "nt", reason="realpath/junction containment is Windows-specific")
def test_windows_containment_is_case_insensitive(tmp_path):
    """Windows filesystems are case-insensitive: a vault must contain a target
    whose case differs. Verified on the windows-latest CI runner."""
    vault = os.path.join(os.path.realpath(tmp_path), "Vault")
    os.makedirs(vault)
    with open(os.path.join(vault, "Note.md"), "w") as f:
        f.write("hi")

    # differently-cased target resolves to the same file and must be accepted
    ps.validate_vault_path(vault, os.path.join(vault.upper(), "NOTE.MD"))


@pytest.mark.skipif(os.name != "nt", reason="realpath/junction containment is Windows-specific")
def test_windows_validate_vault_path_rejects_traversal(tmp_path):
    vault = os.path.join(os.path.realpath(tmp_path), "vault")
    os.makedirs(vault)
    outside = os.path.join(os.path.realpath(tmp_path), "outside")
    os.makedirs(outside)

    traversal_path = os.path.join(vault, "..", "outside", "secret.md")
    with pytest.raises(MCPError):
        ps.validate_vault_path(vault, traversal_path)
