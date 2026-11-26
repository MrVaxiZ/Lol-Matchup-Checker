# PyInstaller build recipe for "LoL Matchup Checker.exe". Run build_exe.cmd (or:
#   python -m PyInstaller --noconfirm --clean packaging/LoLMatchupChecker.spec)
# Result: dist/LoL Matchup Checker.exe, a single file you can hand to anyone.
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files

ROOT = Path(SPECPATH).parent

datas, binaries, hiddenimports = [], [], []
# packages with data files / native parts / lazy imports PyInstaller can't see on its own
for package in ("patchright", "scrapling", "browserforge", "apify_fingerprint_datapoints", "curl_cffi", "tld"):
    d, b, h = collect_all(package)
    datas += d
    binaries += b
    hiddenimports += h
datas += collect_data_files("lol_matchup_checker")  # window icon
hiddenimports += ["lol_matchup_checker.gui", "lol_matchup_checker.cli", "lol_matchup_checker.counters"]

a = Analysis(
    [str(ROOT / "packaging" / "app_entry.py")],
    pathex=[str(ROOT)],
    datas=datas,
    binaries=binaries,
    hiddenimports=hiddenimports,
    # Scrapling's optional IPython shell and AI tools aren't used by this app.
    excludes=["IPython", "mcp", "markdownify", "pytest", "matplotlib", "numpy", "pandas"],
    noarchive=False,
)
# Scrapling 0.4.x imports `playwright` (for type names); the browser itself is always started through
# patchright. Keep playwright's Python code but drop its ~130 MB Node driver, which is never run.
def _not_playwright_driver(entry):
    dest = entry[0].replace("\\", "/")
    return not dest.startswith("playwright/driver/")

a.datas = [e for e in a.datas if _not_playwright_driver(e)]
a.binaries = [e for e in a.binaries if _not_playwright_driver(e)]
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="LoL Matchup Checker",
    icon=str(ROOT / "packaging" / "icon.ico"),
    console=False,  # GUI app: no black console window
    upx=False,  # UPX-packed exes trigger far more antivirus false positives
    runtime_tmpdir=None,
)
