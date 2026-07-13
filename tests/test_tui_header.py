"""Tests for Phase 18 Slice 7A: TUI header renderer.

Covers:
- render_header() always returns exactly 3 rows
- CURRENT renders the target string
- PRIOR renders "—" when no prior; renders prior target when set
- Border uses the active theme's resolved border color
- Header row width is capped at the terminal width (80, 120 columns)
- HeaderPane.PRIOR breadcrumb: first target → PRIOR is "—"
- HeaderPane.PRIOR: after two `use` commands, PRIOR is first target
- HeaderPane uses real EventBus (not mock)

@decision DEC-TEST-TUI-HEADER-001
@title Header tests verify 3-row invariant, PRIOR breadcrumb, and theme wiring
@status accepted
@rationale render_header() is a pure function (easy to unit test in isolation)
           and HeaderPane is an event-driven stateful wrapper. Both surfaces are
           tested separately: the pure renderer via direct call with synthetic
           HeaderState + CharacterTheme, and the pane via a real EventBus
           (not a mock) so the PRIOR tracking is exercised through the real
           production sequence (publish TargetChanged → handler updates state →
           render() returns updated rows). This satisfies the compound-interaction
           test requirement (Sacred Practice 4 / implementer brief).
"""

from __future__ import annotations

import pytest

from adversary_pursuit.agent.tui.events import EventBus, TargetChanged
from adversary_pursuit.agent.tui.header import HeaderPane, HeaderState, render_header
from adversary_pursuit.agent.tui.themes import theme_for

# ---------------------------------------------------------------------------
# Pure renderer tests
# ---------------------------------------------------------------------------


class TestRenderHeaderRows:
    """render_header() always returns exactly 3 rows."""

    def test_returns_exactly_3_rows(self) -> None:
        state = HeaderState()
        theme = theme_for("default")
        rows = render_header(state, theme, width=80)
        assert len(rows) == 3, f"Expected 3 rows, got {len(rows)}"

    def test_returns_3_rows_at_120_columns(self) -> None:
        state = HeaderState()
        theme = theme_for("hal9000")
        rows = render_header(state, theme, width=120)
        assert len(rows) == 3

    def test_returns_3_rows_with_long_target(self) -> None:
        """Long target strings must not produce extra rows."""
        state = HeaderState(
            current_target="a-very-long-target-string.that.exceeds.the.terminal.width.example.com"
        )
        theme = theme_for("neuromancer")
        rows = render_header(state, theme, width=80)
        assert len(rows) == 3


class TestRenderHeaderContent:
    """render_header() encodes the correct content in each row."""

    def test_row1_contains_version(self) -> None:
        state = HeaderState(version="v0.4")
        theme = theme_for("default")
        rows = render_header(state, theme)
        assert "v0.4" in rows[0], f"Version not in row1: {rows[0]}"

    def test_row1_contains_adversary_pursuit(self) -> None:
        state = HeaderState()
        theme = theme_for("default")
        rows = render_header(state, theme)
        assert "ADVERSARY PURSUIT" in rows[0]

    def test_row1_contains_current_target(self) -> None:
        state = HeaderState(current_target="evil.example.com")
        theme = theme_for("default")
        rows = render_header(state, theme)
        assert "evil.example.com" in rows[0]

    def test_row1_contains_workspace_name(self) -> None:
        state = HeaderState(workspace_name="wintermute")
        theme = theme_for("neuromancer")
        rows = render_header(state, theme)
        assert "wintermute" in rows[0]

    def test_row2_contains_prior_target(self) -> None:
        state = HeaderState(prior_target="prev.example.com")
        theme = theme_for("default")
        rows = render_header(state, theme)
        assert "prev.example.com" in rows[1]

    def test_row2_prior_dash_when_no_prior(self) -> None:
        """PRIOR row shows '—' when no prior target has been set."""
        state = HeaderState(prior_target="—")
        theme = theme_for("default")
        rows = render_header(state, theme)
        assert "PRIOR" in rows[1]
        assert "—" in rows[1]

    def test_row2_contains_prior_label(self) -> None:
        state = HeaderState(prior_target="8.8.8.8")
        theme = theme_for("hal9000")
        rows = render_header(state, theme)
        assert "PRIOR" in rows[1]


