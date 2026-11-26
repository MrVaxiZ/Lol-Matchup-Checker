"""GUI plumbing tests that don't need a display: log forwarding and the background job."""

import queue

import pytest

pytest.importorskip("tkinter")

from lol_matchup_checker import gui, scraper  # noqa: E402
from test_counters import FakeScraper  # noqa: E402


def drain(events: queue.Queue, timeout: float = 10.0):
    out = []
    while True:
        item = events.get(timeout=timeout)
        out.append(item)
        if item[0] == "done":
            return out


def test_queue_writer_splits_lines():
    q = queue.Queue()
    w = gui.QueueWriter(q)
    w.write("one\ntw")
    w.write("o\n")
    w.write("three")
    w.flush()
    assert [q.get_nowait()[1] for _ in range(3)] == ["one", "two", "three"]


def test_job_runs_counters_and_returns_results(tmp_path, monkeypatch):
    monkeypatch.setattr(scraper, "UggScraper", FakeScraper)
    events = queue.Queue()
    gui.Job("counters", ["Kha'Zix", "--out", str(tmp_path / "c.xlsx")], events).start()
    items = drain(events)
    kind, code, collect, stopped = items[-1]
    assert (code, stopped) == (0, False)
    assert collect["results"][0].target == "Kha'Zix"
    assert collect["excel"].exists()
    logs = [i[1] for i in items if i[0] == "log"]
    assert any(line.startswith("=== Best counters vs Kha'Zix") for line in logs)


def test_job_bad_patch_reports_error(monkeypatch):
    monkeypatch.setattr(scraper, "UggScraper", FakeScraper)
    events = queue.Queue()
    gui.Job("counters", ["Elise", "--patch", "nope"], events).start()
    items = drain(events)
    assert items[-1][1] == 1
    assert any("invalid options" in i[1] for i in items if i[0] == "log")


def test_settings_remember_and_forget(tmp_path):
    path = tmp_path / "settings.json"
    s = gui.Settings(path)
    assert not s.remember
    s.save(True, {"matchups": {"lane": "jg", "champs": ["Elise", "Kha'Zix"]}}, {"workers": "2"})
    again = gui.Settings(path)
    assert again.remember
    assert again.data["picks"]["matchups"]["champs"] == ["Elise", "Kha'Zix"]
    again.save(False, {"matchups": {"lane": "jg", "champs": ["Elise"]}})
    assert gui.Settings(path).data == {"remember": False}  # unticking forgets the picks


def test_settings_survive_a_broken_file(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{not json", encoding="utf-8")
    assert gui.Settings(path).data == {}


def test_fmt_duration():
    assert gui.fmt_duration(5) == "5s"
    assert gui.fmt_duration(65) == "1m 05s"
    assert gui.fmt_duration(3725) == "1h 02m"
    assert gui.fmt_duration(-3) == "0s"


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def test_eta_tracker_single_phase():
    clock = Clock()
    eta = gui.EtaTracker(1, clock)
    clock.t = 30  # tier list loading
    eta.new_phase()
    clock.t = 32
    eta.progress(1, 50)
    assert eta.remaining() is None  # too early to guess
    clock.t = 40
    eta.progress(5, 50)  # 2 s per page -> 45 pages left -> 90 s
    assert eta.remaining() == 90
    clock.t = 50
    assert eta.remaining() == 80  # counts down between updates
    assert eta.elapsed() == 50


def test_eta_tracker_counts_later_phases():
    clock = Clock()
    eta = gui.EtaTracker(2, clock)
    eta.new_phase()
    clock.t = 10
    eta.progress(10, 40)  # 1 s/page: 30 s left now + 40 s for the second champion
    assert eta.remaining() == 70
    eta.new_phase()
    clock.t = 30
    eta.progress(20, 40)
    assert eta.remaining() == 20  # last phase: nothing extra


def test_chimes_are_valid_quiet_wavs():
    import io
    import struct
    import wave

    for kind in ("done", "error"):
        data = gui.make_chime(kind, rate=8000)
        with wave.open(io.BytesIO(data)) as w:
            assert (w.getnchannels(), w.getsampwidth()) == (1, 2)
            assert 1.0 < w.getnframes() / w.getframerate() < 2.0
            frames = w.readframes(w.getnframes())
        peak = max(abs(v) for v in struct.unpack(f"<{len(frames) // 2}h", frames))
        assert 0.25 * 32767 < peak < 0.4 * 32767  # audible but nowhere near full volume
