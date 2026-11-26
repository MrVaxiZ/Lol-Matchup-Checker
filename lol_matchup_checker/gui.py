"""Desktop GUI for the matchup checker and the counter finder.

    python -m lol_matchup_checker.gui        (or double-click gui.cmd)

Home screen: pick "Find counters" or "Matchup sheet". Then pick a lane and click champion
icons (Riot's Data Dragon icons, cached on disk), press START, watch the log in the built-in
terminal, and get the results as a colour-coded table. The scraping is the exact same code as
the command line tools; it runs in a background thread so the window stays responsive.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import io
import json
import os
import queue
import re
import sys
import threading
import time
import traceback
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

from .data import champion_slug
from .excel import RATING_STYLES

# ------------------------------------------------------------------ look & feel

C = {
    "bg": "#0e1318",
    "panel": "#151c23",
    "card": "#1c252e",
    "hover": "#26323d",
    "line": "#2b3641",
    "gold": "#c8aa6e",
    "gold_dim": "#7a6a48",
    "teal": "#0ac8b9",
    "text": "#e8e6e3",
    "muted": "#8a96a3",
    "term_bg": "#090c0f",
    "term_fg": "#c9d1d9",
    "red": "#ff6b6b",
    "yellow": "#f2cc60",
    "green": "#56d364",
}
LANES = [("top", "TOP"), ("jg", "JUNGLE"), ("mid", "MID"), ("adc", "ADC"), ("sup", "SUPPORT")]
DDRAGON = "https://ddragon.leagueoflegends.com"

SUPPORT_URL = "https://buymeacoffee.com/vaxiz"


def _cache_dir() -> Path:
    from .cache import app_data_dir
    return app_data_dir()


def _get(url: str, timeout: float = 15.0) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "lol-matchup-checker"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (fixed https host)
        return resp.read()


class Settings:
    """Small JSON file with the user's remembered picks and options."""

    def __init__(self, path: Path | None = None):
        self.path = path or (_cache_dir() / "settings.json")
        try:
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(self.data, dict):
                self.data = {}
        except (OSError, ValueError):
            self.data = {}

    @property
    def remember(self) -> bool:
        return bool(self.data.get("remember", False))

    def save(self, remember: bool, picks: dict | None = None, options: dict | None = None) -> None:
        self.data = {"remember": remember}
        if remember:
            self.data["picks"] = picks or {}
            self.data["options"] = options or {}
        try:
            self.path.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass


def is_frozen() -> bool:
    """True when running as the packaged .exe (PyInstaller)."""
    return bool(getattr(sys, "frozen", False))


def output_dir() -> Path:
    """Where Excel files go: Documents\\LoL Matchup Checker for the .exe, the current folder otherwise."""
    if is_frozen():
        docs = Path.home() / "Documents"
        path = (docs if docs.is_dir() else Path.home()) / "LoL Matchup Checker"
        path.mkdir(parents=True, exist_ok=True)
        return path
    return Path.cwd()


def asset(name: str) -> Path:
    return Path(__file__).resolve().parent / "assets" / name


# ------------------------------------------------------------------ champion icons

class ChampionCatalog:
    """Champion names + icon bytes from Riot's Data Dragon, cached under %LOCALAPPDATA%.
    Works offline from the cache once it has run with internet once."""

    def __init__(self, events: queue.Queue):
        self.events = events
        self.cache = _cache_dir()
        self.version: str | None = None
        self.champions: list[dict] = []  # {"id": "MonkeyKing", "name": "Wukong"}, sorted by name

    def start(self) -> None:
        threading.Thread(target=self._load, daemon=True).start()

    def _load(self) -> None:
        try:
            try:
                self.version = json.loads(_get(f"{DDRAGON}/api/versions.json"))[0]
                path = self.cache / f"champions_{self.version}.json"
                if not path.exists():
                    path.write_bytes(_get(f"{DDRAGON}/cdn/{self.version}/data/en_US/champion.json"))
            except Exception:
                cached = sorted(self.cache.glob("champions_*.json"), key=lambda p: p.stat().st_mtime)
                if not cached:
                    raise
                path = cached[-1]
                self.version = path.stem.split("_", 1)[1]
            data = json.loads(path.read_text(encoding="utf-8"))["data"]
            self.champions = sorted(({"id": c["id"], "name": c["name"]} for c in data.values()),
                                    key=lambda c: c["name"].lower())
        except Exception as exc:
            self.events.put(("catalog_error", f"Couldn't load the champion list from Riot ({exc})."))
            return
        self.events.put(("catalog", self.champions))

        icon_dir = self.cache / "icons"
        icon_dir.mkdir(exist_ok=True)

        def fetch(champ: dict) -> None:
            path = icon_dir / f"{champ['id']}.png"
            try:
                if not path.exists():
                    path.write_bytes(_get(f"{DDRAGON}/cdn/{self.version}/img/champion/{champ['id']}.png"))
                self.events.put(("icon", champ["name"], path.read_bytes()))
            except Exception:
                pass  # tile keeps its text placeholder

        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(fetch, self.champions))


class IconStore:
    """PhotoImages per (champion slug, size). Must be used from the Tk thread."""

    def __init__(self):
        self.raw: dict[str, bytes] = {}
        self.images: dict[tuple[str, int], tk.PhotoImage] = {}
        try:
            from PIL import Image, ImageTk  # noqa: F401
            self.pil = True
        except ImportError:
            self.pil = False

    def add(self, name: str, data: bytes) -> None:
        self.raw[champion_slug(name)] = data

    def get(self, name: str, size: int, grey: bool = False) -> tk.PhotoImage | None:
        """Icon at `size` px; `grey=True` gives a dimmed black & white version (needs Pillow)."""
        slug = champion_slug(name)
        key = (slug, size, grey)
        if key in self.images:
            return self.images[key]
        data = self.raw.get(slug)
        if data is None:
            return None
        try:
            if self.pil:
                from PIL import Image, ImageTk
                img = Image.open(io.BytesIO(data)).convert("RGBA")
                # Riot icons have a thin dark border; crop it off for a cleaner look
                w, h = img.size
                img = img.crop((w // 20, h // 20, w - w // 20, h - h // 20)).resize((size, size), Image.LANCZOS)
                if grey:
                    from PIL import ImageEnhance, ImageOps
                    img = ImageEnhance.Brightness(ImageOps.grayscale(img).convert("RGBA")).enhance(0.35)
                photo = ImageTk.PhotoImage(img)
            else:
                if grey:
                    return self.get(name, size)  # no Pillow: no greyscale, keep the colour icon
                photo = tk.PhotoImage(data=base64.b64encode(data))
                photo = photo.subsample(max(1, round(photo.width() / size)))
        except Exception:
            return None
        self.images[key] = photo
        return photo


# ------------------------------------------------------------------ small widgets

class ScrollFrame(tk.Frame):
    """A vertically scrollable frame; put children in `.inner`."""

    def __init__(self, master, bg: str, **kw):
        super().__init__(master, bg=bg, **kw)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self.bar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = tk.Frame(self.canvas, bg=bg)
        self._win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.bar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.bar.pack(side="right", fill="y")
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self._win, width=e.width))
        self.bind("<Enter>", lambda e: self._wheel(True))
        self.bind("<Leave>", lambda e: self._wheel(False))

    def _wheel(self, on: bool) -> None:
        if on:
            self.bind_all("<MouseWheel>", self._on_wheel)
            self.bind_all("<Button-4>", lambda e: self.canvas.yview_scroll(-3, "units"))
            self.bind_all("<Button-5>", lambda e: self.canvas.yview_scroll(3, "units"))
        else:
            self.unbind_all("<MouseWheel>")
            self.unbind_all("<Button-4>")
            self.unbind_all("<Button-5>")

    def _on_wheel(self, event) -> None:
        if self.canvas.yview() != (0.0, 1.0):
            self.canvas.yview_scroll(int(-event.delta / 40) or (-1 if event.delta > 0 else 1), "units")

    def to_top(self) -> None:
        self.canvas.yview_moveto(0)


