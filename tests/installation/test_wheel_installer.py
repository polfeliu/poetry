from __future__ import annotations

import re

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from poetry.core.constraints.version import parse_constraint

from poetry.installation.wheel_installer import WheelInstaller
from poetry.utils._compat import WINDOWS
from poetry.utils.env import MockEnv


if TYPE_CHECKING:
    from pytest import TempPathFactory

    from tests.types import FixtureDirGetter


@pytest.fixture
def env(tmp_path: Path) -> MockEnv:
    return MockEnv(path=tmp_path / "env")


@pytest.fixture(scope="module")
def demo_wheel(fixture_dir: FixtureDirGetter) -> Path:
    return fixture_dir("distributions/demo-0.1.0-py2.py3-none-any.whl")


@pytest.fixture(scope="module")
def default_installation(tmp_path_factory: TempPathFactory, demo_wheel: Path) -> Path:
    env = MockEnv(path=tmp_path_factory.mktemp("default_install"))
    installer = WheelInstaller(env)
    installer.install(demo_wheel)
    return Path(env.paths["purelib"])


def test_default_installation_source_dir_content(default_installation: Path) -> None:
    source_dir = default_installation / "demo"
    assert source_dir.exists()
    assert (source_dir / "__init__.py").exists()


def test_default_installation_dist_info_dir_content(default_installation: Path) -> None:
    dist_info_dir = default_installation / "demo-0.1.0.dist-info"
    assert dist_info_dir.exists()
    assert (dist_info_dir / "INSTALLER").exists()
    assert (dist_info_dir / "METADATA").exists()
    assert (dist_info_dir / "RECORD").exists()
    assert (dist_info_dir / "WHEEL").exists()


def test_installer_file_contains_valid_version(default_installation: Path) -> None:
    installer_file = default_installation / "demo-0.1.0.dist-info" / "INSTALLER"
    with open(installer_file, encoding="utf-8") as f:
        installer_content = f.read()
    match = re.match(r"Poetry (?P<version>.*)", installer_content)
    assert match
    parse_constraint(match.group("version"))  # must not raise an error


def test_default_installation_no_bytecode(default_installation: Path) -> None:
    cache_dir = default_installation / "demo" / "__pycache__"
    assert not cache_dir.exists()


@pytest.mark.parametrize("compile", [True, False])
def test_enable_bytecode_compilation(
    env: MockEnv, demo_wheel: Path, compile: bool
) -> None:
    installer = WheelInstaller(env)
    installer.enable_bytecode_compilation(compile)
    installer.install(demo_wheel)
    cache_dir = Path(env.paths["purelib"]) / "demo" / "__pycache__"
    if compile:
        assert cache_dir.exists()
        assert list(cache_dir.glob("*.pyc"))
        assert not list(cache_dir.glob("*.opt-1.pyc"))
        assert not list(cache_dir.glob("*.opt-2.pyc"))
    else:
        assert not cache_dir.exists()


def test_install_dir_is_symlink(tmp_path: Path, demo_wheel: Path) -> None:
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    symlink_dir = tmp_path / "symlink"
    symlink_dir.symlink_to(target_dir, target_is_directory=True)

    env = MockEnv(path=symlink_dir)

    installer = WheelInstaller(env)
    installer.install(demo_wheel)

    assert (Path(env.paths["purelib"]) / "demo").exists()


@pytest.mark.parametrize("existing", [False, True])
def test_no_path_traversal(
    env: MockEnv, wheel_with_path_traversal: Path, existing: bool
) -> None:
    """see also test_extractall_wheel_no_path_traversal in test_helpers.py"""
    target = env.path.parent / "traversal.txt"
    if existing:
        target.write_text("original", encoding="utf-8")
    installer = WheelInstaller(env)
    with pytest.raises(ValueError):
        installer.install(wheel_with_path_traversal)

    if existing:
        assert target.exists()
        assert target.read_text(encoding="utf-8") == "original"
    else:
        assert not target.exists()


@pytest.fixture(scope="module")
def hardlink_installation(
    tmp_path_factory: TempPathFactory, demo_wheel: Path
) -> Path:
    env = MockEnv(path=tmp_path_factory.mktemp("hardlink_install"))
    installer = WheelInstaller(env, link_mode="hardlink")
    installer.install(demo_wheel, content_hash="sha256:test_demo_wheel")
    return Path(env.paths["purelib"])


def test_hardlink_installation_source_dir_content(
    hardlink_installation: Path,
) -> None:
    source_dir = hardlink_installation / "demo"
    assert source_dir.exists()
    assert (source_dir / "__init__.py").exists()


def test_hardlink_installation_dist_info_dir_content(
    hardlink_installation: Path,
) -> None:
    dist_info_dir = hardlink_installation / "demo-0.1.0.dist-info"
    assert dist_info_dir.exists()
    assert (dist_info_dir / "INSTALLER").exists()
    assert (dist_info_dir / "METADATA").exists()
    assert (dist_info_dir / "RECORD").exists()
    assert (dist_info_dir / "WHEEL").exists()


