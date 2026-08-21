"""Maps filesystem errors to MCPError, mirroring TS `utils/errors.ts`."""

from __future__ import annotations

import errno

from mcp.shared.exceptions import MCPError
from mcp.types import INTERNAL_ERROR, INVALID_REQUEST


def handle_fs_error(error: Exception, operation: str) -> None:
    """Raises an MCPError mapped from a filesystem OSError. Never returns normally."""
    if isinstance(error, MCPError):
        raise error

    if isinstance(error, OSError):
        code = error.errno
        if code == errno.ENOENT:
            raise MCPError(INVALID_REQUEST, f"File or directory not found: {error.strerror}") from error
        if code == errno.EACCES:
            raise MCPError(INVALID_REQUEST, f"Permission denied: {error.strerror}") from error
        if code == errno.EEXIST:
            raise MCPError(INVALID_REQUEST, f"File or directory already exists: {error.strerror}") from error
        if code == errno.ENOSPC:
            raise MCPError(INTERNAL_ERROR, "Not enough space to write file") from error
        raise MCPError(INTERNAL_ERROR, f"Failed to {operation}: {error}") from error

    raise MCPError(INTERNAL_ERROR, f"Unexpected error during {operation}: {error}") from error


def create_note_exists_error(path: str) -> MCPError:
    return MCPError(
        INVALID_REQUEST,
        f"A note already exists at: {path}\n\n"
        "To prevent accidental modifications, this operation has been cancelled.\n"
        "If you want to modify an existing note, please explicitly request to edit or replace it.",
    )


def create_note_not_found_error(path: str) -> MCPError:
    return MCPError(INVALID_REQUEST, f'Note "{path}" not found in vault')
