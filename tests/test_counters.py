"""Offline tests for the counter finder (no network/browser: the scraper is faked)."""

from pathlib import Path

from openpyxl import load_workbook
from scrapling.parser import Selector

from lol_matchup_checker import counters
from lol_matchup_checker.data import Lane
from lol_matchup_checker.models import Matchup
from lol_matchup_checker.parsing import parse_tier_list_data

FIXTURES = Path(__file__).parent / "fixtures"


def ssr_page() -> Selector:
    return Selector((FIXTURES / "tier_list_ssr.html").read_text(encoding="utf-8"))


def role_data():
    page = ssr_page()
    out = {}
    for lane in Lane:
        data = parse_tier_list_data(page, lane.value)
        if data and data.entries:
            out[lane] = data
    return out


def test_detect_lane_picks_role_with_most_games():
    lane, name, games = counters.detect_lane("teemo", role_data())
    assert (lane, name) == (Lane.TOP, "Teemo")
    assert games == {Lane.JG: 10741, Lane.TOP: 50000}


def test_detect_lane_alias_and_unknown():
    assert counters.detect_lane("j4", role_data())[:2] == (Lane.JG, "Jarvan IV")
    assert counters.detect_lane("robal", role_data())[1] == "Kha'Zix"
    assert counters.detect_lane("notachamp", role_data()) is None


def test_lane_pool_applies_pick_rate_cutoff():
    picked, played = counters.lane_pool(role_data()[Lane.JG], 0.5)
    assert "Teemo" not in picked and "Annie" not in picked  # 0.49% and 0.001%
    assert "Nunu & Willump" in picked  # exactly 0.5%
    assert len(played) == 8


def test_rank_counters_orders_and_splits_low_sample():
    ms = [Matchup("A", "X", 500, 52.0), Matchup("B", "X", 50, 60.0), Matchup("C", "X", 900, 55.5),
          Matchup("D", "X", 300, 45.0)]
    reliable, thin = counters.rank_counters(ms, 100)
    assert [m.champ_playing for m in reliable] == ["C", "A", "D"]
    assert [m.champ_playing for m in thin] == ["B"]


def test_report_text():
    r = counters.CounterResult("Darius", Lane.TOP, [Matchup("Quinn", "Darius", 800, 54.2),
                                                    Matchup("Garen", "Darius", 900, 47.1),
                                                    Matchup("Vayne", "Darius", 40, 58.0)])
    text = counters.format_report(r, top=10, min_matches=100, patch_label="26.23")
    assert "Best counters vs Darius (top, patch 26.23)" in text
    assert text.index("Quinn") < text.index("Garen")
    assert "Don't pick into Darius: Garen (47.1%)" in text
    assert "Vayne (58.0%, 40 games)" in text


def test_counters_excel(tmp_path):
    r = counters.CounterResult("Kha'Zix", Lane.JG, [Matchup("Elise", "Kha'Zix", 800, 54.2),
                                                    Matchup("Rammus", "Kha'Zix", 20, 70.0)],
                               failures=[("Lee Sin", "Kha'Zix", "timeout")])
    out = counters.write_counters_excel(tmp_path / "c", [r], 100, "26.23")
    assert out.name == "c.xlsx"
    ws = load_workbook(out)["Kha'Zix jungle"]
    assert ws["A1"].value == "Counters vs Kha'Zix (jungle) - Patch 26.23"
    rows = [[c.value for c in row[:5]] for row in ws.iter_rows(min_row=4)]
    assert rows == [[1, "Elise", 54.2, 800, "D"], [None, "Rammus", 70.0, 20, "UD"],
                    [None, "Lee Sin", "N/A", "N/A", "N/A"]]
    assert ws["E4"].fill.start_color.rgb.endswith("008000")


class FakeScraper:
    """Stands in for UggScraper: tier page from the fixture, made-up matchup numbers."""
    calls = []

    def __init__(self, options, log=print):
        self.opt = options
        self.patch_shown = "26.21"
        self.lane_all_champions = []
        self.last_tier_page = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        pass

    async def get_lane_champions(self, lane):
        self.last_tier_page = ssr_page()
        return []

    async def champion_has_page(self, lane, name):
        return False

    async def get_matchups(self, lane, lane_champions, my_champs):
        FakeScraper.calls.append((lane, list(lane_champions), list(my_champs)))
        (target,) = lane_champions
        wr = {"Teemo": 55.0, "Elise": 53.0}
        return [Matchup(c, target, 1000, wr.get(c, 48.0)) for c in my_champs], []


def test_full_run_with_fake_scraper(tmp_path, monkeypatch, capsys):
    from lol_matchup_checker import scraper
    monkeypatch.setattr(scraper, "UggScraper", FakeScraper)
    FakeScraper.calls.clear()

    out = tmp_path / "Counters.xlsx"
    assert counters.main(["robal", "--out", str(out)]) == 0

    lane, targets, checked = FakeScraper.calls[0]
    assert lane == Lane.JG and targets == ["Kha'Zix"]  # role auto-detected from the tier data
    assert "Kha'Zix" not in checked and "Teemo" not in checked  # self and below-cutoff excluded
    text = capsys.readouterr().out
    assert "Kha'Zix is played jungle in 100% of games" in text
    assert text.index("Elise") < text.index("Lee Sin")
    assert load_workbook(out).sheetnames == ["Kha'Zix jungle"]


def test_forced_lane(tmp_path, monkeypatch):
    from lol_matchup_checker import scraper
    monkeypatch.setattr(scraper, "UggScraper", FakeScraper)
    FakeScraper.calls.clear()
    assert counters.main(["teemo", "--lane", "jg", "--no-excel"]) == 0
    assert FakeScraper.calls[0][0] == Lane.JG


def test_route_errors_are_swallowed():
    """The ad-blocking route handler must not let 'Route.continue_: Assertion error' escape."""
    import asyncio
    import sys

    from lol_matchup_checker.scraper import _quiet_route_errors

    _quiet_route_errors()
    _quiet_route_errors()  # idempotent
    patched = [m for n, m in sys.modules.items()
               if n.startswith("scrapling.") and hasattr(m, "create_async_intercept_handler")]
    assert patched and all(getattr(m.create_async_intercept_handler, "_lmc_safe", False) for m in patched)

    class Request:
        resource_type = "script"
        url = "https://ads.example.com/x.js"

    class Route:
        request = Request()

        async def continue_(self):
            raise RuntimeError("Route.continue_: Assertion error")

        async def abort(self):
            raise RuntimeError("Route.abort: Assertion error")

    handler = patched[0].create_async_intercept_handler(True, {"example.com"})
    asyncio.run(handler(Route()))  # must not raise
