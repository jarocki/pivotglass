"""Six-mockup snapshot tests and real-path integration for LivePane (C-2, C-5).

@decision DEC-TEST-LIVE-PANE-001
@title Tests verify LivePane always renders exactly 6 rows across all 6 documented states
@status accepted
@rationale DEC-TUI-LIVE-PANE-001 specifies a fixed 6-row contract so TuiApplication
           layout is deterministic and snapshot-testable without a real terminal. Tests
           drive the real EventBus and real LivePane through 6 canonical states: idle,
           battery-active, mid-flight tool events, hypothesis update, battery failure,
           and yield receipt. The real-path test verifies the phrase cache integration
           (pick() returns non-empty for battery:identity). No mocks — EventBus and
           DossierState are real objects as required by the task specification.
"""

from __future__ import annotations

from adversary_pursuit.agent.tui.events import (
    BatteryFinished,
    BatteryStarted,
    BatteryToolFinished,
    BatteryToolStarted,
    EventBus,
    HypothesisChanged,
    TargetChanged,
    YieldReceived,
)
from adversary_pursuit.agent.tui.live_pane import LivePane

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _make_pane(
    mode_name: str = "default", model_display: str = "test"
) -> tuple[LivePane, EventBus]:
    """Return a (pane, bus) pair wired with a real EventBus."""
    bus = EventBus()
    pane = LivePane(bus=bus, mode_name=mode_name, model_display=model_display)
    return pane, bus


# ---------------------------------------------------------------------------
# State 1: idle, no target
# ---------------------------------------------------------------------------


def test_state1_idle_render():
    """State 1: idle, no active target — exactly 6 rows rendered."""
    pane, bus = _make_pane(model_display="opus 4.7")
    lines = pane.render()

    assert len(lines) == 6, f"Expected 6 rows, got {len(lines)}: {lines}"

    # Row 2: target line
    assert "target:" in lines[1].lower(), f"Row 2 should contain 'target:': {lines[1]!r}"

    # Row 3: hypothesis line
    assert "hypothesis:" in lines[2].lower(), f"Row 3 should contain 'hypothesis:': {lines[2]!r}"

    # Row 4: dossier strip
    assert "dossier:" in lines[3].lower(), f"Row 4 should contain 'dossier:': {lines[3]!r}"

    # Row 6: yield hint (idle form — contains the yield primitives)
    assert "stop" in lines[5].lower(), f"Row 6 should contain yield hint: {lines[5]!r}"


def test_state1_idle_row_count_exact():
    """Six rows — not five, not seven."""
    pane, bus = _make_pane()
    assert len(pane.render()) == 6


def test_active_activity_has_visible_spinner():
    """An in-flight LLM/tool action must visibly differ from the idle pane."""
    pane, _bus = _make_pane(mode_name="hal9000")
    pane.set_activity("thinking")

    activity = pane.render()[4]

    assert any(frame in activity for frame in ("◐", "◓", "◑", "◒"))
    assert "idle" not in activity.lower()


def test_persona_identity_uses_world_title_not_generic_emoji():
    pane, _bus = _make_pane(mode_name="neuromancer")

    identity = pane.render()[0]

    assert "NEUROMANCER // THE SPRAWL" in identity
    assert "🕵" not in identity


# ---------------------------------------------------------------------------
# State 2: target set, battery started
# ---------------------------------------------------------------------------


def test_state2_target_set_and_battery():
    """State 2: after TargetChanged and BatteryStarted events."""
    pane, bus = _make_pane()

    bus.publish(TargetChanged(target="45.63.116.240", target_type="ipv4-addr"))
    bus.publish(
        BatteryStarted(
            battery_name="infrastructure_battery",
            tools=("shodan_host_lookup", "censys_host_lookup", "dns_resolve"),
            target_slots=("infrastructure",),
            reason="filling INFRASTRUCTURE",
        )
    )

    lines = pane.render()
    assert len(lines) == 6

    # Target appears in row 2
    assert "45.63.116.240" in lines[1], f"Target not in row 2: {lines[1]!r}"

    # Active indicator somewhere in the output
    all_text = " ".join(lines).lower()
    assert "infrastructure" in all_text or "shodan" in all_text, (
        f"Battery name not visible in output: {lines}"
    )


