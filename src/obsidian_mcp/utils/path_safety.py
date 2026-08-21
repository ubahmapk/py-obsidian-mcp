"""Vault path validation and containment checks.

Ported from the TypeScript project's `utils/path.ts`, macOS/Linux only (no Windows
branches — see project ISA "Out of Scope"). Every function here is deliberately
synchronous, not just as a style choice: the TS original's `validateVaultPath()`
called the async `checkPathSafety()` without `await`. Since a JS Promise object is
always truthy, `!checkPathSafety(...)` was always `False` and the containment check
never threw — a real path-traversal vulnerability in the shipped server. Keeping
these functions plain `def` removes the async/await boundary entirely, so that bug
class is structurally impossible here rather than merely patched.
"""

from __future__ import annotations

import os
import re
import unicodedata

from mcp.shared.exceptions import MCPError
from mcp.types import INVALID_REQUEST

_MAX_PATH_LENGTH = 4096
_MAX_COMPONENT_LENGTH = 255

_SYSTEM_DIRS = (
    "/bin",
    "/sbin",
    "/usr/bin",
    "/usr/sbin",
    "/etc",
    "/var",
    "/tmp",
    "/dev",
    "/sys",
)

_NETWORK_MOUNT_PREFIXES = ("/net/", "/mnt/", "/media/", "/Volumes/")


def _mcp_error(message: str) -> MCPError:
    return MCPError(INVALID_REQUEST, message)


def check_path_characters(vault_path: str) -> str | None:
    """Returns an error message if the path contains problematic characters, else None."""
    if len(vault_path) > _MAX_PATH_LENGTH:
        return f"Path exceeds maximum length ({_MAX_PATH_LENGTH} characters)"

    components = vault_path.split("/")
    for component in components:
        if len(component) > _MAX_COMPONENT_LENGTH:
            return f'Directory/file name too long: "{component[:50]}..."'

    if vault_path == "/":
        return "Cannot use filesystem root directory"

    if "." in components or ".." in components:
        return "Path cannot contain relative components (. or ..)"

    if re.search(r"[\x00-\x1F\x7F]", vault_path):
        return "Contains non-printable characters"

    if "\x00" in vault_path:
        return "Contains invalid characters for Unix paths"

    if "�" in vault_path:
        return "Contains invalid Unicode characters"

    if vault_path != vault_path.strip():
        return "Contains leading or trailing whitespace"

    if re.search(r"/{2,}", vault_path):
        return "Contains consecutive path separators"

    return None


def check_local_path(vault_path: str) -> str | None:
    """Best-effort local-filesystem check.

    Deliberately simplified from the TS original, which shelled out to `df` with a
    5s timeout on every startup validation. Uses `os.path.ismount()` plus a denylist
    of common network/removable mount prefixes instead -- no subprocess calls.
    """
    try:
        real_path = os.path.realpath(vault_path)
    except OSError:
        return None

    if any(real_path.startswith(prefix) for prefix in _NETWORK_MOUNT_PREFIXES):
        return "Network or removable filesystem is not supported"

    return None


def check_suspicious_path(vault_path: str) -> str | None:
    """Returns an error message if the path looks suspicious, else None."""
    for part in vault_path.split(os.sep):
        if part.startswith(".") and part != ".obsidian":
            return "Contains hidden directories"

    lowered = vault_path.lower()
    if any(lowered.startswith(d.lower()) for d in _SYSTEM_DIRS):
        return "Points to a system directory"

    if vault_path == os.path.expanduser("~"):
        return "Points to home directory root"

    if len(vault_path) > 255:
        return "Path is too long (maximum 255 characters)"

    char_issue = check_path_characters(vault_path)
    if char_issue:
        return char_issue

    return None


def normalize_path(input_path: str) -> str:
    """Normalizes a path consistently. Raises McpError on empty/invalid input."""
    if not input_path or not isinstance(input_path, str):
        raise _mcp_error(f"Invalid path: {input_path!r}")

    if unicodedata.category(input_path[0]) == "Cc":
        raise _mcp_error(f"Invalid path: {input_path!r}")

    normalized = input_path.replace("\\", "/")

    if normalized.startswith(("./", "../")):
        return os.path.abspath(normalized)

    return normalized


