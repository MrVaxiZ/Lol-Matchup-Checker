"""Entry point for the packaged app (PyInstaller needs a script, not `-m`).

`"LoL Matchup Checker.exe" --selftest` checks that everything needed was bundled, then exits.
"""

import sys


def selftest() -> int:
    import os
    from pathlib import Path

    # same as the GUI: a windowed .exe has no console, so print into a file next to the exe
    log_path = Path(sys.executable).with_name("selftest.txt") if getattr(sys, "frozen", False) else None
    out = open(log_path, "w", encoding="utf-8") if log_path else sys.stdout  # noqa: SIM115
    ok = True

    def check(label, fn):
        nonlocal ok
        try:
            detail = fn()
            print(f"OK    {label}" + (f": {detail}" if detail else ""), file=out)
        except Exception as exc:
            ok = False
            print(f"FAIL  {label}: {type(exc).__name__}: {exc}", file=out)

    check("gui", lambda: __import__("lol_matchup_checker.gui", fromlist=["App"]) and None)
    check("scraper + scrapling stealth session",
          lambda: __import__("lol_matchup_checker.scraper", fromlist=["UggScraper"]).AsyncStealthySession.__name__)
    check("excel (openpyxl)", lambda: __import__("openpyxl").__version__)
    check("icons (Pillow)", lambda: __import__("PIL").__version__)

    def driver():
        from patchright._impl._driver import compute_driver_executable
        parts = compute_driver_executable()
        parts = parts if isinstance(parts, (tuple, list)) else (parts,)
        missing = [str(p) for p in parts if not Path(p).exists()]
        if missing:
            raise FileNotFoundError(", ".join(missing))
        return "found"

    check("browser driver bundled", driver)
    def browsers():
        from lol_matchup_checker.browser import browser_installed, use_shared_browser_folder
        folder = use_shared_browser_folder()
        state = "installed" if browser_installed() else "not installed yet, downloads on first START"
        return f"{folder} ({state})"

    check("browser folder", browsers)
    check("window icon", lambda: __import__("lol_matchup_checker.gui", fromlist=["asset"]).asset("icon.png").exists() or 1 / 0)
    url = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--selftest-browser=")), None)
    if url:  # optional: actually start the browser and load a page (downloads the browser if missing)
        def load_page():
            import asyncio
            from lol_matchup_checker.scraper import ScraperOptions, UggScraper

            async def go():
                async with UggScraper(ScraperOptions(workers=1, timeout_s=60), log=lambda m: print(m, file=out)) as s:
                    page = await s._session.fetch(url, timeout=60_000)
                    return f"status {page.status}, title {page.css('title::text').get()!r}"
            return asyncio.run(go())
        check("browser loads a page", load_page)
    print("ALL OK" if ok else "SOME CHECKS FAILED", file=out)
    if log_path:
        out.close()
    return 0 if ok else 1


if __name__ == "__main__":
    from lol_matchup_checker.browser import use_shared_browser_folder

    use_shared_browser_folder()  # before anything starts the browser library
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    from lol_matchup_checker.gui import main

    sys.exit(main())
