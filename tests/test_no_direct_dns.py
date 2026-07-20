"""Repository invariants for service-backed domain intelligence.

AP must never resolve indicators directly from the operator host. Domain
evidence is acquired through explicit intelligence-service modules instead.
"""

from pathlib import Path

from adversary_pursuit.agent.battery_registry import dispatch_batteries
from adversary_pursuit.agent.tools import ToolContext, create_tools


SOURCE_ROOT = Path(__file__).parents[1] / "src" / "adversary_pursuit"


def test_production_source_contains_no_direct_dns_calls():
    forbidden = (
        "socket.getaddrinfo",
        "socket.gethostbyname",
        "socket.gethostbyaddr",
        ".getaddrinfo(",
    )
    violations: list[str] = []
    for path in SOURCE_ROOT.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        for token in forbidden:
            if token in source:
                violations.append(f"{path.relative_to(SOURCE_ROOT)}: {token}")

    assert not violations, "Direct DNS calls are forbidden:\n" + "\n".join(violations)


def test_domain_dispatch_uses_intelligence_services_not_dns():
    batteries = dispatch_batteries("domain-name", None)
    tools = {tool for battery in batteries for tool in battery.tools}

    assert "dns_resolve" not in tools
    assert {
        "virustotal_lookup",
        "otx_threat_intel",
        "passivetotal_lookup",
        "scan_url",
    }.issubset(tools)


def test_agent_tool_catalog_excludes_direct_dns():
    tool_names = {tool["function"]["name"] for tool in create_tools(ToolContext())}
    assert "dns_resolve" not in tool_names
