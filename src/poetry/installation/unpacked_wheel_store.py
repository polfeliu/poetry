from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from typing import TYPE_CHECKING
from typing import BinaryIO
from typing import Iterator

from installer.records import Hash
from installer.records import RecordEntry
from installer.utils import copyfileobj_with_hashing

from poetry.utils.filesystem import link_or_copy

if TYPE_CHECKING:
    from collections.abc import Iterable


class UnpackedWheelStore:
    """
    Store for unpacked wheel files that can be hardlinked into virtual environments.

    Wheels are stored in a content-addressed directory structure based on the
    content hash from the lock file to ensure cache validity.
    """

    def __init__(self, cache_dir: Path) -> None:
        """
        Initialize the unpacked wheel store.

        Args:
            cache_dir: Base cache directory (typically ~/.cache/pypoetry)
        """
        self.cache_dir = cache_dir / "unpacked"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get_store_path(self, content_hash: str) -> Path:
        """
        Get the store path for a wheel identified by its content hash.

        Args:
            content_hash: Content hash from the lock file (e.g. "sha256:abc...")

        Returns:
            Path to the unpacked wheel directory in the store
        """
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
        link_mode: str,
        is_executable: bool,
        hash_algorithm: str = "sha256",
    ) -> RecordEntry:
        store_file = self.get_store_path(store_key) / path

        force_copy = (
            path.endswith(".dist-info/RECORD")
            or path.endswith(".dist-info/direct_url.json")
            or path.endswith(".dist-info/.pth")
        )

        if not store_file.exists():
            store_file.parent.mkdir(parents=True, exist_ok=True)
            with store_file.open("wb") as f:
                hash_, size = copyfileobj_with_hashing(stream, f, hash_algorithm)

            link_or_copy(
                store_file,
                target_path,
                link_mode=link_mode,
                is_executable=is_executable,
                force_copy=force_copy,
            )

            return RecordEntry(path, Hash(hash_algorithm, hash_), size)

        link_or_copy(
            store_file,
            target_path,
            link_mode=link_mode,
            is_executable=is_executable,
            force_copy=force_copy,
        )

        hash_ = hashlib.sha256()
        with target_path.open("rb") as f:
            while chunk := f.read(65536):
                hash_.update(chunk)
        hash_ = hash_.hexdigest()
        size = target_path.stat().st_size

        return RecordEntry(path, Hash(hash_algorithm, hash_), size)

    def list_entries(self) -> Iterable[Path]:
        """
        List all entries in the unpacked wheel store.

        Returns:
            Iterable of store entry paths
        """
        if not self.cache_dir.exists():
            return []

        return self.cache_dir.iterdir()

    def prune_unreferenced(self, dry_run: bool = False) -> Iterator[Path]:
        """
        Prune store entries that are no longer referenced by any venv.

        Uses link counts to determine if files are still in use.

        Args:
            dry_run: If True, yield entries that would be pruned without deleting.

        Yields:
            Path of each store entry that was pruned (or would be pruned in dry run).
        """
        for store_entry in self.list_entries():
            if not store_entry.is_dir():
                continue

            # Check if this is a valid store entry
            marker_file = store_entry / ".extracted"
            if not marker_file.exists():
                continue

            # Check link counts of files in the store
            try:
                # Check if any file has link count > 1 (referenced by venv)
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

                # Yield if unreferenced
                if not is_referenced:
                    if not dry_run:
                        shutil.rmtree(store_entry)
                    yield store_entry

            except OSError:
                # Entry is likely in use or corrupted, skip it
                continue

    def clear(self) -> None:
        """
        Clear the entire unpacked wheel store.
        """
        if self.cache_dir.exists():
            shutil.rmtree(self.cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)