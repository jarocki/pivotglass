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


def test_web_music_schedules_ahead_and_reuses_expensive_audio_material():
    engine = Path("web/app/flow-music.ts").read_text()

    assert "horizon=now+1.4" in engine
    assert "setInterval(()=>this.schedule(),100)" in engine
    assert "private waves=new Map<Instrument,PeriodicWave>()" in engine
    assert "private noiseBuffers=new Map<Instrument,AudioBuffer>()" in engine
    assert "this.periodicWave(spec.instrument)" in engine
    assert "this.noiseBuffer(spec.instrument)" in engine
    assert "exponentialRampToValueAtTime(floor" in engine
    assert "linearRampToValueAtTime(0,now+.5)" in engine


def test_web_music_acknowledges_only_new_authoritative_milestones():
    page = Path("web/app/page.tsx").read_text()
    engine = Path("web/app/flow-music.ts").read_text()

    assert "scoreMilestones.current = current" in page
    assert "previous.workspace !== current.workspace" in page
    assert "current.badges > previous.badges" in page
    assert 'audioRef.current?.accent("badge")' in page
    assert "current.dossierFilled > previous.dossierFilled" in page
    assert 'audioRef.current?.accent("dossier")' in page
    assert 'if(this.stopped||!this.timer||this.context.state!=="running")return' in engine
    assert "now-this.lastAccentAt<1.4" in engine
    assert "planMusicalAccent(this.id,kind)" in engine


def test_analyst_advisor_waits_for_extended_inactivity_and_resets_on_work():
    page = Path("web/app/page.tsx").read_text()
    idle = Path("web/app/advisor-idle.ts").read_text()

    assert "full: 5 * 60_000" in idle
    assert "brief: 8 * 60_000" in idle
    assert "ADVISOR_COOLDOWN_MS = 15 * 60_000" in idle
    assert '"keydown", "pointerdown", "wheel", "touchstart"' in page
    assert "current.feed !== previous.feed" in page
    assert "current.objects !== previous.objects" in page
    assert "current.active !== previous.active" in page
    assert "setTimeout(present, 16_000)" not in page
    assert "setInterval(present, 120_000)" not in page


def test_scientific_workbench_exposes_conflicts_without_auto_promoting_them():
    workbench = Path("web/app/scientific-workbench.tsx").read_text()
    rigor = Path("src/adversary_pursuit/core/analytic_rigor.py").read_text()

    assert "CONFIDENCE &amp; CONTRADICTION REVIEW" in workbench
    assert "RECORD CONTRADICTION" in workbench
    assert "METHOD-DERIVED · NOT YET RECORDED" in workbench
    assert "dependence_group_count" in workbench
    assert '"content_class": "method_derived_suggestion"' in rigor
    assert "duplicate reporting is not corroboration" in rigor


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


def test_enrichment_and_constellation_share_literal_rgb_led_status_blocks():
    page = Path("web/app/page.tsx").read_text()
    workspace = Path("web/app/visualization-workspace.tsx").read_text()
    led = Path("web/app/rgb-led.tsx").read_text()

    assert "<TaskMatrix intent={enrichmentActivity}" in page
    assert "liveRows={liveEnrichmentRows}" in page
    assert "newest activity first" in page
    assert "<RGBLed status={status}" in workspace
    assert "rgbLabelForStatus(status)" in workspace
    for mapping in ("empty: [0, 0, 0]", "succeeded: [0, 255, 0]", "partial: [128, 128, 128]"):
        assert mapping in led


def test_constellation_uses_compact_shape_redundant_lite_brite_pegs():
    workspace = Path("web/app/visualization-workspace.tsx").read_text()
    peg = Path("web/app/lite-brite-peg.tsx").read_text()
    styles = Path("web/app/pivotglass.css").read_text()

    assert 'className={`task-matrix ${isConstellation ? "constellation-matrix" : ""}`}' in workspace
    assert "<LiteBritePeg" in workspace
    assert "CONSTELLATION_COLUMN_LABELS" in workspace
    for motif in ('"filled"', '"partial"', '"deferred"', '"empty"'):
        assert motif in peg
    for selector in (
        ".lite-brite-peg.motif-filled",
        ".lite-brite-peg.motif-partial",
        ".lite-brite-peg.motif-deferred",
        ".lite-brite-peg.motif-empty",
    ):
        assert selector in styles
    assert ".constellation-matrix .lite-brite-cell" in styles


def test_field_guidance_is_idle_gated_character_voiced_and_not_evidence():
    page = Path("web/app/page.tsx").read_text()
    guidance = Path("web/app/character-guidance.ts").read_text()

    assert "advisorCanInterrupt" in page
    assert "lastAnalystActivityAt" in page
    assert "lastAdvisorPresentedAt" in page
    assert "NARRATION, NOT EVIDENCE" in page
    assert 'contentClass: "narration"' in guidance
    assert "evidence: false" in guidance
    assert "ANALYST ADVISOR · NARRATION, NOT EVIDENCE" in page
    assert "CharacterAdvisorArtwork" in page
    assert "READ ALOUD" in page
    assert "pivotglass.narration.audio" in page
    for character in (
        "chuck_norris",
        "hal9000",
        "troll",
        "sherlock_holmes",
        "neuromancer",
        "the_matrix",
    ):
        assert f"{character}:" in guidance


def test_advisor_is_viewport_top_character_art_and_opt_in_device_speech():
    page = Path("web/app/page.tsx").read_text()
    artwork = Path("web/app/character-advisor.tsx").read_text()
    styles = Path("web/app/pivotglass.css").read_text()

    advisor = styles.split("\n.configuration-advisory{", 1)[1].split("}", 1)[0]
    assert "position:fixed" in advisor
    assert "top:max(" in advisor
    assert "left:50%" in advisor
    assert "bottom:" not in advisor
    assert "z-index:20001" in advisor
    assert "SpeechSynthesisUtterance" in artwork
    assert "localService !== false" in artwork
    assert "createPortal" in artwork
    assert "AdvisorPortal" in page
    assert "No actor or character voice is cloned." in page
    for identity in (
        "chuck_norris",
        "hal9000",
        "troll",
        "sherlock_holmes",
        "neuromancer",
        "the_matrix",
    ):
        assert f'identity === "{identity}"' in artwork


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
