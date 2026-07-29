"""Local procedural soundtracks for terminal sessions.

Music is presentation only. It consumes no investigation events and exposes no
analytical state. Playback is opt-in, non-blocking, and uses an original,
deterministically generated WAV through an already-installed system player.

The composition engine deliberately builds an inspectable score before audio
rendering. Character identity therefore lives in motif, rhythm, harmony, form,
and instrumental roles rather than in frequency palettes hidden in a sample
loop. See ``docs/PROCEDURAL_MUSIC.md`` for the design note.
"""

from __future__ import annotations

import math
import random
import shutil
import struct
import subprocess
import threading
import wave
from array import array
from dataclasses import dataclass
from pathlib import Path

_SAMPLE_RATE = 22_050


@dataclass(frozen=True)
class ThemeSpec:
    """Declarative musical identity used by the deterministic score planner."""

    root_midi: int
    scale: tuple[int, ...]
    motif: tuple[int, ...]
    rhythm: tuple[float, ...]
    bass: tuple[int, ...]
    tempo: float
    meter: int
    lead_voice: str
    bass_voice: str
    pad_voice: str
    articulation: float
    counterpoint: float
    pulse: tuple[float, ...]
    pulse_rate: float = 1.0
    pulse_voice: str = "pulse"
    tension_curve: tuple[float, ...] = (0.72, 0.9, 1.0, 0.68)
    public_identity: str = "Default (Analyst)"
    phrase_bars: int = 4
    cadence: tuple[int, ...] = (4, 2, 0)
    form: tuple[str, ...] = ("establish", "question", "develop", "return")
    chords: tuple[tuple[int, ...], ...] = ()
    progression: tuple[int, ...] = ()
    orchestration: str = "measured"


@dataclass(frozen=True)
class NoteEvent:
    """A rendered-independent musical event measured in seconds."""

    start: float
    duration: float
    frequency: float
    amplitude: float
    voice: str


_THEMES: dict[str, ThemeSpec] = {
    "default": ThemeSpec(
        40,
        (0, 2, 4, 7, 9),
        (0, 2, 4, 1, 3),
        (0.5, 0.5, 1, 0.5, 2.5),
        (0, 3, 1, 4),
        64,
        4,
        "seed",
        "field",
        "sky",
        0.86,
        0.56,
        (1, 0, 1, 0),
        0.5,
        "stride",
        (0.55, 0.66, 0.78, 0.9),
    ),
    "ninja": ThemeSpec(
        35,
        (0, 1, 3, 5, 6, 8, 10),
        (0, 1, 4, 2, 6, 3),
        (0.5, 0.5, 1, 0.5, 0.5, 2),
        (0, 6, 2, 5),
        140,
        4,
        "blade",
        "shadow",
        "veil",
        0.32,
        0.41,
        (1, 0, 1, 0),
        0.5,
        "step",
        (0.18, 0.34, 0.86, 1.0),
    ),
    "full_troll": ThemeSpec(43, (0, 2, 4, 6, 7, 9, 10), (0, 4, 1, 5, 2, 6), (0.5, 0.5, 1, 0.5, 0.5, 2), (0, 4, 1, 5), 108, 4, "brass", "grit", "glass", 0.58, 0.44, (1, 0, 1, 1)),
    "bureaucrat": ThemeSpec(41, (0, 2, 3, 5, 7, 8, 10), (0, 1, 0, 2, 0, 3), (1, 1, 1, 1, 1, 3), (0, 0, 4, 0), 68, 4, "clock", "square", "air", 0.84, 0.18, (1, 0, 0, 0)),
    "strategist": ThemeSpec(
        40,
        (0, 2, 3, 5, 7, 9, 10),
        (0, 2, 5, 3, 1),
        (1, 1, 2, 1, 3),
        (0, 4, 2, 5),
        60,
        4,
        "plan",
        "foundation",
        "horizon",
        0.9,
        0.64,
        (1, 0, 0, 0),
        1.0,
        "measure",
        (0.28, 0.5, 0.76, 1.0),
    ),
    "sensei": ThemeSpec(
        41,
        (0, 2, 5, 7, 9),
        (0, 2, 1, 4, 3),
        (2, 1, 3, 2, 4),
        (0, 3, 1, 4),
        48,
        6,
        "bowl",
        "earth",
        "breath",
        0.98,
        0.84,
        (1, 0),
        3.0,
        "gong",
    ),
    "detective": ThemeSpec(
        38,
        (0, 2, 3, 5, 7, 8, 11),
        (0, 1, 4, 2, 5, 3),
        (0.5, 0.5, 1, 0.5, 1.5, 2),
        (0, 4, 1, 5),
        72,
        3,
        "clue",
        "footfall",
        "rain",
        0.46,
        0.58,
        (1, 0, 1),
        1.0,
        "knock",
        (0.18, 0.95, 0.78, 0.9),
    ),
    "the_computer": ThemeSpec(
        36,
        (0, 2, 4, 7, 9, 11),
        (0, 3, 5, 2, 4, 1),
        (0.5, 0.5, 1, 0.5, 0.5, 2),
        (0, 3, 1, 4),
        64,
        4,
        "star",
        "current",
        "cloud",
        0.88,
        0.7,
        (1, 1, 1, 1),
        0.5,
        "orbit",
        (0.72, 0.76, 0.8, 0.74),
    ),
    "the_sprawl": ThemeSpec(
        31,
        (0, 1, 3, 5, 6, 8, 10),
        (6, 5, 3, 4, 2, 1, 0),
        (0.5, 0.5, 1, 0.5, 1.5, 0.5, 2.5),
        (0, 1, 6, 2),
        55,
        7,
        "cascade",
        "grid",
        "fog",
        0.82,
        0.73,
        (1, 0, 0, 0, 1, 0, 0),
        0.5,
        "signal",
        (0.42, 0.66, 0.84, 1.0),
    ),
    "m4tr1x": ThemeSpec(
        36,
        (0, 2, 3, 5, 7, 8, 10),
        (0, 0, 4, 2, 0, 5, 4, 2),
        (0.5, 0.5, 0.5, 0.5, 1, 0.5, 0.5, 2),
        (0, 5, 3, 6),
        114,
        4,
        "machine",
        "sub",
        "neon",
        0.46,
        0.5,
        (1, 1, 1, 1),
        0.5,
    ),
}

