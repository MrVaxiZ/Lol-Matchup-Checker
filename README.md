<p align="center">
  <img src="lol_matchup_checker/assets/icon.png" width="120" alt="LoL Matchup Checker icon">
</p>

<h1 align="center">LoL Matchup Checker</h1>

<p align="center">
  <b>Find who counters your enemy, or see how your champions do against every laner.</b><br>
  Live win rates from <a href="https://u.gg">u.gg</a>, colour-coded and saved to Excel.
</p>

<p align="center">
  <a href="https://github.com/MrVaxiZ/Lol-Matchup-Checker/releases/latest/download/LoL-Matchup-Checker.exe"><b>⬇ Download for Windows</b></a>
  &nbsp;·&nbsp; <a href="#-how-to-use">How to use</a>
  &nbsp;·&nbsp; <a href="#-ratings">Ratings</a>
  &nbsp;·&nbsp; <a href="#-faq">FAQ</a>
</p>

---

## ⚡ Get started

**You only need one file.**

1. Download **[LoL-Matchup-Checker.exe](https://github.com/MrVaxiZ/Lol-Matchup-Checker/releases/latest/download/LoL-Matchup-Checker.exe)**.
2. Double-click it.

No Python and nothing else to install. The first time you press **START**, the app downloads the browser it needs (one time, about 150 MB) and shows the progress in its terminal.

> **"Windows protected your PC"?** Click **More info → Run anyway**. Windows shows this for any app that isn't code-signed.

---

## 🎮 How to use

| | |
|---|---|
| **1. Pick a mode** | **Find counters**: who beats an enemy champion. **Matchup sheet**: your champions vs every laner. |
| **2. Pick a lane** | Top, Jungle, Mid, ADC or Support. *Counters* also has **Auto** (the role the champion is played in most). |
| **3. Pick champions** | Click the icons, or type to search (`j4`, `robal`, `ksante` work too) and press **Enter**. |
| **4. Press START** | Watch the progress, the time left and the log. **Stop** cancels the run. |
| **5. Read the results** | Click a rating like **D+** to highlight only those; click it again to show all. **Open Excel** opens the saved file. |

- **Remember my picks** keeps your champions and settings for next time.
- Results are saved, so running again on the same patch only loads what's new.
- Excel files go to **Documents\LoL Matchup Checker**.

---

## 🎨 Ratings

Your win rate in the matchup:

| Rating | Meaning | Win rate |
|:---:|---|:---:|
| 🟥 `-` | Don't pick | below 49% |
| 🟨 `S` | Skill matchup | 49–51% |
| 🟩 `+` | Good pick | 51–53% |
| 🟢 `D` | Distinguished | 53–55% |
| 🔵 `D+` | Distinguished plus | 55–60% |
| 🟣 `UD` | Ultra distinguished | 60%+ |

Matchups with few games (under 100 by default) are shown greyed out, because there isn't enough data to trust them.

---

## ❓ FAQ

<details>
<summary><b>It's stuck on "Opening u.gg" / pages keep failing</b></summary>

u.gg sits behind Cloudflare. Tick **Show browser** (or **Use my Chrome**) and/or lower **Tabs** to 2, then try again.
</details>

<details>
<summary><b>How do I get fresh numbers?</b></summary>

Results are reused for 24 hours on the same patch. Untick **Use saved results** to scrape everything again.
</details>

<details>
<summary><b>Where does the app keep its files?</b></summary>

| What | Where |
|---|---|
| Excel files | `Documents\LoL Matchup Checker` |
| Settings, saved results, champion icons | `%LOCALAPPDATA%\lol-matchup-checker` |
| Browser (downloaded once) | `%LOCALAPPDATA%\ms-playwright` |

To remove everything, delete the .exe and those folders.
</details>

<details>
<summary><b>The app starts slowly</b></summary>

A one-file .exe unpacks itself on every start, which takes a few seconds. After that it's quick.
</details>

<details>
<summary><b>A champion I want isn't on the list for a lane</b></summary>

By default, only champions picked in at least 0.5% of that lane's games are checked, the same as u.gg's tier list. Lower **Min pick %** (0 = everyone).
</details>

---

## 🧑‍💻 For developers

<details>
<summary><b>Run from source</b></summary>

Needs Python 3.10+.

```bash
git clone https://github.com/MrVaxiZ/Lol-Matchup-Checker
cd Lol-Matchup-Checker
pip install -r requirements.txt
scrapling install          # one-time browser download
```

Then double-click **`gui.cmd`**, or run `python -m lol_matchup_checker.gui`.
</details>

<details>
<summary><b>Command line</b></summary>

```bash
# Matchup sheet: your champions vs every jungler -> Matchups.xlsx
python -m lol_matchup_checker gen --lane jg --champs elise j4 robal sylas

# Counters: who beats Darius (role auto-detected) -> Counters.xlsx
python -m lol_matchup_checker.counters darius
python -m lol_matchup_checker.counters vlad --lane mid --top 15

# List champion aliases
python -m lol_matchup_checker alias
```

After `pip install -e .` the shortcuts `lol-matchup`, `lol-counters` and `lol-matchup-gui` work too.

| Option | What it does | Default |
|---|---|---|
| `--lane` | `top`, `jg`, `mid`, `adc`, `sup` (counters: optional, auto-detected) | |
| `--patch 26.18` | Data for a specific patch | latest |
| `--min-pick-rate` | Only check opponents picked in at least this % of games | `0.5` |
| `--workers` | Pages loaded in parallel; lower it if you get blocked | `4` |
| `--no-cache` / `--cache-hours` | Ignore saved results / how long they stay fresh | `24` h |
| `--show-browser` / `--real-chrome` | Help against Cloudflare | off |
| `--out` | Excel file path | `Matchups.xlsx` / `Counters.xlsx` |
| `--top` / `--min-matches` | *Counters:* how many to print / low-sample cutoff | `10` / `100` |
| `--retries` / `--timeout` / `--debug` | Attempts per page / seconds per page / save failing pages to `./debug` | `3` / `60` / off |
</details>

<details>
<summary><b>Build the .exe</b></summary>

- **On your PC:** double-click **`build_exe.cmd`**. It produces `dist\LoL Matchup Checker.exe` and runs a self-test.
- **Publish a release:** commit your changes, then double-click **`release.cmd`** and type the new version (e.g. `2.1.0`). It updates the version number, commits, tags and pushes. GitHub Actions (`.github/workflows/build-exe.yml`) then builds the exe on Windows, writes the release notes (download section, your commit messages since the last version, a checksum) and publishes the release as `LoL-Matchup-Checker.exe`, which is the file the download link above points to.

The icon is drawn by `packaging/make_icon.py`. `"LoL Matchup Checker.exe" --selftest` writes `selftest.txt` listing what was bundled.
</details>

<details>
<summary><b>How it works</b></summary>

1. Opens the lane's u.gg tier list with [Scrapling](https://github.com/D4Vinci/Scrapling)'s stealth browser, which gets through Cloudflare. It reads the data embedded in the page: every champion in every role, with pick rates and the current patch.
2. For each matchup it opens `u.gg/lol/champions/<enemy>/build/<lane>?opp=<champion>` and reads **Win Rate** and **Matches**. That page shows the enemy's win rate, so yours is `100 − value`.
3. "A vs B" and "B vs A" are the same page seen from both sides, so each pair is loaded once. Results are saved per patch and lane and reused for 24 hours.
4. Several browser tabs share one Cloudflare clearance and run in parallel.
</details>

<details>
<summary><b>Project layout and tests</b></summary>

```
lol_matchup_checker/
├── gui.py        desktop app
├── cli.py        `gen` / `alias` commands (matchup sheet)
├── counters.py   counter finder
├── scraper.py    u.gg scraping (Scrapling), retries, Cloudflare
├── parsing.py    reading u.gg pages
├── cache.py      saved results
├── browser.py    first-run browser download
├── excel.py      Excel export
├── models.py     ratings, champion names
├── data.py       lanes, aliases, URLs, patches
└── assets/       app icon
packaging/        .exe build (PyInstaller spec, entry script, icon)
tests/            offline tests, no internet needed
```

Run the tests with `pip install pytest` and then `pytest`.
</details>

---

<p align="center">
  Made by <a href="https://github.com/MrVaxiZ">MrVaxiZ</a> · MIT License · GLHF on the Rift!<br>
  <sub>Not affiliated with Riot Games or u.gg. Champion icons © Riot Games.</sub>
</p>

<p align="center">
  <sub>☕ If you enjoy the app and would like to support me, <a href="#https://buymeacoffee.com/vaxiz?new=1"><b>buy me a coffee</b></a>! 💛✨</sub>
</p>
