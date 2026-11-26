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


def repo_url() -> str:
    """https://github.com/owner/repo of the 'origin' remote (works for https and ssh remotes)."""
    url = git("remote", "get-url", "origin")
    m = re.search(r"github\.com[:/](.+?)(?:\.git)?/?$", url)
    return f"https://github.com/{m.group(1)}" if m else url


def published(tag: str) -> bool:
    return bool(git("ls-remote", "--tags", "origin", f"refs/tags/{tag}"))


def main(argv: list[str]) -> int:
    current = current_version()
    raw = argv[0] if argv else input(
        f"Current version is {current}. New version (e.g. 2.1.0), or {current} again to finish an unpublished release: ")
    new = parse(raw)
    if new is None:
        print(f"'{raw}' isn't a version like 2.1.0")
        return 1
    version = ".".join(map(str, new))
    tag = f"v{version}"
    if git("status", "--porcelain"):
        print("You have uncommitted changes. Commit (or stash) them first, then run this again.")
        return 1

    if version == current:
        # The version was already bumped but the release never reached GitHub (e.g. the push failed):
        # tag the current commit (which may include fixes made since) and push.
        if published(tag):
            print(f"{tag} is already published. Use a higher version, e.g. {new[0]}.{new[1]}.{new[2] + 1}.")
            return 1
        if git("tag", "--list", tag):
            git("tag", "-d", tag)
        print(f"Finishing the unpublished release {tag}...")
    elif parse(current) and new < parse(current):
        print(f"{version} must be higher than the current {current}")
        return 1
    else:
        if git("tag", "--list", tag):
            print(f"Tag {tag} already exists.")
            return 1
        set_version(version)
        git("add", *(str(p.relative_to(ROOT)) for p in VERSION_FILES))
        git("commit", "-m", f"Release {tag}")

    git("tag", "-a", tag, "-m", f"LoL Matchup Checker {tag}")
    branch = git("rev-parse", "--abbrev-ref", "HEAD")
    print(f"Pushing {branch} and {tag}...")
    git("push", "--set-upstream", "origin", branch)  # works even if the branch was never linked to GitHub
    git("push", "origin", tag)
    url = repo_url()
    print("\nDone! GitHub is now building the exe and publishing the release (about 5 minutes):")
    print(f"  progress: {url}/actions")
    print(f"  release:  {url}/releases/tag/{tag}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except subprocess.CalledProcessError as exc:
        print(f"git failed: {' '.join(exc.cmd)}\n{exc.stderr or exc.stdout}")
        sys.exit(1)
