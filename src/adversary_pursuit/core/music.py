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
import shutil
import struct
import subprocess
import threading
import wave
from array import array
from dataclasses import dataclass
from pathlib import Path

_SAMPLE_RATE = 22_050
_DURATION = 32.0


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


def _transformed_motif(theme: ThemeSpec, section: int) -> tuple[int, ...]:
    motif = theme.motif
    if section == 0:
        return motif
    if section == 1:
        return motif[2:] + motif[:2]
    if section == 2:
        axis = motif[0] + motif[-1]
        return tuple(max(0, axis - degree) for degree in motif)
    return motif[:3] + tuple(reversed(motif[:2]))


def _plan_score(theme: ThemeSpec) -> tuple[NoteEvent, ...]:
    """Build a deterministic four-act score: establish, disturb, pursue, return."""
    beat = 60.0 / theme.tempo
    events: list[NoteEvent] = []

    for section in range(4):
        section_start = section * 8.0
        tension = theme.tension_curve[section]
        bass_degree = theme.bass[section]

        # A section pedal and changing upper tones establish harmonic direction.
        events.append(NoteEvent(section_start, 8.05, _frequency(theme, bass_degree, -1), 0.12 * tension, theme.pad_voice))
        for chord_degree in (bass_degree + 2, bass_degree + 4):
            events.append(NoteEvent(section_start, 7.8, _frequency(theme, chord_degree), 0.035 * tension, theme.pad_voice))

        motif = _transformed_motif(theme, section)
        cursor = section_start + (beat * (0.5 if section == 1 else 0.0))
        phrase = 0
        while cursor < section_start + 7.45:
            phrase_start = cursor
            for note_index, degree in enumerate(motif):
                rhythm = theme.rhythm[note_index % len(theme.rhythm)] * beat
                if cursor >= section_start + 7.55:
                    break
                octave = 1 if section == 2 and note_index >= len(motif) // 2 else 0
                duration = min(rhythm * theme.articulation, section_start + 7.8 - cursor)
                accent = 1.12 if note_index == 0 else 1.0
                events.append(NoteEvent(cursor, duration, _frequency(theme, degree, octave), 0.13 * tension * accent, theme.lead_voice))

                # The pursuit section answers the motif at a stable delay. This
                # is actual voice-leading, not a copy of the lead oscillator.
                if section == 2 and note_index % 2 == 0:
                    answer_degree = motif[(note_index - 1) % len(motif)] + 2
                    answer_start = cursor + beat * theme.counterpoint
                    events.append(NoteEvent(answer_start, duration * 0.82, _frequency(theme, answer_degree), 0.065, "answer"))
                cursor += rhythm

            # A breath between phrases makes recurrence and transformation clear.
            phrase += 1
            cursor = max(cursor, phrase_start + beat * theme.meter)
            cursor += beat * (0.35 if phrase % 2 else 0.65)

        # Bass motion follows meter while the lead breathes independently.
        bass_cursor = section_start
        bass_step = 0
        while bass_cursor < section_start + 7.7:
            degree = theme.bass[(section + bass_step) % len(theme.bass)]
            events.append(NoteEvent(bass_cursor, beat * 0.7, _frequency(theme, degree, -1), 0.12 * tension, theme.bass_voice))
            bass_cursor += beat * theme.meter
            bass_step += 1

        # Theme-specific pulse patterns give meters a physical identity.
        pulse_step = beat * theme.pulse_rate
        for pulse_index in range(int(8.0 / pulse_step)):
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

    return tuple(event for event in events if event.start < _DURATION)


