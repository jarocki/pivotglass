"""AI voice stays opt-in through configuration and never alters narration text."""

import json

import pytest

from pivotglass.web import advisor_voice


class _Config:
    def __init__(self, key=None):
        self.key = key

    def get_provider_api_key(self, provider):
        assert provider == "openai"
        return self.key


def test_voice_requires_key_and_bounded_visible_text():
    with pytest.raises(ValueError, match="not configured"):
        advisor_voice.synthesize_advisor_voice(_Config(), "sensei", "Visible advice")
    with pytest.raises(ValueError, match="1–600"):
        advisor_voice.synthesize_advisor_voice(_Config("test"), "sensei", "x" * 601)


def test_voice_uses_character_direction_without_changing_narration(monkeypatch):
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def read(self, size):
            assert size == 2_000_001
            return b"ID3sample"

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr(advisor_voice, "urlopen", fake_urlopen)
    assert advisor_voice.synthesize_advisor_voice(_Config("test-key"), "full_troll", "Check the source.") == b"ID3sample"
    body = json.loads(captured["request"].data)
    assert body["input"] == "Check the source."
    assert body["voice"] == "fable"
    assert body["model"] == "gpt-4o-mini-tts"
    assert captured["timeout"] == 20
