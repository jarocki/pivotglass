"""Procedural music remains local, optional, and independent of analysis."""

import struct
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch

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


def test_character_identity_lives_in_score_not_only_rendering(tmp_path: Path):
    sensei = ProceduralMusicController(tmp_path, mode="sensei")._score()
    sprawl = ProceduralMusicController(tmp_path, mode="the_sprawl")._score()
    computer = ProceduralMusicController(tmp_path, mode="the_computer")._score()

    def signature(score):
        return tuple(
            (round(event.start, 3), round(event.duration, 3), round(event.frequency, 2), event.voice)
            for event in score
        )

    assert signature(sensei) != signature(sprawl)
    assert signature(sprawl) != signature(computer)
    assert len({event.voice for event in sensei}) >= 5
    assert len({event.voice for event in sprawl}) >= 5


def test_score_has_form_memory_and_transformation(tmp_path: Path):
    score = ProceduralMusicController(tmp_path, mode="sensei")._score()
    lead = [event for event in score if event.voice == "bowl"]
    answers = [event for event in score if event.voice == "answer"]

    assert any(event.start < 8 for event in lead)
    assert any(8 <= event.start < 16 for event in lead)
    assert any(16 <= event.start < 24 for event in lead)
    assert any(24 <= event.start < 32 for event in lead)
    assert answers


def test_m4tr1x_has_sample_informed_machine_pulse(tmp_path: Path):
    score = ProceduralMusicController(tmp_path, mode="m4tr1x")._score()
    pulses = [event for event in score if event.voice == "pulse" and event.start < 8]
    pulse_gaps = [round(right.start - left.start, 3) for left, right in zip(pulses, pulses[1:])]

    assert {event.voice for event in score} >= {"machine", "sub", "neon", "pulse"}
    assert pulse_gaps
    assert all(0.26 <= gap <= 0.27 for gap in pulse_gaps)


def test_sensei_has_sample_informed_breathing_form(tmp_path: Path):
    sensei = ProceduralMusicController(tmp_path, mode="sensei")._score()
    m4tr1x = ProceduralMusicController(tmp_path, mode="m4tr1x")._score()
    gongs = [event for event in sensei if event.voice == "gong"]

    assert {event.voice for event in sensei} >= {"bowl", "earth", "breath", "gong"}
    assert len(sensei) < len(m4tr1x)
    assert len(gongs) == 4
    assert [event.start for event in gongs] == [0, 8, 16, 24]


def test_sprawl_has_sample_informed_falling_grid_and_late_bloom(tmp_path: Path):
    score = ProceduralMusicController(tmp_path, mode="the_sprawl")._score()
    cascades = [event for event in score if event.voice == "cascade" and event.start < 8]
    fog_drones = [event for event in score if event.voice == "fog" and event.duration > 8]

    assert {event.voice for event in score} >= {"cascade", "grid", "fog", "signal"}
    assert [event.frequency for event in cascades[:3]] == sorted(
        (event.frequency for event in cascades[:3]), reverse=True
    )
    assert fog_drones[-1].amplitude > fog_drones[0].amplitude * 2


def test_ninja_has_reference_informed_stealth_to_impact_reveal(tmp_path: Path):
    score = ProceduralMusicController(tmp_path, mode="ninja")._score()
    steps = [event for event in score if event.voice == "step" and event.start < 8]
    veils = [event for event in score if event.voice == "veil" and event.duration > 8]
    step_gaps = [round(right.start - left.start, 3) for left, right in zip(steps, steps[1:])]

    assert {event.voice for event in score} >= {"blade", "shadow", "veil", "step"}
    assert step_gaps and all(0.428 <= gap <= 0.429 for gap in step_gaps)
    assert veils[-1].amplitude > veils[0].amplitude * 5


def test_detective_has_reference_informed_crooked_investigation_pulse(tmp_path: Path):
    score = ProceduralMusicController(tmp_path, mode="detective")._score()
    knocks = [event for event in score if event.voice == "knock" and event.start < 8]
    rain = [event for event in score if event.voice == "rain" and event.duration > 8]
    knock_gaps = {round(right.start - left.start, 3) for left, right in zip(knocks, knocks[1:])}

    assert {event.voice for event in score} >= {"clue", "footfall", "rain", "knock"}
    assert knock_gaps == {0.833, 1.667}
    assert rain[1].amplitude > rain[0].amplitude * 5


