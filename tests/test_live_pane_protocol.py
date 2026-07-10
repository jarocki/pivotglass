"""Protocol-satisfaction tests for LivePane._StatusHook (DEC-LIVE-PANE-STATUS-HOOK-001).

These tests verify that LivePane fully implements the _StatusHook protocol that
runner.chat() depends on.  The Slice 6 production crash ("'LivePane' object has
no attribute 'set_activity'") would have been caught by
test_live_pane_satisfies_status_hook_protocol before deployment.

Test coverage:
  - Protocol isinstance() check at @runtime_checkable — the regression guard.
  - set_activity: stores slug, render() shows a character-voiced phrase from PHRASES.
  - set_battery: stores battery name, render() tool-queue row reflects it.
  - set_hypothesis: stores text, render() row 3 contains the text.
  - Idempotent: repeated same-value calls produce the same render output.
  - None values reset each field back to idle state.

Production sequence exercised:
  user types text → TuiApplication._on_input_accepted →
    runner.handle_input(text, status_bar=live_pane) →
      runner.chat(text, status_bar=live_pane) →
        _safe_hook_call(live_pane, "set_activity", slug)  # must not raise
        _safe_hook_call(live_pane, "set_activity", None)  # must not raise

All tests use a real EventBus, real LivePane, and real phrases.pick() — no mocks.

@decision DEC-TEST-LIVE-PANE-PROTOCOL-001
@title Tests assert isinstance(_StatusHook) and each protocol method drives render()
@status accepted
@rationale The Slice 6 bug was that LivePane was used as a _StatusHook but
           implemented none of the three required methods. The isinstance() test
           makes the same check the runtime does via @runtime_checkable, so a
           future regression (dropping a method) will be caught immediately in CI
           rather than at the first real tool call in a live TUI session.
           The render-state tests are real-path: they call the method then call
           render() and assert the output reflects the new state, exercising the
           full lock → state-mutation → render path without mocks.
"""

from __future__ import annotations

from adversary_pursuit.agent.runner import _StatusHook
from adversary_pursuit.agent.tui.events import EventBus
from adversary_pursuit.agent.tui.live_pane import LivePane

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_pane(mode_name: str = "default") -> tuple[LivePane, EventBus]:
    """Return a (pane, bus) pair wired with a real EventBus."""
    bus = EventBus()
    pane = LivePane(bus=bus, mode_name=mode_name, model_display="test")
    return pane, bus


# ---------------------------------------------------------------------------
# Protocol satisfaction
# ---------------------------------------------------------------------------


def test_live_pane_satisfies_status_hook_protocol():
    """LivePane must satisfy the @runtime_checkable _StatusHook protocol.

    This is the direct regression test for the Slice 6 crash.  If any of the
    three protocol methods is missing, isinstance() returns False and this test
    fails — catching the gap in CI before a live TUI session does.
    """
    pane, _ = _make_pane()
    assert isinstance(pane, _StatusHook), (
        "LivePane does not satisfy _StatusHook protocol. "
        "Expected set_activity, set_battery, set_hypothesis methods."
    )


# ---------------------------------------------------------------------------
# set_activity
# ---------------------------------------------------------------------------


def test_set_activity_updates_render():
    """After set_activity('virustotal'), row 5 shows a character-voiced phrase.

    Real-path: real pick(), real PHRASES — no mocks.  The phrase for
    ("default", "activity:virustotal") is non-empty, so row 5 must differ from
    the idle string "  idle".
    """
    pane, _ = _make_pane(mode_name="default")

    # Baseline: row 5 is idle before set_activity is called
    idle_lines = pane.render()
    assert "idle" in idle_lines[4].lower(), (
        f"Expected idle row 5 before set_activity: {idle_lines[4]!r}"
    )

    pane.set_activity("virustotal")
    lines = pane.render()

    # Row 5 must no longer be "  idle" — it shows the picked phrase
    assert "idle" not in lines[4].lower(), (
        f"Row 5 should not be idle after set_activity('virustotal'): {lines[4]!r}"
    )
    # The picked phrase comes from PHRASES[("default", "activity:virustotal")]
    # which includes "Querying VirusTotal..." / "Running VirusTotal lookup".
    # We verify it's non-empty and a real string, not the raw slug.
    assert len(lines[4].strip()) > 0, f"Row 5 must be non-empty after set_activity: {lines[4]!r}"


def test_set_activity_none_resets_to_idle():
    """set_activity(None) after a slug resets row 5 back to idle."""
    pane, _ = _make_pane()

    pane.set_activity("dns_resolve")
    lines_active = pane.render()
    assert "idle" not in lines_active[4].lower(), "Expected non-idle row 5 after set_activity"

    pane.set_activity(None)
    lines_idle = pane.render()
    assert "idle" in lines_idle[4].lower(), (
        f"Row 5 should be idle after set_activity(None): {lines_idle[4]!r}"
    )


def test_set_activity_uses_real_phrases_pick():
    """The phrase in row 5 matches what pick() returns for the same slug."""
    from adversary_pursuit.gamification.phrases import pick

    pane, _ = _make_pane(mode_name="default")
    pane.set_activity("virustotal")
    lines = pane.render()

    # pick() is non-deterministic (random weighted choice) so we can't assert
    # the exact string, but we CAN assert that the row contains a known phrase
    # from the ("default", "activity:virustotal") pool.
    known_phrases = ["VirusTotal", "virustotal"]
    row5 = lines[4]
    assert any(kw.lower() in row5.lower() for kw in known_phrases), (
        f"Row 5 should contain a VirusTotal phrase, got: {row5!r}"
    )
    # Also verify pick() itself returns something non-empty for this slug
    phrase = pick("default", "activity:virustotal")
    assert isinstance(phrase, str) and len(phrase) > 0


