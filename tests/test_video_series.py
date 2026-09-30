"""Publication contracts for the four-video series and caption transformation."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "docs/media/series-v1.0.0"
spec = importlib.util.spec_from_file_location(
    "series_renderer", ROOT / "scripts/render_video_series.py"
)
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)


def test_captions_preserve_actual_words_and_adjust_timing():
    srt = "1\n00:00:00,000 --> 00:00:01,000\nWhat if\n\n2\n00:00:01,000 --> 00:00:02,000\na connection\n\n3\n00:00:02,000 --> 00:00:04,000\nopened a question?\n"
    cues = renderer.caption_cues(srt, 1.25)
    assert " ".join(c[2] for c in cues) == "What if a connection opened a question?"
    assert cues[0][0] == 0
    assert cues[-1][1] == 3.2


def test_score_is_deterministic_bounded_and_uses_existing_theme():
    first = renderer.soundtrack_events("default", 12, [0, 4, 8])
    assert first == renderer.soundtrack_events("default", 12, [0, 4, 8])
    assert first
    assert all(0 <= e.start < 12 and 0 < e.duration <= 12 - e.start for e in first)
    assert first != renderer.soundtrack_events("the_matrix", 12, [0, 4, 8])


def test_all_four_published_edits_have_complete_word_coverage_and_sources():
    plan = json.loads((BASE / "production-plan.json").read_text())
    timing = json.loads((BASE / "narration-timing.json").read_text())
    assert {v["id"] for v in plan["videos"]} == {"overview", "analyst", "pivot", "visualization"}
    for v in plan["videos"]:
        stem = f"pivotglass-{v['id']}-v1.0.0"
        manifest = json.loads((BASE / f"{stem}.json").read_text())
        assert manifest["synthetic"] and not manifest["network_enrichment"]
        assert manifest["voice"]["provider"] == "Descript"
        assert manifest["music"]["speech_ducking"]
        assert manifest["music"]["engine"] == "pivotglass.core.music"
        video = BASE / f"{stem}.mp4"
        with video.open("rb") as handle:
            assert b"ftyp" in handle.read(64)
        assert video.stat().st_size > 100000
        captions = renderer.caption_cues(timing[v["id"]]["srt"], v["pace"])
        assert (
            " ".join(c[2] for c in captions).split()
            == " ".join(p["text"] for p in timing[v["id"]]["paragraphs"]).split()
        )
        assert captions[-1][1] <= manifest["duration"] + 0.001
        assert (BASE / f"{stem}.vtt").read_text().startswith("WEBVTT")
        assert (BASE / f"{stem}-transcript.md").stat().st_size > 500
        assert (BASE / f"{stem}-poster.png").is_file()
        previous = 0
        for chapter in manifest["chapters"]:
            assert abs(chapter["start"] - previous) < 0.005
            previous = chapter["start"] + chapter["duration"]
            for source in chapter["captures"]:
                assert (BASE / source).is_file()
        assert abs(previous - manifest["duration"]) < 0.005
        assert f"{stem}.mp4" in (BASE / "index.html").read_text()
        assert f"{stem}.vtt" in (BASE / "index.html").read_text()
