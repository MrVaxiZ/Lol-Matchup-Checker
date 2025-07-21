# LoL Matchup CLI Tool

A powerful multithreaded command-line tool written in C# (.NET 8) that scrapes real-time matchup data from [u.gg](https://u.gg) and exports it into a well-formatted Excel spreadsheet. The tool is designed to assist League of Legends players in understanding champion matchups based on winrates and pick data.

---

## 💡 Features

- 🔎 Scrapes winrate & match count data from [u.gg](https://u.gg) for given champion matchups.
- 🧠 Accepts lane and champion inputs directly via command line.
- 📊 Exports results into an Excel file using ClosedXML with styling and alignment.
- ⚙️ Multithreaded design for fast parallel scraping.
- ♻️ Automatic retries on scrape failure (up to 3 times).
- 🛠️ Internal logger with timestamps and debug trace.
- 🎯 Designed for repeatable automated use.

---

## 🚀 Quick Start

### 🔧 Requirements

- .NET 8 SDK
- Chrome browser installed
- [u.gg](https://u.gg) must be publicly accessible (no login required)

### 🧪 Build & Run

```bash
dotnet build
dotnet run -- --lane mid --champs lb vlad
```

Or run the built `.exe` file directly:

```bash
LoL Matchup CLI Tool.exe --lane top --champs sett darius irelia
```

---

## 🧾 Command Line Arguments

| Argument     | Description                                      | Example                      |
|--------------|--------------------------------------------------|------------------------------|
| `--lane`     | Required. Lane for matchups (`top`, `jng`, `mid`, `adc`, `sup`) | `--lane mid`                |
| `--champs`   | Required. List of champion aliases or names       | `--champs lb vlad`          |
| `--open`     | Optional. Open each matchup in browser (Chrome)   | `--open`                    |
| `--debug`    | Optional. Enables detailed console debug logs     | `--debug`                   |
| `--alias`    | Optional. Displays all available aliases          | `--alias`                   |

---

## 📂 Output

- Results are exported to `Results_<lane>.xlsx` in the app directory.
- Excel file includes:
  - Champion names
  - Matchup winrates (%)
  - Number of matches
  - Color-coded cells for visibility

---

## ✍️ Example Usage

```bash
LoL Matchup CLI Tool.exe --lane top --champs darius sett riven
```

Expected output:
- Creates an Excel file with matchup data for each of those champions vs all meta top laners.
- Stats include win rate and match count pulled directly from u.gg.

---

## 🗃️ File Structure

```
/GetTopMachupsForGivenChamps
├── /Props
│   └── Matchup.cs
├── /Helpers
│   └── ExcelHandler.cs
├── Program.cs
├── MatchupScraper.cs
├── StaticVars.cs
├── Logger.cs
├── LoL Matchup CLI Tool.exe
└── Result_<lane>.xlsx
```

---

## 🧠 Technical Highlights

- Uses `Selenium` WebDriver to navigate and scrape u.gg.
- Parallelized scraping using `ConcurrentBag` and `Parallel.ForEach`.
- Robust error handling with crash dump generation (`_debug.html`, `_debug.png`).
- Alias normalization (e.g., `lb` → `LeBlanc`, `vlad` → `Vladimir`).

---

## 🔍 Debugging

If a crash occurs:
- HTML source and screenshot are dumped to `_debug.html` and `_debug.png` for inspection.
- Logs are printed to the console if `--debug` is used.

---

## 📜 License

This project is released under the MIT License. Do whatever you want with it, but give credit if you use it publicly.

---

## 👤 Author

Made by [MrVaxiZ](https://github.com/MrVaxiZ)  
Inspired by the need for fast, accurate matchup prep for ranked.

---

**GLHF on the Rift!**
