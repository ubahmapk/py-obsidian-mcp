from __future__ import annotations

import os

from obsidian_mcp.utils.files import (
    ensure_directory,
    file_exists,
    get_all_markdown_files,
    safe_read_file,
)


async def test_get_all_markdown_files_recursive_and_skips_hidden(tmp_path):
    base = os.path.realpath(tmp_path)
    os.makedirs(os.path.join(base, "sub"))
    os.makedirs(os.path.join(base, ".hidden"))
    with open(os.path.join(base, "a.md"), "w") as f:
        f.write("a")
    with open(os.path.join(base, "sub", "b.md"), "w") as f:
        f.write("b")
    with open(os.path.join(base, ".hidden", "c.md"), "w") as f:
        f.write("c")
    with open(os.path.join(base, "notmd.txt"), "w") as f:
        f.write("x")

    found = await get_all_markdown_files(base)
    relative = sorted(os.path.relpath(f, base) for f in found)
    assert relative == ["a.md", os.path.join("sub", "b.md")]


async def test_file_exists(tmp_path):
    base = os.path.realpath(tmp_path)
    path = os.path.join(base, "a.md")
    assert await file_exists(path) is False
    with open(path, "w") as f:
        f.write("a")
    assert await file_exists(path) is True


async def test_safe_read_file_returns_none_for_missing(tmp_path):
    base = os.path.realpath(tmp_path)
    assert await safe_read_file(os.path.join(base, "missing.md")) is None


async def test_ensure_directory_creates_nested(tmp_path):
    base = os.path.realpath(tmp_path)
    target = os.path.join(base, "a", "b", "c")
    await ensure_directory(target)
    assert os.path.isdir(target)
    # calling again should not raise
    await ensure_directory(target)
