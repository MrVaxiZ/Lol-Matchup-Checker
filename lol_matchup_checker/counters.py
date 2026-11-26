"""Counter finder: give it a champion, get the champions that beat it, from u.gg.

Uses exactly the same scraping as `lol-matchup gen`: for every champion on the lane's
tier list it opens  u.gg/lol/champions/<target>/build/<lane>?opp=<candidate>  and reads
Win Rate + Matches. That page shows the target's win rate, so the candidate's win rate
against the target is 100 - value. The candidates with the highest win rate are the counters.

    lol-counters darius
    lol-counters vlad --lane mid --top 15
    python -m lol_matchup_checker.counters j4 elise --lane jg
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from .data import CHAMP_ALIASES, LANE_INPUTS, Lane, champion_slug, normalize_patch
from .models import Matchup, guess_name, resolve_champions

NA = "N/A"


# ------------------------------------------------------------------ pure helpers

@dataclass
class CounterResult:
    target: str
    lane: Lane
    matchups: list[Matchup]  # champ_playing = candidate, win_rate = candidate's WR vs target
    failures: list[tuple[str, str, str]] = field(default_factory=list)


def lane_pool(data, min_pick_rate: float) -> tuple[list[str], list[str]]:
    """(champions above the pick-rate cutoff, every champion with games) for one role's TierListData."""
    played = [e.name for e in data.entries if e.matches > 0]
    picked = [e.name for e in data.entries if e.pick_rate >= min_pick_rate]
    return picked, played


def detect_lane(raw: str, role_data: dict) -> tuple[Lane, str, dict[Lane, int]] | None:
    """The role the champion is played in most (by games), its display name and its games per role.
    role_data: Lane -> TierListData. None if the champion isn't in any role."""
    text = raw.strip()
    slug = champion_slug(CHAMP_ALIASES.get(text.lower(), text))
    games: dict[Lane, int] = {}
    name = None
    for lane, data in role_data.items():
        for e in data.entries:
            if champion_slug(e.name) == slug and e.matches > 0:
                games[lane] = e.matches
                name = e.name
    if not games:
        return None
    return max(games, key=games.get), name, games


def rank_counters(matchups: list[Matchup], min_matches: int) -> tuple[list[Matchup], list[Matchup]]:
    """(counters with enough games, best first; low-sample ones, best first)."""
    ordered = sorted(matchups, key=lambda m: (-m.win_rate, -m.matches))
    reliable = [m for m in ordered if m.matches >= min_matches]
    thin = [m for m in ordered if m.matches < min_matches]
    return reliable, thin


def format_report(result: CounterResult, top: int, min_matches: int, patch_label: str) -> str:
    reliable, thin = rank_counters(result.matchups, min_matches)
    lines = ["", f"=== Best counters vs {result.target} ({result.lane.value}, patch {patch_label}) ==="]
    if not reliable:
        lines.append(f"No matchups with at least {min_matches} games. Try --min-matches lower.")
    else:
        lines.append(f"{'#':>3}  {'Champion':<16}{'Win rate':>9}{'Matches':>10}  Rating")
        for i, m in enumerate(reliable[:top], start=1):
            lines.append(f"{i:>3}  {m.champ_playing:<16}{m.win_rate:>8.2f}%{m.matches:>10,}  {m.rating}")
        worst = [m for m in reversed(reliable) if m.win_rate < 50.0][:5]
        if worst:
            lines.append(f"Don't pick into {result.target}: "
                         + ", ".join(f"{m.champ_playing} ({m.win_rate:.1f}%)" for m in worst))
    thin_good = [m for m in thin if m.win_rate >= 51.0][:5]
    if thin_good:
        lines.append(f"Promising but under {min_matches} games: "
                     + ", ".join(f"{m.champ_playing} ({m.win_rate:.1f}%, {m.matches} games)" for m in thin_good))
    return "\n".join(lines)


