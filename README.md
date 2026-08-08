# LoL Matchup CLI Tool

UPDATE :: Why is it NOT working? :
Since some time now u.gg stated to use claudflare which prevents my scraper from working I will have to fully remake it in order for this to work again.  


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

### 🧪 Run
Run `LoL Matchup CLI Tool.exe` file directly:

```bash
LoL Matchup CLI Tool.exe gen --lane top --champs vlad darius ww
```

---

## 🧾 Command Line Arguments

| Argument     | Description                                      | Example                      |
|--------------|--------------------------------------------------|------------------------------|
| `gen`        | Main Command to gen excel below it's params.     |  `gen`  
| `--lane`     | Required. Lane for matchups (`top`, `jng`, `mid`, `adc`, `sup`) | `--lane mid`                |
| `--champs`   | Required. List of champion aliases or names       | `--champs lb vlad`          |
| `--out`      | Optional. Overwrittes deafult excel output path   | `--out "C:\mid_champs.xlsx"`|
| `--debug`    | Optional. Enables detailed console debug logs     | `--debug`  (In Future)      |
| `alias`      | Command to displays all available aliases         | `alias`                   |

---

## 📂 Output

- Results are exported to `Matchups.xlsx` in the app directory.
(Can be overwritten by providing '--out' parameter)
- Excel file includes:
  - Champion names
  - Matchups
  - Color-coded cells for visibility

### 📘 Excel Legend

| Symbol | Meaning                  | Winrate Range                  |
|--------|--------------------------|-------------------------------|
| `-`    | Do not pick this champ.  | Winrate is below 49%.         |
| `S`    | Skill-based matchup.     | Winrate is between 49%–51%.   |
| `+`    | Can pick this champ.     | Winrate is between 51%–53%.   |
| `D`    | Distinguished pick.      | Winrate is between 53%–55%.   |
| `D+`   | Distinguished pick plus. | Winrate is between 55%–60%.   |
| `UD`   | Ultra Distinguished.     | Winrate is over 60%.          |

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
