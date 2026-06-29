"""
Benchmark: installing poetry + all lockfile deps into two venvs
using copy mode vs hardlink mode, measuring time and disk usage.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import time
from pathlib import Path

import tomlkit

from poetry.installation.wheel_installer import WheelInstaller
from poetry.utils.env import VirtualEnv
from poetry.utils.env.env_manager import EnvManager
from poetry.utils.filesystem import LinkMode


PROJECT_DIR = Path(__file__).resolve().parent


def build_project_wheel(tmp_dir: Path) -> Path:
    subprocess.run(
        [sys.executable, "-m", "poetry", "build", "-q"],
        check=True,
        cwd=PROJECT_DIR,
    )
    dist = PROJECT_DIR / "dist"
    wheels = sorted(dist.glob("*.whl"))
    if not wheels:
        raise RuntimeError("no wheel built")
    wheel = wheels[-1]
    dest_dir = tmp_dir / "wheels"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / wheel.name
    shutil.copy2(wheel, dest)
    return dest


def download_dep_wheels(tmp_dir: Path) -> list[Path]:
    dest = tmp_dir / "wheels"
    dest.mkdir(parents=True, exist_ok=True)

    with open(PROJECT_DIR / "poetry.lock") as f:
        lock = tomlkit.parse(f.read())

    # Write exact-pinned requirements
    reqs = tmp_dir / "requirements.txt"
    with open(reqs, "w") as f:
        for pkg in lock.get("package", []):
            name = pkg["name"]
            version = pkg["version"]
            f.write(f"{name}=={version}\n")

    subprocess.run(
        ["pip", "download", "-r", str(reqs), "-d", str(dest)],
        check=True,
    )
    return sorted(dest.glob("*.whl"))


def disk_usage(paths: list[Path]) -> int:
    """Count actual disk blocks used by unique inodes across *paths*."""
    args = ["find"] + [str(p) for p in paths] + ["-type", "f", "-printf", "%D:%i %b\\n"]
    r = subprocess.run(args, capture_output=True, text=True, check=True)
    blocks = set()
    for line in r.stdout.strip().split("\n"):
        if not line.strip():
            continue
        inode, blk = line.strip().split()
        blocks.add((inode, int(blk)))
    return sum(b for _, b in blocks) * 512


def install_all(
    wheels: list[Path],
    venv_path: Path,
    mode: LinkMode,
    label: str,
) -> float:
    if venv_path.exists():
        shutil.rmtree(venv_path)
    EnvManager.build_venv(venv_path)

    venv = VirtualEnv(venv_path)
    installer = WheelInstaller(venv, link_mode=mode)

    start = time.perf_counter()
    for i, wheel in enumerate(wheels, 1):
        print(f"    [{i}/{len(wheels)}] {wheel.name}", end="\r")
        h = hashlib.sha256(wheel.read_bytes()).hexdigest()
        installer.install(wheel, content_hash=f"sha256:{h}")
    elapsed = time.perf_counter() - start
    print(f"  {label:<35s} {elapsed:.3f}s")
    return elapsed


def main() -> None:
    tmp = Path("/tmp/benchmark_poetry")
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)

    # Store path is derived from venv location: venv/../../cache
    # Put venv under tmp/src/ so ../../ resolves to tmp/
    work = tmp / "w"
    work.mkdir()

    print("Building poetry wheel...")
    project_wheel = build_project_wheel(tmp)
    print(f"  {project_wheel.name} ({project_wheel.stat().st_size / 1024:.0f} KB)")

    print("Downloading dependency wheels from lockfile...")
    dep_wheels = download_dep_wheels(tmp)
    all_wheels = list({w.name: w for w in [project_wheel] + dep_wheels}.values())
    print(f"  {len(all_wheels)} unique wheels ({sum(w.stat().st_size for w in all_wheels) / 1024:.0f} KB)\n")

    copy_venv = work / "copy_venv"
    link_venv = work / "link_venv"

    print("--- Copy mode ---")
    install_all(all_wheels, copy_venv, LinkMode.COPY, "cold (copy)")
    install_all(all_wheels, copy_venv, LinkMode.COPY, "warm (copy)")

    print("\n--- Hardlink mode ---")
    install_all(all_wheels, link_venv, LinkMode.HARDLINK, "cold (hardlink, store miss)")
    install_all(all_wheels, link_venv, LinkMode.HARDLINK, "warm (hardlink, store hit)")

    # Second venv to show shared store benefit
    link_venv2 = work / "link_venv2"
    print("\n--- Hardlink mode, second venv (shared store) ---")
    install_all(all_wheels, link_venv2, LinkMode.HARDLINK, "hardlink, 2nd venv (store hit)")

    # Disk usage (actual blocks, counting unique inodes once)
    store_path = tmp / "cache" / "unpacked"
    copy_actual = disk_usage([copy_venv])
    store_actual = disk_usage([store_path])
    hardlink_total = disk_usage([store_path, link_venv, link_venv2])

    two_copy = 2 * copy_actual

    print(f"""
{'─' * 62}
  {'Disk usage (actual blocks)':<35s} {'Size':>10s}
{'─' * 62}
  {'Copy venv (one env)':<35s} {copy_actual / 1024:>10.0f} KB
  {'Wheel store':<35s} {store_actual / 1024:>10.0f} KB
  {'Store + 2 hardlink venvs':<35s} {hardlink_total / 1024:>10.0f} KB
  {'Store overhead (RECORD, scripts, etc)':<35s} {(hardlink_total - store_actual) / 1024:>10.0f} KB
{'─' * 62}
  {'Copy: 2 envs (estimated)':<35s} {two_copy / 1024:>10.0f} KB
  {'Hardlink: 2 envs + store (actual)':<35s} {hardlink_total / 1024:>10.0f} KB
  {'Saved with hardlinks':<35s} {(two_copy - hardlink_total) / 1024:>10.0f} KB
  {'Savings ratio':<35s} {(1 - hardlink_total / two_copy) * 100:>9.1f}%
{'─' * 62}""")


if __name__ == "__main__":
    main()