def test_computer_has_reference_informed_dreamy_cyberspace_orbit(tmp_path: Path):
    score = ProceduralMusicController(tmp_path, mode="the_computer")._score()
    orbits = [event for event in score if event.voice == "orbit" and event.start < 8]
    clouds = [event for event in score if event.voice == "cloud" and event.duration > 8]
    orbit_gaps = [round(right.start - left.start, 3) for left, right in zip(orbits, orbits[1:])]

    assert {event.voice for event in score} >= {"star", "current", "cloud", "orbit"}
    assert orbit_gaps and all(gap == 0.469 for gap in orbit_gaps)
    assert max(event.amplitude for event in clouds) < min(event.amplitude for event in clouds) * 1.12


def test_strategist_has_reference_informed_long_range_build(tmp_path: Path):
    score = ProceduralMusicController(tmp_path, mode="strategist")._score()
    measures = [event for event in score if event.voice == "measure"]
    horizons = [event for event in score if event.voice == "horizon" and event.duration > 8]
    measure_gaps = {round(right.start - left.start, 3) for left, right in zip(measures, measures[1:])}

    assert {event.voice for event in score} >= {"plan", "foundation", "horizon", "measure"}
    assert measure_gaps == {4.0}
    assert horizons[-1].amplitude > horizons[0].amplitude * 3.5


def test_default_has_reference_informed_open_forward_motion(tmp_path: Path):
    score = ProceduralMusicController(tmp_path, mode="default")._score()
    strides = [event for event in score if event.voice == "stride" and event.start < 8]
    skies = [event for event in score if event.voice == "sky" and event.duration > 8]
    stride_gaps = {round(right.start - left.start, 3) for left, right in zip(strides, strides[1:])}

    assert {event.voice for event in score} >= {"seed", "field", "sky", "stride"}
    assert stride_gaps == {0.938}
    assert skies[-1].amplitude > skies[0].amplitude * 1.6


def test_renderer_has_headroom_and_faded_loop_edges(tmp_path: Path):
    output = tmp_path / "sprawl.wav"
    ProceduralMusicController(tmp_path, mode="the_sprawl", volume=100)._render(output)
    with wave.open(str(output), "rb") as rendered:
        samples = struct.unpack(f"<{rendered.getnframes()}h", rendered.readframes(rendered.getnframes()))

    assert max(abs(sample) for sample in samples) < 32767
    assert max(abs(sample) for sample in samples[:100]) < 1_000
    assert max(abs(sample) for sample in samples[-100:]) < 1_000
    assert 29_000 <= max(abs(sample) for sample in samples) <= 30_000


def test_volume_remains_linear_and_reaches_useful_maximum(tmp_path: Path):
    quiet = tmp_path / "quiet.wav"
    loud = tmp_path / "loud.wav"
    ProceduralMusicController(tmp_path, mode="default", volume=20)._render(quiet)
    ProceduralMusicController(tmp_path, mode="default", volume=100)._render(loud)

    def peak(path: Path) -> int:
        with wave.open(str(path), "rb") as rendered:
            samples = struct.unpack(
                f"<{rendered.getnframes()}h", rendered.readframes(rendered.getnframes())
            )
        return max(abs(sample) for sample in samples)

    assert 5_800 <= peak(quiet) <= 6_000
    assert 29_000 <= peak(loud) <= 30_000


def test_enabled_state_survives_theme_change(tmp_path: Path):
    controller = ProceduralMusicController(tmp_path, mode="default")
    controller._enabled = True
    controller._muted = False
    controller.stop = MagicMock()  # type: ignore[method-assign]
    controller.start = MagicMock(return_value=True)  # type: ignore[method-assign]

    controller.set_mode("sensei")

    assert controller.mode == "sensei"
    controller.stop.assert_called_once_with()
    controller.start.assert_called_once_with()


def test_muted_state_survives_theme_change(tmp_path: Path):
    controller = ProceduralMusicController(tmp_path, mode="default")
    controller.stop = MagicMock()  # type: ignore[method-assign]
    controller.start = MagicMock(return_value=True)  # type: ignore[method-assign]

    controller.set_mode("sensei")

    assert controller.mode == "sensei"
    assert controller.status.muted is True
    controller.stop.assert_not_called()
    controller.start.assert_not_called()


def test_mode_and_volume_are_clamped_without_starting_audio(tmp_path: Path):
    controller = ProceduralMusicController(tmp_path)
    controller.set_mode("the_sprawl")
    controller.set_volume(200)
    assert controller.mode == "the_sprawl"
    assert controller.status.volume == 100
    assert controller.status.muted is True
