#!/usr/bin/env bash
# Writes the GitHub release text (Markdown) to stdout. Used by .github/workflows/build-exe.yml.
#   bash packaging/release_notes.sh v2.1.0 dist/LoL-Matchup-Checker.exe
#
# "What's new" is built from the commit messages since the previous version, so write commit
# messages for players, e.g. "Add Ambessa alias", not "fix stuff". You can always edit the
# release text on GitHub afterwards.
set -euo pipefail

TAG="$1"
EXE="$2"
REPO="${GITHUB_SERVER_URL:-https://github.com}/${GITHUB_REPOSITORY:-MrVaxiZ/Lol-Matchup-Checker_v2}"  # the repo this runs in
SUPPORT_URL="https://buymeacoffee.com/vaxiz"

PREV="$(git describe --tags --abbrev=0 "${TAG}^" 2>/dev/null || true)"
if [ -n "$PREV" ]; then
  CHANGES="$(git log --no-merges --pretty='- %s' "${PREV}..${TAG}" | grep -v -i -E '^- (release v|merge )' || true)"
  [ -n "$CHANGES" ] || CHANGES="- Small fixes and improvements"
else
  # first release: the whole history would be too long, so describe the app instead
  CHANGES="First release of the desktop app 🎉

- ⚔️ **Find counters**: pick an enemy champion and see who beats it, best first
- 📊 **Matchup sheet**: your champions vs every laner, colour-coded, with a best pick per enemy
- 🖱️ Click a rating like **D+** to highlight only those matchups
- 💾 Saved results: re-runs on the same patch only load what's new
- 📁 Everything is also saved to Excel in Documents\\LoL Matchup Checker"
fi
SHA256="$(sha256sum "$EXE" | cut -d' ' -f1)"
SIZE_MB="$(( $(wc -c < "$EXE") / 1024 / 1024 ))"

cat <<EOF
## ⬇️ Download

### [**LoL-Matchup-Checker.exe**](${REPO}/releases/download/${TAG}/LoL-Matchup-Checker.exe) · Windows · ${SIZE_MB} MB

Download it, double-click it, done. No Python and nothing else to install.

> [!NOTE]
> - The first time you press **START**, the app downloads its browser (one time, about 150 MB).
> - **"Windows protected your PC"?** Click **More info → Run anyway**. The app isn't code-signed.

EOF
# VirusTotal result written by packaging/virustotal_scan.py (only when the scan ran)
if [ -s virustotal.md ]; then
  tr -d '\r' < virustotal.md
  echo
fi
cat <<EOF
## ✨ What's new

${CHANGES}

EOF
if [ -n "$PREV" ]; then
  echo "**All changes:** [${PREV}...${TAG}](${REPO}/compare/${PREV}...${TAG})"
  echo
fi
cat <<EOF
<details>
<summary>🔒 Checksum</summary>

\`SHA256: ${SHA256}\`

Check it in PowerShell: \`Get-FileHash .\\LoL-Matchup-Checker.exe\`
</details>

---

<sub>☕ If you enjoy the app and would like to support me, [**buy me a coffee**](${SUPPORT_URL})! 💛✨</sub>
EOF
