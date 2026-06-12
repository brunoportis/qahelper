"""Open the GNOME Shell screenshot UI on X11 and import its result."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path


def pictures_directory() -> Path:
    try:
        result = subprocess.run(
            ["xdg-user-dir", "PICTURES"],
            check=True,
            capture_output=True,
            text=True,
        )
        directory = Path(result.stdout.strip()).expanduser()
        if directory.is_dir():
            return directory
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass
    return Path.home() / "Pictures"


def png_snapshot(root: Path) -> dict[Path, tuple[int, int]]:
    if not root.is_dir():
        return {}
    snapshot: dict[Path, tuple[int, int]] = {}
    for path in root.rglob("*.png"):
        try:
            stat = path.stat()
        except OSError:
            continue
        snapshot[path] = (stat.st_mtime_ns, stat.st_size)
    return snapshot


def wait_for_screenshot(
    root: Path,
    before: dict[Path, tuple[int, int]],
    timeout_seconds: float = 120,
) -> Path:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        current = png_snapshot(root)
        changed = [
            path
            for path, metadata in current.items()
            if before.get(path) != metadata
        ]
        if changed:
            return max(changed, key=lambda path: current[path][0])
        time.sleep(0.2)
    raise RuntimeError("Nenhuma captura foi criada pela interface do GNOME.")


def capture(destination: Path, delay: float = 0) -> None:
    pictures = pictures_directory()
    before = png_snapshot(pictures)
    if delay:
        print(f"Captura em {delay:g} segundos...", flush=True)
        time.sleep(delay)

    subprocess.run(["xdotool", "key", "Print"], check=True)
    source = wait_for_screenshot(pictures, before)
    shutil.copyfile(source, destination)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("destination", type=Path)
    parser.add_argument("--delay", type=float, default=0)
    args = parser.parse_args()
    try:
        capture(args.destination, args.delay)
    except Exception as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