# Public character names intentionally resolve to seven distinct score bibles.
# Historical/internal identifiers remain accepted so saved preferences and old
# workspaces keep sounding the same while the product restores its public names.
_PUBLIC_SCORE_IDS: dict[str, str] = {
    "default": "default",
    "analyst": "default",
    "chuck_norris": "chuck_norris",
    "sensei": "chuck_norris",
    "troll": "full_troll",
    "full_troll": "full_troll",
    "hal9000": "hal9000",
    "the_computer": "hal9000",
    "sherlock_holmes": "sherlock_holmes",
    "sherlock": "sherlock_holmes",
    "detective": "sherlock_holmes",
    "neuromancer": "neuromancer",
    "the_sprawl": "neuromancer",
    "the_matrix": "the_matrix",
    "matrix": "the_matrix",
    "m4tr1x": "the_matrix",
    "trinity": "the_matrix",
}

_THEMES.update(
    {
        "chuck_norris": ThemeSpec(
            38, (0, 2, 4, 5, 7, 9, 10), (0, 4, 3, 5, 2), (0.5, 0.5, 1, 0.5, 1.5),
            (0, 4, 1, 5), 132, 4, "french_horn", "low_brass", "strings",
            0.72, 0.38, (1, 0, 1, 0, 0, 1, 0, 0), 0.5, "timpani",
            (0.55, 0.82, 1.0, 0.62), "Chuck Norris", 4, (5, 2, 0),
            ("swagger", "setup", "impact", "wink"),
        ),
        "hal9000": ThemeSpec(
            36, (0, 2, 4, 6, 8, 10), (0, 3, 2, 4, 1), (1.5, 0.5, 0.5, 1, 1.5),
            (0, 3, 1, 4), 76, 5, "glass_harmonica", "cello", "choir",
            0.92, 0.72, (1, 0, 0, 1, 0), 1.0, "frame_drum",
            (0.7, 0.74, 0.82, 0.66), "HAL9000", 2, (3, 1, 0),
            ("symmetry", "substitution", "canon", "withhold"),
        ),
        "sherlock_holmes": ThemeSpec(
            38, (0, 2, 3, 5, 7, 8, 11), (0, 5, 4, 2, 3, 1), (0.75, 0.25, 1, 0.5, 0.5, 2),
            (0, 4, 1, 5), 96, 6, "solo_violin", "bassoon", "chamber_strings",
            0.76, 0.74, (1, 0, 0, 1, 0, 0), 0.5, "woodblock",
            (0.42, 0.7, 0.96, 0.74), "Sherlock Holmes", 2, (4, 2, 1),
            ("clue", "deduction", "proof", "one_detail_remains"),
        ),
        "neuromancer": ThemeSpec(
            31, (0, 2, 3, 5, 7, 8, 10), (0, 0, 4, 3, 6, 5, 3, 2),
            (0.5, 0.5, 0.5, 0.5, 1, 0.5, 0.5, 2), (0, 0, 5, 3), 132, 4,
            "electric_cello", "contrabass", "dark_strings", 0.82, 0.7, (1, 0, 0, 1, 0, 1, 0),
            0.5, "timpani", (0.5, 0.74, 1.0, 0.78), "Neuromancer", 4, (5, 2, 0),
            ("night_drive", "jack_in", "ice", "afterimage"),
        ),
        "the_matrix": ThemeSpec(
            36, (0, 1, 3, 5, 7, 8, 10), (0, 0, 4, 2, 0, 5, 4, 2),
            (0.5, 0.5, 0.5, 0.5, 1, 0.5, 0.5, 2), (0, 5, 3, 6), 126, 4,
            "string_ostinato", "low_strings", "brass_choir", 0.68, 0.56, (1, 0, 1, 0, 1, 0, 0, 1),
            0.5, "taiko", (0.5, 0.74, 1.0, 0.68), "The Matrix", 4, (4, 1, 0),
            ("signal", "pursuit", "rabbit", "exit"),
        ),
    }
)

