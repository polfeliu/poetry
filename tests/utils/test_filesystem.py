from __future__ import annotations

import stat

from typing import TYPE_CHECKING

import pytest

from poetry.utils.filesystem import LinkMode
from poetry.utils.filesystem import copy_file
from poetry.utils.filesystem import link_or_copy
from poetry.utils.filesystem import try_hardlink
from poetry.utils.filesystem import try_reflink


if TYPE_CHECKING:
    from pathlib import Path


def test_try_hardlink_creates_link(tmp_path: Path) -> None:
    src = tmp_path / "src.txt"
    dst = tmp_path / "dst.txt"
    src.write_text("content")

    assert try_hardlink(src, dst)
    assert dst.exists()
    assert dst.read_text() == "content"
    assert dst.stat().st_ino == src.stat().st_ino


def test_try_hardlink_nonexistent_src(tmp_path: Path) -> None:
    src = tmp_path / "nonexistent.txt"
    dst = tmp_path / "dst.txt"

    assert not try_hardlink(src, dst)
    assert not dst.exists()


def test_try_hardlink_nested_directory(tmp_path: Path) -> None:
    src = tmp_path / "src.txt"
    dst = tmp_path / "sub" / "dst.txt"
    src.write_text("content")

    assert try_hardlink(src, dst)
    assert dst.exists()
    assert dst.stat().st_ino == src.stat().st_ino


def test_try_reflink_fallback_to_copy(tmp_path: Path) -> None:
    src = tmp_path / "src.txt"
    dst = tmp_path / "dst.txt"
    src.write_text("content")

    result = try_reflink(src, dst)
    if result:
        assert dst.exists()
        assert dst.read_text() == "content"


def test_try_reflink_nonexistent_src(tmp_path: Path) -> None:
    src = tmp_path / "nonexistent.txt"
    dst = tmp_path / "dst.txt"

    assert not try_reflink(src, dst)
    assert not dst.exists()


def test_copy_file_basic(tmp_path: Path) -> None:
    src = tmp_path / "src.txt"
    dst = tmp_path / "dst.txt"
    src.write_text("content")

    copy_file(src, dst)
    assert dst.exists()
    assert dst.read_text() == "content"


def test_copy_file_executable(tmp_path: Path) -> None:
    src = tmp_path / "src.sh"
    dst = tmp_path / "dst.sh"
    src.write_text("#!/bin/sh\necho hello")

    copy_file(src, dst, is_executable=True)
    assert dst.exists()
    mode = dst.stat().st_mode
    assert mode & stat.S_IXUSR
    assert mode & stat.S_IXGRP
    assert mode & stat.S_IXOTH


def test_link_or_copy_hardlink(tmp_path: Path) -> None:
    src = tmp_path / "src.txt"
    dst = tmp_path / "dst.txt"
    src.write_text("content")

    link_or_copy(src, dst, link_mode=LinkMode.HARDLINK)
    assert dst.exists()
    assert dst.read_text() == "content"
    assert dst.stat().st_ino == src.stat().st_ino


def test_link_or_copy_fallback_to_copy(tmp_path: Path) -> None:
    src = tmp_path / "src.txt"
    dst = tmp_path / "dst.txt"
    src.write_text("content")

    link_or_copy(src, dst, link_mode=LinkMode.COPY)
    assert dst.exists()
    assert dst.read_text() == "content"


def test_link_or_copy_executable(tmp_path: Path) -> None:
    src = tmp_path / "src.sh"
    dst = tmp_path / "dst.sh"
    src.write_text("#!/bin/sh\necho hello")

    link_or_copy(src, dst, link_mode=LinkMode.COPY, is_executable=True)
    assert dst.exists()
    mode = dst.stat().st_mode
    assert mode & stat.S_IXUSR


def test_link_or_copy_reflink_fallback(tmp_path: Path) -> None:
    src = tmp_path / "src.txt"
    dst = tmp_path / "dst.txt"
    src.write_text("content")

    link_or_copy(src, dst, link_mode=LinkMode.REFLINK)
    assert dst.exists()
    assert dst.read_text() == "content"


def test_link_or_copy_nonexistent_src(tmp_path: Path) -> None:
    src = tmp_path / "nonexistent.txt"
    dst = tmp_path / "dst.txt"

    with pytest.raises(FileNotFoundError):
        link_or_copy(src, dst, link_mode=LinkMode.COPY)


def test_copy_file_creates_parent_dirs(tmp_path: Path) -> None:
    src = tmp_path / "src.txt"
    dst = tmp_path / "sub" / "dst.txt"
    src.write_text("content")

    copy_file(src, dst)
    assert dst.exists()