class FlatButton(tk.Label):
    """Label that behaves like a flat button (tk.Button ignores colours on macOS and looks dated on Windows)."""

    def __init__(self, master, text, command, *, bg=None, fg=None, hover=None, font=None, padx=14, pady=7, **kw):
        self._bg = bg or C["card"]
        self._fg = fg or C["text"]
        self._hover = hover or C["hover"]
        self._command = command
        self._enabled = True
        super().__init__(master, text=text, bg=self._bg, fg=self._fg, font=font, padx=padx, pady=pady,
                         cursor="hand2", **kw)
        self.bind("<Enter>", lambda e: self._enabled and super(FlatButton, self).configure(bg=self._hover))
        self.bind("<Leave>", lambda e: super(FlatButton, self).configure(bg=self._bg))
        self.bind("<Button-1>", lambda e: self._enabled and self._command and self._command())

    def set_colors(self, bg, fg=None, hover=None) -> None:
        self._bg, self._fg = bg, fg or self._fg
        self._hover = hover or self._hover
        self.configure(bg=self._bg, fg=self._fg)

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        self.configure(fg=self._fg if enabled else C["muted"], cursor="hand2" if enabled else "arrow")


class QueueWriter(io.TextIOBase):
    """stdout replacement for the worker thread: forwards whole lines to the GUI."""

    def __init__(self, events: queue.Queue):
        self.events = events
        self.buf = ""

    def write(self, text: str) -> int:
        self.buf += text
        while "\n" in self.buf:
            line, self.buf = self.buf.split("\n", 1)
            self.events.put(("log", line))
        return len(text)

    def flush(self) -> None:
        if self.buf:
            self.events.put(("log", self.buf))
            self.buf = ""


# ------------------------------------------------------------------ sounds

# (frequency Hz, start s) per note; soft bell-like tones
_CHIMES = {
    "done": [(1046.50, 0.00), (1318.51, 0.11), (1567.98, 0.22)],  # C6 E6 G6, rising: finished
    "error": [(659.25, 0.00), (523.25, 0.16)],                    # E5 C5, falling: finished with errors
}


def make_chime(kind: str = "done", rate: int = 44100) -> bytes:
    """A short, quiet chime as WAV bytes (16-bit mono), synthesised so no sound file is needed."""
    import math
    import struct
    import wave

    notes = _CHIMES[kind]
    length = notes[-1][1] + 1.1
    samples = [0.0] * int(length * rate)
    for freq, start in notes:
        first = int(start * rate)
        for i in range(int(1.1 * rate)):
            t = i / rate
            env = min(1.0, t / 0.006) * math.exp(-t * 4.2)  # quick soft attack, bell-like decay
            # fundamental + a little octave and fifth for warmth
            v = (math.sin(2 * math.pi * freq * t) + 0.25 * math.sin(4 * math.pi * freq * t) * math.exp(-t * 6)
                 + 0.08 * math.sin(6 * math.pi * freq * t) * math.exp(-t * 9))
            if first + i < len(samples):
                samples[first + i] += env * v
    peak = max(abs(x) for x in samples) or 1.0
    volume = 0.32  # well below full scale: pleasant, not startling
    fade = int(0.05 * rate)
    for i in range(fade):  # no click at the very end
        samples[-1 - i] *= i / fade
    frames = struct.pack(f"<{len(samples)}h", *(int(x / peak * volume * 32767) for x in samples))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(frames)
    return buf.getvalue()