# Enrich the two reused public bibles without duplicating their established
# musical material.
_THEMES["default"] = ThemeSpec(
    **{**_THEMES["default"].__dict__, "root_midi": 45, "tempo": 108,
       "scale": (0, 2, 4, 5, 7, 9, 10), "motif": (0, 1, 3, 2, 4),
       "rhythm": (1, 1, 0.5, 0.5, 2), "bass": (0, 3, 4, 0),
       "lead_voice": "piano", "bass_voice": "cello", "pad_voice": "strings",
       "pulse_voice": "timpani", "articulation": 0.74,
       "public_identity": "Default (Analyst)", "phrase_bars": 4,
       "cadence": (4, 2, 0), "form": ("observe", "question", "synthesize", "resolve")}
)
_THEMES["full_troll"] = ThemeSpec(
    **{**_THEMES["full_troll"].__dict__, "tempo": 118, "meter": 7,
       "motif": (0, 3, 1, 4, 2, 1), "bass": (0, 3, 1, 0),
       "lead_voice": "bass_clarinet", "bass_voice": "cello",
       "pad_voice": "muted_strings", "pulse_voice": "woodblock",
       "public_identity": "Troll", "phrase_bars": 2,
       "cadence": (6, 1, 0), "form": ("bait", "eyeroll", "heckle", "grudging_help")}
)

