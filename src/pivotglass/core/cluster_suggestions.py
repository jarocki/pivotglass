"""Cluster suggestions from shared pivot values (#30).

@decision DEC-CLUSTER-SUGGEST-001
@title Suggest clusters from typed shared values; the analyst accepts or rejects each one
@status accepted
@rationale Indicators that share a certificate, an exact nameserver set, a
registrar within a short registration window, or an ASN plus JARM fingerprint
often belong to one operator, but each of those can also be coincidence (a
large registrar, shared hosting). So Pivotglass only proposes. A suggestion
names its rule, the shared values and a strength label, and never becomes a
cluster on its own. Accepting records a ``cluster`` tag on every member whose
note cites the rule and the shared values, so the grouping keeps its evidence.
Rejecting records an attributed analyst judgment in the ledger (subject
``cluster-suggestion:<id>``), so the same suggestion is not offered again.
Pivot values are read from the stored object and from every evidence observation
of it, because later modules' fields live in observations. Indicators tagged
Benign / noise are left out. A suggestion whose members
already share a cluster tag is not offered.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from datetime import datetime
from typing import Any

from pivotglass.core.indicator_tags import IndicatorTagAuthority

REGISTRATION_WINDOW_DAYS = 14
MAX_SUGGESTIONS = 50
_SUBJECT = "cluster-suggestion:"

RULES = {
    "certificate": ("strong", "share a TLS certificate"),
    "asn-jarm": ("strong", "share an ASN and a JARM fingerprint"),
    "nameservers": ("moderate", "use the identical set of nameservers"),
    "registrar-window": ("weak", f"use the same registrar and were registered within {REGISTRATION_WINDOW_DAYS} days"),
}


def _value(item: dict[str, Any]) -> str:
    return str(item.get("value", item.get("x_indicator_value", item.get("name", "")))).strip()


def _certificates(item: dict[str, Any]) -> set[str]:
    found = {str(item[k]).lower() for k in ("certificate_fingerprint", "x509_serial_number") if item.get(k)}
    for service in item.get("x_services") or []:
        if isinstance(service, dict) and service.get("x_certificates"):
            found.add(str(service["x_certificates"]).lower())
    return found


def _nameservers(item: dict[str, Any]) -> tuple[str, ...]:
    names = list(item.get("x_rdap_nameservers") or [])
    names += list((item.get("x_dns_records") or {}).get("NS") or [])
    return tuple(sorted({str(n).lower().rstrip(".") for n in names if n}))


def _asn(item: dict[str, Any]) -> str:
    asn = item.get("x_asn_number") or (item.get("x_autonomous_system") or {}).get("asn")
    return str(asn) if asn else ""


def _jarm(item: dict[str, Any]) -> str:
    return str(item.get("jarm") or item.get("x_jarm") or "").lower()


def _date(text: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except ValueError:
        return None


def suggestion_id(rule: str, shared: Iterable[str], members: Iterable[tuple[str, str]]) -> str:
    raw = "\u0000".join([rule, *sorted(shared), *sorted(f"{t}|{v}" for t, v in members)])
    return hashlib.sha256(raw.encode()).hexdigest()[:10]


def _groups(objects: list[dict[str, Any]]) -> list[tuple[str, tuple[str, ...], list[tuple[str, str]]]]:
    keyed: dict[tuple[str, tuple[str, ...]], set[tuple[str, str]]] = {}
    by_registrar: dict[str, list[tuple[datetime, tuple[str, str]]]] = {}
    for item in objects:
        kind, value = str(item.get("type", "")), _value(item)
        if not value:
            continue
        member = (kind, value)
        for cert in _certificates(item):
            keyed.setdefault(("certificate", (cert,)), set()).add(member)
        if kind == "domain-name" and (ns := _nameservers(item)):
            keyed.setdefault(("nameservers", ns), set()).add(member)
        if kind in {"ipv4-addr", "ipv6-addr"} and (asn := _asn(item)) and (jarm := _jarm(item)):
            keyed.setdefault(("asn-jarm", (f"AS{asn}", jarm)), set()).add(member)
        registered = _date(item.get("x_rdap_registered"))
        if kind == "domain-name" and item.get("x_rdap_registrar") and registered:
            by_registrar.setdefault(str(item["x_rdap_registrar"]), []).append((registered, member))
    groups = [(rule, shared, sorted(members)) for (rule, shared), members in keyed.items() if len(members) > 1]
    for registrar, dated in by_registrar.items():
        dated.sort()
        window: list[tuple[datetime, tuple[str, str]]] = []
        for entry in [*dated, None]:
            if entry is not None and (not window or (entry[0] - window[0][0]).days <= REGISTRATION_WINDOW_DAYS):
                window.append(entry)
                continue
            if len(window) > 1:
                span = f"{window[0][0].date()} to {window[-1][0].date()}"
                groups.append(("registrar-window", (registrar, span), sorted({m for _d, m in window})))
            window = [entry] if entry is not None else []
    return groups


def _merged_objects(workspace_manager: Any) -> list[dict[str, Any]]:
    """Each indicator with the fields every source reported for it.

    A stored object keeps the fields of the first module that created it; later
    modules' answers live in evidence observations. Pivot values (nameservers,
    ASN, certificates) usually arrive later, so they are read from both.
    """

    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for item in workspace_manager.get_stix_objects():
        merged[(str(item.get("type", "")), _value(item))] = dict(item)
    for observation in workspace_manager.get_observations():
        blob = observation.get("observed_blob")
        key = (str(observation.get("entity_type", "")), str(observation.get("entity_value", "")))
        if isinstance(blob, dict) and key in merged:
            for field, value in blob.items():
                if value not in (None, "", [], {}):
                    merged[key].setdefault(field, value)
    return list(merged.values())


def _rejected(workspace_manager: Any) -> set[str]:
    from pivotglass.core.analytic_ledger import AnalyticLedger

    return {
        str(a["subject_ref"])[len(_SUBJECT):]
        for a in AnalyticLedger(workspace_manager).snapshot()["assertions"]
        if str(a.get("subject_ref") or "").startswith(_SUBJECT) and a.get("predicate") == "rejected"
    }


def suggest_clusters(workspace_manager: Any) -> list[dict[str, Any]]:
    """Open suggestions, strongest first."""

    tags = IndicatorTagAuthority(workspace_manager).current()
    benign = {(t["entity_type"], t["normalized_value"]) for t in tags if t["dimension"] == "role" and t["value"] == "benign"}
    clusters: dict[tuple[str, str], set[str]] = {}
    for tag in tags:
        if tag["dimension"] == "cluster":
            clusters.setdefault((tag["entity_type"], tag["normalized_value"]), set()).add(tag["value"])
    rejected = _rejected(workspace_manager)
    strength_order = {"strong": 0, "moderate": 1, "weak": 2}
    out = []
    for rule, shared, members in _groups(_merged_objects(workspace_manager)):
        members = [m for m in members if m not in benign]
        if len(members) < 2:  # noqa: PLR2004
            continue
        if set.intersection(*(clusters.get(m, set()) for m in members)):
            continue  # already clustered together
        sid = suggestion_id(rule, shared, members)
        if sid in rejected:
            continue
        strength, reason = RULES[rule]
        out.append({
            "id": sid, "rule": rule, "strength": strength, "shared": list(shared),
            "members": [{"entity_type": t, "value": v} for t, v in members],
            "rationale": f"{len(members)} indicators {reason}: {', '.join(shared)}.",
            "basis": "suggestion from shared values, not a finding",
        })
    out.sort(key=lambda s: (strength_order[s["strength"]], -len(s["members"]), s["id"]))
    return out[:MAX_SUGGESTIONS]


def _cluster_name(suggestion: dict[str, Any], name: str | None) -> str:
    raw = (name or f"{suggestion['rule']} {suggestion['shared'][0]}").casefold()
    cleaned = re.sub(r"[^a-z0-9._:/ -]+", " ", raw).strip(" .-_:/")
    return " ".join(cleaned.split())[:64] or f"cluster {suggestion['id']}"


def _find(workspace_manager: Any, sid: str) -> dict[str, Any]:
    match = next((s for s in suggest_clusters(workspace_manager) if s["id"] == sid), None)
    if match is None:
        raise ValueError(f"no open cluster suggestion {sid}; run 'cluster suggest' to list them")
    return match


def accept_suggestion(workspace_manager: Any, sid: str, name: str | None = None, *, operator: str = "local analyst") -> dict[str, Any]:
    suggestion = _find(workspace_manager, sid)
    cluster = _cluster_name(suggestion, name)
    note = f"Accepted cluster suggestion {sid}: {suggestion['rationale']}"
    IndicatorTagAuthority(workspace_manager).apply(
        [{"entity_type": m["entity_type"], "normalized_value": m["value"], "dimension": "cluster",
          "value": cluster, "note": note} for m in suggestion["members"]],
        operator=operator,
    )
    return {"cluster": cluster, "members": suggestion["members"], "note": note}


def reject_suggestion(workspace_manager: Any, sid: str, reason: str) -> dict[str, Any]:
    from pivotglass.core.analytic_ledger import AnalyticLedger, AssertionType

    if not reason.strip():
        raise ValueError("say why: cluster reject <id> | <reason>")
    suggestion = _find(workspace_manager, sid)
    AnalyticLedger(workspace_manager).create_assertion(
        f"Rejected cluster suggestion {sid} ({suggestion['rationale']}): {reason.strip()}",
        assertion_type=AssertionType.JUDGMENT,
        subject_ref=f"{_SUBJECT}{sid}", predicate="rejected", object_value=suggestion["rule"],
    )
    return {"rejected": sid, "reason": reason.strip()}


USAGE = "cluster suggest | cluster accept <id> [name] | cluster reject <id> | <reason>"


def execute_cluster_command(text: str, workspace_manager: Any) -> dict[str, Any]:
    """One grammar for every surface: ``{title, data}``."""

    head, _, reason = text.partition("|")
    tokens = head.split()
    action = tokens[0].lower() if tokens else "suggest"
    if action in {"suggest", "list", "show"}:
        suggestions = suggest_clusters(workspace_manager)
        return {"title": f"{len(suggestions)} cluster suggestion(s)", "data": suggestions}
    if action == "accept" and len(tokens) >= 2:  # noqa: PLR2004
        result = accept_suggestion(workspace_manager, tokens[1], " ".join(tokens[2:]) or None)
        return {"title": f"Cluster '{result['cluster']}' tagged on {len(result['members'])} indicators", "data": result}
    if action == "reject" and len(tokens) >= 2:  # noqa: PLR2004
        return {"title": f"Suggestion {tokens[1]} rejected", "data": reject_suggestion(workspace_manager, tokens[1], reason)}
    raise ValueError(f"usage: {USAGE}")
