"""Portable publication gates for the current synthetic guided demonstration."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MEDIA = ROOT / "docs" / "media"
STEM = "pivotglass-guided-demo-v1.0.0"


def test_current_public_navigation_links_current_video_and_assets_exist():
    for relative in ("README.md", "docs/README.md"):
        assert f"{STEM}.mp4" in (ROOT / relative).read_text()
    video = MEDIA / f"{STEM}.mp4"
    assert video.stat().st_size > 1024
    with video.open("rb") as handle:
        assert b"ftyp" in handle.read(64), "Expected an ISO media container."
    for suffix in ("vtt", "html"):
        assert (MEDIA / f"{STEM}.{suffix}").stat().st_size > 0
    assert (MEDIA / "pivotglass-guided-demo-poster-v1.0.0.png").stat().st_size > 0


def test_demo_declares_synthetic_local_case_and_bounded_caption_timeline():
    manifest = json.loads((MEDIA / "pivotglass-guided-demo-manifest-v1.0.0.json").read_text())
    assert manifest["version"] == "1.0.0"
    assert manifest["synthetic"] is True
    assert manifest["network_enrichment"] is False
    duration = manifest["duration"]
    assert duration > 0
    assert manifest["chapters"]
    previous_end = 0.0
    for chapter in manifest["chapters"]:
        assert chapter["chapter"] and chapter["capture"] and chapter["narration"]
        assert chapter["duration"] > 0
        assert abs(chapter["start"] - previous_end) < 0.005
        previous_end = chapter["start"] + chapter["duration"]
    assert abs(previous_end - duration) < 0.005
    captions = (MEDIA / f"{STEM}.vtt").read_text()
    assert captions.startswith("WEBVTT")
    stamps = re.findall(r"(\d\d):(\d\d):(\d\d)\.(\d\d\d)", captions)
    assert len(stamps) >= 2
    seconds = [int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000 for h, m, s, ms in stamps]
    assert seconds == sorted(seconds)
    assert max(seconds) <= duration + 0.005