def _oscillator(voice: str, phase: float) -> float:
    sine = math.sin(phase)
    if voice in {"warm", "reed", "answer", "current", "orbit", "plan", "foundation", "measure", "field", "stride"}:
        return 0.78 * sine + 0.18 * math.sin(2 * phase) + 0.04 * math.sin(3 * phase)
    if voice in {"bell", "bowl", "gong", "glass", "digital", "machine", "cascade", "blade", "clue", "star", "seed"}:
        return 0.68 * sine + 0.22 * math.sin(2.01 * phase) + 0.1 * math.sin(3.97 * phase)
    if voice in {"square", "grit", "pulse", "sub", "earth", "grid", "signal", "shadow", "step", "footfall", "knock"}:
        return 0.72 * sine + 0.2 * math.sin(3 * phase) + 0.08 * math.sin(5 * phase)
    if voice in {"hollow", "distant"}:
        return 0.82 * sine - 0.18 * math.sin(2 * phase)
    if voice in {"air", "breath", "smoke", "fog", "cold", "neon", "veil", "rain", "cloud", "horizon", "sky"}:
        shimmer = 0.16 if voice == "neon" else 0.1
        return (1.0 - shimmer) * sine + shimmer * math.sin(phase * 1.005)
    return sine


def _envelope(voice: str, position: float, duration: float) -> float:
    attack = min(0.24 if voice in {"air", "breath", "smoke", "fog", "cold", "neon", "veil", "rain", "cloud", "horizon", "sky"} else 0.035, duration * 0.25)
    release = min(0.28 if voice not in {"pluck", "pulse", "clock"} else 0.08, duration * 0.4)
    attack_level = min(1.0, position / max(attack, 0.001))
    release_level = min(1.0, (duration - position) / max(release, 0.001))
    body = 0.86 + 0.14 * math.sin(math.pi * min(1.0, position / max(duration, 0.001)))
    if voice in {"pluck", "clock", "bell", "bowl", "gong", "pulse", "machine", "cascade", "signal", "blade", "step", "clue", "knock"}:
        body *= math.exp(-2.8 * position / max(duration, 0.001))
    return max(0.0, min(attack_level, release_level)) * body


class ProceduralMusicController:
    """Generate and loop a restrained local soundtrack without blocking UI."""

    def __init__(self, cache_dir: Path, mode: str = "default", volume: int = 18) -> None:
        self.cache_dir = cache_dir
        self.mode = mode if mode in _THEMES else "default"
        self.volume = max(0, min(100, volume))
        self._player = self._find_player()
        self._process: subprocess.Popen[bytes] | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._enabled = False
        self._muted = True

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
        next_mode = mode if mode in _THEMES else "default"
        if next_mode == self.mode:
            return
        was_enabled = self._enabled
        if was_enabled:
            self.stop()
        self.mode = next_mode
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
        self._render(self.cache_dir / "atmosphere.wav")
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
        path = self.cache_dir / "atmosphere.wav"
        while not self._stop.is_set() and self._player is not None:
            try:
                self._process = subprocess.Popen(  # noqa: S603
                    [*self._player, str(path)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                self._process.wait()
            except OSError:
                self._player = None
                break
        self._enabled = False
        self._muted = True

    def _score(self) -> tuple[NoteEvent, ...]:
        """Return the inspectable deterministic score for the active theme."""
        return _plan_score(_THEMES[self.mode])

    def _render(self, path: Path) -> None:
        """Render the active score as an original 32-second mono movement."""
        frame_count = int(_SAMPLE_RATE * _DURATION)
        mix = array("d", [0.0]) * frame_count

        for event in self._score():
            first_frame = max(0, int(event.start * _SAMPLE_RATE))
            event_frames = min(int(event.duration * _SAMPLE_RATE), frame_count - first_frame)
            for offset in range(event_frames):
                position = offset / _SAMPLE_RATE
                phase = 2 * math.pi * event.frequency * position
                sample = event.amplitude * _oscillator(event.voice, phase)
                mix[first_frame + offset] += sample * _envelope(event.voice, position, event.duration)

        def shaped_sample(index: int, sample: float) -> float:
            time = index / _SAMPLE_RATE
            edge = min(1.0, time / 0.18, (_DURATION - time) / 0.28)
            return math.tanh(sample * 0.82) * max(0.0, edge)

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