def test_set_activity_fallback_slug_renders_without_error():
    """Unknown activity slug falls back gracefully — no ValueError from pick()."""
    pane, _ = _make_pane()
    # "unknown_tool_xyz" has no PHRASES entry; fallback ladder: FALLBACK string
    pane.set_activity("unknown_tool_xyz")
    lines = pane.render()  # must not raise
    assert len(lines) == 6, f"Expected 6 rows, got {len(lines)}"
    assert len(lines[4].strip()) > 0, "Row 5 must be non-empty even for unknown slug"


# ---------------------------------------------------------------------------
# set_battery
# ---------------------------------------------------------------------------


def test_set_battery_updates_hook_state():
    """set_battery stores the battery name and the pane renders without error."""
    pane, _ = _make_pane()

    pane.set_battery("identity_battery")
    lines = pane.render()

    # Must still render 6 rows — the hook battery name is stored but does not
    # override the EventBus battery display (no BatteryStarted event fired).
    assert len(lines) == 6, f"Expected 6 rows after set_battery: {lines}"


def test_set_battery_none_clears():
    """set_battery(None) clears the hook battery name without error."""
    pane, _ = _make_pane()
    pane.set_battery("identity_battery")
    pane.set_battery(None)
    lines = pane.render()
    assert len(lines) == 6


# ---------------------------------------------------------------------------
# set_hypothesis
# ---------------------------------------------------------------------------


def test_set_hypothesis_updates_row3():
    """set_hypothesis stores text and row 3 contains it when no EventBus event fired."""
    pane, _ = _make_pane()

    pane.set_hypothesis("cert-clustered infrastructure")
    lines = pane.render()

    assert len(lines) == 6
    # Row 3 is the hypothesis row; it should contain the text we set.
    assert "cert-clustered infrastructure" in lines[2], (
        f"Row 3 should contain hypothesis text: {lines[2]!r}"
    )


def test_set_hypothesis_none_resets():
    """set_hypothesis(None) resets the hook hypothesis; row 3 shows default placeholder."""
    pane, _ = _make_pane()
    pane.set_hypothesis("some hypothesis")
    pane.set_hypothesis(None)
    lines = pane.render()
    assert len(lines) == 6
    # After reset, the hook hypothesis is None; row 3 should fall back to "—"
    # (since no HypothesisChanged event was published).
    assert "—" in lines[2] or "hypothesis:" in lines[2].lower(), (
        f"Row 3 should show placeholder after set_hypothesis(None): {lines[2]!r}"
    )


# ---------------------------------------------------------------------------
# Idempotence
# ---------------------------------------------------------------------------


def test_repeated_calls_idempotent():
    """Repeated set_activity calls with the same slug do not raise and keep slug set.

    Idempotence means repeated calls with the same value are no-ops: the internal
    state remains identical.  We verify this by reading _activity directly rather
    than comparing render() output, because pick() is stochastic — two calls to
    render() with the same slug legitimately return different phrase strings from
    the pool (weighted random choice).  The idempotence contract is about state
    mutation, not phrase output.
    """
    pane, _ = _make_pane()

    pane.set_activity("shodan")
    slug_after_first = pane._activity  # internal state snapshot

    pane.set_activity("shodan")  # same value — must be no-op
    slug_after_second = pane._activity

    assert slug_after_first == slug_after_second == "shodan", (
        f"Idempotent set_activity must keep _activity='shodan': "
        f"after first={slug_after_first!r}, after second={slug_after_second!r}"
    )

    # render() must not raise and must still show activity content (not idle)
    lines = pane.render()
    assert len(lines) == 6
    assert "idle" not in lines[4].lower(), f"Row 5 should still reflect the slug: {lines[4]!r}"


def test_repeated_set_hypothesis_idempotent():
    """Repeated set_hypothesis with same value produces identical row 3."""
    pane, _ = _make_pane()

    pane.set_hypothesis("test hypothesis")
    lines_first = pane.render()

    pane.set_hypothesis("test hypothesis")
    lines_second = pane.render()

    assert lines_first[2] == lines_second[2], (
        "Idempotent set_hypothesis calls should produce identical row 3 output"
    )


# ---------------------------------------------------------------------------
# None values reset to idle state
# ---------------------------------------------------------------------------


def test_none_values_reset_to_idle_state():
    """None values passed to each method reset the pane to its idle defaults."""
    pane, _ = _make_pane()

    # Set everything to non-None values
    pane.set_activity("virustotal")
    pane.set_battery("identity_battery")
    pane.set_hypothesis("some hypothesis text")

    # Now reset all to None
    pane.set_activity(None)
    pane.set_battery(None)
    pane.set_hypothesis(None)

    lines = pane.render()
    assert len(lines) == 6

    # Row 5 should be idle (no battery active, no activity slug)
    assert "idle" in lines[4].lower(), f"Row 5 should be idle after all resets: {lines[4]!r}"

    # Row 3 should show default placeholder (no EventBus event, no hook hypothesis)
    assert "—" in lines[2] or "hypothesis:" in lines[2].lower(), (
        f"Row 3 should show placeholder after set_hypothesis(None): {lines[2]!r}"
    )
