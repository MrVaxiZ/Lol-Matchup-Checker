"""Saved results + 'A vs B is B vs A' de-duplication (no browser: page fetching is faked)."""

import asyncio

from lol_matchup_checker.cache import MatchupCache, pair_key
from lol_matchup_checker.data import Lane
from lol_matchup_checker.models import Matchup
from lol_matchup_checker.scraper import ScraperOptions, UggScraper


class Clock:
    def __init__(self, t=1_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


def test_pair_key_is_order_independent():
    k1, f1 = pair_key("26.23", "jungle", "Sylas", "Kha'Zix")
    k2, f2 = pair_key("26.23", "jungle", "Kha'Zix", "Sylas")
    assert k1 == k2 == "26.23|jungle|khazix|sylas"
    assert (f1, f2) == (True, False)


def test_cache_answers_both_directions(tmp_path):
    cache = MatchupCache(tmp_path / "c.json")
    cache.put("26.23", "jungle", Matchup("Sylas", "Kha'Zix", 2182, 47.57))  # from your real run
    cache.save()
    again = MatchupCache(tmp_path / "c.json")
    m = again.get("26.23", "jungle", "Kha'Zix", "Sylas")
    assert (m.champ_playing, m.champ_against, m.matches, m.win_rate) == ("Kha'Zix", "Sylas", 2182, 52.43)
    assert again.get("26.23", "jungle", "Sylas", "Kha'Zix").win_rate == 47.57
    assert again.get("26.23", "top", "Sylas", "Kha'Zix") is None  # other lane
    assert again.get("26.24", "jungle", "Sylas", "Kha'Zix") is None  # other patch


def test_cache_expires(tmp_path):
    clock = Clock()
    cache = MatchupCache(tmp_path / "c.json", max_age_hours=24, clock=clock)
    cache.put("26.23", "mid", Matchup("Ahri", "Zed", 100, 51.0))
    clock.t += 23 * 3600
    assert cache.get("26.23", "mid", "Ahri", "Zed") is not None
    clock.t += 2 * 3600
    assert cache.get("26.23", "mid", "Ahri", "Zed") is None


def test_cache_keeps_only_recent_patches(tmp_path):
    cache = MatchupCache(tmp_path / "c.json")
    for patch in ("26.9", "26.22", "26.23"):
        cache.put(patch, "top", Matchup("Darius", "Garen", 10, 50.0))
    cache.save()
    assert {k.split("|")[0] for k in MatchupCache(tmp_path / "c.json").entries} == {"26.22", "26.23"}


def test_cache_survives_broken_file(tmp_path):
    (tmp_path / "c.json").write_text("{oops", encoding="utf-8")
    assert MatchupCache(tmp_path / "c.json").entries == {}


def make_scraper(tmp_path, use_cache=True):
    scraper = UggScraper(ScraperOptions(use_cache=use_cache, cache_path=tmp_path / "c.json"), log=lambda m: None)
    scraper.patch_shown = "26.23"
    scraper.fetched = []
    true_wr = {("Sylas", "Kha'Zix"): 47.57, ("Jarvan IV", "Sylas"): 49.56, ("Elise", "Jarvan IV"): 49.69}

    async def fake_fetch(lane, against, playing):
        scraper.fetched.append((playing, against))
        wr = true_wr.get((playing, against))
        if wr is None:
            wr = 100 - true_wr.get((against, playing), 50.0)
        return Matchup(playing, against, 1000, round(wr, 2))

    scraper._fetch_matchup = fake_fetch
    return scraper


def test_get_matchups_opens_each_pair_once(tmp_path):
    scraper = make_scraper(tmp_path, use_cache=False)
    mine = ["Jarvan IV", "Elise", "Kha'Zix", "Sylas"]
    lane = mine + ["Lee Sin", "Viego"]
    matchups, failures = asyncio.run(scraper.get_matchups(Lane.JG, lane, mine))
    assert not failures
    assert len(matchups) == 4 * 5  # every requested direction is in the results...
    assert len(scraper.fetched) == 4 * 5 - 6  # ...but the 6 pairs among my champs were opened once
    got = {(m.champ_playing, m.champ_against): m.win_rate for m in matchups}
    assert got[("Sylas", "Kha'Zix")] == 47.57 and got[("Kha'Zix", "Sylas")] == 52.43


def test_second_run_uses_saved_results(tmp_path):
    first = make_scraper(tmp_path)
    asyncio.run(first.get_matchups(Lane.JG, ["Lee Sin", "Viego", "Sylas"], ["Sylas"]))
    assert len(first.fetched) == 2

    second = make_scraper(tmp_path)  # new run, same patch
    matchups, _ = asyncio.run(second.get_matchups(Lane.JG, ["Lee Sin", "Viego", "Sylas", "Elise"], ["Sylas", "Elise"]))
    # Sylas vs Lee Sin/Viego are saved; Elise vs Sylas also answers Sylas vs Elise
    assert len(second.fetched) == 3
    assert {("Elise", "Lee Sin"), ("Elise", "Viego")} <= set(second.fetched)
    assert {frozenset(f) for f in second.fetched} >= {frozenset({"Elise", "Sylas"})}  # either direction, once
    assert len(matchups) == 6

    third = make_scraper(tmp_path, use_cache=False)  # --no-cache scrapes everything again
    asyncio.run(third.get_matchups(Lane.JG, ["Lee Sin", "Viego", "Sylas"], ["Sylas"]))
    assert len(third.fetched) == 2


def test_no_cache_without_known_patch(tmp_path):
    scraper = make_scraper(tmp_path)
    scraper.patch_shown = None
    asyncio.run(scraper.get_matchups(Lane.JG, ["Lee Sin"], ["Sylas"]))
    assert not (tmp_path / "c.json").exists()