def check_path_safety(base_path: str, target_path: str) -> bool:
    """True if target_path is safely contained within base_path.

    Resolves symlinks and checks containment against both the resolved real path
    and the literal normalized path. For targets that don't exist yet, falls back
    to checking the parent directory's real path. Plain sync function -- see
    module docstring for why that matters.

    Expects `base_path` to already be a realpath (no symlink components) -- the CLI
    bootstrap resolves vault paths with `os.path.realpath()` before storing them, so
    every containment check downstream compares like-for-like. Without that, macOS's
    `/var` -> `/private/var` symlink (among others) would falsely reject legitimate
    in-vault paths whenever the vault itself sits behind a symlinked prefix.
    """
    resolved_path = normalize_path(target_path)
    resolved_base_path = normalize_path(base_path)

    try:
        real_path = os.path.realpath(resolved_path)
        if os.path.lexists(resolved_path):
            normalized_real = normalize_path(real_path)
            if not (normalized_real == resolved_base_path or normalized_real.startswith(resolved_base_path + "/")):
                return False
            return resolved_path == resolved_base_path or resolved_path.startswith(resolved_base_path + "/")
        raise FileNotFoundError(resolved_path)
    except OSError:
        parent_dir = os.path.dirname(resolved_path)
        try:
            real_parent = os.path.realpath(parent_dir)
            normalized_parent = normalize_path(real_parent)
            return normalized_parent == resolved_base_path or normalized_parent.startswith(resolved_base_path + "/")
        except OSError:
            return False


def validate_vault_path(vault_path: str, target_path: str) -> None:
    """Raises McpError if target_path is not contained within vault_path."""
    if not check_path_safety(vault_path, target_path):
        raise _mcp_error(f"Path must be within the vault directory. Path: {target_path}, Vault: {vault_path}")


def safe_join_path(vault_path: str, *segments: str) -> str:
    """Joins path segments onto vault_path and validates containment."""
    joined = os.path.join(vault_path, *segments)
    resolved = normalize_path(joined)
    validate_vault_path(vault_path, resolved)
    return resolved


def sanitize_vault_name(name: str) -> str:
    """Lowercase, non-alphanumeric runs -> hyphen, trim, fallback to 'unnamed-vault'."""
    sanitized = re.sub(r"[^a-z0-9]+", "-", name.lower())
    sanitized = sanitized.strip("-")
    return sanitized or "unnamed-vault"


def is_parent_path(parent: str, child: str) -> bool:
    """True if `parent` contains `child`."""
    try:
        relative = os.path.relpath(child, parent)
    except ValueError:
        return False
    return not relative.startswith("..") and not os.path.isabs(relative)


def check_path_overlap(paths: list[str]) -> None:
    """Raises McpError if any two paths are duplicates or nested within each other."""
    normalized_paths = [os.path.normpath(p).rstrip("/") for p in paths]

    seen: dict[str, int] = {}
    for index, normalized in enumerate(normalized_paths):
        if normalized in seen:
            other = seen[normalized]
            raise _mcp_error(
                "Duplicate vault path provided:\n"
                "  Original paths:\n"
                f"    1: {paths[other]}\n"
                f"    2: {paths[index]}\n"
                f"  Both resolve to: {normalized}"
            )
        seen[normalized] = index

    for i in range(len(normalized_paths)):
        for j in range(i + 1, len(normalized_paths)):
            if is_parent_path(normalized_paths[i], normalized_paths[j]) or is_parent_path(
                normalized_paths[j], normalized_paths[i]
            ):
                raise _mcp_error(
                    "Vault paths cannot overlap:\n"
                    f"  Path 1: {paths[i]}\n"
                    f"  Path 2: {paths[j]}\n"
                    "  (One vault directory cannot be inside another)\n"
                    "  Normalized paths:\n"
                    f"    1: {normalized_paths[i]}\n"
                    f"    2: {normalized_paths[j]}"
                )


def ensure_markdown_extension(file_path: str) -> str:
    """Normalizes a filename/path and ensures it has a .md extension."""
    normalized = normalize_path(file_path)
    return normalized if normalized.endswith(".md") else f"{normalized}.md"
