"""Tests for evidence-safe enrichment teaching cards."""

from adversary_pursuit.agent.battery_registry import DEFAULT_BATTERIES
from adversary_pursuit.agent.enrichment_briefings import BRIEFINGS, render_briefing


def test_every_battery_tool_has_an_enrichment_briefing():
    battery_tools = {tool for battery in DEFAULT_BATTERIES.values() for tool in battery.tools}
    assert battery_tools <= BRIEFINGS.keys()


def test_briefing_teaches_artifacts_purpose_and_analyst_focus():
    card = render_briefing("passivetotal_lookup", "suspect.test")
    assert all(label in card for label in ("GATHER", "WHY", "WATCH"))
    assert "passive-DNS history" in card
    assert "without querying DNS from the operator host" in card


def test_briefing_does_not_claim_results_before_response():
    card = render_briefing("virustotal_lookup", "198.51.100.10")
    assert "findings are not assumed" in card
    assert "STATE   querying" in card


def test_unknown_tool_gets_safe_generic_briefing():
    card = render_briefing("future_service", "artifact")
    assert "deterministic tool/API" in card
    assert "provenance" in card