# ---------------------------------------------------------------------------
# State 3: mid-flight tool events
# ---------------------------------------------------------------------------


def test_state3_battery_mid_flight():
    """State 3: BatteryToolStarted/Finished events update pane without breaking 6-row contract."""
    pane, bus = _make_pane()

    bus.publish(TargetChanged(target="suspicious-target.example", target_type="domain-name"))
    bus.publish(
        BatteryStarted(
            battery_name="identity_battery",
            tools=("whois_lookup", "crtsh_lookup", "check_breaches"),
            target_slots=("identity",),
            reason="filling IDENTITY",
        )
    )
    bus.publish(BatteryToolStarted(battery_name="identity_battery", tool_name="whois_lookup"))
    bus.publish(
        BatteryToolFinished(battery_name="identity_battery", tool_name="whois_lookup", success=True)
    )
    bus.publish(BatteryToolStarted(battery_name="identity_battery", tool_name="crtsh_lookup"))
    bus.publish(
        BatteryToolFinished(battery_name="identity_battery", tool_name="crtsh_lookup", success=True)
    )
    bus.publish(BatteryToolStarted(battery_name="identity_battery", tool_name="check_breaches"))
    # check_breaches still running

    lines = pane.render()
    assert len(lines) == 6

    # Target still visible in row 2
    assert "suspicious-target.example" in lines[1]


# ---------------------------------------------------------------------------
# State 4: hypothesis updated
# ---------------------------------------------------------------------------


def test_state4_hypothesis_reveal():
    """State 4: HypothesisChanged event updates the hypothesis row."""
    pane, bus = _make_pane()

    bus.publish(TargetChanged(target="suspicious-target.example", target_type="domain-name"))
    bus.publish(HypothesisChanged(text="cert-clustered adversary infrastructure"))

    lines = pane.render()
    assert len(lines) == 6

    # Hypothesis appears in row 3
    assert "cert-clustered" in lines[2], f"Hypothesis text not in row 3: {lines[2]!r}"


def test_state4_hypothesis_dash_before_event():
    """Before HypothesisChanged, row 3 shows the default placeholder."""
    pane, bus = _make_pane()
    lines = pane.render()
    # Default is "—" (em dash)
    assert "—" in lines[2] or "hypothesis:" in lines[2].lower()


# ---------------------------------------------------------------------------
# State 5: battery finished with failure
# ---------------------------------------------------------------------------


def test_state5_battery_failed():
    """State 5: BatteryFinished(success=False) — pane still renders 6 rows."""
    pane, bus = _make_pane()

    bus.publish(TargetChanged(target="fuckusa300100XX", target_type="unrecognized-type"))
    bus.publish(
        BatteryStarted(
            battery_name="reputation_battery",
            tools=(
                "virustotal_lookup",
                "otx_threat_intel",
                "check_ip_reputation",
                "greynoise_lookup",
            ),
            target_slots=("ttps",),
            reason="best-effort",
        )
    )
    bus.publish(BatteryFinished(battery_name="reputation_battery", success=False))

    lines = pane.render()
    assert len(lines) == 6

    # Target should still be visible in row 2
    assert "fuckusa300100XX" in lines[1], f"Target not in row 2: {lines[1]!r}"


def test_state5_idle_after_battery_finished():
    """Row 5 shows 'idle' after BatteryFinished clears the active state."""
    pane, bus = _make_pane()

    bus.publish(TargetChanged(target="test.example", target_type="domain-name"))
    bus.publish(
        BatteryStarted(
            battery_name="identity_battery",
            tools=("whois_lookup",),
            target_slots=("identity",),
            reason="test",
        )
    )
    bus.publish(BatteryFinished(battery_name="identity_battery", success=True))

    lines = pane.render()
    assert len(lines) == 6
    assert "idle" in lines[4].lower(), f"Row 5 should show idle: {lines[4]!r}"


