"""Procedural music remains local, optional, and independent of analysis."""

import struct
import threading
import time
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch

from adversary_pursuit.core.music import (
    _PERFORMED_CONTRACTS,
    _THEMES,
    ProceduralMusicController,
    _score_id,
)


def test_music_starts_muted_and_reports_unavailable_honestly(tmp_path: Path):
    with patch.object(ProceduralMusicController, "_find_player", return_value=None):
        controller = ProceduralMusicController(tmp_path)
    assert controller.status.muted is True
    assert controller.status.enabled is False
    assert controller.status.available is False
    assert controller.start() is False
    assert not tmp_path.exists() or list(tmp_path.iterdir()) == []


def test_start_returns_before_initial_render_finishes(tmp_path: Path):
    controller = ProceduralMusicController(tmp_path)
    controller._player = ("fake-player",)
    entered = threading.Event()
    release = threading.Event()

    def slow_render(*args, **kwargs):
        entered.set()
        release.wait(timeout=2)
        return False

    controller._render = slow_render  # type: ignore[method-assign]
    started = time.monotonic()
    assert controller.start() is True
    assert time.monotonic() - started < 0.2
    assert entered.wait(timeout=1)
    release.set()
    assert controller._thread is not None
    controller._thread.join(timeout=1)


def test_next_tui_cycle_is_prerendered_while_current_cycle_plays(tmp_path: Path):
    controller = ProceduralMusicController(tmp_path)
    controller._player = ("fake-player",)
    rendered_cycles: list[int] = []
    next_ready = threading.Event()

    def render(*args, cycle=None, **kwargs):
        rendered_cycles.append(cycle)
        if cycle == 1:
            next_ready.set()
        return True

    class FakeProcess:
        def wait(self):
            assert next_ready.wait(timeout=1)
            controller._stop.set()

        def poll(self):
            return 0

    controller._render = render  # type: ignore[method-assign]
    with patch("adversary_pursuit.core.music.subprocess.Popen", return_value=FakeProcess()):
        controller._play_loop()
    assert rendered_cycles == [0, 1]


def test_renderer_writes_owned_local_layered_wave(tmp_path: Path):
    controller = ProceduralMusicController(tmp_path, mode="sensei", volume=20)
    output = tmp_path / "sensei.wav"
    controller._render(output)
    assert output.read_bytes().startswith(b"RIFF")
    with wave.open(str(output), "rb") as rendered:
        assert rendered.getframerate() == 22_050
        assert rendered.getnchannels() == 1
        assert 25 <= rendered.getnframes() / rendered.getframerate() <= 38
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
            (
                round(event.start, 3),
                round(event.duration, 3),
                round(event.frequency, 2),
                event.voice,
            )
            for event in score
        )

    assert signature(sensei) != signature(sprawl)
    assert signature(sprawl) != signature(computer)
    assert len({event.voice for event in sensei}) >= 5
    assert len({event.voice for event in sprawl}) >= 5


def test_score_has_form_memory_and_transformation(tmp_path: Path):
    score = ProceduralMusicController(tmp_path, mode="sherlock_holmes")._score()
    lead = [event for event in score if event.voice == _THEMES["sherlock_holmes"].lead_voice]
    answers = [event for event in score if event.voice == "answer"]
    section = 60 / _THEMES["sherlock_holmes"].tempo * 6 * 2

    assert any(event.start < section for event in lead)
    assert any(section <= event.start < section * 2 for event in lead)
    assert any(section * 2 <= event.start < section * 3 for event in lead)
    assert any(section * 3 <= event.start < section * 4 for event in lead)
    assert answers


def test_public_score_bibles_have_distinct_compositional_grammar():
    names = (
        "default",
        "chuck_norris",
        "full_troll",
        "hal9000",
        "sherlock_holmes",
        "neuromancer",
        "the_matrix",
    )
    specs = [_THEMES[name] for name in names]
    signatures = {
        (
            spec.tempo,
            spec.meter,
            spec.phrase_bars,
            spec.scale,
            spec.motif,
            spec.rhythm,
            spec.cadence,
            spec.form,
            spec.lead_voice,
            spec.bass_voice,
            spec.pad_voice,
            spec.pulse,
        )
        for spec in specs
    }
    assert len(signatures) == len(names)
    assert {spec.public_identity for spec in specs} == {
        "Default (Analyst)",
        "Chuck Norris",
        "Troll",
        "HAL9000",
        "Sherlock Holmes",
        "Neuromancer",
        "The Matrix",
    }
    synthetic_tokens = {"machine", "code", "packet", "signal", "pulse", "square"}
    for spec in specs:
        assert not synthetic_tokens.intersection(
            {spec.lead_voice, spec.bass_voice, spec.pad_voice, spec.pulse_voice}
        )


