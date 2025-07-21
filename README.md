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
| `--out`      | Optional. Overwrittes deafult excel output path   | `--out "C:\mid_champs.xlsx"`|
| `--debug`    | Optional. Enables detailed console debug logs     | `--debug`  (In Future)      |
| `--alias`    | Optional. Displays all available aliases          | `--alias`  (In Future)      |

---

## 📂 Output

- Results are exported to `Matchups.xlsx` in the app directory.
- Excel file includes:
  - Champion names
  - Matchups
  - Color-coded cells for visibility

Legends :
'-' - Do not pick this champ.   Winrate is below 49%.
'S' - Skill based matchup.      Winrate is between 49% and 51%.
------------------ Everything past this line means this champ is good against the enemy.
'+' - Can pick this champ.      Winrate is between 51% and 53%.
'D' - Distinguished pick.       Winrate is between 53% and 55%.
'D+' - Distinguished pick plus. Winrate is between 55% and 60%.
'UD' - Ultra Distinguished.     Winrate is over 60%. (Yes there are matchups like these).

---

## ✍️ Example Usage

```bash
LoL Matchup CLI Tool.exe --lane top --champs darius sett riven
```

Expected output:
- Creates an Excel file with matchup data for each of those champions vs all meta top laners.
- Matchup ratings are based on win rate and match count pulled directly from u.gg.

---

## 🗃️ File Structure

```
/LoL Matchup CLI Tool
├── /Data
|   └── EndPoints.cs
|   └── EnumLanes.cs
|   └── Aliases.cs
├── /Props
│   └── Matchup.cs
|   └── ExcelHandler.cs
├── /Helpers
│   └── ExcelHandler.cs
|   └── Validator.cs
├── Program.cs
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
Inspired by the need for accurate matchup prep for ranked games.

---

**GLHF on the Rift!**
