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
        sample_rate = 8_000
        seconds = 6
        amplitude = int(2_400 * (self.volume / 100))
        notes = _PALETTES.get(self.mode, _PALETTES["default"])
        frames = bytearray()
        for index in range(sample_rate * seconds):
            segment = min(len(notes) - 1, index // (sample_rate * 2))
            phase = 2 * math.pi * notes[segment] * index / sample_rate
            envelope = 0.55 + 0.45 * math.sin(math.pi * (index % (sample_rate * 2)) / (sample_rate * 2))
            frames.extend(struct.pack("<h", int(amplitude * envelope * math.sin(phase))))
        with wave.open(str(path), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(sample_rate)
            output.writeframes(frames)
