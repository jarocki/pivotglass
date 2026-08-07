"""Deterministic operational authority and degraded-state projection.

The registry explains which component owns an action and whether that
component is ready, disabled, missing configuration, or recently failed.  It
does not test remote services in the background and never exposes credentials.
"""

from __future__ import annotations

from typing import Any

SERVICE_TOOL_NAMES: dict[str, tuple[str, ...]] = {
    "shodan": ("shodan_host_lookup",),
    "virustotal": ("virustotal_lookup",),
    "abuseipdb": ("check_ip_reputation",),
    "hibp": ("check_breaches",),
    "otx": ("otx_threat_intel",),
    "urlscan": ("scan_url",),
    "censys_pat": ("censys_host_lookup",),
    "greynoise": ("greynoise_lookup",),
    "passivetotal": ("passivetotal_lookup",),
    "crtsh": ("crtsh_lookup",),
    "whois": ("whois_lookup",),
}


def build_authority_registry(
    configuration: dict[str, Any],
    tool_names: list[str],
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return a masked, read-only operational registry for the cockpit."""

    recent_fault_tools = {
        str(event.get("tool"))
        for event in events
        if event.get("event_class") == "source_fault" and event.get("tool")
    }
    tools = set(tool_names)
    authorities: list[dict[str, Any]] = [
        {
            "id": "workspace",
            "label": "Workspace evidence and analytic ledger",
            "kind": "local_authority",
            "authority": "Pivotglass workspace database",
            "state": "ready",
            "reason": "Local deterministic storage is available.",
            "background_network": False,
        }
    ]

    for service in configuration.get("services", []):
        service_id = str(service.get("id") or "unknown")
        candidates = SERVICE_TOOL_NAMES.get(service_id, (service_id,))
        matching_tools = sorted(name for name in candidates if name in tools)
        enabled = bool(service.get("enabled", True))
        credential_source = str(service.get("credential_source") or "missing")
        needs_credential = bool(service.get("credential_fields"))
        faulted = any(name in recent_fault_tools for name in matching_tools)
        if not enabled:
            state = "disabled"
            reason = "Disabled by the operator; no request will be sent."
        elif needs_credential and credential_source == "missing":
            state = "missing_configuration"
            reason = "Enabled, but a required credential is missing."
        elif not matching_tools:
            state = "unavailable"
            reason = "No deterministic adapter is registered in this build."
        elif faulted:
            state = "degraded"
            reason = "A recent request failed; local evidence and other sources remain available."
        else:
            state = "ready"
            reason = "A deterministic adapter is available; no background test was performed."
        authorities.append(
            {
                "id": service_id,
                "label": str(service.get("display_name") or service_id),
                "kind": "intelligence_source",
                "authority": "Direct API or local deterministic adapter",
                "state": state,
                "reason": reason,
                "credential_source": credential_source,
                "tools": matching_tools,
                "background_network": False,
            }
        )

    model = dict(configuration.get("model") or {})
    if not model.get("enabled", True):
        model_state = "disabled"
        model_reason = "Model synthesis is disabled; deterministic commands remain available."
    elif not model.get("credential_configured", False):
        model_state = "missing_configuration"
        model_reason = "The selected model provider is missing a required credential."
    else:
        model_state = "ready"
        model_reason = "Synthesis is available only when an analyst request requires it."
    authorities.append(
        {
            "id": "model_synthesis",
            "label": "AI synthesis",
            "kind": "optional_synthesis",
            "authority": "Selected model provider; never evidence authority",
            "state": model_state,
            "reason": model_reason,
            "provider": model.get("provider"),
            "model": model.get("model"),
            "credential_source": model.get("credential_source"),
            "background_network": False,
        }
    )

    counts = {
        state: sum(1 for row in authorities if row["state"] == state)
        for state in ("ready", "degraded", "disabled", "missing_configuration", "unavailable")
    }
    overall = (
        "degraded"
        if counts["degraded"] or counts["missing_configuration"] or counts["unavailable"]
        else "ready"
    )
    return {
        "state": overall,
        "counts": counts,
        "authorities": authorities,
        "offline_behavior": (
            "Workspace search, reports, analytic methods, and stored evidence remain available. "
            "Unavailable intelligence sources are skipped explicitly; Pivotglass does not "
            "substitute model-generated telemetry."
        ),
    }