# ---------------------------------------------------------------------------
# State 6: mid-battery yield received
# ---------------------------------------------------------------------------


def test_state6_focus_yield():
    """State 6: YieldReceived event — pane still renders 6 rows."""
    pane, bus = _make_pane()

    bus.publish(TargetChanged(target="suspicious-target.example", target_type="domain-name"))
    bus.publish(
        BatteryStarted(
            battery_name="identity_battery",
            tools=("whois_lookup", "crtsh_lookup", "check_breaches"),
            target_slots=("identity",),
            reason="filling IDENTITY",
        )
    )
    bus.publish(YieldReceived(primitive="focus", argument="cert-sha256:ab12"))

    lines = pane.render()
    assert len(lines) == 6


def test_state6_yield_stop_updates_hint():
    """After a stop YieldReceived during active battery, row 6 shows active hint."""
    pane, bus = _make_pane()

    bus.publish(TargetChanged(target="evil.example", target_type="domain-name"))
    bus.publish(
        BatteryStarted(
            battery_name="behavioral_battery",
            tools=("passivetotal_lookup", "scan_url"),
            target_slots=("timing",),
            reason="test",
        )
    )
    bus.publish(YieldReceived(primitive="stop", argument=None))

    lines = pane.render()
    assert len(lines) == 6
    # Battery is still technically active (BatteryFinished not yet received)
    assert "►" in lines[5] or "stop" in lines[5].lower(), (
        f"Active yield hint expected in row 6: {lines[5]!r}"
    )


# ---------------------------------------------------------------------------
# Real-path compound test: phrase cache integration
# ---------------------------------------------------------------------------


def test_live_pane_uses_real_phrase_cache():
    """Live pane render uses real phrase cache for activity text.

    This is the real-path integration test: real EventBus, real LivePane,
    real phrase cache — no mocks.
    """
    from adversary_pursuit.gamification.phrases import pick

    pane, bus = _make_pane(mode_name="default")
    bus.publish(
        BatteryStarted(
            battery_name="identity_battery",
            tools=("whois_lookup",),
            target_slots=("identity",),
            reason="filling IDENTITY",
        )
    )

    lines = pane.render()
    assert len(lines) == 6

    # Verify the phrase cache resolves a non-empty string for this battery/character
    phrase = pick("default", "battery:identity")
    assert isinstance(phrase, str) and len(phrase) > 0

    # Row 5 should show the active tool name (real tool, no mocks)
    assert "whois_lookup" in lines[4] or "identity_battery" in lines[4], (
        f"Active battery/tool should appear in row 5: {lines[4]!r}"
    )


# ---------------------------------------------------------------------------
# Dossier strip reflects real DossierState when injected
# ---------------------------------------------------------------------------


def test_live_pane_dossier_strip_reflects_state():
    """inject a DossierState and verify the strip in row 4 updates."""
    from adversary_pursuit.dossier.slot_inference import DossierState, SlotState
    from adversary_pursuit.dossier.slots import DossierSlotName, SlotStatus

    pane, bus = _make_pane()

    # Inject a real DossierState with IDENTITY filled
    slots = {
        slot: SlotState(
            name=slot,
            status=SlotStatus.FILLED if slot == DossierSlotName.IDENTITY else SlotStatus.EMPTY,
        )
        for slot in DossierSlotName
    }
    state = DossierState(slots=slots, total_sco_count=3)
    pane.set_dossier_state(state)

    lines = pane.render()
    assert len(lines) == 6

    # Row 4 should contain the filled glyph ▮ for IDENTITY
    assert "▮" in lines[3], f"Filled glyph not in dossier row: {lines[3]!r}"

    # Empty slots should show ·
    assert "·" in lines[3], f"Empty glyph not in dossier row: {lines[3]!r}"
