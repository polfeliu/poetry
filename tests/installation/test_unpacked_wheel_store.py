from __future__ import annotations

from pathlib import Path

import pytest

from poetry.installation.unpacked_wheel_store import UnpackedWheelStore


@pytest.fixture
def store(tmp_path: Path) -> UnpackedWheelStore:
    return UnpackedWheelStore(tmp_path)


def test_get_store_path_deterministic(store: UnpackedWheelStore) -> None:
    hash_a = "sha256:abc123def456abc123def456abc123def456abc123def456abc123def456"
    hash_b = "sha256:abc123def456abc123def456abc123def456abc123def456abc123def456"

    assert store.get_store_path(hash_a) == store.get_store_path(hash_b)


def test_get_store_path_different_hashes(store: UnpackedWheelStore) -> None:
    hash_a = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    hash_b = "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"

    assert store.get_store_path(hash_a) != store.get_store_path(hash_b)


def test_get_store_path_under_cache_dir(store: UnpackedWheelStore) -> None:
    content_hash = "sha256:abc123def456abc123def456abc123def456abc123def456abc123def456"
    path = store.get_store_path(content_hash)

    assert str(path).startswith(str(store.cache_dir))
    assert path.parent == store.cache_dir


def test_list_entries_empty(store: UnpackedWheelStore) -> None:
    entries = list(store.list_entries())
    assert entries == []


def test_clear_removes_all_entries(store: UnpackedWheelStore) -> None:
    (store.cache_dir / "entry1").mkdir(parents=True)
    (store.cache_dir / "entry2").mkdir(parents=True)

    store.clear()

    assert list(store.list_entries()) == []


def test_is_extracted_returns_false_for_missing_entry(
    store: UnpackedWheelStore,
) -> None:
    assert not store.is_extracted("sha256:nonexistent")


def test_is_extracted_returns_true_after_mark(
    store: UnpackedWheelStore,
) -> None:
    content_hash = "sha256:test_marked"
    store.mark_extracted(content_hash)
    assert store.is_extracted(content_hash)


def test_is_extracted_returns_false_without_marker(
    store: UnpackedWheelStore,
) -> None:
    content_hash = "sha256:test_no_marker"
    store_path = store.get_store_path(content_hash)
    store_path.mkdir(parents=True)
    assert not store.is_extracted(content_hash)


def test_prune_unreferenced_removes_unused(
    store: UnpackedWheelStore,
) -> None:
    store_path = store.cache_dir / "test_entry"
    store_path.mkdir(parents=True)
    (store_path / ".extracted").touch()
    (store_path / "some_file.txt").write_text("test")

    pruned = list(store.prune_unreferenced())
    assert len(pruned) == 1
    assert not store_path.exists()


def test_prune_referenced_is_kept(store: UnpackedWheelStore) -> None:
    store_path = store.cache_dir / "test_entry"
    store_path.mkdir(parents=True)
    (store_path / ".extracted").touch()
    store_file = store_path / "some_file.txt"
    store_file.write_text("test")
    ref_dir = store.cache_dir / "refs"
    ref_dir.mkdir(parents=True, exist_ok=True)
    ref_file = ref_dir / "some_file.txt"
    ref_file.hardlink_to(store_file)

    pruned = list(store.prune_unreferenced())
    assert len(pruned) == 0


def test_prune_skips_missing_marker(store: UnpackedWheelStore) -> None:
    store_path = store.cache_dir / "test_entry"
    store_path.mkdir(parents=True)
    (store_path / "some_file.txt").write_text("test")
    # No .extracted marker

    pruned = list(store.prune_unreferenced())
    assert len(pruned) == 0
