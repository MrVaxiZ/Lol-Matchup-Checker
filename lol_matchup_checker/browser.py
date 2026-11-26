"""Makes sure the browser Scrapling drives is installed, downloading it on first use.

With pip, `scrapling install` does this. The .exe can't run that, so if the browser is missing
the app downloads it itself (one time, ~150 MB, into %LOCALAPPDATA%\\ms-playwright).
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

def default_browsers_dir() -> Path:
    """Where Playwright-style browsers normally live, shared with `scrapling install`."""
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "ms-playwright"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "ms-playwright"
    return Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "ms-playwright"


def use_shared_browser_folder() -> Path:
    """Inside the .exe, patchright would look for the browser in the app's temporary unpack folder
    (PLAYWRIGHT_BROWSERS_PATH=0), which a one-file exe deletes on exit: the browser would be
    downloaded again on every launch. Point it at the normal shared folder instead."""
    if "PLAYWRIGHT_BROWSERS_PATH" not in os.environ and getattr(sys, "frozen", False):
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(default_browsers_dir())
    path = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    return Path(path) if path and path != "0" else default_browsers_dir()


def _driver_command() -> list[str]:
    from patchright._impl._driver import compute_driver_executable

    driver = compute_driver_executable()
    return [str(part) for part in (driver if isinstance(driver, (tuple, list)) else (driver,))]


def _run_driver(args: list[str], **kwargs) -> subprocess.Popen:
    from patchright._impl._driver import get_driver_env

    use_shared_browser_folder()
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0  # no console window popping up
    return subprocess.Popen([*_driver_command(), *args], env=get_driver_env(), stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                            creationflags=flags, **kwargs)


def browser_installed() -> bool:
    """True if the exact Chromium build this version of patchright needs is downloaded."""
    proc = _run_driver(["install", "--dry-run", "chromium"])
    out, _ = proc.communicate(timeout=60)
    locations = re.findall(r"Install location:\s*(.+)", out)
    return bool(locations) and Path(locations[0].strip()).is_dir()


_ANSI = re.compile(r"\x1b\[[0-9;]*m")


MISSING_HINTS = ("Executable doesn't exist", "playwright install", "patchright install", "browserType.launch")


def looks_like_missing_browser(exc: BaseException) -> bool:
    text = str(exc)
    return any(hint in text for hint in MISSING_HINTS[:3]) or (
        MISSING_HINTS[3] in text and "doesn't exist" in text.lower()
    )


def install_browser(log: Callable[[str], None] = print) -> None:
    """Download Chromium for patchright (the browser library Scrapling's stealth mode uses)."""
    log("First run: downloading the browser this app uses (one time, about 150 MB). Please wait...")
    proc = _run_driver(["install", "chromium"])
    assert proc.stdout is not None
    last_error = ""
    for raw in proc.stdout:
        line = _ANSI.sub("", raw).strip()
        if not line or line.startswith("at "):  # skip blank lines and Node stack traces
            continue
        if line.startswith("Error"):
            last_error = line
        log(f"  {line}")
    if proc.wait() != 0:
        hint = f" ({last_error})" if last_error else ""
        raise RuntimeError(f"Downloading the browser failed{hint}. Check your internet connection and try again.")
    log("Browser installed.")
