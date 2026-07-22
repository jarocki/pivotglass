"""Cross-interface gates for the v0.4.9 quality-assurance release."""

from pathlib import Path

from adversary_pursuit.agent.tui.themes import (
    COCKPIT_PROFILES,
    DEFAULT_THEMES,
    PRESENTATION_CONTRACTS,
)
from adversary_pursuit.gamification.modes import DEFAULT_MODES


def test_every_selectable_mode_has_one_complete_presentation_contract():
    names = set(DEFAULT_MODES)
    assert set(DEFAULT_THEMES) == names
    assert set(COCKPIT_PROFILES) == names
    assert set(PRESENTATION_CONTRACTS) == names
    for contract in PRESENTATION_CONTRACTS.values():
        assert contract.geometry_family
        assert contract.motion_language
        assert len(contract.instrument_vocabulary) >= 3
        assert contract.event_flourish
        assert contract.voice_policy
        assert contract.repetition_budget > 0
        assert contract.music_palette


def test_first_wave_signature_worlds_are_structurally_distinct():
    first_wave = {"m4tr1x", "the_sprawl", "sensei", "detective", "the_computer"}
    contracts = [PRESENTATION_CONTRACTS[name] for name in first_wave]
    assert len({item.geometry_family for item in contracts}) == len(first_wave)
    assert len({item.ambient_layer for item in contracts}) == len(first_wave)
    assert len({item.event_flourish for item in contracts}) == len(first_wave)
    assert len({item.music_palette for item in contracts}) == len(first_wave)


def test_web_music_is_local_opt_in_and_effects_have_off_path():
    page = Path("web/app/page.tsx").read_text()
    css = Path("web/app/pivotglass.css").read_text()
    assert "new AudioContext()" in page
    assert "OFF BY DEFAULT" in page
    assert "fetch(" not in page[page.index("function startMusic"):page.index("function toggleMusic")]
    assert ".effects-off .ambient-environment{display:none}" in css


def test_retired_characters_never_reenter_selectable_catalogue():
    assert "drunken_master" not in DEFAULT_MODES
    assert "bobby_hill" not in DEFAULT_MODES
