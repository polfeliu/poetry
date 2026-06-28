from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from poetry.installation.unpacked_wheel_store import UnpackedWheelStore
from poetry.installation.wheel_installer import WheelInstaller
from poetry.utils.env import VirtualEnv


if TYPE_CHECKING:
    from tests.types import FixtureDirGetter


pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def demo_wheel(fixture_dir: FixtureDirGetter) -> Path:
    return fixture_dir("distributions/demo-0.1.0-py2.py3-none-any.whl")


def test_hardlink_install_into_real_venv(
    tmp_venv: VirtualEnv, demo_wheel: Path
) -> None:
    installer = WheelInstaller(tmp_venv, link_mode="hardlink")
    installer.install(demo_wheel, content_hash="sha256:test_real_venv")

    purelib = Path(tmp_venv.paths["purelib"])
    assert (purelib / "demo" / "__init__.py").exists()
    assert (purelib / "demo-0.1.0.dist-info" / "METADATA").exists()

    store = UnpackedWheelStore(
        tmp_venv.path / ".." / ".." / "cache"
    ).get_store_path("sha256:test_real_venv")
    assert store.exists()


def test_hardlink_shared_store_two_venvs(
    tmp_path: Path, demo_wheel: Path
) -> None:
    from poetry.utils.env.env_manager import EnvManager

    import shutil

    venv_a_path = tmp_path / "venv_a"
    venv_b_path = tmp_path / "venv_b"
    EnvManager.build_venv(venv_a_path)
    EnvManager.build_venv(venv_b_path)
    venv_a = VirtualEnv(venv_a_path)
    venv_b = VirtualEnv(venv_b_path)

    content_hash = "sha256:test_shared_store_integration"
    cache_dir = tmp_path / "cache"
    installer_a = WheelInstaller(
        venv_a, link_mode="hardlink", store_base_path=cache_dir
    )
    installer_b = WheelInstaller(
        venv_b, link_mode="hardlink", store_base_path=cache_dir
    )
    installer_a.install(demo_wheel, content_hash=content_hash)
    installer_b.install(demo_wheel, content_hash=content_hash)

    store = UnpackedWheelStore(cache_dir)
    entry = store.get_store_path(content_hash)
    assert entry.exists()
    hardlinked = [
        f for f in entry.rglob("*") if f.is_file() and f.suffix == ".py"
    ]
    assert len(hardlinked) > 0
    for f in hardlinked:
        assert f.stat().st_nlink > 1, f"Not hardlinked: {f}"

    shutil.rmtree(venv_a_path)
    shutil.rmtree(venv_b_path)


def test_hardlink_content_hash_isolation(
    tmp_path: Path, demo_wheel: Path
) -> None:
    from poetry.utils.env.env_manager import EnvManager

    venv_path = tmp_path / "venv"
    EnvManager.build_venv(venv_path)
    venv = VirtualEnv(venv_path)

    hash_a = "sha256:" + "a" * 64
    hash_b = "sha256:" + "b" * 64

    cache_dir = tmp_path / "cache"
    installer = WheelInstaller(venv, link_mode="hardlink", store_base_path=cache_dir)
    installer.install(demo_wheel, content_hash=hash_a)
    installer.install(demo_wheel, content_hash=hash_b)

    store = UnpackedWheelStore(cache_dir)
    assert store.get_store_path(hash_a).exists()
    assert store.get_store_path(hash_b).exists()
    assert store.get_store_path(hash_a) != store.get_store_path(hash_b)


def test_prune_unreferenced_store_entry(
    tmp_path: Path, demo_wheel: Path
) -> None:
    from poetry.utils.env.env_manager import EnvManager

    import shutil

    venv_path = tmp_path / "venv"
    EnvManager.build_venv(venv_path)
    venv = VirtualEnv(venv_path)

    content_hash = "sha256:test_prune_me"
    cache_dir = tmp_path / "cache"
    installer = WheelInstaller(
        venv, link_mode="hardlink", store_base_path=cache_dir
    )
    installer.install(demo_wheel, content_hash=content_hash)

    store = UnpackedWheelStore(cache_dir)
    entry = store.get_store_path(content_hash)
    assert entry.exists()

    shutil.rmtree(venv_path)

    pruned = list(store.prune_unreferenced())
    assert len(pruned) == 1
    assert not entry.exists()


def test_prune_referenced_entry_kept(
    tmp_path: Path, demo_wheel: Path
) -> None:
    from poetry.utils.env.env_manager import EnvManager

    venv_path = tmp_path / "venv"
    EnvManager.build_venv(venv_path)
    venv = VirtualEnv(venv_path)

    content_hash = "sha256:test_keep_me"
    cache_dir = tmp_path / "cache"
    installer = WheelInstaller(
        venv, link_mode="hardlink", store_base_path=cache_dir
    )
    installer.install(demo_wheel, content_hash=content_hash)

    store = UnpackedWheelStore(cache_dir)
    entry = store.get_store_path(content_hash)
    assert entry.exists()

    pruned = list(store.prune_unreferenced())
    assert len(pruned) == 0
    assert entry.exists()


def test_installed_package_importable(
    tmp_venv: VirtualEnv, demo_wheel: Path
) -> None:
    installer = WheelInstaller(tmp_venv, link_mode="hardlink")
    installer.install(demo_wheel, content_hash="sha256:test_import")

    output = tmp_venv.run_python_script(
        "import demo; print(demo.__file__, end='')"
    )
    assert output
    purelib = Path(tmp_venv.paths["purelib"])
    assert str(purelib) in output


def test_bytecode_compilation_in_hardlink_mode(
    tmp_venv: VirtualEnv, demo_wheel: Path
) -> None:
    installer = WheelInstaller(tmp_venv, link_mode="hardlink")
    installer.enable_bytecode_compilation(True)
    installer.install(demo_wheel, content_hash="sha256:test_bytecode")

    purelib = Path(tmp_venv.paths["purelib"])
    pycache = purelib / "demo" / "__pycache__"
    assert pycache.exists()
    pyc_files = list(pycache.glob("*.pyc"))
    assert len(pyc_files) > 0


def test_copy_mode_in_real_venv_no_store(
    tmp_venv: VirtualEnv, demo_wheel: Path
) -> None:
    installer = WheelInstaller(tmp_venv, link_mode="copy")
    installer.install(demo_wheel, content_hash="sha256:test_copy")

    purelib = Path(tmp_venv.paths["purelib"])
    assert (purelib / "demo" / "__init__.py").exists()

    purelib_py_files = list((purelib / "demo").rglob("*.py"))
    assert len(purelib_py_files) > 0


def test_hardlink_links_from_store_to_venv(
    tmp_venv: VirtualEnv, demo_wheel: Path
) -> None:
    content_hash = "sha256:test_hardlink_same_inode"
    installer = WheelInstaller(tmp_venv, link_mode="hardlink")
    installer.install(demo_wheel, content_hash=content_hash)

    purelib = Path(tmp_venv.paths["purelib"])
    init_py = purelib / "demo" / "__init__.py"
    assert init_py.exists()

    cache_base = tmp_venv.path / ".." / ".." / "cache"
    store_init = (
        UnpackedWheelStore(cache_base).get_store_path(content_hash)
        / "demo"
        / "__init__.py"
    )
    assert store_init.exists()
    assert store_init.stat().st_ino == init_py.stat().st_ino
