"""Saved matchup results, so re-runs on the same patch don't scrape pages again.

One entry per champion *pair* per patch and lane: "A vs B" and "B vs A" are the same u.gg data
seen from opposite sides (the two win rates add up to 100), so either direction is answered
from one entry. Entries expire after `max_age_hours` because u.gg keeps adding games during a patch.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from .data import champion_slug
from .models import Matchup

_VERSION = 1
KEEP_PATCHES = 2  # older patches are dropped when saving


def app_data_dir() -> Path:
    """%LOCALAPPDATA%\\lol-matchup-checker on Windows, ~/.cache/lol-matchup-checker elsewhere."""
    base = os.environ.get("LOCALAPPDATA") or (Path.home() / ".cache")
    path = Path(base) / "lol-matchup-checker"
    path.mkdir(parents=True, exist_ok=True)
    return path


def pair_key(patch: str, lane: str, a: str, b: str) -> tuple[str, bool]:
    """(key, flipped): the key names the pair alphabetically by slug; flipped=True if `a` is second."""
    sa, sb = champion_slug(a), champion_slug(b)
    first, second = sorted((sa, sb))
    return f"{patch}|{lane}|{first}|{second}", sa != first


def _patch_tuple(patch: str) -> tuple[int, ...]:
    try:
        return tuple(int(x) for x in patch.split("."))
    except ValueError:
        return (0,)


class MatchupCache:
    def __init__(self, path: Path | None = None, max_age_hours: float = 24.0, clock=time.time):
        self.path = path or (app_data_dir() / "matchup_cache.json")
        self.max_age = max_age_hours * 3600.0
        self.clock = clock
        self.entries: dict[str, list] = {}  # key -> [win rate of the alphabetically-first champ, matches, saved at]
        self.dirty = False
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if data.get("version") == _VERSION and isinstance(data.get("entries"), dict):
                self.entries = data["entries"]
        except (OSError, ValueError, AttributeError):
            pass

    def get(self, patch: str, lane: str, playing: str, against: str) -> Matchup | None:
        key, flipped = pair_key(patch, lane, playing, against)
        entry = self.entries.get(key)
        if not entry:
            return None
        try:
            win_rate, matches, saved_at = float(entry[0]), int(entry[1]), float(entry[2])
        except (TypeError, ValueError, IndexError):
            return None
        if self.clock() - saved_at > self.max_age:
            return None
        return Matchup(playing, against, matches, round(100.0 - win_rate if flipped else win_rate, 2))

    def put(self, patch: str, lane: str, m: Matchup) -> None:
        key, flipped = pair_key(patch, lane, m.champ_playing, m.champ_against)
        win_rate = round(100.0 - m.win_rate if flipped else m.win_rate, 2)
        self.entries[key] = [win_rate, m.matches, self.clock()]
        self.dirty = True

    def save(self) -> None:
        if not self.dirty:
            return
        patches = sorted({k.split("|", 1)[0] for k in self.entries}, key=_patch_tuple, reverse=True)
        keep = set(patches[:KEEP_PATCHES])
        self.entries = {k: v for k, v in self.entries.items() if k.split("|", 1)[0] in keep}
        try:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"version": _VERSION, "entries": self.entries}), encoding="utf-8")
            os.replace(tmp, self.path)
            self.dirty = False
        except OSError:
            pass
