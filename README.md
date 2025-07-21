# LoL Matchup CLI Tool

A powerful multithreaded command-line tool written in C# (.NET 8) that scrapes real-time matchup data from [u.gg](https://u.gg) and exports it into a well-formatted Excel spreadsheet. The tool is designed to assist League of Legends players in understanding champion matchups based on winrates and pick data.

---

## 💡 Features

- 🔎 Scrapes winrate & match count data from [u.gg](https://u.gg) for given champion matchups.
- 🧠 Accepts lane and champion inputs directly via command line.
- 📊 Exports results into an Excel file using ClosedXML with styling and alignment.
- ⚙️ Multithreaded design for fast parallel scraping. (still not as fast as it should be)
- ♻️ Automatic retries on scrape failure.
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

rem CLI Usage Example :
"LoL Matchup CLI Tool.exe" --lane mid --champs lb vlad
