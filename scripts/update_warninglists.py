"""Refresh the bundled MISP warninglist subset (DEC-KNOWN-GOOD-001).

Run once per minor release:

    uv run python scripts/update_warninglists.py

Downloads each selected list from the MISP/misp-warninglists repository at
its current ``main`` commit and writes ``src/pivotglass/data/warninglists.json.gz``
with the commit, each list's upstream version, and the Pivotglass category.
The warninglists are CC0 1.0. The selection lives in
``pivotglass.core.known_good.SELECTED_LISTS``; this script only fetches.
"""

from __future__ import annotations

import gzip
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pivotglass.core.known_good import BUNDLE_PATH, SELECTED_LISTS  # noqa: E402

REPO = "MISP/misp-warninglists"


def main() -> int:
    with httpx.Client(timeout=60.0, follow_redirects=True) as http:
        commit = http.get(f"https://api.github.com/repos/{REPO}/commits/main").raise_for_status().json()["sha"]
        lists = {}
        for list_id in SELECTED_LISTS:
            url = f"https://raw.githubusercontent.com/{REPO}/{commit}/lists/{list_id}/list.json"
            data = http.get(url).raise_for_status().json()
            lists[list_id] = {
                "name": data["name"],
                "type": data["type"],
                "version": data.get("version"),
                "list": sorted({str(item).strip() for item in data["list"] if str(item).strip()}),
            }
            print(f"{list_id:28} {data['type']:9} {len(lists[list_id]['list']):6} v{data.get('version')}")
    bundle = {
        "source": f"https://github.com/{REPO}",
        "commit": commit,
        "licence": "CC0 1.0",
        "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "lists": lists,
    }
    payload = json.dumps(bundle, separators=(",", ":"), sort_keys=True).encode()
    BUNDLE_PATH.write_bytes(gzip.compress(payload, compresslevel=9, mtime=0))
    print(f"wrote {BUNDLE_PATH.relative_to(ROOT)} ({BUNDLE_PATH.stat().st_size:,} bytes) at {commit[:12]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
