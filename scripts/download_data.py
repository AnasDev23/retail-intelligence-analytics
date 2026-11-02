"""Download the official UCI Online Retail II archive (CC BY 4.0) into data/raw.

Source: https://archive.ics.uci.edu/dataset/502/online+retail+ii  (Daqing Chen)
Uses only the Python standard library. No login or key is required by UCI.
Writes data/raw/SOURCE_MANIFEST.json (URL, access time, SHA-256, size).
"""
from __future__ import annotations

import hashlib
import json
import sys
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src import config  # noqa: E402


def main() -> int:
    config.RAW_DIR.mkdir(parents=True, exist_ok=True)
    target = config.RAW_DIR / config.XLSX_NAME
    if target.exists():
        print(f"Already present: {target}. Delete it to re-download.")
        return 0
    zip_path = config.RAW_DIR / "online_retail_ii.zip"
    print(f"Downloading {config.DOWNLOAD_URL} (~43.5 MB) ...")
    try:
        req = urllib.request.Request(config.DOWNLOAD_URL, headers={"User-Agent": "retail-portfolio-project"})
        with urllib.request.urlopen(req, timeout=120) as resp, open(zip_path, "wb") as fh:
            while chunk := resp.read(1 << 20):
                fh.write(chunk)
    except Exception as exc:  # network/proxy/firewall problems
        print(f"Automatic download failed: {exc}\nManual steps:\n  1. Open {config.LANDING_URL}\n"
              f"  2. Click Download and unzip.\n  3. Put {config.XLSX_NAME} in {config.RAW_DIR}")
        return 1
    sha = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        match = [n for n in names if n.lower().endswith(".xlsx")]
        if not match:
            print(f"No .xlsx in archive; contents: {names}")
            return 1
        with zf.open(match[0]) as src, open(target, "wb") as dst:
            dst.write(src.read())
    manifest = {"title": config.DATASET_TITLE, "author": config.DATASET_AUTHOR, "landing_page": config.LANDING_URL,
                "download_url": config.DOWNLOAD_URL, "license": config.LICENSE_NAME,
                "accessed_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "archive_sha256": sha, "archive_bytes": zip_path.stat().st_size, "extracted_file": target.name,
                "note": "UCI does not publish a checksum; this hash records what was downloaded."}
    (config.RAW_DIR / "SOURCE_MANIFEST.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Saved {target}\nManifest written. Next: python scripts/prepare_data.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
