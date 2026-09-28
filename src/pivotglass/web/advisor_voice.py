"""Optional, bounded AI speech for presentation-only Advisor narration."""

from __future__ import annotations

import json
from urllib.request import Request, urlopen

_VOICES = {
    "default": ("marin", "Warm, clear, measured analyst briefing."),
    "sensei": ("cedar", "Confident, wry, energetic, with natural pauses."),
    "the_computer": ("onyx", "Quiet, deep, restrained, spacious, and subtly ominous."),
    "full_troll": ("fable", "Playful, quick-witted, bouncy, and conversational."),
    "detective": ("sage", "Curious, incisive, lightly theatrical, with thoughtful pauses."),
    "the_sprawl": ("ash", "Low, intimate, dark, and reflective."),
    "m4tr1x": ("coral", "Kinetic, assured, conversational, and rhythmically varied."),
}


def synthesize_advisor_voice(config_mgr: object, character: str, message: str) -> bytes:
    """Speak visible narration with a configured OpenAI key; never send evidence."""
    text = message.strip()
    if not text or len(text) > 600:
        raise ValueError("advisor narration must contain 1–600 characters")
    key = config_mgr.get_provider_api_key("openai")  # type: ignore[attr-defined]
    if not key:
        raise ValueError("OpenAI voice is not configured")
    voice, direction = _VOICES.get(character, _VOICES["default"])
    body = json.dumps({
        "model": "gpt-4o-mini-tts",
        "voice": voice,
        "input": text,
        "instructions": direction + " Speak naturally. Do not add or change words.",
        "response_format": "mp3",
    }).encode("utf-8")
    request = Request(
        "https://api.openai.com/v1/audio/speech",
        data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=20) as response:
        audio = response.read(2_000_001)
    if not audio or len(audio) > 2_000_000:
        raise ValueError("advisor audio response is empty or too large")
    return audio