_PERFORMED_CONTRACTS = {
    "default": {
        "pulse": (1, 0, 0, 0, 1, 0, 0, 0), "rhythm": (1, 1, 0.5, 0.5, 2),
        "chords": ((0, 2, 4), (3, 5, 0), (4, 6, 1), (0, 2, 4)),
        "progression": (0, 1, 2, 0), "orchestration": "measured",
    },
    "chuck_norris": {
        "pulse": (1, 0, 1, 0, 0, 1, 0, 0), "rhythm": (0.5, 0.5, 1, 0.5, 1.5),
        "chords": ((0, 2, 4), (3, 5, 1), (4, 6, 2), (0, 2, 4)),
        "progression": (0, 2, 1, 0), "orchestration": "stop-time",
    },
    "full_troll": {
        "pulse": (1, 0, 1, 0, 1, 0, 0), "rhythm": (0.5, 0.5, 1, 0.5, 0.5, 1),
        "chords": ((0, 2, 4), (3, 5, 1), (1, 4, 0), (0, 2, 4)),
        "progression": (0, 2, 1, 0), "orchestration": "crooked",
    },
    "hal9000": {
        "pulse": (1, 0, 0, 1, 0), "rhythm": (1.5, 0.5, 0.5, 1, 1.5),
        "chords": ((0, 2, 4), (1, 3, 5), (4, 0, 2), (2, 4, 1)),
        "progression": (0, 1, 2, 3), "orchestration": "orbital",
    },
    "sherlock_holmes": {
        "pulse": (1, 0, 0, 1, 0, 0), "rhythm": (0.75, 0.25, 1, 0.5, 0.5, 2),
        "chords": ((0, 2, 4), (3, 5, 1), (4, 0, 2), (0, 2, 4)),
        "progression": (0, 2, 1, 3), "orchestration": "chamber",
    },
    "neuromancer": {
        # Four-on-the-floor low pulse, syncopated cello ostinato, and minor
        # modal harmony produce a darkwave drive without reverting to bleeps.
        "pulse": (1, 0, 1, 0, 1, 0, 1, 0),
        "rhythm": (0.5, 0.5, 0.5, 0.5, 1, 0.5, 0.5, 2),
        "chords": ((0, 2, 4), (5, 0, 2), (3, 5, 1), (4, 1, 3)),
        "progression": (0, 1, 2, 0, 3, 2), "orchestration": "signals",
    },
    "the_matrix": {
        "pulse": (1, 0, 1, 0, 1, 0, 0, 1), "rhythm": (0.5, 0.5, 0.5, 0.5, 1, 0.5, 0.5, 2),
        "chords": ((0, 2, 4), (4, 1, 3), (3, 5, 1), (0, 2, 4)),
        "progression": (0, 1, 2, 1), "orchestration": "pursuit",
    },
}
for _theme_name, _contract in _PERFORMED_CONTRACTS.items():
    _THEMES[_theme_name] = ThemeSpec(
        **{**_THEMES[_theme_name].__dict__, **_contract, "pulse_rate": 0.5}
    )


def _score_id(mode: str) -> str:
    """Resolve a public or preserved internal mode to one score authority."""
    return _PUBLIC_SCORE_IDS.get(mode.strip().lower(), mode if mode in _THEMES else "default")


@dataclass(frozen=True)
class MusicStatus:
    available: bool
    enabled: bool
    muted: bool
    volume: int
    reason: str = ""


def _frequency(theme: ThemeSpec, degree: int, octave: int = 0) -> float:
    scale_size = len(theme.scale)
    scale_octave, scale_degree = divmod(degree, scale_size)
    midi = theme.root_midi + theme.scale[scale_degree] + (scale_octave + octave) * 12
    return 440.0 * (2.0 ** ((midi - 69) / 12))


def _transformed_motif(theme: ThemeSpec, section: int, cycle: int = 0) -> tuple[int, ...]:
    motif = theme.motif
    if section == 0:
        transformed = motif
    elif section == 1:
        transformed = motif[2:] + motif[:2]
    elif section == 2:
        axis = motif[0] + motif[-1]
        transformed = tuple(max(0, axis - degree) for degree in motif)
    else:
        transformed = theme.cadence if section == len(theme.form) - 1 else motif[:3] + tuple(reversed(motif[:2]))
    if cycle and section not in {0, len(theme.form) - 1}:
        offset = cycle % len(transformed)
        transformed = transformed[offset:] + transformed[:offset]
    return transformed


