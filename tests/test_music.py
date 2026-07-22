"""Procedural music remains local, optional, and independent of analysis."""

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


def test_renderer_writes_owned_local_mono_wave(tmp_path: Path):
    controller = ProceduralMusicController(tmp_path, mode="sensei", volume=20)
    output = tmp_path / "sensei.wav"
    controller._render(output)
    assert output.read_bytes().startswith(b"RIFF")
    assert output.stat().st_size < 100_000


def test_mode_and_volume_are_clamped_without_starting_audio(tmp_path: Path):
    controller = ProceduralMusicController(tmp_path)
    controller.set_mode("the_sprawl")
    controller.set_volume(200)
    assert controller.mode == "the_sprawl"
    assert controller.status.volume == 100
    assert controller.status.muted is True