def test_hardlink_installer_file_contains_valid_version(
    hardlink_installation: Path,
) -> None:
    installer_file = hardlink_installation / "demo-0.1.0.dist-info" / "INSTALLER"
    with open(installer_file, encoding="utf-8") as f:
        installer_content = f.read()
    match = re.match(r"Poetry (?P<version>.*)", installer_content)
    assert match
    parse_constraint(match.group("version"))


def _store_dir(env: MockEnv) -> Path:
    return (env.path / ".." / ".." / "cache" / "unpacked").resolve()


def _store_entry_for_hash(env: MockEnv, content_hash: str) -> Path:
    store = _store_dir(env)
    key = content_hash.replace(":", "-")[:16]
    return store / key


def test_hardlink_installation_store_created(
    tmp_path: Path, demo_wheel: Path
) -> None:
    env = MockEnv(path=tmp_path / "env")
    installer = WheelInstaller(env, link_mode="hardlink")
    content_hash = "sha256:test_store_created"
    installer.install(demo_wheel, content_hash=content_hash)
    entry = _store_entry_for_hash(env, content_hash)
    assert entry.exists()


def test_hardlink_store_shared(tmp_path: Path, demo_wheel: Path) -> None:
    env_a = MockEnv(path=tmp_path / "env_a")
    env_b = MockEnv(path=tmp_path / "env_b")
    installer_a = WheelInstaller(env_a, link_mode="hardlink")
    installer_b = WheelInstaller(env_b, link_mode="hardlink")
    content_hash = "sha256:test_shared_store"

    installer_a.install(demo_wheel, content_hash=content_hash)
    installer_b.install(demo_wheel, content_hash=content_hash)

    entry = _store_entry_for_hash(env_a, content_hash)
    assert entry.exists()
    hardlinkable = [
        f
        for f in entry.rglob("*")
        if f.is_file()
        and f.name not in (".extracted",)
        and f.suffix in (".py", ".pth")
    ]
    assert len(hardlinkable) > 0, "No hardlinkable files in store"
    for f in hardlinkable:
        assert f.stat().st_nlink > 1


def test_hardlink_no_store_without_hash(tmp_path: Path, demo_wheel: Path) -> None:
    env = MockEnv(path=tmp_path / "env")
    installer = WheelInstaller(env, link_mode="hardlink")
    installer.install(demo_wheel)

    purelib = Path(env.paths["purelib"])
    assert (purelib / "demo" / "__init__.py").exists()


def test_copy_mode_no_store(tmp_path: Path, demo_wheel: Path) -> None:
    env = MockEnv(path=tmp_path / "env")
    installer = WheelInstaller(env, link_mode="copy")
    installer.install(demo_wheel, content_hash="sha256:test_copy_no_store")

    purelib = Path(env.paths["purelib"])
    assert (purelib / "demo" / "__init__.py").exists()


def test_default_installation_uses_copy(env: MockEnv, demo_wheel: Path) -> None:
    installer = WheelInstaller(env)
    installer.install(demo_wheel)
    source_dir = Path(env.paths["purelib"]) / "demo"
    assert source_dir.exists()


def test_enable_bytecode_compilation_hardlink(
    tmp_path: Path, demo_wheel: Path
) -> None:
    env = MockEnv(path=tmp_path / "env")
    installer = WheelInstaller(env, link_mode="hardlink")
    installer.enable_bytecode_compilation(True)
    installer.install(demo_wheel, content_hash="sha256:test_bytecode")
    cache_dir = Path(env.paths["purelib"]) / "demo" / "__pycache__"
    assert cache_dir.exists()
    assert list(cache_dir.glob("*.pyc"))


@pytest.mark.parametrize("existing", [False, True])
def test_no_path_traversal_via_symlink(
    tmp_path: Path,
    env: MockEnv,
    wheel_with_path_traversal_via_symlink: Path,
    existing: bool,
) -> None:
    """see also test_extractall_wheel_no_path_traversal_via_symlink
    in test_helpers.py"""
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    target = target_dir / "traversal.txt"
    if existing:
        target.write_text("original", encoding="utf-8")

    installer = WheelInstaller(env)
    with pytest.raises(FileNotFoundError if WINDOWS else NotADirectoryError):
        installer.install(wheel_with_path_traversal_via_symlink)

    traversal_link = Path(env.paths["purelib"]) / "symlink" / "traversal_link"
    assert traversal_link.exists()
    assert not traversal_link.is_symlink()  # not even extracted as symlink
    assert target_dir.exists()
    if existing:
        assert target.read_text(encoding="utf-8") == "original"
    else:
        assert not list(target_dir.iterdir())