def _plan_score(theme: ThemeSpec, cycle: int = 0) -> tuple[NoteEvent, ...]:
    """Build one reproducible four-act cycle from complete musical phrases."""
    beat = 60.0 / theme.tempo
    section_duration = beat * theme.meter * theme.phrase_bars
    total_duration = section_duration * len(theme.form)
    rng = random.Random(sum((index + 1) * ord(char) for index, char in enumerate(theme.public_identity)) + cycle * 104_729)
    events: list[NoteEvent] = []

    for section in range(len(theme.form)):
        section_start = section * section_duration
        tension = theme.tension_curve[section]
        if theme.chords and theme.progression:
            chord_index = theme.progression[section % len(theme.progression)]
            chord = theme.chords[chord_index % len(theme.chords)]
        else:
            bass_fallback = theme.bass[section % len(theme.bass)]
            chord = (bass_fallback, bass_fallback + 2, bass_fallback + 4)
        bass_degree = chord[0]

        events.append(NoteEvent(section_start, section_duration * 1.01, _frequency(theme, bass_degree, -1), 0.12 * tension, theme.pad_voice))
        upper_degrees = chord[1:3] if tension > 0.65 else chord[1:2]
        for chord_degree in upper_degrees:
            events.append(NoteEvent(section_start, section_duration * 0.97, _frequency(theme, chord_degree), 0.035 * tension, theme.pad_voice))

        motif = _transformed_motif(theme, section, cycle)
        cursor = section_start + (beat * (0.5 if section == 1 else 0.0))
        note_index = 0
        while cursor < section_start + section_duration - beat * 0.2:
            degree = motif[note_index % len(motif)]
            rhythm = theme.rhythm[note_index % len(theme.rhythm)] * beat
            protected_cadence = section == len(theme.form) - 1 and note_index >= len(motif) - 2
            if cycle and not protected_cadence and rng.random() < 0.16:
                degree += rng.choice((-1, 1))
            octave = 1 if section == 2 and note_index >= len(motif) // 2 else 0
            duration = min(rhythm * theme.articulation, section_start + section_duration - cursor)
            accent = 1.12 if note_index % len(motif) == 0 else 1.0
            stop_time = (
                theme.orchestration == "stop-time"
                and section % 2
                and cursor > section_start + section_duration - beat
            )
            if not stop_time:
                events.append(NoteEvent(cursor, duration, _frequency(theme, degree, octave), 0.13 * tension * accent, theme.lead_voice))
            counter_entry = (
                (theme.orchestration == "chamber" and note_index % 3 == 1)
                or (theme.orchestration == "signals" and note_index % 4 == 0)
                or (theme.orchestration == "orbital" and note_index % 5 == 0)
                or (section == 2 and note_index % 2 == 0)
            )
            if counter_entry:
                answer_start = cursor + beat * theme.counterpoint
                counter_degree = degree + (3 if theme.orchestration == "crooked" else 2)
                events.append(NoteEvent(answer_start, duration * 0.82, _frequency(theme, counter_degree), 0.065, "answer"))
            cursor += rhythm
            note_index += 1

        # Bass motion follows meter while the lead breathes independently.
        bass_cursor = section_start
        bass_step = 0
        while bass_cursor < section_start + section_duration - beat * 0.2:
            degree = theme.bass[(section + bass_step) % len(theme.bass)]
            events.append(NoteEvent(bass_cursor, beat * 0.7, _frequency(theme, degree, -1), 0.12 * tension, theme.bass_voice))
            bass_cursor += beat * theme.meter
            bass_step += 1

        # Theme-specific pulse patterns give meters a physical identity.
        pulse_step = beat * theme.pulse_rate
        for pulse_index in range(int(section_duration / pulse_step)):
            if theme.pulse[pulse_index % len(theme.pulse)]:
                start = section_start + pulse_index * pulse_step
                events.append(
                    NoteEvent(
                        start,
                        pulse_step * 0.22,
                        _frequency(theme, bass_degree, -2),
                        0.055 * tension,
                        theme.pulse_voice,
                    )
                )

    return tuple(event for event in events if event.start < total_duration)


