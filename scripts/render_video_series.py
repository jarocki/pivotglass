"""Render reviewed Descript speech with actual captures and Pivotglass scores.

No speech synthesis or provider calls occur here. Supply privately exported
Descript audio separately; published plans contain no signed URLs or credentials.
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import textwrap
from dataclasses import asdict, replace
from pathlib import Path

from pivotglass.core.music import _THEMES, NoteEvent, ProceduralMusicController, _plan_score


def soundtrack_events(
    theme_name: str, duration: float, cue_starts: list[float]
) -> tuple[NoteEvent, ...]:
    """Develop the existing theme, with a sparse middle and an earned return."""
    theme = _THEMES[theme_name]
    cycle_length = 60 / theme.tempo * theme.meter * theme.phrase_bars * len(theme.form)
    result = []
    for cycle in range(math.ceil(duration / cycle_length)):
        for event in _plan_score(theme, cycle):
            start = cycle * cycle_length + event.start
            if start >= duration:
                continue
            chapter = sum(cue <= start for cue in cue_starts) - 1
            progression = chapter / max(1, len(cue_starts) - 1)
            # Establish -> explore -> reflect -> return. Percussion is quieter
            # in analytical passages; not every edit is a musical impact.
            density = 0.8 if progression < 0.2 else 0.58 if progression < 0.7 else 0.9
            if event.voice == "electronic_kick" and 0.2 <= progression < 0.7:
                density *= 0.65
            ending = min(1.0, (duration - start) / 3)
            result.append(
                replace(
                    event,
                    start=start,
                    duration=min(event.duration, duration - start),
                    amplitude=event.amplitude * density * ending,
                )
            )
    return tuple(result)


class VideoScore(ProceduralMusicController):
    def __init__(self, theme: str, events: tuple[NoteEvent, ...]):
        super().__init__(theme, volume=55)
        self.events = events

    def _score(self, cycle=None):
        return self.events


def run(*args: str):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


def stamp(seconds: float) -> str:
    ms = round(seconds * 1000)
    return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02}.{ms % 1000:03}"


def caption_cues(srt: str, pace: float) -> list[tuple[float, float, str]]:
    """Group actual Descript transcript ticks, preserving every word in order."""

    def seconds(value):
        h, m, s = value.replace(",", ".").split(":")
        return int(h) * 3600 + int(m) * 60 + float(s)

    ticks = []
    for block in srt.strip().split("\n\n"):
        lines = block.splitlines()
        start, end = lines[1].split(" --> ")
        ticks.append((seconds(start), seconds(end), " ".join(lines[2:])))
    result = []
    words = []
    start = 0
    for a, b, text in ticks:
        if not words:
            start = a
        words.append(text)
        if b - start >= 3.5 or len(" ".join(words)) >= 105:
            result.append((start / pace, b / pace, " ".join(words)))
            words = []
    if words:
        result.append((start / pace, ticks[-1][1] / pace, " ".join(words)))
    assert " ".join(t[2] for t in ticks).split() == " ".join(t[2] for t in result).split()
    return result


def render(video: dict, timing: dict, base: Path, audio_dir: Path, work: Path):
    key = video["id"]
    folder = work / key
    folder.mkdir(parents=True, exist_ok=True)
    pace = video["pace"]
    paragraphs = timing["paragraphs"]
    assert len(paragraphs) == len(video["scenes"])
    duration = timing["duration"] / pace
    # Existing original score remains the composition/synthesis authority.
    cues = [p["start"] / pace for p in paragraphs]
    events = soundtrack_events(video["theme"], duration, cues)
    VideoScore(video["theme"], events)._render(folder / "score.wav")
    (base / f"{key}-score.json").write_text(
        json.dumps(
            {
                "theme": video["theme"],
                "duration": duration,
                "cue_starts": cues,
                "events": [asdict(e) for e in events],
            },
            indent=2,
        )
        + "\n"
    )
    clips = []
    manifest_chapters = []
    for i, (scene, paragraph) in enumerate(zip(video["scenes"], paragraphs, strict=True)):
        start = paragraph["start"] / pace
        end = paragraph["end"] / pace
        captures = scene["captures"]
        steps = scene.get("capture_offsets", [])
        # Offsets can be taken from exact transcript ticks. Otherwise each
        # scene is visibly an edited illustrative montage, not click evidence.
        bounds = [start] + [start + o / pace for o in steps] + [end]
        if not steps:
            bounds = [start + (end - start) * j / len(captures) for j in range(len(captures) + 1)]
        assert len(bounds) == len(captures) + 1
        for j, (capture, a, b) in enumerate(zip(captures, bounds, bounds[1:], strict=False)):
            frames = round(b * 25) - round(a * 25)
            assert frames > 0
            path = (base / capture).resolve()
            assert path.is_file(), path
            out = folder / f"{i:02}-{j:02}.mp4"
            # Rapid cuts follow spoken view names. UI captures stay stable for
            # legibility; title art alone gets a gentle animated approach.
            vf = "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=0x10171b,setsar=1,pad=1280:816:0:0:color=0x10171b"
            if "brand/" in capture:
                vf = "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=0x10171b,zoompan=z='min(zoom+0.0003,1.05)':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d=1:s=1280x720:fps=25,setsar=1,pad=1280:816:0:0:color=0x10171b"
            run(
                "-loop",
                "1",
                "-i",
                str(path),
                "-vf",
                vf,
                "-frames:v",
                str(frames),
                "-r",
                "25",
                "-c:v",
                "libx264",
                "-preset",
                "fast",
                "-crf",
                "20",
                "-pix_fmt",
                "yuv420p",
                str(out),
            )
            clips.append(out)
        manifest_chapters.append({**scene, "start": start, "duration": end - start})
    listing = folder / "concat.txt"
    listing.write_text("".join(f"file '{p}'\n" for p in clips))
    filters = f"[1:a]atempo={pace},highpass=f=80,loudnorm=I=-16:TP=-2:LRA=7,asplit=2[voice][side];[2:a]lowpass=f=6500,loudnorm=I=-28:TP=-6:LRA=8[bed];[bed][side]sidechaincompress=threshold=0.03:ratio=6:attack=10:release=240[duck];[voice][duck]amix=inputs=2:normalize=0,alimiter=limit=0.89:level=0,afade=t=out:st={max(0, duration - 1)}:d=1[mix]"
    stem = f"pivotglass-{key}-v0.9.9"
    captions = caption_cues(timing["srt"], pace)
    (base / f"{stem}.vtt").write_text(
        "WEBVTT\n\n"
        + "\n\n".join(
            f"{stamp(a)} --> {stamp(b)}\n{textwrap.fill(text, width=70)}" for a, b, text in captions
        )
        + "\n"
    )
    transcript = [
        f"# {video['title']}",
        "",
        "Actual UI capture montage from a synthetic training case. Narration: Descript Jesse, accelerated without changing pitch. Captions use the provider's one-second aligned transcript groups, adjusted for playback speed; they are not exact word timestamps.",
        "",
    ]
    for scene, p in zip(video["scenes"], paragraphs, strict=True):
        transcript += [
            f"## {stamp(p['start'] / pace)} — {scene['chapter']}",
            "",
            p["text"],
            "",
        ]
    (base / f"{stem}-transcript.md").write_text("\n".join(transcript))
    run(
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(listing),
        "-i",
        str(audio_dir / f"{key}.m4a"),
        "-i",
        str(folder / "score.wav"),
        "-filter_complex",
        filters,
        "-map",
        "0:v",
        "-map",
        "[mix]",
        "-c:v",
        "libx264",
        "-profile:v",
        "main",
        "-level:v",
        "3.2",
        "-preset",
        "fast",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-r",
        "25",
        "-g",
        "50",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-ar",
        "44100",
        "-ac",
        "2",
        "-t",
        str(duration),
        "-movflags",
        "+faststart",
        str(base / f"{stem}.mp4"),
    )
    manifest = {
        "id": key,
        "title": video["title"],
        "version": "0.9.9",
        "status": "review_candidate",
        "synthetic": True,
        "network_enrichment": False,
        "duration": duration,
        "voice": {
            "provider": "Descript",
            "name": "Jesse",
            "tempo_multiplier": pace,
            "emotion_control": "not exposed by stock-voice synthesis",
        },
        "music": {
            "engine": "pivotglass.core.music",
            "theme": video["theme"],
            "speech_ducking": True,
        },
        "method": "Edited actual UI captures and branded title art; narration generated in Descript. Original procedural score shaped to scene progression and ducked beneath speech.",
        "chapters": manifest_chapters,
    }
    (base / f"{stem}.json").write_text(json.dumps(manifest, indent=2) + "\n")
    run(
        "-ss",
        "1",
        "-i",
        str(base / f"{stem}.mp4"),
        "-frames:v",
        "1",
        str(base / f"{stem}-poster.png"),
    )
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio-dir", type=Path, required=True)
    parser.add_argument("--timing", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--only")
    args = parser.parse_args()
    base = Path("docs/media/series-v0.9.9")
    plan = json.loads((base / "production-plan.json").read_text())
    timings = json.loads(args.timing.read_text())
    for video in plan["videos"]:
        if args.only and video["id"] != args.only:
            continue
        result = render(video, timings[video["id"]], base, args.audio_dir, args.work_dir)
        print(f"Rendered {video['id']}: {result['duration']:.2f}s", flush=True)


if __name__ == "__main__":
    main()
