"""Publish a new version: bump the version number, commit, tag and push.

    python packaging/release.py 2.1.0      (or double-click release.cmd)

Pushing the tag starts GitHub Actions (.github/workflows/build-exe.yml), which builds the .exe,
writes the release notes and publishes the release. Nothing else to do.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO_URL = "https://github.com/MrVaxiZ/Lol-Matchup-Checker"
VERSION_FILES = {
    ROOT / "pyproject.toml": r'(?m)^version = "([^"]*)"',
    ROOT / "lol_matchup_checker" / "__init__.py": r'(?m)^__version__ = "([^"]*)"',
}


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, text=True, capture_output=True).stdout.strip()


def parse(version: str) -> tuple[int, int, int] | None:
    m = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", version.strip())
    return tuple(int(x) for x in m.groups()) if m else None


def current_version() -> str:
    path, pattern = next(iter(VERSION_FILES.items()))
    return re.search(pattern, path.read_text(encoding="utf-8")).group(1)


def set_version(version: str) -> None:
    for path, pattern in VERSION_FILES.items():
        text = path.read_text(encoding="utf-8")
        start, end = re.search(pattern, text).span(1)
        path.write_text(text[:start] + version + text[end:], encoding="utf-8")


def main(argv: list[str]) -> int:
    current = current_version()
    raw = argv[0] if argv else input(f"Current version is {current}. New version (e.g. 2.1.0): ")
    new = parse(raw)
    if new is None:
        print(f"'{raw}' isn't a version like 2.1.0")
        return 1
    version = ".".join(map(str, new))
    if parse(current) and new <= parse(current):
        print(f"{version} must be higher than the current {current}")
        return 1
    if git("status", "--porcelain"):
        print("You have uncommitted changes. Commit (or stash) them first, then run this again.")
        return 1
    if git("tag", "--list", f"v{version}"):
        print(f"Tag v{version} already exists.")
        return 1

    set_version(version)
    git("add", *(str(p.relative_to(ROOT)) for p in VERSION_FILES))
    git("commit", "-m", f"Release v{version}")
    git("tag", "-a", f"v{version}", "-m", f"LoL Matchup Checker v{version}")
    print(f"Pushing v{version}...")
    git("push")
    git("push", "origin", f"v{version}")
    print(f"\nDone! GitHub is now building the exe and publishing the release (about 5 minutes):")
    print(f"  progress: {REPO_URL}/actions")
    print(f"  release:  {REPO_URL}/releases/tag/v{version}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except subprocess.CalledProcessError as exc:
        print(f"git failed: {' '.join(exc.cmd)}\n{exc.stderr or exc.stdout}")
        sys.exit(1)
