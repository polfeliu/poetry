from __future__ import annotations

import shutil

from typing import TYPE_CHECKING
from typing import BinaryIO

from installer.records import Hash
from installer.records import RecordEntry
from installer.utils import copyfileobj_with_hashing

from poetry.utils.filesystem import LinkMode
from poetry.utils.filesystem import link_or_copy
from poetry.utils.helpers import get_file_hash


if TYPE_CHECKING:
    from collections.abc import Iterable
    from collections.abc import Iterator
    from pathlib import Path


class UnpackedWheelStore:
    """
    Store for unpacked wheel files that can be hardlinked into virtual environments.

    Wheels are stored in a content-addressed directory structure based on the
    content hash from the lock file to ensure cache validity.
    """

    def __init__(self, cache_dir: Path) -> None:
        self.cache_dir = cache_dir / "unpacked"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get_store_path(self, content_hash: str) -> Path:
        key = content_hash.replace(":", "-")
        return self.cache_dir / key

    def is_extracted(self, content_hash: str) -> bool:
        return (self.get_store_path(content_hash) / ".extracted").exists()

    def mark_extracted(self, content_hash: str) -> None:
        self.get_store_path(content_hash).mkdir(parents=True, exist_ok=True)
        (self.get_store_path(content_hash) / ".extracted").touch()

    def write_file(
        self,
        store_key: str,
        path: str,
        stream: BinaryIO,
        target_path: Path,
        link_mode: LinkMode,
        is_executable: bool,
        hash_algorithm: str = "sha256",
    ) -> RecordEntry:
        store_file = self.get_store_path(store_key) / path

        if not store_file.exists():
            store_file.parent.mkdir(parents=True, exist_ok=True)
            with store_file.open("wb") as f:
                hash_, size = copyfileobj_with_hashing(stream, f, hash_algorithm)

            link_or_copy(
                store_file,
                target_path,
                link_mode=link_mode,
                is_executable=is_executable,
            )

            return RecordEntry(path, Hash(hash_algorithm, hash_), size)

        # Cache hit: link from store, recompute hash (store doesn't persist them).
        link_or_copy(
            store_file,
            target_path,
            link_mode=link_mode,
            is_executable=is_executable,
        )

        hash_ = get_file_hash(store_file, hash_algorithm)
        size = store_file.stat().st_size

        return RecordEntry(path, Hash(hash_algorithm, hash_), size)

    def list_entries(self) -> Iterable[Path]:
        if not self.cache_dir.exists():
            return []

        return self.cache_dir.iterdir()

    def prune_unreferenced(self, dry_run: bool = False) -> Iterator[Path]:
        """
        Prune store entries that are no longer referenced by any venv.

        Uses link counts to determine if files are still in use.
        """
        for store_entry in self.list_entries():
            if not store_entry.is_dir():
                continue

            marker_file = store_entry / ".extracted"
            if not marker_file.exists():
                continue

            try:
                is_referenced = False
                for file_path in store_entry.rglob("*"):
                    if file_path.is_file():
                        try:
                            link_count = file_path.stat().st_nlink
                            if link_count > 1:
                                is_referenced = True
                                break
                        except (OSError, FileNotFoundError):
                            continue

                if not is_referenced:
                    if not dry_run:
                        shutil.rmtree(store_entry)
                    yield store_entry

            except OSError:
                continue

    def clear(self) -> None:
        if self.cache_dir.exists():
            shutil.rmtree(self.cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
