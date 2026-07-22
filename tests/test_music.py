"""Procedural music remains local, optional, and independent of analysis."""

import wave
from pathlib import Path
from unittest.mock import patch

from adversary_pursuit.core.music import ProceduralMusicController


def test_music_starts_muted_and_reports_unavailable_honestly(tmp_path: Path):
    with patch.object(ProceduralMusicController, "_find_player", return_value=None):
        controller = ProceduralMusicController(tmp_path)
    assert controller.status.muted is True
    assert controller.status.enabled is False
    assert controller.status.available is False
    assert controller.start() is False
    assert not tmp_path.exists() or list(tmp_path.iterdir()) == []


def test_renderer_writes_owned_local_layered_wave(tmp_path: Path):
    controller = ProceduralMusicController(tmp_path, mode="sensei", volume=20)
    output = tmp_path / "sensei.wav"
    controller._render(output)
    assert output.read_bytes().startswith(b"RIFF")
    with wave.open(str(output), "rb") as rendered:
        assert rendered.getframerate() == 22_050
        assert rendered.getnchannels() == 1
        assert 31 <= rendered.getnframes() / rendered.getframerate() <= 33
        frames = rendered.readframes(rendered.getnframes())
    assert len(set(frames[index : index + 2] for index in range(0, len(frames), 2))) > 1_000


def test_renderer_is_deterministic_and_character_distinct(tmp_path: Path):
    sensei_a = tmp_path / "sensei-a.wav"
    sensei_b = tmp_path / "sensei-b.wav"
    sprawl = tmp_path / "sprawl.wav"
    ProceduralMusicController(tmp_path, mode="sensei", volume=20)._render(sensei_a)
    ProceduralMusicController(tmp_path, mode="sensei", volume=20)._render(sensei_b)
    ProceduralMusicController(tmp_path, mode="the_sprawl", volume=20)._render(sprawl)
    assert sensei_a.read_bytes() == sensei_b.read_bytes()
    assert sensei_a.read_bytes() != sprawl.read_bytes()


def test_mode_and_volume_are_clamped_without_starting_audio(tmp_path: Path):
    controller = ProceduralMusicController(tmp_path)
    controller.set_mode("the_sprawl")
    controller.set_volume(200)
    assert controller.mode == "the_sprawl"
    assert controller.status.volume == 100
    assert controller.status.muted is True
