"""Uploads the .exe to VirusTotal and writes a Markdown line for the release notes.

    VT_API_KEY=... python packaging/virustotal_scan.py dist/LoL-Matchup-Checker.exe --out virustotal.md

Used by .github/workflows/build-exe.yml. Waits up to --wait seconds for the scan to finish; if it
takes longer, the line just links to the scan page. Never fails the build: if anything goes wrong
it writes nothing and exits 0, so a VirusTotal hiccup can't block a release.
Only the Python standard library is used. The free public API allows 4 requests a minute.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.request
import uuid
from pathlib import Path

API = os.environ.get("VT_API_BASE", "https://www.virustotal.com/api/v3")
GUI = "https://www.virustotal.com/gui/file/"
DIRECT_LIMIT = 32 * 1024 * 1024  # bigger files must go through an upload URL


def _request(url: str, key: str, data: bytes | None = None, content_type: str | None = None) -> dict:
    req = urllib.request.Request(url, data=data, method="POST" if data is not None else "GET")
    req.add_header("x-apikey", key)
    req.add_header("accept", "application/json")
    if content_type:
        req.add_header("content-type", content_type)
    with urllib.request.urlopen(req, timeout=600) as resp:  # noqa: S310 (fixed https API)
        return json.loads(resp.read().decode("utf-8"))


def _multipart(path: Path) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    head = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{path.name}\"\r\n"
            "Content-Type: application/octet-stream\r\n\r\n").encode()
    body = head + path.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    return body, f"multipart/form-data; boundary={boundary}"


def scan(path: Path, key: str, wait_s: float, poll_s: float = 20.0, log=print) -> tuple[str, dict | None]:
    """Upload and wait. Returns (sha256, stats or None if the scan didn't finish in time)."""
    sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    body, ctype = _multipart(path)
    if path.stat().st_size > DIRECT_LIMIT:
        upload_url = _request(f"{API}/files/upload_url", key)["data"]
    else:
        upload_url = f"{API}/files"
    log(f"Uploading {path.name} ({path.stat().st_size / 1e6:.0f} MB) to VirusTotal...")
    analysis_id = _request(upload_url, key, body, ctype)["data"]["id"]

    deadline = time.monotonic() + wait_s
    while time.monotonic() < deadline:
        time.sleep(poll_s)  # 20 s between checks stays under the free API's 4 requests/minute
        attrs = _request(f"{API}/analyses/{analysis_id}", key)["data"]["attributes"]
        log(f"  scan status: {attrs.get('status')}")
        if attrs.get("status") == "completed":
            return sha256, attrs.get("stats") or {}
    return sha256, None


def markdown(sha256: str, stats: dict | None) -> str:
    link = GUI + sha256
    if stats is None:
        return f"> 🛡️ **VirusTotal:** [see the scan]({link}) (still running when this release was published)"
    flagged = int(stats.get("malicious", 0)) + int(stats.get("suspicious", 0))
    total = flagged + int(stats.get("undetected", 0)) + int(stats.get("harmless", 0))
    if flagged == 0:
        return f"> 🛡️ **VirusTotal: clean.** 0 of {total} antivirus engines flagged it. [See the scan]({link})"
    return (f"> 🛡️ **VirusTotal:** {flagged} of {total} antivirus engines flagged it. [See the scan]({link})\n"
            "> Apps packaged with PyInstaller often get a few false alarms like this. "
            "The full source code is in this repository.")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("file", type=Path)
    parser.add_argument("--out", type=Path, required=True, help="Markdown file to write the result line to")
    parser.add_argument("--wait", type=float, default=900, help="Seconds to wait for the scan (default 900)")
    parser.add_argument("--poll", type=float, default=20, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    key = os.environ.get("VT_API_KEY", "").strip()
    if not key:
        print("VT_API_KEY isn't set, skipping the VirusTotal scan.")
        return 0
    try:
        sha256, stats = scan(args.file, key, args.wait, args.poll)
    except Exception as exc:  # never block a release because of VirusTotal
        hint = " (check the VT_API_KEY secret)" if "401" in str(exc) or "403" in str(exc) else ""
        print(f"VirusTotal scan failed, the release goes out without it{hint}: {type(exc).__name__}: {exc}")
        return 0
    line = markdown(sha256, stats)
    args.out.write_text(line + "\n", encoding="utf-8")
    print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
