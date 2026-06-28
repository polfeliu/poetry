from __future__ import annotations

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from poetry.installation.unpacked_wheel_store import UnpackedWheelStore


if TYPE_CHECKING:
    from tests.types import FixtureDirGetter


@pytest.fixture
def store(tmp_path: Path) -> UnpackedWheelStore:
    return UnpackedWheelStore(tmp_path)


@pytest.fixture(scope="module")
def demo_wheel(fixture_dir: FixtureDirGetter) -> Path:
    return fixture_dir("distributions/demo-0.1.0-py2.py3-none-any.whl")


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


def test_extract_wheel_creates_files(
    store: UnpackedWheelStore, demo_wheel: Path
) -> None:
    content_hash = "sha256:test_hash_for_extraction"

    store_path = store.extract_wheel(demo_wheel, content_hash)
    assert store_path.exists()
    assert store_path.is_dir()
    assert (store_path / ".extracted").exists()


def test_extract_wheel_returns_same_path_on_second_call(
    store: UnpackedWheelStore, demo_wheel: Path
) -> None:
    content_hash = "sha256:test_hash_for_caching"

    first_path = store.extract_wheel(demo_wheel, content_hash)
    second_path = store.extract_wheel(demo_wheel, content_hash)
    assert first_path == second_path


def test_extract_wheel_re_extracts_after_incomplete(
    store: UnpackedWheelStore, demo_wheel: Path
) -> None:
    content_hash = "sha256:test_hash_for_reextract"

    store_path = store.extract_wheel(demo_wheel, content_hash)
    (store_path / ".extracted").unlink()

    second_path = store.extract_wheel(demo_wheel, content_hash)
    assert second_path == store_path
    assert (store_path / ".extracted").exists()


def test_list_entries_empty(store: UnpackedWheelStore) -> None:
    entries = list(store.list_entries())
    assert entries == []


def test_list_entries_after_extraction(
    store: UnpackedWheelStore, demo_wheel: Path
) -> None:
    store.extract_wheel(demo_wheel, "sha256:test_hash_for_listing")
    entries = list(store.list_entries())
    assert len(entries) == 1


def test_clear_removes_all_entries(
    store: UnpackedWheelStore, demo_wheel: Path
) -> None:
    store.extract_wheel(demo_wheel, "sha256:test_hash_for_clear1")
    store.extract_wheel(demo_wheel, "sha256:test_hash_for_clear2")

    store.clear()

    assert list(store.list_entries()) == []


def test_prune_unreferenced_removes_unused(
    store: UnpackedWheelStore, demo_wheel: Path
) -> None:
    store_path = store.extract_wheel(
        demo_wheel, "sha256:test_hash_for_prune"
    )
    pruned = list(store.prune_unreferenced())
    assert len(pruned) == 1
    assert not store_path.exists()


def test_prune_referenced_is_kept(
    store: UnpackedWheelStore, demo_wheel: Path
) -> None:
    store_path = store.extract_wheel(
        demo_wheel, "sha256:test_hash_for_keep"
    )
    store_file = None
    for f in store_path.rglob("*"):
        if f.is_file() and f.name != ".extracted":
            store_file = f
            break
    assert store_file is not None
    ref_dir = store.cache_dir / "refs"
    ref_dir.mkdir(parents=True, exist_ok=True)
    ref_file = ref_dir / store_file.name
    ref_file.hardlink_to(store_file)
    pruned = list(store.prune_unreferenced())
    assert len(pruned) == 0


def test_prune_skips_missing_marker(
    store: UnpackedWheelStore, demo_wheel: Path
) -> None:
    store_path = store.extract_wheel(
        demo_wheel, "sha256:test_hash_for_no_marker"
    )
    (store_path / ".extracted").unlink()

    pruned = list(store.prune_unreferenced())
    assert len(pruned) == 0