def test_public_scores_keep_their_characteristic_ensembles():
    expected = {
        "default": ("piano", "cello", "strings", "timpani"),
        "chuck_norris": ("french_horn", "baritone_guitar", "strings", "timpani"),
        "full_troll": ("bass_clarinet", "pizzicato_strings", "muted_strings", "woodblock"),
        "hal9000": ("glass_harmonica", "cello", "choir", "frame_drum"),
        "sherlock_holmes": ("solo_violin", "bassoon", "chamber_strings", "woodblock"),
        "neuromancer": ("electric_cello", "synth_bass", "analog_strings", "gated_snare"),
        "the_matrix": ("string_ostinato", "low_strings", "brass_choir", "taiko"),
    }
    for name, ensemble in expected.items():
        theme = _THEMES[name]
        assert (theme.lead_voice, theme.bass_voice, theme.pad_voice, theme.pulse_voice) == ensemble


def test_preserved_internal_ids_resolve_to_requested_public_scores():
    assert _score_id("sensei") == "chuck_norris"
    assert _score_id("the_computer") == "hal9000"
    assert _score_id("detective") == "sherlock_holmes"
    assert _score_id("the_sprawl") == "neuromancer"
    assert _score_id("m4tr1x") == "the_matrix"


def test_all_public_scores_render_pairwise_distinct_event_timelines(tmp_path: Path):
    names = (
        "default",
        "chuck_norris",
        "full_troll",
        "hal9000",
        "sherlock_holmes",
        "neuromancer",
        "the_matrix",
    )
    signatures = set()
    for name in names:
        score = ProceduralMusicController(tmp_path, mode=name)._score()
        signatures.add(
            tuple(
                (
                    round(event.start, 3),
                    round(event.duration, 3),
                    round(event.frequency, 2),
                    event.voice,
                )
                for event in score
            )
        )
        assert len({event.voice for event in score}) >= 4
    assert len(signatures) == len(names)


def test_macro_cycles_are_reproducible_varied_and_protect_return(tmp_path: Path):
    controller = ProceduralMusicController(tmp_path, mode="neuromancer")
    first = controller._score(cycle=1)
    repeat = controller._score(cycle=1)
    next_cycle = controller._score(cycle=2)
    assert first == repeat
    assert first != next_cycle
    theme = _THEMES["neuromancer"]
    return_start = 3 * (60 / theme.tempo * theme.meter * theme.phrase_bars)
    first_return = [
        event.frequency
        for event in first
        if event.voice == theme.lead_voice and event.start >= return_start
    ]
    next_return = [
        event.frequency
        for event in next_cycle
        if event.voice == theme.lead_voice and event.start >= return_start
    ]
    assert first_return[-2:] == next_return[-2:]


def test_tui_identity_fields_match_web_score_authority_contract():
    expected = {
        "default": (45, 108, 4, 4, (0, 2, 4, 5, 7, 9, 10), (0, 1, 3, 2, 4)),
        "chuck_norris": (38, 132, 4, 4, (0, 2, 4, 5, 7, 9, 10), (0, 4, 3, 5, 2)),
        "full_troll": (43, 118, 7, 2, (0, 2, 4, 6, 7, 9, 10), (0, 3, 1, 4, 2, 1)),
        "hal9000": (36, 76, 5, 2, (0, 2, 4, 6, 8, 10), (0, 3, 2, 4, 1)),
        "sherlock_holmes": (38, 96, 6, 2, (0, 2, 3, 5, 7, 8, 11), (0, 5, 4, 2, 3, 1)),
        "neuromancer": (31, 132, 4, 4, (0, 2, 3, 5, 7, 8, 10), (0, 0, 4, 3, 6, 5, 3, 2)),
        "the_matrix": (36, 126, 4, 4, (0, 1, 3, 5, 7, 8, 10), (0, 0, 4, 2, 0, 5, 4, 2)),
    }
    for name, identity in expected.items():
        theme = _THEMES[name]
        assert (
            theme.root_midi,
            theme.tempo,
            theme.meter,
            theme.phrase_bars,
            theme.scale,
            theme.motif,
        ) == identity
        contract = _PERFORMED_CONTRACTS[name]
        assert theme.rhythm == contract["rhythm"]
        assert theme.pulse == contract["pulse"]
        assert theme.chords == contract["chords"]
        assert theme.progression == contract["progression"]
        assert theme.orchestration == contract["orchestration"]
        assert theme.pulse_rate == 0.5


def test_renderer_has_headroom_and_faded_loop_edges(tmp_path: Path):
    output = tmp_path / "sprawl.wav"
    ProceduralMusicController(tmp_path, mode="the_sprawl", volume=100)._render(output)
    with wave.open(str(output), "rb") as rendered:
        samples = struct.unpack(
            f"<{rendered.getnframes()}h", rendered.readframes(rendered.getnframes())
        )

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