def _oscillator(voice: str, phase: float) -> float:
    """Return an additive acoustic-instrument approximation.

    The profiles emphasize formants and natural harmonic roll-off instead of
    square/saw waves, removing the arcade-like "bloop" character while keeping
    the renderer dependency-free and deterministic.
    """
    profiles: dict[str, tuple[float, ...]] = {
        "piano": (1.0, 0.62, 0.34, 0.2, 0.11, 0.07, 0.04),
        "strings": (1.0, 0.48, 0.30, 0.19, 0.12, 0.08, 0.05),
        "chamber_strings": (1.0, 0.52, 0.32, 0.20, 0.13, 0.08),
        "muted_strings": (1.0, 0.34, 0.17, 0.09, 0.05),
        "dark_strings": (1.0, 0.42, 0.28, 0.18, 0.12, 0.07),
        "low_strings": (1.0, 0.55, 0.32, 0.18, 0.10),
        "string_ostinato": (1.0, 0.58, 0.36, 0.22, 0.14, 0.08),
        "cello": (1.0, 0.55, 0.30, 0.16, 0.10, 0.06),
        "electric_cello": (1.0, 0.52, 0.28, 0.20, 0.13, 0.08),
        "contrabass": (1.0, 0.48, 0.24, 0.13, 0.07),
        "solo_violin": (1.0, 0.58, 0.37, 0.24, 0.16, 0.10, 0.06),
        "french_horn": (1.0, 0.28, 0.46, 0.24, 0.14, 0.07),
        "low_brass": (1.0, 0.38, 0.52, 0.25, 0.12, 0.06),
        "brass_choir": (1.0, 0.33, 0.46, 0.28, 0.16, 0.08),
        "bassoon": (1.0, 0.20, 0.55, 0.16, 0.32, 0.08),
        "bass_clarinet": (1.0, 0.04, 0.58, 0.03, 0.30, 0.02, 0.14),
        "answer": (1.0, 0.03, 0.62, 0.02, 0.34, 0.01, 0.18),
        "choir": (1.0, 0.35, 0.18, 0.30, 0.12, 0.16, 0.07),
        "glass_harmonica": (1.0, 0.08, 0.42, 0.05, 0.24, 0.04, 0.16),
        "timpani": (1.0, 0.12, 0.05),
        "taiko": (1.0, 0.20, 0.08),
        "frame_drum": (1.0, 0.10, 0.04),
        "woodblock": (1.0, 0.35, 0.16),
    }
    partials = profiles.get(voice, profiles.get("strings", (1.0,)))
    normalization = max(1.0, sum(partials) * 0.72)
    return sum(
        strength * math.sin((index + 1) * phase)
        for index, strength in enumerate(partials)
    ) / normalization


def _envelope(voice: str, position: float, duration: float) -> float:
    sustained = {
        "strings", "chamber_strings", "muted_strings", "dark_strings",
        "low_strings", "cello", "electric_cello", "contrabass", "solo_violin",
        "french_horn", "low_brass", "brass_choir", "bassoon",
        "bass_clarinet", "choir", "glass_harmonica", "answer",
    }
    percussion = {"piano", "timpani", "taiko", "frame_drum", "woodblock"}
    attack = min(0.18 if voice in sustained else 0.012, duration * 0.25)
    release = min(0.42 if voice in sustained else 0.14, duration * 0.42)
    attack_level = min(1.0, position / max(attack, 0.001))
    release_level = min(1.0, (duration - position) / max(release, 0.001))
    body = 0.86 + 0.14 * math.sin(math.pi * min(1.0, position / max(duration, 0.001)))
    if voice in percussion:
        rate = 2.0 if voice == "piano" else 4.2
        body *= math.exp(-rate * position / max(duration, 0.001))
    return max(0.0, min(attack_level, release_level)) * body


