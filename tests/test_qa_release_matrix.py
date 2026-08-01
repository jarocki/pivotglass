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
    engine = Path("web/app/flow-music.ts").read_text()
    css = Path("web/app/pivotglass.css").read_text()
    assert "new AudioContext()" in engine
    assert "schedule()" in engine
    assert 'MusicPhase = "idle" | "investigating" | "caution" | "complete"' in engine
    assert "OFF BY DEFAULT" in page
    assert "fetch(" not in engine
    assert ".effects-off .ambient-environment{display:none}" in css


def test_public_characters_have_distinct_interactive_diversions():
    page = Path("web/app/page.tsx").read_text()
    arcade = Path("web/app/arcade-games.tsx").read_text()
    for component, title in {
        "SherlockChessGame": "CHESS · THE FORCED CONCLUSION",
        "HalShutdownGame": "DISABLE THE COMPUTER",
        "NeuromancerJackInGame": "JACK IN / AVOID ICE",
        "MatrixPowerGridGame": "HACK THE POWER GRID",
    }.items():
        assert f"function {component}" in arcade
        assert title in arcade
    assert "OPTIONAL DIVERSION · NO ANALYTICAL MEANING" in arcade
    assert "publicModeLabel={publicModeLabel}" in page


def test_web_arcade_replayability_is_seeded_and_presentation_only():
    arcade = Path("web/app/arcade-games.tsx").read_text()
    engine = Path("web/app/arcade-engine.ts").read_text()
    assert "buildJackInRun" in engine
    assert "seededShuffle" in engine
    assert len(engine.split("TRIAGE_CARDS", 1)[1].split("] as const", 1)[0].split("prompt:")) >= 11
    assert "NEXT LEVEL" in arcade
    assert "RETRY SAME MAP" in arcade
    assert "BURN ID / NEW RUN" in arcade
    assert "never affect evidence, confidence, dossier, command, or investigation state" in arcade
    assert "window.addEventListener" not in arcade


def test_character_palettes_encode_identity_without_old_chuck_pink():
    page = Path("web/app/page.tsx").read_text()
    night_chuck = page.split("chuck_norris:", 1)[1].splitlines()[0]
    assert "#c86b32" in night_chuck
    assert "#e7b54a" in night_chuck
    assert "#ff5fff" not in night_chuck
    assert 'neuromancer: { border_color: "#7a86a8"' in page


def test_retired_characters_never_reenter_selectable_catalogue():
    assert "drunken_master" not in DEFAULT_MODES
    assert "bobby_hill" not in DEFAULT_MODES


def test_command_completion_has_an_explicit_top_level_stacking_contract():
    css = Path("web/app/pivotglass.css").read_text()

    focused = css.split("main>.command-rail.has-focus{", 1)[1].split("}", 1)[0]
    completion = css.split(".command-completions{", 1)[1].split("}", 1)[0]

    assert "z-index:12000!important" in focused
    assert "overflow:visible!important" in focused
    assert "isolation:isolate" in focused
    assert "z-index:12001!important" in completion
    assert "background:var(--elevated)" in completion
    assert "z-index:20000!important" in css


def test_constellation_defaults_to_persistent_indicator_dimension_status():
    workspace = Path("web/app/visualization-workspace.tsx").read_text()
    authority = Path("src/adversary_pursuit/core/visualization.py").read_text()

    assert 'intent.intent_id === "indicator-constellation"' in workspace
    assert 'useState("last_desc")' in workspace
    for label in (
        "IoC type",
        "Completeness",
        "Directly related to",
        "First seen on/after",
        "Last seen on/before",
    ):
        assert label in workspace
    assert "for dimension in DossierSlotName" in authority
    assert "infer_dossier_state(connected_evidence)" in authority
    assert "indicator_constellation_intent(workspace, objects, graph)" in authority


def test_product_uses_enrichment_and_reserves_connection_for_graph_relations():
    product_files = (
        Path("README.md"),
        Path("docs/USER_GUIDE.md"),
        Path("src/adversary_pursuit/web/server.py"),
        Path("src/adversary_pursuit/agent/tui/application.py"),
        Path("src/adversary_pursuit/core/visualization.py"),
        Path("web/app/page.tsx"),
        Path("web/app/visualization-workspace.tsx"),
    )
    combined = "\n".join(path.read_text().lower() for path in product_files)
    retired_active_contact_term = "".join(("pro", "be"))

    assert retired_active_contact_term not in combined
    assert "enrichment" in combined
    assert "a connection is an evidence-backed relationship between graph nodes" in combined