def write_counters_excel(path: str | Path, results: list[CounterResult], min_matches: int,
                         patch_label: str | None = None) -> Path:
    """One sheet per target champion, counters sorted best first, colour-coded like Matchups.xlsx."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    from .excel import RATING_STYLES, _autofit

    path = Path(path)
    if path.suffix.lower() != ".xlsx":
        path = path.with_name(path.name + ".xlsx")

    wb = Workbook()
    wb.remove(wb.active)
    used: set[str] = set()
    for result in results:
        title = f"{result.target} {result.lane.value}"
        for ch in "[]:*?/\\":
            title = title.replace(ch, "")
        title = title[:31]
        n = 2
        while title in used:
            title = f"{title[:28]} {n}"
            n += 1
        used.add(title)
        ws = wb.create_sheet(title)

        ws.append([f"Counters vs {result.target} ({result.lane.value})"
                   + (f" - Patch {patch_label}" if patch_label else "")])
        ws["A1"].font = Font(bold=True, size=13)
        ws.append([f"Win rate = the counter's win rate against {result.target}. "
                   f"Grey rows have fewer than {min_matches} games."])
        ws["A2"].font = Font(italic=True, color="666666")
        ws.append(["#", "Counter", "Win Rate %", "Matches", "Rating"])
        for cell in ws[3]:
            cell.font = Font(bold=True)

        reliable, thin = rank_counters(result.matchups, min_matches)
        for i, m in enumerate(reliable, start=1):
            ws.append([i, m.champ_playing, m.win_rate, m.matches, m.rating])
            fill, font = RATING_STYLES[m.rating]
            cell = ws.cell(row=ws.max_row, column=5)
            cell.fill = PatternFill("solid", start_color=fill, end_color=fill)
            cell.font = Font(color=font, bold=True)
        for m in thin:
            ws.append(["", m.champ_playing, m.win_rate, m.matches, m.rating])
            for cell in ws[ws.max_row]:
                cell.font = Font(color="999999", italic=True)
        for playing, _against, reason in result.failures:
            ws.append(["", playing, NA, NA, NA])
            ws.cell(row=ws.max_row, column=6, value=reason).font = Font(color="999999", italic=True)

        ws.auto_filter.ref = f"A3:E{max(ws.max_row, 3)}"
        ws.freeze_panes = "A4"
        _autofit(ws)
        ws.column_dimensions["A"].width = 5  # the long title in A1 shouldn't widen the rank column

    wb.save(path)
    return path.resolve()


# ----------------------------------------------------------------------- CLI

def _patch_arg(text: str) -> str:
    try:
        return normalize_patch(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from None


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="lol-counters",
        description="Finds the champions that counter the given champion(s), using u.gg matchup data.",
        epilog="Example: lol-counters darius   |   lol-counters vlad --lane mid --top 15",
    )
    p.add_argument("champs", nargs="+", metavar="CHAMP", help="Champion(s) to find counters for (names or aliases).")
    p.add_argument("--lane", "--role", type=str.lower, choices=sorted(LANE_INPUTS), metavar="LANE", default=None,
                   help="top, jg, mid, adc or sup. Default: the role the champion is played in most.")
    p.add_argument("--top", type=int, default=10, help="How many counters to print (default: 10). Excel has all.")
    p.add_argument("--min-matches", type=int, default=100,
                   help="Matchups with fewer games are listed separately as low-sample (default: 100).")
    p.add_argument("--out", default="Counters.xlsx", help="Excel output path (default: Counters.xlsx).")
    p.add_argument("--no-excel", action="store_true", help="Only print the results, don't write Excel.")
    p.add_argument("--patch", type=_patch_arg, default=None, metavar="PATCH",
                   help="Patch to pull data for, e.g. 26.18 (default: latest).")
    p.add_argument("--min-pick-rate", type=float, default=0.5, metavar="PERCENT",
                   help="Only check champions picked in at least this %% of the lane's games (default: 0.5).")
    p.add_argument("--workers", type=int, default=4, help="Pages scraped in parallel (default: 4).")
    p.add_argument("--retries", type=int, default=3, help="Attempts per page (default: 3).")
    p.add_argument("--timeout", type=int, default=60, help="Seconds per page (default: 60).")
    p.add_argument("--show-browser", action="store_true", help="Run the browser visibly.")
    p.add_argument("--real-chrome", action="store_true", help="Use your installed Google Chrome.")
    p.add_argument("--browser-path", help="Path to a specific Chromium/Chrome executable.")
    p.add_argument("--no-block-ads", action="store_true", help="Don't block ad/tracker requests.")
    p.add_argument("--no-cache", action="store_true",
                     help="Scrape every page again instead of reusing results saved earlier on this patch.")
    p.add_argument("--cache-hours", type=float, default=24.0, metavar="HOURS",
                     help="Reuse saved results up to this old (default: 24).")
    p.add_argument("--debug", action="store_true", help="Verbose logs; saves the HTML of failed pages into ./debug.")
    return p


def _quiet_tier_log(msg: str) -> None:
    # The tier list loader prints every champion it finds; that's noise here.
    if "Found champion :" in msg or msg.startswith("Found total of"):
        return
    print(msg)


async def run(args: argparse.Namespace, collect: dict | None = None) -> int:
    """`collect`, if given, receives the results (used by the GUI)."""
    from .parsing import parse_tier_list_data
    from .scraper import ScraperOptions, UggScraper

    started = time.monotonic()
    forced_lane = LANE_INPUTS[args.lane] if args.lane else None
    options = ScraperOptions(
        workers=max(1, args.workers), retries=max(1, args.retries), timeout_s=max(10, args.timeout),
        headless=not args.show_browser, real_chrome=args.real_chrome, executable_path=args.browser_path,
        block_ads=not args.no_block_ads, debug=args.debug, patch=args.patch,
        min_pick_rate=max(0.0, args.min_pick_rate),
        use_cache=not args.no_cache, cache_hours=max(0.0, args.cache_hours),
    )
    results: list[CounterResult] = []

    print(f"Patch: {args.patch}" if args.patch else "Patch: latest")
    async with UggScraper(options, log=_quiet_tier_log) as scraper:
        # Any tier-list page carries u.gg's data for all five roles.
        base_champs = await scraper.get_lane_champions(forced_lane or Lane.TOP)
        base_all = list(scraper.lane_all_champions)
        patch_label = scraper.patch_shown or args.patch or "latest"
        if scraper.patch_shown:
            print(f"u.gg is showing data for patch {scraper.patch_shown}.")

        role_data = {}
        if scraper.last_tier_page is not None:
            for lane in Lane:
                data = parse_tier_list_data(scraper.last_tier_page, lane.value)
                if data and data.entries:
                    role_data[lane] = data

        for raw in args.champs:
            # ---- which lane
            if forced_lane:
                lane = forced_lane
            else:
                found = detect_lane(raw, role_data)
                if found is None:
                    print(f"\n'{raw}': couldn't find which role it's played in on u.gg (typo?). "
                          "Pass --lane to choose one. Skipping.")
                    continue
                lane, name, games = found
                share = 100.0 * games[lane] / sum(games.values())
                others = ", ".join(f"{l.value} {100.0 * g / sum(games.values()):.0f}%"
                                   for l, g in sorted(games.items(), key=lambda kv: -kv[1]) if l != lane and g)
                print(f"\n{name} is played {lane.value} in {share:.0f}% of games"
                      + (f" (also: {others})" if others else "") + f". Finding {lane.value} counters "
                      "(use --lane for another role).")

            # ---- who to check, and the target's exact name
            if lane in role_data:
                candidates, played = lane_pool(role_data[lane], options.min_pick_rate)
            else:  # embedded data missing: only the lane we fetched is known
                candidates, played = base_champs, base_all or base_champs
            resolved, _ = resolve_champions([raw], played)
            if resolved:
                target = resolved[0]
            else:
                target = guess_name(raw)
                if not await scraper.champion_has_page(lane, target):
                    print(f"'{raw}' -> {target}: no u.gg {lane.value} page found (typo?). Skipping.")
                    continue
                print(f"{target} isn't on the u.gg {lane.value} tier list, but has a page there. Matchup data may be thin.")

            if lane in role_data:
                entry = next((e for e in role_data[lane].entries if e.name == target), None)
                if entry is not None and entry.pick_rate < options.min_pick_rate:
                    print(f"Note: {target} has only {entry.matches:,} {lane.value} games, results may be noisy.")

            opponents = [c for c in candidates if c != target]
            if not opponents:
                print(f"No {lane.value} champions to check against {target}.")
                continue
            print(f"Checking {len(opponents)} {lane.value} champions against {target} "
                  f"(pick rate >= {options.min_pick_rate}%)...")

            # Same pages as `gen`: <target>/build/<lane>?opp=<candidate>
            matchups, failures = await scraper.get_matchups(lane, [target], opponents)
            result = CounterResult(target, lane, matchups, failures)
            results.append(result)
            print(format_report(result, max(1, args.top), max(0, args.min_matches), patch_label))
            if failures:
                print(f"{len(failures)} matchup(s) could not be scraped"
                      + ("." if args.debug else " (re-run with --debug to save their HTML)."))

    if not results:
        print("Nothing found.")
        return 1
    path = None
    if not args.no_excel:
        path = write_counters_excel(args.out, results, max(0, args.min_matches), patch_label)
        print(f"\nExcel saved to : \n'{path}'")
    if collect is not None:
        collect.update(results=results, patch=patch_label, min_matches=max(0, args.min_matches), excel=path)

    elapsed = int(time.monotonic() - started)
    print(f"Program was running for : [{elapsed // 3600:02}:{elapsed % 3600 // 60:02}:{elapsed % 60:02}]")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    from .scraper import ScrapeError

    try:
        return asyncio.run(run(args))
    except ScrapeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