class ProceduralMusicController:
    """Generate and loop a restrained local soundtrack without blocking UI."""

    def __init__(self, cache_dir: Path, mode: str = "default", volume: int = 18) -> None:
        self.cache_dir = cache_dir
        self.mode = mode if _score_id(mode) != "default" or mode in {"default", "analyst"} else "default"
        self.volume = max(0, min(100, volume))
        self._player = self._find_player()
        self._process: subprocess.Popen[bytes] | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._enabled = False
        self._muted = True
        self._cycle = 0

    @staticmethod
    def _find_player() -> tuple[str, ...] | None:
        for command, args in (("afplay", ()), ("aplay", ("-q",)), ("paplay", ())):
            resolved = shutil.which(command)
            if resolved:
                return (resolved, *args)
        return None

    @property
    def status(self) -> MusicStatus:
        return MusicStatus(
            available=self._player is not None,
            enabled=self._enabled,
            muted=self._muted,
            volume=self.volume,
            reason="" if self._player else "no supported local audio player",
        )

    def set_mode(self, mode: str) -> None:
        next_mode = mode if _score_id(mode) != "default" or mode in {"default", "analyst"} else "default"
        if next_mode == self.mode:
            return
        was_enabled = self._enabled
        if was_enabled:
            self.stop()
        self.mode = next_mode
        self._cycle = 0
        if was_enabled:
            self.start()

    def set_volume(self, volume: int) -> None:
        self.volume = max(0, min(100, volume))
        if self._enabled:
            self.stop()
            self.start()

    def toggle_mute(self) -> MusicStatus:
        if self._enabled:
            self.stop()
        else:
            self.start()
        return self.status

    def start(self) -> bool:
        if self._player is None or self._enabled:
            return False
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._stop.clear()
        self._enabled = True
        self._muted = False
        self._thread = threading.Thread(target=self._play_loop, daemon=True, name="ap-music")
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop.set()
        process = self._process
        if process is not None and process.poll() is None:
            process.terminate()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=1.0)
        self._process = None
        self._thread = None
        self._enabled = False
        self._muted = True

    def _play_loop(self) -> None:
        current_path = self.cache_dir / "atmosphere-0.wav"
        if not self._render(current_path, cycle=self._cycle, cancel=self._stop):
            self._enabled = False
            self._muted = True
            return
        while not self._stop.is_set() and self._player is not None:
            try:
                self._process = subprocess.Popen(  # noqa: S603
                    [*self._player, str(current_path)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                next_cycle = self._cycle + 1
                next_path = self.cache_dir / f"atmosphere-{next_cycle % 2}.wav"
                rendered = [False]

                def prepare_next() -> None:
                    rendered[0] = self._render(
                        next_path,
                        cycle=next_cycle,
                        cancel=self._stop,
                    )

                renderer = threading.Thread(
                    target=prepare_next,
                    daemon=True,
                    name=f"ap-music-render-{next_cycle}",
                )
                renderer.start()
                self._process.wait()
                renderer.join()
                if not self._stop.is_set() and rendered[0]:
                    self._cycle = next_cycle
                    current_path = next_path
            except OSError:
                self._player = None
                break
        self._enabled = False
        self._muted = True

    def _score(self, cycle: int | None = None) -> tuple[NoteEvent, ...]:
        """Return the inspectable deterministic score for the active theme."""
        return _plan_score(_THEMES[_score_id(self.mode)], self._cycle if cycle is None else cycle)

    def _render(
        self,
        path: Path,
        *,
        cycle: int | None = None,
        cancel: threading.Event | None = None,
    ) -> bool:
        """Render the active score as one complete original mono movement."""
        score = self._score(cycle)
        duration = max(event.start + event.duration for event in score) + 0.3
        frame_count = int(_SAMPLE_RATE * duration)
        mix = array("d", [0.0]) * frame_count

        for event in score:
            first_frame = max(0, int(event.start * _SAMPLE_RATE))
            event_frames = min(int(event.duration * _SAMPLE_RATE), frame_count - first_frame)
            for offset in range(event_frames):
                if cancel is not None and offset % 4096 == 0 and cancel.is_set():
                    return False
                position = offset / _SAMPLE_RATE
                phase = 2 * math.pi * event.frequency * position
                sample = event.amplitude * _oscillator(event.voice, phase)
                mix[first_frame + offset] += sample * _envelope(event.voice, position, event.duration)

        def shaped_sample(index: int, sample: float) -> float:
            time = index / _SAMPLE_RATE
            edge = min(1.0, time / 0.18, (duration - time) / 0.28)
            # Three quiet, non-periodic early reflections create a restrained
            # orchestral room without turning the movement into an echo loop.
            room = sample
            for delay, gain in ((0.071, 0.11), (0.137, 0.075), (0.223, 0.045)):
                delayed_index = index - int(delay * _SAMPLE_RATE)
                if delayed_index >= 0:
                    room += mix[delayed_index] * gain
            return math.tanh(room * 0.78) * max(0.0, edge)

        peak = max(abs(shaped_sample(index, sample)) for index, sample in enumerate(mix))
        amplitude = 30_000 * (self.volume / 100) / max(peak, 1e-9)
        frames = bytearray()
        for index, sample in enumerate(mix):
            # Fade the complete form at both edges so a loop seam never clicks.
            softened = shaped_sample(index, sample)
            frames.extend(struct.pack("<h", max(-32767, min(32767, int(amplitude * softened)))))

        with wave.open(str(path), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(_SAMPLE_RATE)
            output.writeframes(frames)
        return True
