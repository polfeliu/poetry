from __future__ import annotations

import enum
import os
import shutil
import stat

from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from pathlib import Path


class LinkMode(str, enum.Enum):
    COPY = "copy"
    HARDLINK = "hardlink"
    REFLINK = "reflink"


def try_hardlink(src: Path, dst: Path) -> bool:
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)

        if src.stat().st_dev != dst.parent.stat().st_dev:
            return False

        dst.hardlink_to(src)
        return True
    except OSError:
        return False


def try_reflink(src: Path, dst: Path) -> bool:
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)

        _reflink = getattr(os, "reflink", None)
        if _reflink is not None:
            with src.open("rb") as fsrc, dst.open("wb") as fdst:
                _reflink(fsrc.fileno(), fdst.fileno())
            return True

        shutil.copyfile(src, dst, follow_symlinks=False)

        if src.stat().st_ino == dst.stat().st_ino:
            return True

        dst.unlink()
        return False

    except (OSError, NotImplementedError, AttributeError, FileNotFoundError):
        return False


def copy_file(src: Path, dst: Path, is_executable: bool = False) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)

    shutil.copy2(src, dst, follow_symlinks=True)

    if is_executable:
        current_mode = dst.stat().st_mode
        dst.chmod(current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def link_or_copy(
    src: Path,
    dst: Path,
    *,
    link_mode: LinkMode = LinkMode.COPY,
    is_executable: bool = False,
) -> None:
    if link_mode is LinkMode.REFLINK:
        if try_reflink(src, dst):
            return
        link_mode = LinkMode.HARDLINK

    if link_mode is LinkMode.HARDLINK:
        if try_hardlink(src, dst):
            return
        link_mode = LinkMode.COPY

    copy_file(src, dst, is_executable)