def play_chime(kind: str = "done", fallback=None) -> None:
    """Play the chime without blocking the window. `fallback` (e.g. root.bell) is used if nothing else works."""
    try:
        path = _cache_dir() / f"chime_{kind}.wav"
        if not path.exists():
            path.write_bytes(make_chime(kind))
        if sys.platform == "win32":
            import winsound
            winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
            return
        import shutil
        import subprocess
        for player in (["afplay"], ["paplay"], ["aplay", "-q"]):
            if shutil.which(player[0]):
                subprocess.Popen([*player, str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return
    except Exception:
        pass
    if fallback:
        fallback()


# ------------------------------------------------------------------ time estimate

def fmt_duration(seconds: float) -> str:
    seconds = int(round(max(0.0, seconds)))
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    if h:
        return f"{h}h {m:02}m"
    if m:
        return f"{m}m {s:02}s"
    return f"{s}s"


class EtaTracker:
    """Estimates time left from the "[done/total]" progress lines.

    A run has one scraping phase per counters target (one in total for a matchup sheet);
    phases still to come are assumed to take as long as the current one.
    """

    def __init__(self, phases: int = 1, clock=time.monotonic):
        self.clock = clock
        self.started = clock()
        self.phases = max(1, phases)
        self.phase = 0
        self.phase_started: float | None = None
        self.done = self.total = 0
        self.eta_at: float | None = None

    def new_phase(self) -> None:
        self.phase = min(self.phase + 1, self.phases)
        self.phase_started = self.clock()
        self.done = self.total = 0
        self.eta_at = None

    def progress(self, done: int, total: int) -> None:
        if self.phase_started is None:
            self.new_phase()
        now = self.clock()
        self.done, self.total = done, total
        if done >= min(3, total) and total:  # a few pages in, so the rate means something
            per_page = (now - self.phase_started) / done
            later_phases = (self.phases - self.phase) * total * per_page
            self.eta_at = now + per_page * (total - done) + later_phases

    def remaining(self) -> float | None:
        return None if self.eta_at is None else max(0.0, self.eta_at - self.clock())

    def elapsed(self) -> float:
        return self.clock() - self.started


# ------------------------------------------------------------------ background job

class Job:
    """Runs `lol-matchup gen` / `lol-counters` (same code) in a thread with its own event loop."""

    def __init__(self, mode: str, argv: list[str], events: queue.Queue):
        self.mode, self.argv, self.events = mode, argv, events
        self.loop: asyncio.AbstractEventLoop | None = None
        self.task: asyncio.Task | None = None
        self.stopping = False

    def start(self) -> None:
        threading.Thread(target=self._thread, daemon=True).start()

    def stop(self) -> None:
        self.stopping = True
        if self.loop and self.task:
            self.loop.call_soon_threadsafe(self.task.cancel)

    def _thread(self) -> None:
        writer = QueueWriter(self.events)
        collect: dict = {}
        code = 1
        with contextlib.redirect_stdout(writer), contextlib.redirect_stderr(writer):
            try:
                code = asyncio.run(self._main(collect))
            except Exception:
                print(traceback.format_exc())
            writer.flush()
        self.events.put(("done", code, collect, self.stopping))

    async def _main(self, collect: dict) -> int:
        from . import cli, counters
        from .scraper import ScrapeError

        self.loop = asyncio.get_running_loop()
        self.task = asyncio.current_task()
        try:
            if self.mode == "counters":
                args = counters.build_parser().parse_args(self.argv)
                return await counters.run(args, collect)
            args = cli.build_parser().parse_args(["gen", *self.argv])
            return await cli.cmd_gen(args, collect)
        except asyncio.CancelledError:
            print("Stopped.")
            return 130
        except ScrapeError as exc:
            print(f"ERROR: {exc}")
        except PermissionError as exc:
            print(f"ERROR: couldn't write {exc.filename!r}. Is it open in Excel? Close it and press START again.")
        except SystemExit:  # argparse rejected something
            print("ERROR: invalid options.")
        return 1


# ------------------------------------------------------------------ the app

class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.events: queue.Queue = queue.Queue()
        self.icons = IconStore()
        self.catalog = ChampionCatalog(self.events)
        self.champions: list[dict] = []
        self.catalog_error: str | None = None
        self.job: Job | None = None
        self.mode = "counters"
        # each screen keeps its own picks: counters targets vs. the champions you play
        self.sel_by_mode: dict[str, list[str]] = {"counters": [], "matchups": []}
        self.lane_by_mode: dict[str, str | None] = {"counters": "auto", "matchups": None}
        self.selected: list[str] = self.sel_by_mode["counters"]
        self.lane: str | None = "auto"
        self.rating_filter: str | None = None
        self.running = False
        self.filter_painters: list = []
        self.settings = Settings()
        self.remember = tk.BooleanVar(value=self.settings.remember)
        self.opt_vars = {
            "patch": tk.StringVar(value=""), "workers": tk.StringVar(value="4"),
            "min_pick": tk.StringVar(value="0.5"), "top": tk.StringVar(value="15"),
            "min_matches": tk.StringVar(value="100"),
            "show_browser": tk.BooleanVar(value=False), "real_chrome": tk.BooleanVar(value=False),
            "sound": tk.BooleanVar(value=True), "cache": tk.BooleanVar(value=True),
        }
        self._load_remembered()
        self.tiles: dict[str, dict] = {}
        self.scale = max(1.0, root.winfo_fpixels("1i") / 96.0)

        families = set(tkfont.families())
        ui = next((f for f in ("Segoe UI", "SF Pro Text", "Helvetica Neue", "DejaVu Sans") if f in families), "TkDefaultFont")
        mono = next((f for f in ("Cascadia Mono", "Consolas", "Menlo", "DejaVu Sans Mono") if f in families), "TkFixedFont")
        self.f = {
            "title": (ui, 22, "bold"), "h1": (ui, 15, "bold"), "h2": (ui, 11, "bold"), "body": (ui, 10),
            "small": (ui, 8), "btn": (ui, 10, "bold"), "big": (ui, 13, "bold"), "mono": (mono, 9),
            "cell": (ui, 9, "bold"),
        }

        root.title("LoL Matchup Checker")
        root.configure(bg=C["bg"])
        try:
            self._window_icon = tk.PhotoImage(file=str(asset("icon.png")))
            root.iconphoto(True, self._window_icon)
        except (tk.TclError, OSError):
            pass
        root.geometry(f"{self.px(1180)}x{self.px(800)}")
        root.minsize(self.px(900), self.px(620))
        self._style()

        self.screen = tk.Frame(root, bg=C["bg"])
        self.screen.pack(fill="both", expand=True)
        self.catalog.start()
        self.show_home()
        root.after(50, self._poll)
        root.protocol("WM_DELETE_WINDOW", self._on_close)

    def px(self, n: float) -> int:
        return int(n * self.scale)

    def _style(self) -> None:
        s = ttk.Style(self.root)
        s.theme_use("clam")
        s.configure("TScrollbar", background=C["card"], troughcolor=C["panel"], bordercolor=C["panel"],
                    arrowcolor=C["muted"], lightcolor=C["card"], darkcolor=C["card"])
        s.map("TScrollbar", background=[("active", C["hover"])])
        s.configure("Gold.Horizontal.TProgressbar", background=C["gold"], troughcolor=C["card"],
                    bordercolor=C["card"], lightcolor=C["gold"], darkcolor=C["gold"])
        s.configure("TNotebook", background=C["bg"], borderwidth=0, tabmargins=0, bordercolor=C["line"],
                    lightcolor=C["bg"], darkcolor=C["bg"])
        s.configure("TNotebook.Tab", background=C["panel"], foreground=C["muted"], padding=(self.px(16), self.px(6)),
                    borderwidth=0, font=self.f["btn"], bordercolor=C["line"], lightcolor=C["panel"], darkcolor=C["panel"])
        s.map("TNotebook.Tab", background=[("selected", C["card"])], foreground=[("selected", C["gold"])],
              lightcolor=[("selected", C["card"])])
        s.configure("TSpinbox", fieldbackground=C["card"], background=C["card"], foreground=C["text"],
                    arrowcolor=C["muted"], bordercolor=C["line"], insertcolor=C["text"])

    def _clear(self) -> None:
        for w in self.screen.winfo_children():
            w.destroy()
        self.tiles = {}
        self._support_footer()

    def _support_footer(self) -> None:
        """Small "buy me a coffee" line at the bottom of every screen."""
        bar = tk.Frame(self.screen, bg=C["bg"])
        bar.pack(side="bottom", fill="x", pady=(self.px(3), self.px(4)))
        line = tk.Frame(bar, bg=C["bg"])
        line.pack()
        small = self.f["small"]
        tk.Label(line, text="☕ ", fg=C["gold"], bg=C["bg"], font=small, padx=0).pack(side="left")
        tk.Label(line, text="If you enjoy the app and would like to support me, ", fg=C["muted"], bg=C["bg"],
                 font=small, padx=0).pack(side="left")
        link = tk.Label(line, text="buy me a coffee", fg=C["gold"], bg=C["bg"], cursor="hand2", padx=0,
                        font=(small[0], small[1], "underline"))
        link.pack(side="left")
        tk.Label(line, text="!", fg=C["muted"], bg=C["bg"], font=small, padx=0).pack(side="left")
        tk.Label(line, text="  ♥ ✨", fg=C["gold"], bg=C["bg"], font=small, padx=0).pack(side="left")
        link.bind("<Enter>", lambda e: link.configure(fg=C["teal"]))
        link.bind("<Leave>", lambda e: link.configure(fg=C["gold"]))
        link.bind("<Button-1>", lambda e: self._open_support())

    def _open_support(self) -> None:
        if SUPPORT_URL:
            import webbrowser
            webbrowser.open(SUPPORT_URL)

    # ---------------------------------------------------------------- event pump

    def _poll(self) -> None:
        try:
            for _ in range(400):
                event = self.events.get_nowait()
                kind = event[0]
                if kind == "catalog":
                    self.champions = event[1]
                    if hasattr(self, "grid_frame") and self.grid_frame.winfo_exists():
                        self._build_tiles()
                elif kind == "catalog_error":
                    self.catalog_error = event[1]
                    if hasattr(self, "grid_status") and self.grid_status.winfo_exists():
                        self.grid_status.configure(text=event[1] + " Check your internet connection and restart.")
                elif kind == "icon":
                    self.icons.add(event[1], event[2])
                    tile = self.tiles.get(event[1])
                    if tile:
                        self._set_tile_icon(tile)
                elif kind == "log":
                    self._log(event[1])
                elif kind == "done":
                    self._job_done(*event[1:])
        except queue.Empty:
            pass
        self.root.after(50, self._poll)

    # ---------------------------------------------------------------- remembered picks

    _SAVED_OPTIONS = ("workers", "min_pick", "min_matches", "show_browser", "real_chrome", "sound", "cache")

    def _load_remembered(self) -> None:
        if not self.settings.remember:
            return
        picks = self.settings.data.get("picks") or {}
        for mode in ("counters", "matchups"):
            entry = picks.get(mode) or {}
            champs = [str(c) for c in entry.get("champs") or [] if c]
            self.sel_by_mode[mode][:] = list(dict.fromkeys(champs))
            if entry.get("lane"):
                self.lane_by_mode[mode] = str(entry["lane"])
        self.selected = self.sel_by_mode[self.mode]
        self.lane = self.lane_by_mode[self.mode]
        for key, value in (self.settings.data.get("options") or {}).items():
            if key in self._SAVED_OPTIONS:
                try:
                    self.opt_vars[key].set(value)
                except (tk.TclError, KeyError):
                    pass

    def _save_remembered(self) -> None:
        picks = {mode: {"lane": self.lane_by_mode[mode], "champs": list(self.sel_by_mode[mode])}
                 for mode in ("counters", "matchups")}
        options = {key: self.opt_vars[key].get() for key in self._SAVED_OPTIONS}
        self.settings.save(self.remember.get(), picks, options)

    def _on_close(self) -> None:
        self._save_remembered()
        if self.job:
            self.job.stop()
            self.root.after(1500, self.root.destroy)  # give the browser a moment to close
        else:
            self.root.destroy()

    # ---------------------------------------------------------------- home

    def show_home(self) -> None:
        self._clear()
        wrap = tk.Frame(self.screen, bg=C["bg"])
        wrap.place(relx=0.5, rely=0.45, anchor="center")
        logo = getattr(self, "_window_icon", None)
        if logo is not None:
            self._home_logo = logo.subsample(2) if self.scale < 1.5 else logo  # 128 px, 256 on high-DPI
            tk.Label(wrap, image=self._home_logo, bg=C["bg"]).pack(pady=(0, self.px(10)))
        tk.Label(wrap, text="LoL MATCHUP CHECKER", font=self.f["title"], fg=C["gold"], bg=C["bg"]).pack()
        from . import __version__
        tk.Label(wrap, text=f"v{__version__}  ·  data from u.gg  ·  icons from Riot Data Dragon", font=self.f["body"],
                 fg=C["muted"], bg=C["bg"]).pack(pady=(self.px(4), self.px(36)))

        cards = tk.Frame(wrap, bg=C["bg"])
        cards.pack()
        self._home_card(cards, "⚔", "Find counters",
                        "Pick an enemy champion.\nSee who beats it, best first.", lambda: self.show_setup("counters"))
        self._home_card(cards, "▦", "Matchup sheet",
                        "Pick the champions you play.\nSee how each does vs every laner.", lambda: self.show_setup("matchups"))

    def _home_card(self, parent, glyph, title, text, command) -> None:
        card = tk.Frame(parent, bg=C["card"], width=self.px(300), height=self.px(220), cursor="hand2",
                        highlightthickness=self.px(1), highlightbackground=C["line"])
        card.pack(side="left", padx=self.px(14))
        card.pack_propagate(False)
        parts = [
            tk.Label(card, text=glyph, font=(self.f["title"][0], 34), fg=C["gold"], bg=C["card"]),
            tk.Label(card, text=title, font=self.f["h1"], fg=C["text"], bg=C["card"]),
            tk.Label(card, text=text, font=self.f["body"], fg=C["muted"], bg=C["card"], justify="center"),
        ]
        parts[0].pack(pady=(self.px(30), self.px(6)))
        parts[1].pack()
        parts[2].pack(pady=(self.px(8), 0))

        def paint(color, border):
            card.configure(bg=color, highlightbackground=border)
            for p in parts:
                p.configure(bg=color)

        for w in (card, *parts):
            w.bind("<Enter>", lambda e: paint(C["hover"], C["gold"]))
            w.bind("<Leave>", lambda e: paint(C["card"], C["line"]))
            w.bind("<Button-1>", lambda e: command())

    # ---------------------------------------------------------------- setup

    def _top_bar(self, title: str, back) -> tk.Frame:
        bar = tk.Frame(self.screen, bg=C["panel"])
        bar.pack(fill="x")
        self.back_btn = FlatButton(bar, "←  Back", back, bg=C["panel"], font=self.f["btn"])
        self.back_btn.pack(side="left", padx=self.px(8), pady=self.px(8))
        tk.Label(bar, text=title, font=self.f["h1"], fg=C["gold"], bg=C["panel"]).pack(side="left", padx=self.px(8))
        return bar

    def show_setup(self, mode: str) -> None:
        self.mode = mode
        self.selected = self.sel_by_mode[mode]
        self.lane = self.lane_by_mode[mode]
        self._clear()
        counters_mode = mode == "counters"
        self._top_bar("Find counters" if counters_mode else "Matchup sheet", self.show_home)

        body = tk.Frame(self.screen, bg=C["bg"])
        body.pack(fill="both", expand=True, padx=self.px(18), pady=(self.px(12), 0))

        # 1) lane
        self._step(body, "1", "Lane" + ("  (Auto = the role the champion is played in most)" if counters_mode else ""))
        lanes = tk.Frame(body, bg=C["bg"])
        lanes.pack(fill="x", pady=(self.px(4), self.px(12)))
        self.lane_btns = {}
        options = ([("auto", "AUTO")] if counters_mode else []) + LANES
        for key, label in options:
            b = FlatButton(lanes, label, lambda k=key: self._pick_lane(k), font=self.f["btn"],
                           padx=self.px(18), pady=self.px(8))
            b.pack(side="left", padx=(0, self.px(6)))
            self.lane_btns[key] = b
        self._paint_lanes()

        # 2) champions
        self._step(body, "2", "Enemy champion(s) to counter" if counters_mode else "Champions you play")
        row = tk.Frame(body, bg=C["bg"])
        row.pack(fill="x", pady=(self.px(4), self.px(6)))
        search_box = tk.Frame(row, bg=C["card"], highlightthickness=self.px(1), highlightbackground=C["line"],
                              highlightcolor=C["gold"])
        search_box.pack(side="left")
        tk.Label(search_box, text="🔍", bg=C["card"], fg=C["muted"], font=self.f["body"]).pack(side="left", padx=(self.px(8), 0))
        self.search = tk.StringVar()
        entry = tk.Entry(search_box, textvariable=self.search, bg=C["card"], fg=C["text"], insertbackground=C["text"],
                         relief="flat", font=self.f["body"], width=26, highlightthickness=0)
        entry.pack(side="left", ipady=self.px(6), padx=self.px(8))
        entry.bind("<Return>", lambda e: self._search_enter())
        entry.bind("<Escape>", lambda e: self.search.set(""))
        self.search.trace_add("write", lambda *a: self._filter_tiles())
        entry.focus_set()

        tk.Checkbutton(row, text="Remember my picks", variable=self.remember, command=self._save_remembered,
                       bg=C["bg"], fg=C["text"], selectcolor=C["card"], activebackground=C["bg"],
                       activeforeground=C["gold"], font=self.f["body"], highlightthickness=0, bd=0,
                       cursor="hand2").pack(side="right")
        self.sel_strip = tk.Frame(row, bg=C["bg"])
        self.sel_strip.pack(side="left", fill="x", expand=True, padx=(self.px(14), 0))

        self.grid_scroll = ScrollFrame(body, bg=C["panel"])
        self.grid_scroll.pack(fill="both", expand=True)
        self.grid_frame = self.grid_scroll.inner
        self.grid_status = tk.Label(self.grid_frame, text=self.catalog_error or "Loading champions from Riot…",
                                    fg=C["muted"], bg=C["panel"], font=self.f["body"])
        self.grid_status.grid(row=0, column=0, padx=self.px(20), pady=self.px(20))
        self.grid_scroll.canvas.bind("<Configure>", self._on_grid_resize, add="+")
        self._cols = 0
        if self.champions:
            self._build_tiles()

        # 3) options + start
        bottom = tk.Frame(self.screen, bg=C["panel"])
        bottom.pack(fill="x", side="bottom")
        opt_rows = tk.Frame(bottom, bg=C["panel"])
        opt_rows.pack(side="left", padx=self.px(18), pady=self.px(8))
        opts = tk.Frame(opt_rows, bg=C["panel"])
        opts.pack(anchor="w")
        checks = tk.Frame(opt_rows, bg=C["panel"])
        checks.pack(anchor="w", pady=(self.px(6), 0))
        v = self.opt_vars
        self._opt_entry(opts, "Patch", v["patch"], 7, "blank = latest")
        self._opt_entry(opts, "Tabs", v["workers"], 3)
        self._opt_entry(opts, "Min pick %", v["min_pick"], 4)
        if counters_mode:
            self._opt_entry(opts, "Min games", v["min_matches"], 5)
        for key, label in (("cache", "Use saved results (24h)"), ("sound", "Sound when done"),
                           ("show_browser", "Show browser"), ("real_chrome", "Use my Chrome")):
            tk.Checkbutton(checks, text=label, variable=v[key], bg=C["panel"], fg=C["text"], selectcolor=C["card"],
                           activebackground=C["panel"], activeforeground=C["text"], font=self.f["body"],
                           highlightthickness=0, bd=0).pack(side="left", padx=(self.px(10), 0))

        go = tk.Frame(bottom, bg=C["panel"])
        go.pack(side="right", padx=self.px(18), pady=self.px(8))
        self.start_btn = FlatButton(go, "START  ▶", self.start_job, bg=C["gold"], fg="#10151a", hover="#e0c48a",
                                    font=self.f["big"], padx=self.px(34), pady=self.px(10))
        self.start_btn.pack()
        self.start_hint = tk.Label(go, text="", fg=C["muted"], bg=C["panel"], font=self.f["small"])
        self.start_hint.pack(pady=(self.px(3), 0))
        self._refresh_selection()

    def _step(self, parent, num, text) -> None:
        row = tk.Frame(parent, bg=C["bg"])
        row.pack(fill="x")
        tk.Label(row, text=num, font=self.f["h2"], fg="#10151a", bg=C["gold"], width=2).pack(side="left")
        tk.Label(row, text=text, font=self.f["h2"], fg=C["text"], bg=C["bg"]).pack(side="left", padx=self.px(8))

    def _opt_entry(self, parent, label, var, width, hint=None) -> None:
        tk.Label(parent, text=label, fg=C["muted"], bg=C["panel"], font=self.f["body"]).pack(side="left", padx=(self.px(10), self.px(4)))
        e = tk.Entry(parent, textvariable=var, width=width, bg=C["card"], fg=C["text"], insertbackground=C["text"],
                     relief="flat", font=self.f["body"], justify="center", highlightthickness=self.px(1),
                     highlightbackground=C["line"], highlightcolor=C["gold"])
        e.pack(side="left", ipady=self.px(3))
        if hint:
            e.bind("<FocusIn>", lambda ev: self.start_hint.configure(text=hint))
            e.bind("<FocusOut>", lambda ev: self._refresh_selection())

    def _pick_lane(self, key: str) -> None:
        self.lane = key
        self.lane_by_mode[self.mode] = key
        self._paint_lanes()
        self._refresh_selection()

    def _paint_lanes(self) -> None:
        for key, b in self.lane_btns.items():
            if key == self.lane:
                b.set_colors(C["gold"], "#10151a", "#e0c48a")
            else:
                b.set_colors(C["card"], C["text"], C["hover"])

    # ---- champion grid

    def _tile_size(self) -> int:
        return self.px(58)

    def _build_tiles(self) -> None:
        self.grid_status.grid_forget()
        size = self._tile_size()
        for champ in self.champions:
            name = champ["name"]
            frame = tk.Frame(self.grid_frame, bg=C["panel"], cursor="hand2", padx=self.px(3), pady=self.px(3))
            img_lbl = tk.Label(frame, bg=C["card"], width=size, height=size, bd=0)
            # a 1x1 transparent image makes width/height count in pixels before the icon arrives
            img_lbl._blank = tk.PhotoImage(width=1, height=1)
            img_lbl.configure(image=img_lbl._blank, text=name[:2], compound="center", fg=C["muted"], font=self.f["h2"])
            img_lbl.pack()
            txt = tk.Label(frame, text=name if len(name) <= 11 else name[:10] + "…", bg=C["panel"], fg=C["muted"],
                           font=self.f["small"])
            txt.pack(pady=(self.px(2), 0))
            tile = {"name": name, "frame": frame, "img": img_lbl, "txt": txt}
            for w in (frame, img_lbl, txt):
                w.bind("<Button-1>", lambda e, n=name: self._toggle(n))
                w.bind("<Enter>", lambda e, t=tile: self._hover_tile(t, True))
                w.bind("<Leave>", lambda e, t=tile: self._hover_tile(t, False))
            self.tiles[name] = tile
            self._set_tile_icon(tile)
            self._paint_tile(tile)
        self._cols = 0
        self._on_grid_resize()

    def _set_tile_icon(self, tile) -> None:
        photo = self.icons.get(tile["name"], self._tile_size())
        if photo is not None:
            tile["img"].configure(image=photo, text="")

    def _paint_tile(self, tile, hover=False) -> None:
        sel = tile["name"] in self.selected
        bg = C["gold"] if sel else (C["hover"] if hover else C["panel"])
        tile["frame"].configure(bg=bg)
        tile["txt"].configure(bg=bg, fg="#10151a" if sel else (C["text"] if hover else C["muted"]))

    def _hover_tile(self, tile, on: bool) -> None:
        self._paint_tile(tile, on)

    def _on_grid_resize(self, event=None) -> None:
        width = event.width if event else self.grid_scroll.canvas.winfo_width()
        cols = max(1, width // (self._tile_size() + self.px(14)))
        if cols != self._cols:
            self._cols = cols
            self._filter_tiles()

    def _visible(self) -> list[str]:
        q = champion_slug(self.search.get()) if hasattr(self, "search") else ""
        from .data import CHAMP_ALIASES
        alias = CHAMP_ALIASES.get(self.search.get().strip().lower()) if q else None
        return [c["name"] for c in self.champions
                if not q or q in champion_slug(c["name"]) or (alias and c["name"] == alias)]

    def _filter_tiles(self) -> None:
        if not self.tiles:
            return
        visible = self._visible()
        shown = set(visible)
        for name, tile in self.tiles.items():
            if name not in shown:
                tile["frame"].grid_forget()
        cols = max(1, self._cols)
        for i, name in enumerate(visible):
            self.tiles[name]["frame"].grid(row=i // cols, column=i % cols, padx=self.px(4), pady=self.px(4))
        self.grid_scroll.to_top()

    def _search_enter(self) -> None:
        visible = self._visible()
        if len(visible) >= 1 and self.search.get().strip():
            self._toggle(visible[0])
            self.search.set("")

    def _toggle(self, name: str) -> None:
        if name in self.selected:
            self.selected.remove(name)
        else:
            self.selected.append(name)
        tile = self.tiles.get(name)
        if tile:
            self._paint_tile(tile)
        self._refresh_selection()

    def _refresh_selection(self) -> None:
        if not hasattr(self, "sel_strip") or not self.sel_strip.winfo_exists():
            return
        for w in self.sel_strip.winfo_children():
            w.destroy()
        if not self.selected:
            tk.Label(self.sel_strip, text="Click icons to select · Enter picks the first match",
                     fg=C["muted"], bg=C["bg"], font=self.f["body"]).pack(side="left")
        for name in self.selected:
            chip = tk.Frame(self.sel_strip, bg=C["card"], cursor="hand2")
            chip.pack(side="left", padx=(0, self.px(6)))
            photo = self.icons.get(name, self.px(24))
            parts = []
            if photo:
                parts.append(tk.Label(chip, image=photo, bg=C["card"]))
            parts.append(tk.Label(chip, text=f"{name}  ✕", fg=C["text"], bg=C["card"], font=self.f["body"]))
            for p in parts:
                p.pack(side="left", padx=(self.px(4), 0), pady=self.px(2))
            for w in (chip, *parts):
                w.bind("<Button-1>", lambda e, n=name: self._toggle(n))
        if self.selected:
            FlatButton(self.sel_strip, "Clear", self._clear_selection, bg=C["bg"], fg=C["muted"],
                       font=self.f["body"], padx=self.px(6), pady=self.px(2)).pack(side="left")

        ok, hint = self._ready()
        self.start_btn.set_enabled(ok)
        self.start_btn.set_colors(C["gold"] if ok else C["card"], "#10151a" if ok else C["muted"],
                                  "#e0c48a" if ok else C["card"])
        self.start_hint.configure(text=hint, fg=C["muted"])

    def _clear_selection(self) -> None:
        names = list(self.selected)
        self.selected.clear()
        for n in names:
            if n in self.tiles:
                self._paint_tile(self.tiles[n])
        self._refresh_selection()

    def _ready(self) -> tuple[bool, str]:
        if not self.lane:
            return False, "Pick a lane"
        if not self.selected:
            return False, "Pick at least one champion"
        n = len(self.selected)
        if self.mode == "counters":
            return True, f"{n} champion{'s' if n > 1 else ''} · ~60 pages each"
        return True, f"{n} champion{'s' if n > 1 else ''} · ~{n * 60} pages"

    # ---------------------------------------------------------------- run

    def _argv(self) -> list[str] | None:
        v = self.opt_vars
        argv: list[str] = []
        try:
            workers = int(v["workers"].get() or 4)
            min_pick = float((v["min_pick"].get() or "0.5").replace(",", "."))
        except ValueError:
            self.start_hint.configure(text="Tabs and Min pick % must be numbers", fg=C["red"])
            return None
        argv += ["--workers", str(max(1, workers)), "--min-pick-rate", str(max(0.0, min_pick))]
        if v["patch"].get().strip():
            argv += ["--patch", v["patch"].get().strip()]
        if v["show_browser"].get():
            argv.append("--show-browser")
        if v["real_chrome"].get():
            argv.append("--real-chrome")
        if not v["cache"].get():
            argv.append("--no-cache")
        if self.mode == "counters":
            try:
                min_matches = int(v["min_matches"].get() or 100)
            except ValueError:
                self.start_hint.configure(text="Min games must be a number", fg=C["red"])
                return None
            argv = [*self.selected, *argv, "--min-matches", str(max(0, min_matches)), "--top", "15",
                    "--out", str(output_dir() / "Counters.xlsx")]
            if self.lane != "auto":
                argv += ["--lane", self.lane]
        else:
            argv = ["--lane", self.lane, "--champs", *self.selected, *argv, "--out", str(output_dir() / "Matchups.xlsx")]
        if v["patch"].get().strip():
            from .data import normalize_patch
            try:
                normalize_patch(v["patch"].get())
            except ValueError:
                self.start_hint.configure(text="Patch looks like 26.18 (or leave it blank)", fg=C["red"])
                return None
        return argv

    def start_job(self) -> None:
        ok, _ = self._ready()
        if not ok or self.job:
            return
        argv = self._argv()
        if argv is None:
            return
        self._save_remembered()
        self.show_run()
        self._log("$ " + ("lol-counters " if self.mode == "counters" else "lol-matchup gen ")
                  + " ".join(f'"{a}"' if " " in a else a for a in argv), "cmd")
        self.job = Job(self.mode, argv, self.events)
        self.job.start()

    def show_run(self) -> None:
        self._clear()
        title = ("Counters: " if self.mode == "counters" else "Matchups: ") + ", ".join(self.selected)
        bar = self._top_bar(title if len(title) < 60 else title[:57] + "…", lambda: self.show_setup(self.mode))
        self.back_btn.set_enabled(False)

        self.stop_btn = FlatButton(bar, "■  Stop", self._stop, bg=C["panel"], fg=C["red"], font=self.f["btn"])
        self.stop_btn.pack(side="right", padx=self.px(8))
        self.excel_btn = FlatButton(bar, "Open Excel", self._open_excel, bg=C["panel"], font=self.f["btn"])
        self.excel_btn.pack(side="right", padx=self.px(4))
        self.excel_btn.set_enabled(False)
        self.excel_path = None

        status = tk.Frame(self.screen, bg=C["bg"])
        status.pack(fill="x", padx=self.px(18), pady=(self.px(10), self.px(6)))
        line = tk.Frame(status, bg=C["bg"])
        line.pack(fill="x")
        self.time_lbl = tk.Label(line, text="", fg=C["gold"], bg=C["bg"], font=self.f["h2"], anchor="e")
        self.time_lbl.pack(side="right")
        self.status_lbl = tk.Label(line, text="Opening u.gg (getting through Cloudflare can take a minute)…",
                                   fg=C["text"], bg=C["bg"], font=self.f["body"], anchor="w")
        self.status_lbl.pack(side="left", fill="x")
        self.eta = EtaTracker(len(self.selected) if self.mode == "counters" else 1)
        self.running = True
        self._tick()
        self.progress = ttk.Progressbar(status, mode="indeterminate", style="Gold.Horizontal.TProgressbar")
        self.progress.pack(fill="x", pady=(self.px(6), 0))
        self.progress.start(12)

        self.tabs = ttk.Notebook(self.screen)
        self.tabs.pack(fill="both", expand=True, padx=self.px(18), pady=(self.px(4), self.px(14)))
        term_wrap = tk.Frame(self.tabs, bg=C["term_bg"])
        self.term = tk.Text(term_wrap, bg=C["term_bg"], fg=C["term_fg"], insertbackground=C["term_fg"],
                            font=self.f["mono"], relief="flat", wrap="word", padx=self.px(12), pady=self.px(10),
                            state="disabled", highlightthickness=0)
        sb = ttk.Scrollbar(term_wrap, command=self.term.yview)
        self.term.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.term.pack(fill="both", expand=True)
        for tag, color in (("cmd", C["teal"]), ("err", C["red"]), ("warn", C["yellow"]), ("ok", C["green"]),
                           ("head", C["gold"]), ("dim", C["muted"])):
            self.term.tag_configure(tag, foreground=color)
        self.tabs.add(term_wrap, text="Terminal")
        self.results_tab = tk.Frame(self.tabs, bg=C["bg"])
        self.tabs.add(self.results_tab, text="Results", state="disabled")

    _PROGRESS = re.compile(r"^\[(\d+)/(\d+)\]")

    def _fold_listener_errors(self, line: str) -> bool:
        """Swallow patchright's "Error occurred in event listener" tracebacks (harmless browser noise);
        shows one dim line instead. Returns True if the line was consumed."""
        if line.strip() == "Error occurred in event listener":
            self._in_listener_tb = True
            self._log("  (browser network hiccup, harmless, ignored)", "dim")
            return True
        if getattr(self, "_in_listener_tb", False):
            if line.startswith((" ", "\t", "Traceback")) or not line.strip():
                return True
            self._in_listener_tb = False  # the final "SomeError: ..." line ends the traceback
            return True
        return False

    def _log(self, line: str, tag: str | None = None) -> None:
        if not hasattr(self, "term") or not self.term.winfo_exists():
            return
        if tag is None and self._fold_listener_errors(line):
            return
        if tag is None:
            low = line.lower()
            if "error" in low or "failed" in low or "traceback" in low:
                tag = "err"
            elif "warning" in low or "skipp" in low or "not found" in low or "note:" in low:
                tag = "warn"
            elif line.startswith("===") or line.startswith("Excel saved"):
                tag = "head"
            elif "recognized" in low or line.startswith("u.gg is showing"):
                tag = "ok"
        at_bottom = self.term.yview()[1] > 0.98
        self.term.configure(state="normal")
        self.term.insert("end", line + "\n", (tag,) if tag else ())
        self.term.configure(state="disabled")
        if at_bottom:
            self.term.see("end")

        m = self._PROGRESS.match(line)
        if m:
            done, total = int(m.group(1)), int(m.group(2))
            if str(self.progress.cget("mode")) != "determinate":
                self.progress.stop()
                self.progress.configure(mode="determinate")
            self.progress.configure(maximum=total, value=done)
            self.eta.progress(done, total)
            phase = f"  (champion {self.eta.phase}/{self.eta.phases})" if self.eta.phases > 1 else ""
            self.status_lbl.configure(text=f"Scraping matchups… {done}/{total}{phase}")
            self._tick(reschedule=False)
        elif line.startswith("All ") and "saved results" in line:
            self.status_lbl.configure(text=line)
        elif line.startswith("Scraping ") or line.startswith("Checking "):
            if line.startswith("Scraping "):
                self.eta.new_phase()
            self.status_lbl.configure(text=line)

    def _tick(self, reschedule: bool = True) -> None:
        """Refresh the time label; reschedules itself every second while a job is running."""
        if not self.running or not self.time_lbl.winfo_exists():
            return
        elapsed = fmt_duration(self.eta.elapsed())
        left = self.eta.remaining()
        if left is not None:
            text = f"~{fmt_duration(left)} left  ·  {elapsed} elapsed"
        elif self.eta.phase_started is not None:
            text = f"estimating…  ·  {elapsed} elapsed"
        else:
            text = f"{elapsed} elapsed"
        self.time_lbl.configure(text=text)
        if reschedule:
            self.root.after(1000, self._tick)

    def _stop(self) -> None:
        if self.job:
            self.job.stop()
            self.status_lbl.configure(text="Stopping… (closing the browser)")
            self.stop_btn.set_enabled(False)

    def _open_excel(self) -> None:
        if not self.excel_path:
            return
        path = str(self.excel_path)
        try:
            if sys.platform == "win32":
                os.startfile(path)  # noqa: S606
            elif sys.platform == "darwin":
                os.system(f'open "{path}"')  # noqa: S605
            else:
                os.system(f'xdg-open "{path}" >/dev/null 2>&1 &')  # noqa: S605
        except OSError as exc:
            self._log(f"Couldn't open Excel: {exc}", "err")

    def _job_done(self, code: int, collect: dict, stopped: bool) -> None:
        self.job = None
        self.running = False
        if not hasattr(self, "progress") or not self.progress.winfo_exists():
            return
        self.progress.stop()
        self.progress.configure(mode="determinate", maximum=1, value=1 if collect else 0)
        self.back_btn.set_enabled(True)
        self.stop_btn.set_enabled(False)
        self.excel_path = collect.get("excel")
        self.excel_btn.set_enabled(bool(self.excel_path))
        if not stopped and self.opt_vars["sound"].get():
            failed = not collect or bool(collect.get("failures")) or any(
                r.failures for r in collect.get("results") or [])
            play_chime("error" if failed else "done", fallback=self.root.bell)
        took = fmt_duration(self.eta.elapsed())
        self.time_lbl.configure(text=f"Stopped after {took}" if stopped else f"Finished in {took}")
        if stopped:
            self.status_lbl.configure(text="Stopped.", fg=C["yellow"])
            return
        if not collect:
            self.status_lbl.configure(text="Finished without results, see the terminal for details.", fg=C["red"])
            return
        self.status_lbl.configure(text="Done!  Excel saved to " + str(self.excel_path), fg=C["green"])
        self.tabs.tab(1, state="normal")
        self.rating_filter = None
        self.filter_painters = []
        if self.mode == "counters":
            self._show_counter_results(collect)
        else:
            self._show_matchup_results(collect)
        self.tabs.select(1)

    # ---------------------------------------------------------------- results

    def _rating_badge(self, parent, rating: str, text: str | None = None, width: int = 4) -> tk.Label:
        fill, font = RATING_STYLES.get(rating, RATING_STYLES["N/A"])
        return tk.Label(parent, text=text or rating, bg=f"#{fill}", fg=f"#{font}", font=self.f["cell"], width=width)

    # ---- rating filter: click a rating in the legend to highlight only those, click again to reset

    def _shown(self, rating: str | None) -> bool:
        return self.rating_filter is None or rating == self.rating_filter

    def _set_rating_filter(self, rating: str) -> None:
        self.rating_filter = None if self.rating_filter == rating else rating
        for paint in list(self.filter_painters):
            try:
                paint()
            except tk.TclError:  # widget from an old results page
                self.filter_painters.remove(paint)

    def _make_filter_click(self, widget, rating: str) -> None:
        """Clicking a rating cell in the results works like clicking that rating in the legend."""
        widget.configure(cursor="hand2")
        widget.bind("<Button-1>", lambda e: self._set_rating_filter(rating))

    def _legend(self, parent) -> None:
        row = tk.Frame(parent, bg=C["bg"])
        row.pack(fill="x", pady=(self.px(8), 0))
        for rating, label in (("-", "< 49%"), ("S", "49–51"), ("+", "51–53"), ("D", "53–55"), ("D+", "55–60"), ("UD", "60%+")):
            fill, font = RATING_STYLES[rating]
            ring = tk.Frame(row, bg=C["bg"], padx=self.px(2), pady=self.px(2), cursor="hand2")
            ring.pack(side="left")
            badge = self._rating_badge(ring, rating, width=3)
            badge.configure(cursor="hand2")
            badge.pack()
            text = tk.Label(row, text=label, fg=C["muted"], bg=C["bg"], font=self.f["small"], cursor="hand2")
            text.pack(side="left", padx=(self.px(3), self.px(10)))

            def paint(rating=rating, fill=fill, font=font, ring=ring, badge=badge, text=text):
                active = self.rating_filter == rating
                on = self._shown(rating)
                ring.configure(bg=C["text"] if active else C["bg"])
                badge.configure(bg=f"#{fill}" if on else C["card"], fg=f"#{font}" if on else C["muted"])
                text.configure(fg=C["text"] if active else C["muted"])

            for w in (ring, badge, text):
                w.bind("<Button-1>", lambda e, r=rating: self._set_rating_filter(r))
            self.filter_painters.append(paint)
            paint()
        hint = tk.Label(row, text="← click a rating (here or in the table) to highlight only those, click again to show all",
                        fg=C["muted"], bg=C["bg"], font=self.f["small"])
        hint.pack(side="left", padx=(self.px(6), 0))

    def _show_counter_results(self, collect: dict) -> None:
        from .counters import rank_counters

        results = collect["results"]
        min_matches = collect.get("min_matches", 100)
        holder = self.results_tab
        if len(results) > 1:
            nb = ttk.Notebook(holder)
            nb.pack(fill="both", expand=True)
        for result in results:
            page = tk.Frame(nb if len(results) > 1 else holder, bg=C["bg"])
            if len(results) > 1:
                nb.add(page, text=f"{result.target} ({result.lane.value})")
            else:
                page.pack(fill="both", expand=True)

            head = tk.Frame(page, bg=C["bg"])
            head.pack(fill="x", pady=(self.px(10), self.px(6)))
            photo = self.icons.get(result.target, self.px(48))
            if photo:
                tk.Label(head, image=photo, bg=C["bg"]).pack(side="left", padx=(0, self.px(10)))
            txt = tk.Frame(head, bg=C["bg"])
            txt.pack(side="left")
            tk.Label(txt, text=f"Best counters vs {result.target}", font=self.f["h1"], fg=C["text"], bg=C["bg"]).pack(anchor="w")
            tk.Label(txt, text=f"{result.lane.value} · patch {collect.get('patch')} · win rate of the counter against "
                               f"{result.target}", font=self.f["body"], fg=C["muted"], bg=C["bg"]).pack(anchor="w")
            self._legend(page)

            reliable, thin = rank_counters(result.matchups, min_matches)
            scroll = ScrollFrame(page, bg=C["panel"])
            scroll.pack(fill="both", expand=True, pady=(self.px(8), 0))
            grid = scroll.inner
            for col, (label, anchor) in enumerate((("#", "e"), ("", "w"), ("Champion", "w"), ("Win rate", "w"),
                                                   ("", "e"), ("Games", "e"), ("Rating", ""))):
                tk.Label(grid, text=label, fg=C["muted"], bg=C["panel"], font=self.f["small"]).grid(
                    row=0, column=col, sticky=anchor, padx=self.px(6), pady=(self.px(8), self.px(2)))
            r = 1
            for i, m in enumerate(reliable, start=1):
                self._counter_row(grid, r, str(i), m, dim=False)
                r += 1
            if thin:
                tk.Label(grid, text=f"Under {min_matches} games (not enough data to trust)", fg=C["muted"],
                         bg=C["panel"], font=self.f["h2"]).grid(row=r, column=0, columnspan=7, sticky="w",
                                                              padx=self.px(10), pady=(self.px(14), self.px(4)))
                r += 1
                for m in thin:
                    self._counter_row(grid, r, "", m, dim=True)
                    r += 1
            if result.failures:
                tk.Label(grid, text=f"Couldn't scrape: " + ", ".join(p for p, _a, _r in result.failures),
                         fg=C["red"], bg=C["panel"], font=self.f["body"], wraplength=self.px(800), justify="left").grid(
                    row=r, column=0, columnspan=7, sticky="w", padx=self.px(10), pady=self.px(10))
            grid.grid_columnconfigure(7, weight=1)

    def _counter_row(self, grid, r: int, rank: str, m, dim: bool) -> None:
        pad = {"padx": self.px(6), "pady": self.px(3)}
        size = self.px(32)
        rank_lbl = tk.Label(grid, text=rank, bg=C["panel"], font=self.f["h2"])
        rank_lbl.grid(row=r, column=0, sticky="e", **pad)
        icon = tk.Label(grid, bg=C["panel"])
        icon.grid(row=r, column=1, **pad)
        name = tk.Label(grid, text=m.champ_playing, bg=C["panel"], font=self.f["h2"])
        name.grid(row=r, column=2, sticky="w", **pad)

        bar_w, bar_h = self.px(260), self.px(12)
        bar = tk.Canvas(grid, width=bar_w, height=bar_h, bg=C["card"], highlightthickness=0)
        lo, hi = 40.0, 65.0  # bar range in win-rate %
        frac = min(1.0, max(0.0, (m.win_rate - lo) / (hi - lo)))
        rect = bar.create_rectangle(0, 0, int(bar_w * frac), bar_h, width=0)
        mid = int(bar_w * (50 - lo) / (hi - lo))
        bar.create_line(mid, 0, mid, bar_h, fill=C["muted"], dash=(2, 2))
        bar.grid(row=r, column=3, sticky="w", **pad)
        wr = tk.Label(grid, text=f"{m.win_rate:.2f}%", bg=C["panel"], font=self.f["h2"])
        wr.grid(row=r, column=4, sticky="e", **pad)
        games = tk.Label(grid, text=f"{m.matches:,}", fg=C["muted"], bg=C["panel"], font=self.f["body"])
        games.grid(row=r, column=5, sticky="e", **pad)
        badge = self._rating_badge(grid, m.rating)
        badge.grid(row=r, column=6, **pad)
        self._make_filter_click(badge, m.rating)
        fill, font = RATING_STYLES[m.rating]

        def paint():
            on = self._shown(m.rating)
            bright = on and not dim
            rank_lbl.configure(fg=C["gold"] if on and rank and int(rank) <= 3 else C["muted"] if on else C["line"])
            photo = self.icons.get(m.champ_playing, size, grey=not on)
            if photo:
                icon.configure(image=photo)
            name.configure(fg=C["text"] if bright else C["muted"] if on else C["line"])
            wr.configure(fg=C["text"] if bright else C["muted"] if on else C["line"])
            games.configure(fg=C["muted"] if on else C["line"])
            bar.itemconfigure(rect, fill=f"#{fill}" if bright else C["line"] if on else C["hover"])
            badge.configure(bg=f"#{fill}" if on else C["card"], fg=f"#{font}" if on else C["line"])

        self.filter_painters.append(paint)
        paint()

    def _show_matchup_results(self, collect: dict) -> None:
        mine = collect["my_champs"]
        lookup = {(m.champ_playing, m.champ_against): m for m in collect["matchups"]}
        enemies = sorted(collect["lane_champs"], key=str.lower)

        page = self.results_tab
        head = tk.Frame(page, bg=C["bg"])
        head.pack(fill="x", pady=(self.px(10), 0))
        tk.Label(head, text=f"Your {collect['lane'].value} matchups", font=self.f["h1"], fg=C["text"],
                 bg=C["bg"]).pack(side="left")
        tk.Label(head, text=f"  patch {collect.get('patch')} · your win rate vs each enemy · best pick on the right",
                 font=self.f["body"], fg=C["muted"], bg=C["bg"]).pack(side="left", pady=(self.px(4), 0))
        filt = tk.StringVar()
        fbox = tk.Frame(head, bg=C["card"])
        fbox.pack(side="right")
        tk.Label(fbox, text="🔍", bg=C["card"], fg=C["muted"]).pack(side="left", padx=(self.px(6), 0))
        tk.Entry(fbox, textvariable=filt, bg=C["card"], fg=C["text"], insertbackground=C["text"], relief="flat",
                 font=self.f["body"], width=18, highlightthickness=0).pack(side="left", ipady=self.px(4), padx=self.px(6))
        self._legend(page)

        scroll = ScrollFrame(page, bg=C["panel"])
        scroll.pack(fill="both", expand=True, pady=(self.px(8), 0))
        grid = scroll.inner
        pad = {"padx": self.px(3), "pady": self.px(2)}

        tk.Label(grid, text="Enemy", fg=C["muted"], bg=C["panel"], font=self.f["small"]).grid(row=0, column=1, sticky="w", **pad)
        for j, champ in enumerate(mine):
            cell = tk.Frame(grid, bg=C["panel"])
            cell.grid(row=0, column=3 + j, **pad)
            photo = self.icons.get(champ, self.px(30))
            if photo:
                tk.Label(cell, image=photo, bg=C["panel"]).pack()
            tk.Label(cell, text=champ, fg=C["gold"], bg=C["panel"], font=self.f["small"]).pack()
        tk.Label(grid, text="Best pick", fg=C["muted"], bg=C["panel"], font=self.f["small"]).grid(
            row=0, column=4 + len(mine), sticky="w", padx=(self.px(16), 0))

        rows = []
        for enemy in enemies:
            widgets = []
            icon = tk.Label(grid, bg=C["panel"])
            name = tk.Label(grid, text=enemy, bg=C["panel"], font=self.f["h2"], anchor="w")
            widgets += [(icon, 0, {}), (name, 1, {"sticky": "w"})]
            cells = []  # (label, matchup)
            best = None
            for j, champ in enumerate(mine):
                m = lookup.get((champ, enemy))
                if m:
                    lbl = self._rating_badge(grid, m.rating, f"{m.rating}  {m.win_rate:.1f}%", width=11)
                    self._make_filter_click(lbl, m.rating)
                    cells.append((lbl, m))
                    if best is None or m.win_rate > best.win_rate:
                        best = m
                else:
                    lbl = tk.Label(grid, text="—" if champ == enemy else "N/A", bg=C["card"], fg=C["muted"],
                                   font=self.f["cell"], width=11)
                widgets.append((lbl, 3 + j, {"ipady": self.px(4)}))
            best_parts = None
            if best:
                bf = tk.Frame(grid, bg=C["panel"])
                b_icon = tk.Label(bf, bg=C["panel"])
                b_icon.pack(side="left")
                b_text = tk.Label(bf, text=f"{best.champ_playing}  {best.win_rate:.1f}%", bg=C["panel"], font=self.f["body"])
                b_text.pack(side="left", padx=self.px(6))
                widgets.append((bf, 4 + len(mine), {"sticky": "w", "padx": (self.px(16), 0)}))
                best_parts = (b_icon, b_text, best)

            def paint(enemy=enemy, icon=icon, name=name, cells=cells, best_parts=best_parts):
                row_on = any(self._shown(m.rating) for _l, m in cells) if self.rating_filter else True
                photo = self.icons.get(enemy, self.px(28), grey=not row_on)
                if photo:
                    icon.configure(image=photo)
                name.configure(fg=C["text"] if row_on else C["line"])
                for lbl, m in cells:
                    fill, font = RATING_STYLES[m.rating]
                    on = self._shown(m.rating)
                    lbl.configure(bg=f"#{fill}" if on else C["card"], fg=f"#{font}" if on else C["line"])
                if best_parts:
                    b_icon, b_text, best = best_parts
                    photo = self.icons.get(best.champ_playing, self.px(24), grey=not row_on)
                    if photo:
                        b_icon.configure(image=photo)
                    b_text.configure(fg=C["text"] if row_on else C["line"])

            self.filter_painters.append(paint)
            paint()
            rows.append((enemy, widgets))

        def layout(*_):
            q = champion_slug(filt.get())
            r = 1
            for enemy, widgets in rows:
                show = not q or q in champion_slug(enemy)
                for w, col, extra in widgets:
                    if show:
                        w.grid(row=r, column=col, **{**pad, **extra})
                    else:
                        w.grid_forget()
                r += 1 if show else 0
            scroll.to_top()

        filt.trace_add("write", layout)
        layout()
        if collect.get("failures"):
            tk.Label(page, text=f"{len(collect['failures'])} matchup(s) couldn't be scraped (N/A); see the terminal.",
                     fg=C["yellow"], bg=C["bg"], font=self.f["body"]).pack(anchor="w", pady=(self.px(6), 0))


def main() -> int:
    # A windowed .exe has no console: give print() somewhere harmless to go.
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
    if sys.platform == "win32":
        try:  # sharp text on high-DPI screens
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
        try:  # own taskbar entry + icon instead of Python's
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("MrVaxiZ.LoLMatchupChecker")
        except Exception:
            pass
    root = tk.Tk()
    App(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
