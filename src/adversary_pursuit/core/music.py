"""Local procedural atmosphere for terminal sessions.

Music is presentation only. It consumes no investigation events and exposes no
analytical state. Playback is opt-in, non-blocking, and uses a small generated
WAV through an already-installed operating-system player.
"""

from __future__ import annotations

import math
import shutil
import struct
import subprocess
import threading
import wave
from dataclasses import dataclass
from pathlib import Path

_PALETTES: dict[str, tuple[float, ...]] = {
    "default": (110.0, 164.81, 220.0),
    "ninja": (73.42, 110.0, 146.83),
    "full_troll": (110.0, 220.0, 329.63),
    "bureaucrat": (98.0, 123.47, 146.83),
    "strategist": (82.41, 123.47, 164.81),
    "sensei": (110.0, 146.83, 196.0),
    "detective": (73.42, 92.5, 110.0),
    "the_computer": (65.41, 130.81, 261.63),
    "the_sprawl": (55.0, 82.41, 123.47),
    "m4tr1x": (73.42, 146.83, 220.0),
}


@dataclass(frozen=True)
class MusicStatus:
    available: bool
    enabled: bool
    muted: bool
    volume: int
    reason: str = ""


class ProceduralMusicController:
    """Generate and loop a restrained local atmosphere without blocking UI."""

    def __init__(self, cache_dir: Path, mode: str = "default", volume: int = 18) -> None:
        self.cache_dir = cache_dir
        self.mode = mode
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
        self.mode = mode if mode in _PALETTES else "default"

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
        self._process = None
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

    def _render(self, path: Path) -> None:
        """Render an original four-part movement with recurring, evolving motifs.

        The score is deterministic and consumes no analytical state.  Its form
        moves through ambient, riff, melody, imitation, and release sections so
        the loop breathes without turning hunt results into musical claims.
        """
        sample_rate = 22_050
        seconds = 32
        amplitude = 4_800 * (self.volume / 100)
        notes = _PALETTES.get(self.mode, _PALETTES["default"])
        intervals = (1.0, 9 / 8, 4 / 3, 3 / 2, 5 / 3)
        motif = (0, 2, 4, 1, 3, 2, 0, 4)
        beat = 0.62 if self.mode in {"sensei", "m4tr1x", "full_troll"} else 0.82
        frames = bytearray()
        for index in range(sample_rate * seconds):
            time = index / sample_rate
            step = int(time / beat)
            section = int(time // 8)  # bed -> riff -> imitation -> release
            within = (time % beat) / beat
            envelope = min(1.0, within / 0.08) * max(0.0, 1.0 - within) ** 1.7

            root = notes[0] / 2
            drone = math.sin(2 * math.pi * root * time) * 0.22
            bass_degree = motif[(step // 2 + section) % len(motif)]
            bass_frequency = notes[0] * intervals[bass_degree]
            bass = math.sin(2 * math.pi * bass_frequency * time) * envelope * 0.22

            lead_degree = motif[(step + section) % len(motif)]
            lead_frequency = notes[1] * intervals[lead_degree]
            lead_density = 0.0 if section == 0 and step % 4 else (0.18 if section < 3 else 0.10)
            lead = math.sin(2 * math.pi * lead_frequency * time) * envelope * lead_density

            # A restrained delayed answer creates two-voice imitation in the
            # third section, then recedes for a quiet cadence.
            answer_step = max(0, step - 2)
            answer_degree = motif[(answer_step + 1) % len(motif)]
            answer_frequency = notes[2] * intervals[answer_degree]
            answer = math.sin(2 * math.pi * answer_frequency * time) * envelope * (0.11 if section == 2 else 0.03)

            shimmer = math.sin(2 * math.pi * (lead_frequency * 2.01) * time) * envelope * (0.025 if step % 3 == 0 else 0.0)
            slow_breath = 0.78 + 0.22 * math.sin(2 * math.pi * time / 16)
            sample = amplitude * slow_breath * (drone + bass + lead + answer + shimmer)
            frames.extend(struct.pack("<h", max(-32767, min(32767, int(sample)))))
        with wave.open(str(path), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(sample_rate)
            output.writeframes(frames)