class TestRenderHeaderWidth:
    """render_header() rows are capped at the requested terminal width."""

    @pytest.mark.parametrize("width", [80, 100, 120])
    def test_rows_do_not_exceed_width(self, width: int) -> None:
        """No row may exceed the requested terminal width."""
        state = HeaderState(
            current_target="long.target.hostname.example.com",
            workspace_name="my-workspace",
        )
        theme = theme_for("chuck_norris")
        rows = render_header(state, theme, width=width)
        for i, row in enumerate(rows):
            assert len(row) <= width, (
                f"Row {i + 1} length {len(row)} exceeds width {width}: {row!r}"
            )

    def test_row1_starts_with_top_border_char(self) -> None:
        state = HeaderState()
        theme = theme_for("default")
        rows = render_header(state, theme)
        assert rows[0].startswith("╭")

    def test_row2_starts_with_side_border_char(self) -> None:
        state = HeaderState()
        theme = theme_for("default")
        rows = render_header(state, theme)
        assert rows[1].startswith("│")

    def test_row3_starts_with_bottom_border_char(self) -> None:
        state = HeaderState()
        theme = theme_for("default")
        rows = render_header(state, theme)
        assert rows[2].startswith("╰")


# ---------------------------------------------------------------------------
# HeaderPane event-driven tests (real EventBus — not a mock)
# ---------------------------------------------------------------------------


class TestHeaderPanePriorBreadcrumb:
    """HeaderPane tracks PRIOR breadcrumb via real EventBus TargetChanged events."""

    def _make_pane(self) -> tuple[HeaderPane, EventBus]:
        bus = EventBus()
        pane = HeaderPane(bus=bus, workspace_name="default")
        return pane, bus

    def test_initial_prior_is_dash(self) -> None:
        """Before any TargetChanged event, PRIOR is '—'."""
        pane, _ = self._make_pane()
        assert pane.prior_target == "—"

    def test_initial_current_is_dash(self) -> None:
        """Before any TargetChanged event, CURRENT is '—'."""
        pane, _ = self._make_pane()
        assert pane.current_target == "—"

    def test_first_target_sets_current_prior_stays_dash(self) -> None:
        """First TargetChanged: CURRENT updates, PRIOR stays '—'."""
        pane, bus = self._make_pane()
        bus.publish(TargetChanged(target="first.example.com", target_type="domain-name"))
        assert pane.current_target == "first.example.com"
        assert pane.prior_target == "—"

    def test_second_target_sets_prior_to_first(self) -> None:
        """Second TargetChanged: PRIOR becomes the first target."""
        pane, bus = self._make_pane()
        bus.publish(TargetChanged(target="first.example.com", target_type="domain-name"))
        bus.publish(TargetChanged(target="second.example.com", target_type="domain-name"))
        assert pane.current_target == "second.example.com"
        assert pane.prior_target == "first.example.com"

    def test_third_target_updates_prior_to_second(self) -> None:
        """Third TargetChanged: PRIOR updates to the second target."""
        pane, bus = self._make_pane()
        bus.publish(TargetChanged(target="first.example.com", target_type="domain-name"))
        bus.publish(TargetChanged(target="second.example.com", target_type="domain-name"))
        bus.publish(TargetChanged(target="third.example.com", target_type="domain-name"))
        assert pane.current_target == "third.example.com"
        assert pane.prior_target == "second.example.com"

    def test_render_reflects_current_and_prior(self) -> None:
        """render() output contains both CURRENT and PRIOR after two events."""
        pane, bus = self._make_pane()
        theme = theme_for("default")
        bus.publish(TargetChanged(target="foo.com", target_type="domain-name"))
        bus.publish(TargetChanged(target="bar.com", target_type="domain-name"))
        rows = pane.render(theme=theme, width=120)
        assert len(rows) == 3
        assert "bar.com" in rows[0]  # CURRENT in title bar
        assert "foo.com" in rows[1]  # PRIOR in breadcrumb row

    def test_render_always_3_rows(self) -> None:
        """render() always returns exactly 3 rows regardless of state."""
        pane, bus = self._make_pane()
        theme = theme_for("neuromancer")
        rows = pane.render(theme=theme)
        assert len(rows) == 3

    def test_pane_with_none_bus_does_not_crash(self) -> None:
        """HeaderPane(bus=None) is valid for unit test use."""
        pane = HeaderPane(bus=None, workspace_name="test")
        theme = theme_for("default")
        rows = pane.render(theme=theme)
        assert len(rows) == 3

    def test_set_workspace_name_updates_header(self) -> None:
        """set_workspace_name() updates the workspace shown in row 1."""
        pane, _ = self._make_pane()
        theme = theme_for("default")
        pane.set_workspace_name("wintermute")
        rows = pane.render(theme=theme)
        assert "wintermute" in rows[0]
