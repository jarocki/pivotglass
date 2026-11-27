"""Domain 5 elements: hunting package and detection bundle (#57).

Rules and queries are generated deterministically from collected indicators
(``method`` provenance) and stay untested until the analyst records a
validation with ``report validate``. YARA rules are built only from strings the
analyst supplies from a sample (``report yara``). Nothing here is marked
tested without a validation record.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import uuid
from collections import defaultdict
from typing import Any
from urllib.parse import urlsplit

from pivotglass.reports.claims import actor_subjects, claims
from pivotglass.reports.contract import OutputFormat, ProvenanceClass, render_indicator
from pivotglass.reports.elements import (
    ELEMENTS,
    ElementResult,
    ElementStatus,
    ReportContext,
    element,
)
from pivotglass.reports.elements.common import detailed_indicators, md
from pivotglass.reports.sections import hunt_outcome, section_texts, validations, yara_inputs

E, M, A = ProvenanceClass.EVIDENCE, ProvenanceClass.METHOD, ProvenanceClass.ANALYST
_NS = uuid.UUID("2b0c7f7e-9a8d-4f43-8f5e-6c1a3e0d9b11")  # Pivotglass generated detections (uuid5)
LOCAL_SID_MIN, LOCAL_SID_MAX = 1_000_000, 1_999_999


def _spec(element_id: str):  # noqa: ANN202
    return ELEMENTS[element_id]


def _texts(context: ReportContext, section: str) -> list[dict[str, Any]]:
    return [{"id": r["id"], "text": r["statement"], "author": r.get("author_kind")} for r in section_texts(context.analysis, section)]


def _text_element(context: ReportContext, element_id: str, section: str, heading: str, hint: str) -> ElementResult:
    rows = _texts(context, section)
    spec = _spec(element_id)
    if not rows:
        return spec.result(ElementStatus.EMPTY, {"texts": [], "heading": heading}, gaps=[f"Not written yet (`report write {section} | {hint}`)."])
    return spec.result(ElementStatus.COMPLETE, {"texts": rows, "heading": heading}, citations=[f"assertion:{r['id']}" for r in rows])


def _text_md(result: ElementResult, output: OutputFormat) -> str:
    lines = [f"## {result.content.get('heading', result.title)}", ""]
    lines += [f"{r['text']} <sub>— {r['author']}</sub>" for r in result.content.get("texts", [])] or ["_Not written yet._"]
    return "\n".join(lines)


_HOSTNAME = re.compile(r"^(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}\.?$")
_SAFE_URL = re.compile(r"^[\x21-\x7e]+$")  # printable ASCII, no spaces or control characters


def safe_indicator(kind: str, value: str) -> str | None:
    """The value in a form safe to place in a rule or query, or ``None`` if it does not parse strictly.

    Indicator values come from documents and external sources; a value that is
    not a well-formed address, hostname, URL or hash never reaches a rule file.
    """

    if kind == "ip":
        try:
            address = ipaddress.ip_address(value.strip())
        except ValueError:
            return None
        # A scoped IPv6 address ("fe80::1%<zone>") parses with an arbitrary zone string; never allow one.
        if "%" in value or getattr(address, "scope_id", None):
            return None
        text = address.compressed
        return text if re.fullmatch(r"[0-9A-Fa-f:.]+", text) else None
    if kind == "domain":
        return value.strip().rstrip(".").lower() if _HOSTNAME.match(value.strip()) else None
    if kind == "url":
        parts = urlsplit(value.strip())
        ok = parts.scheme in {"http", "https"} and parts.hostname and _SAFE_URL.match(value.strip())
        host_ok = ok and (_HOSTNAME.match(parts.hostname) or safe_indicator("ip", parts.hostname) is not None)
        return value.strip() if host_ok else None
    if kind == "sha256":
        return value.strip().lower() if re.fullmatch(r"[0-9a-fA-F]{64}", value.strip()) else None
    return None


def blockable(context: ReportContext) -> dict[str, list[str]]:
    """Strictly parsed indicator values by kind, from the indicators suitable for blocking."""

    return _blockable(context)[0]


def rejected_values(context: ReportContext) -> list[str]:
    """Indicator values left out of rules and queries because they did not parse strictly."""

    return _blockable(context)[1]


def _blockable(context: ReportContext) -> tuple[dict[str, list[str]], list[str]]:
    rows, _excluded = detailed_indicators(context, blocking=True)
    kinds: dict[str, list[str]] = defaultdict(list)
    rejected = []
    for row in rows:
        kind = {"domain-name": "domain", "ipv4-addr": "ip", "ipv6-addr": "ip", "url": "url", "file": "sha256"}.get(row["type"])
        if kind is None:
            continue
        safe = safe_indicator(kind, row["value"])
        if safe is None:
            rejected.append(f"{row['type']} {row['value'][:80]!r}")
        else:
            kinds[kind].append(safe)
    return {k: sorted(set(v)) for k, v in kinds.items()}, rejected


def _rule_id(kind: str, values: list[str]) -> str:
    return str(uuid.uuid5(_NS, f"{kind}:{'|'.join(sorted(values))}"))


def _status(rule_id: str, checks: dict[str, dict[str, Any]], *, passed: str, default: str) -> str:
    return passed if checks.get(rule_id, {}).get("result") == "passed" else default


# --- hunting --------------------------------------------------------------------


def _hypothesis_md(result: ElementResult, output: OutputFormat) -> str:
    c = result.content
    lines = ["## Hunt Hypothesis", ""]
    lines += [f"{r['text']} <sub>— {r['author']}</sub>" for r in c.get("texts", [])]
    if not c.get("texts"):
        lines.append("_No hunt hypothesis written (`report write hunt_hypothesis | <behaviour, technique, and what would refute it>`)._")
    if c.get("ledger"):
        lines += ["", "Related hypotheses in the investigation:"] + [f"- {md(h['statement'])} ({h['status']})" for h in c["ledger"]]
    return "\n".join(lines)


@element(
    "hunt_hypothesis",
    "Hunt hypothesis",
    (A,),
    ("report section text", "analytic ledger hypotheses"),
    markdown=_hypothesis_md,
    description="A testable statement of adversary behaviour in this environment, with the ATT&CK technique and what "
    "result would refute it, alongside the investigation's hypotheses.",
)
def build_hunt_hypothesis(context: ReportContext) -> ElementResult:
    texts = _texts(context, "hunt_hypothesis")
    ledger = [{"statement": h["statement"], "status": h["status"]} for h in context.analysis["hypotheses"] if h["status"] != "rejected"]
    spec = _spec("hunt_hypothesis")
    if not texts:
        return spec.result(ElementStatus.EMPTY, {"texts": [], "ledger": ledger},
                           gaps=["No hunt hypothesis is written; the investigation's hypotheses are listed for reference."])
    return spec.result(ElementStatus.COMPLETE, {"texts": texts, "ledger": ledger}, citations=[f"assertion:{t['id']}" for t in texts])


def _context_md(result: ElementResult, output: OutputFormat) -> str:
    c = result.content
    lines = ["## Threat Context", ""]
    lines += [f"{r['text']} <sub>— {r['author']}</sub>" for r in c.get("texts", [])]
    if c.get("actors"):
        lines += ["", "Actors with recorded claims: " + ", ".join(f"{a['name']} ({', '.join(a['techniques']) or 'no exploit or tool claims'})" for a in c["actors"])]
    if not (c.get("texts") or c.get("actors")):
        lines.append("_No context written (`report write threat_context | <who uses this and why alerts miss it>`)._")
    return "\n".join(lines)


@element(
    "threat_context",
    "Threat context",
    (E, A),
    ("report section text", "actor claims"),
    markdown=_context_md,
    description="Who uses the behaviour and why existing alerts may miss it: analyst text and the actors with claims.",
)
def build_threat_context(context: ReportContext) -> ElementResult:
    texts = _texts(context, "threat_context")
    actors = [
        {"name": subject.removeprefix("actor:"),
         "techniques": sorted({str(r.get("object_value")) for p in ("uses-malware", "uses-tool", "exploits") for r in claims(context.analysis, subject, p)})}
        for subject in actor_subjects(context.analysis)
    ]
    spec = _spec("threat_context")
    if not (texts or actors):
        return spec.result(ElementStatus.EMPTY, {"texts": [], "actors": []}, gaps=["No threat context is written."])
    gaps = [] if texts else ["No analyst text explains why existing alerts may miss this behaviour."]
    return spec.result(ElementStatus.PARTIAL if gaps else ElementStatus.COMPLETE, {"texts": texts, "actors": actors}, gaps=gaps)


_DATA_SOURCES = {
    "domain": ("DNS query logs", "Sysmon event 22, Zeek dns.log, Microsoft DnsEvents"),
    "url": ("Web proxy logs", "proxy access logs, Zeek http.log, Microsoft DeviceNetworkEvents RemoteUrl"),
    "ip": ("Network connection logs", "firewall and NetFlow, Sysmon event 3, Microsoft DeviceNetworkEvents"),
    "sha256": ("File and process events with hashes", "EDR file and process events, Sysmon events 1 and 15"),
}


def _sources_md(result: ElementResult, output: OutputFormat) -> str:
    rows = result.content.get("sources", [])
    lines = ["## Required Data Sources", ""]
    if not rows:
        return "\n".join([*lines, "_No indicators to hunt for._"])
    lines += ["| Data | Example log sources | Needed for |", "|---|---|---|"]
    lines += [f"| {r['data']} | {r['examples']} | {r['count']} {r['kind']} indicator(s) |" for r in rows]
    lines += ["", f"_Time window: the last {result.content['lookback_days']} days._"]
    return "\n".join(lines)


@element(
    "hunt_data_sources",
    "Required data sources",
    (M,),
    ("indicator types",),
    markdown=_sources_md,
    description="The log sources each indicator type needs, with examples, and the hunt's time window.",
    options=("lookback_days",),
)
def build_hunt_data_sources(context: ReportContext) -> ElementResult:
    lookback = int(context.options.get("hunt_data_sources", {}).get("lookback_days", 30))
    kinds = blockable(context)
    rows = [{"kind": k, "data": _DATA_SOURCES[k][0], "examples": _DATA_SOURCES[k][1], "count": len(v)} for k, v in sorted(kinds.items())]
    spec = _spec("hunt_data_sources")
    gaps = ["Data sources come from indicator types only; ATT&CK data components for the mapped techniques are not derived yet."]
    if not rows:
        return spec.result(ElementStatus.EMPTY, {"sources": [], "lookback_days": lookback}, gaps=["No huntable indicators."])
    return spec.result(ElementStatus.PARTIAL, {"sources": rows, "lookback_days": lookback}, gaps=gaps)


def _q(values: list[str]) -> str:
    return ", ".join(json.dumps(v) for v in values)


def hunt_queries(kinds: dict[str, list[str]], lookback: int) -> list[dict[str, Any]]:
    """SPL, KQL and EQL for the indicator values. Field names follow each platform's common schema."""

    queries = []
    if not kinds:
        return queries
    spl = []
    if kinds.get("domain"):
        spl.append(f"query IN ({_q(kinds['domain'])})")
    if kinds.get("ip"):
        spl.append(f"dest_ip IN ({_q(kinds['ip'])})")
    if kinds.get("url"):
        spl.append(f"url IN ({_q(kinds['url'])})")
    if kinds.get("sha256"):
        spl.append(f"file_hash IN ({_q(kinds['sha256'])})")
    queries.append({"platform": "Splunk SPL", "language": "spl", "text":
                    f"index=* earliest=-{lookback}d ({' OR '.join(spl)})\n| stats count min(_time) AS first_seen max(_time) AS last_seen BY host, src, dest, query, url, file_hash"})
    kql = [f"let lookback = {lookback}d;"]
    parts = []
    if kinds.get("domain") or kinds.get("ip") or kinds.get("url"):
        conditions = []
        if kinds.get("ip"):
            kql.append(f"let ips = dynamic([{_q(kinds['ip'])}]);")
            conditions.append("RemoteIP in (ips)")
        hosts = sorted(set(kinds.get("domain", [])) | {urlsplit(u).hostname or u for u in kinds.get("url", [])})
        if hosts:
            kql.append(f"let hosts = dynamic([{_q(hosts)}]);")
            conditions.append("RemoteUrl has_any (hosts)")
        parts.append(f"(DeviceNetworkEvents | where Timestamp > ago(lookback) | where {' or '.join(conditions)})")
    if kinds.get("sha256"):
        kql.append(f"let hashes = dynamic([{_q(kinds['sha256'])}]);")
        parts.append("(DeviceFileEvents | where Timestamp > ago(lookback) | where SHA256 in (hashes))")
    queries.append({"platform": "Microsoft Defender / Sentinel KQL", "language": "kql", "text":
                    "\n".join(kql) + "\nunion isfuzzy=true\n  " + ",\n  ".join(parts) + "\n| project Timestamp, DeviceName, InitiatingProcessFileName, RemoteIP, RemoteUrl, SHA256"})
    eql = []
    if kinds.get("domain"):
        eql.append(f"dns where dns.question.name in ({_q(kinds['domain'])})")
    if kinds.get("ip"):
        eql.append(f"network where destination.ip in ({_q(kinds['ip'])})")
    if kinds.get("sha256"):
        eql.append(f"any where file.hash.sha256 in ({_q(kinds['sha256'])}) or process.hash.sha256 in ({_q(kinds['sha256'])})")
    if kinds.get("url"):
        eql.append(f"network where url.full in ({_q(kinds['url'])})")
    for index, text in enumerate(eql, 1):
        queries.append({"platform": f"Elastic EQL ({index} of {len(eql)})", "language": "eql", "text": text})
    for q in queries:
        q["id"] = "query-" + hashlib.sha256(q["text"].encode()).hexdigest()[:12]
    return queries


def _queries_md(result: ElementResult, output: OutputFormat) -> str:
    rows = result.content.get("queries", [])
    lines = ["## Hunt Queries", ""]
    if not rows:
        return "\n".join([*lines, "_No queries: no huntable indicators._"])
    for q in rows:
        lines += [f"### {q['platform']} — {q['status']} (`{q['id']}`)", "", f"```{q['language']}", q["text"], "```", ""]
    lines.append("_Generated from the indicators, unchanged and not defanged so they run as written. Field names follow each "
                 "platform's common schema; adjust to your data model. Record tests with `report validate <id> passed|failed | <how>`._")
    return "\n".join(lines)


@element(
    "hunt_queries",
    "Hunt queries",
    (M,),
    ("indicators",),
    markdown=_queries_md,
    description="SPL, KQL and EQL generated from the indicators, untested until a validation is recorded.",
    options=("lookback_days",),
)
def build_hunt_queries(context: ReportContext) -> ElementResult:
    lookback = int(context.options.get("hunt_queries", {}).get("lookback_days", 30))
    checks = validations(context.analysis)
    queries = hunt_queries(blockable(context), lookback)
    for q in queries:
        q["status"] = {"passed": "tested", "failed": "failed test"}.get(checks.get(q["id"], {}).get("result", ""), "untested")
    spec = _spec("hunt_queries")
    if not queries:
        return spec.result(ElementStatus.EMPTY, {"queries": []}, gaps=["No huntable indicators."])
    untested = [q["id"] for q in queries if q["status"] != "tested"]
    return spec.result(ElementStatus.PARTIAL if untested else ElementStatus.COMPLETE, {"queries": queries, "lookback_days": lookback},
                       gaps=[f"{len(untested)} query(ies) not tested."] if untested else [])


@element("baseline_false_positives", "Expected baseline and false positives", (A,), ("report section text",), markdown=_text_md,
         description="Legitimate activity that matches the queries and how to exclude it without blinding the hunt.")
def build_baseline(context: ReportContext) -> ElementResult:
    return _text_element(context, "baseline_false_positives", "baseline_false_positives", "Expected Baseline and False Positives",
                         "<legitimate matches and how to exclude them>")


@element("triage_playbook", "Triage and escalation", (A,), ("report section text",), markdown=_text_md,
         description="What to check for each hit and the threshold for escalating to incident response.")
def build_triage_playbook(context: ReportContext) -> ElementResult:
    return _text_element(context, "triage_playbook", "triage_playbook", "Triage and Escalation", "<checks per hit and when to escalate>")


def _outcome_md(result: ElementResult, output: OutputFormat) -> str:
    c = result.content
    lines = ["## Hunt Outcome", ""]
    if not c.get("result"):
        return "\n".join([*lines, "_The hunt has not been run or its outcome is not recorded (`report outcome <supported|refuted|inconclusive> | <findings>`)._"])
    lines += [f"**Hypothesis {c['result']}.** {md(c['findings'])} <sub>— {c['author']}, {c['time']}</sub>"]
    if c["result"] != "supported":
        lines += ["", "_A refuted or inconclusive hunt is a result: it records what was searched and not found._"]
    return "\n".join(lines)


@element(
    "hunt_outcome",
    "Hunt outcome",
    (A,),
    ("report outcome",),
    markdown=_outcome_md,
    description="Whether the hypothesis was supported, refuted or inconclusive, and what was found, including nothing.",
)
def build_hunt_outcome(context: ReportContext) -> ElementResult:
    row = hunt_outcome(context.analysis)
    spec = _spec("hunt_outcome")
    if row is None:
        return spec.result(ElementStatus.EMPTY, {}, gaps=["No hunt outcome is recorded."])
    content = {"result": row["object_value"], "findings": row["statement"], "author": row.get("author_kind"), "time": str(row.get("created_at") or "")[:16]}
    return spec.result(ElementStatus.COMPLETE, content, citations=[f"assertion:{row['id']}"])


# --- detection bundle ---------------------------------------------------------------

PYRAMID = (
    ("ttp", "TTPs", "Tough", "Detect the behaviour; the adversary must change how they operate."),
    ("tool", "Tools", "Challenging", "Detect the tool's artefacts; the adversary must retool."),
    ("artifact", "Network and host artefacts", "Annoying", "Detect URL paths, user agents and similar artefacts."),
    ("domain", "Domain names", "Simple", "Block and sinkhole; cheap for the adversary to replace."),
    ("ip", "IP addresses", "Easy", "Block at the edge for a short period."),
    ("hash", "Hash values", "Trivial", "Block in EDR; any change to the file defeats it."),
)
_LEVEL_OF = {"file": "hash", "ipv4-addr": "ip", "ipv6-addr": "ip", "domain-name": "domain", "url": "artifact"}


def _pyramid_md(result: ElementResult, output: OutputFormat) -> str:
    lines = ["## Pyramid of Pain", "", "| Level | Pain to adversary | Items | Response |", "|---|---|---|---|"]
    for level in result.content.get("levels", []):
        items = ", ".join(md(render_indicator(v, t, output)) for t, v in level["items"][:6]) or "—"
        more = f" (+{len(level['items']) - 6})" if len(level["items"]) > 6 else ""  # noqa: PLR2004
        lines.append(f"| {level['label']} | {level['pain']} | {items}{more} | {level['response']} |")
    return "\n".join(lines)


@element(
    "pyramid_of_pain",
    "Pyramid of Pain",
    (M,),
    ("indicator types", "ATT&CK mappings", "actor tool claims"),
    markdown=_pyramid_md,
    description="Indicators, tools and techniques placed on the Pyramid of Pain by type, with the response suited to each level.",
)
def build_pyramid(context: ReportContext) -> ElementResult:
    rows, _excluded = detailed_indicators(context, blocking=True)
    items: dict[str, list[tuple[str | None, str]]] = defaultdict(list)
    for row in rows:
        level = _LEVEL_OF.get(row["type"])
        if level:
            items[level].append((row["type"], row["value"]))
    for m in context.mappings:
        if m.framework.value == "attack" and m.state.value == "accepted":
            items["ttp"].append((None, f"{m.content_id} {m.content_label}"))
    for subject in actor_subjects(context.analysis):
        for predicate in ("uses-malware", "uses-tool"):
            items["tool"] += [(None, str(r.get("object_value"))) for r in claims(context.analysis, subject, predicate)]
    levels = [{"key": k, "label": label, "pain": pain, "response": response, "items": items.get(k, [])} for k, label, pain, response in PYRAMID]
    spec = _spec("pyramid_of_pain")
    if not any(level["items"] for level in levels):
        return spec.result(ElementStatus.EMPTY, {"levels": levels}, gaps=["Nothing to place on the pyramid."])
    gaps = [] if items.get("ttp") else ["No technique is mapped, so nothing sits at the top of the pyramid."]
    return spec.result(ElementStatus.PARTIAL if gaps else ElementStatus.COMPLETE, {"levels": levels}, gaps=gaps)


def _techniques_for(context: ReportContext, values: list[str]) -> list[str]:
    by_value = {str(o.get("entity_value")): str(o["id"]) for o in context.observations}
    refs = {by_value[v] for v in values if v in by_value}
    return sorted({m.content_id.lower() for m in context.mappings
                   if m.framework.value == "attack" and m.state.value == "accepted" and refs & set(m.evidence_refs)})


def sigma_rules(context: ReportContext, kinds: dict[str, list[str]]) -> list[dict[str, Any]]:
    today = context.now.date().isoformat()
    checks = validations(context.analysis)
    plans = []
    if kinds.get("domain"):
        plans.append(("domain", "DNS query for a reported domain", {"category": "dns"}, {"query": kinds["domain"]}))
    if kinds.get("ip"):
        plans.append(("ip", "Connection to a reported IP address", {"category": "network_connection"}, {"DestinationIp": kinds["ip"]}))
    if kinds.get("url"):
        plans.append(("url", "Request to a reported URL", {"category": "proxy"}, {"c-uri|contains": sorted({urlsplit(u).path or "/" for u in kinds["url"]}),
                                                                               "cs-host": sorted({urlsplit(u).hostname or u for u in kinds["url"]})}))
    if kinds.get("sha256"):
        plans.append(("sha256", "Process from a reported file hash", {"category": "process_creation", "product": "windows"},
                      {"Hashes|contains": [f"SHA256={h.upper()}" for h in kinds["sha256"]]}))
    rules = []
    for kind, title, logsource, selection in plans:
        values = kinds[kind]
        rule_id = _rule_id(f"sigma:{kind}", values)
        status = _status(rule_id, checks, passed="test", default="experimental")
        tags = [f"attack.{t}" for t in _techniques_for(context, values)]
        doc = {
            "title": f"Pivotglass: {title}",
            "id": rule_id,
            "status": status,
            "description": f"Matches {len(values)} indicator(s) collected in this investigation. Generated; tune before production use.",
            "author": "Pivotglass report generator",
            "date": today,
            "tags": tags,
            "logsource": logsource,
            "detection": {"selection": selection, "condition": "selection"},
            "falsepositives": ["Legitimate use of shared infrastructure; validate against your environment"],
            "level": "medium",
        }
        if not tags:
            del doc["tags"]
        import yaml

        rules.append({"id": rule_id, "kind": kind, "status": status, "text": yaml.safe_dump(doc, sort_keys=False, allow_unicode=True)})
    return rules


def _rules_md(heading: str, language: str, note: str):  # noqa: ANN202 - small factory
    def render(result: ElementResult, output: OutputFormat) -> str:
        rules = result.content.get("rules", [])
        lines = [f"## {heading}", ""]
        if not rules:
            return "\n".join([*lines, f"_{result.gaps[0] if result.gaps else 'No rules.'}_"])
        for rule in rules:
            lines += [f"**`{rule['id']}`** — {rule['status']}", "", f"```{language}", rule["text"].rstrip(), "```", ""]
        lines.append(f"_{note}_")
        return "\n".join(lines)

    return render


@element(
    "sigma_rules",
    "Sigma rules",
    (M,),
    ("indicators", "ATT&CK mappings"),
    markdown=_rules_md("Sigma Rules", "yaml", "Status stays experimental until a passed validation is recorded. Values are not defanged."),
    description="Sigma rules generated from the indicators by log source, ISO-dated, status experimental until validated, "
    "tagged with the ATT&CK techniques mapped to the same evidence.",
)
def build_sigma_rules(context: ReportContext) -> ElementResult:
    rules = sigma_rules(context, blockable(context))
    spec = _spec("sigma_rules")
    rejected = rejected_values(context)
    gaps = [f"Left out of rules and queries because they are not well formed: {', '.join(rejected[:10])}."] if rejected else []
    if not rules:
        return spec.result(ElementStatus.EMPTY, {"rules": []}, gaps=["No indicators to build Sigma rules from.", *gaps])
    return spec.result(ElementStatus.PARTIAL if gaps else ElementStatus.COMPLETE, {"rules": rules, "rejected": rejected}, gaps=gaps)


def _sid(key: str, used: set[int]) -> int:
    sid = LOCAL_SID_MIN + int(hashlib.sha256(key.encode()).hexdigest()[:8], 16) % (LOCAL_SID_MAX - LOCAL_SID_MIN)
    while sid in used:
        sid = sid + 1 if sid < LOCAL_SID_MAX else LOCAL_SID_MIN
    used.add(sid)
    return sid


def _content(value: str) -> str:
    """Suricata content escaping: backslash, quote, semicolon and the hex-delimiter pipe."""

    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):  # noqa: PLR2004
        raise ValueError("control characters are not allowed in rule content")
    return value.replace("\\", "\\\\").replace('"', '\\"').replace(";", "\\;").replace("|", "|7C|")


def suricata_rules(context: ReportContext, kinds: dict[str, list[str]]) -> list[dict[str, Any]]:
    created = context.now.strftime("%Y_%m_%d")
    used: set[int] = set()
    rules = []

    def add(kind: str, value: str, body: str, msg: str) -> None:
        sid = _sid(f"{kind}:{value}", used)
        text = (f'{body} (msg:"Pivotglass {msg} {_content(value)}"; {{match}}classtype:trojan-activity; '
                f"metadata:created_at {created}, pivotglass_indicator {kind}; sid:{sid}; rev:1;)")
        rules.append({"id": f"sid:{sid}", "kind": kind, "value": value, "status": "untested", "text": text})

    for domain in kinds.get("domain", []):
        add("domain", domain, "alert dns $HOME_NET any -> any any", "DNS query for")
        rules[-1]["text"] = rules[-1]["text"].replace("{match}", f'dns.query; content:"{_content(domain)}"; nocase; isdataat:!1,relative; ')
    for ip in kinds.get("ip", []):
        if not re.fullmatch(r"[0-9A-Fa-f:.]+", ip):  # second layer: header text is digits, hex, colons and dots only
            continue
        add("ip", ip, f"alert ip $HOME_NET any -> [{ip}] any", "traffic to")
        rules[-1]["text"] = rules[-1]["text"].replace("{match}", "")
    for url in kinds.get("url", []):
        parts = urlsplit(url)
        add("url", url, "alert http $HOME_NET any -> $EXTERNAL_NET any", "request to")
        match = f'flow:established,to_server; http.host; content:"{_content(parts.hostname or "")}"; nocase; '
        if parts.path:
            match += f'http.uri; content:"{_content(parts.path)}"; startswith; '
        rules[-1]["text"] = rules[-1]["text"].replace("{match}", match)
    return rules


@element(
    "suricata_rules",
    "Suricata rules",
    (M,),
    ("network indicators",),
    markdown=_rules_md("Suricata Rules", "", "sids are in the local range 1000000-1999999 and stable for the same indicator. "
                       "Each rule carries metadata; add a reference when the indicator has a public source. Untested."),
    description="Suricata rules for domains, addresses and URLs, sid in the local range 1000000-1999999, with metadata.",
)
def build_suricata_rules(context: ReportContext) -> ElementResult:
    rules = suricata_rules(context, blockable(context))
    checks = validations(context.analysis)
    for rule in rules:
        rule["status"] = {"passed": "tested", "failed": "failed test"}.get(checks.get(rule["id"], {}).get("result", ""), "untested")
    spec = _spec("suricata_rules")
    if not rules:
        return spec.result(ElementStatus.EMPTY, {"rules": []}, gaps=["No network indicators to build Suricata rules from."])
    return spec.result(ElementStatus.COMPLETE, {"rules": rules}, gaps=["Rules carry no public reference; Pivotglass sources are not citable URLs."])


def _yara_string(value: str) -> str:
    """YARA text-string escaping; other control characters are written as hex escapes."""

    out = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\t", "\\t").replace("\r", "\\r")
    return "".join(f"\\x{ord(ch):02x}" if ord(ch) < 0x20 or ord(ch) == 0x7F else ch for ch in out)  # noqa: PLR2004


def yara_rules(context: ReportContext) -> list[dict[str, Any]]:
    checks = validations(context.analysis)
    rules = []
    for item in yara_inputs(context.analysis):
        name = f"PG_sample_{item['sha256'][:12]}"
        strings = "\n".join(f'        $s{i} = "{_yara_string(s)}" ascii wide' for i, s in enumerate(item["strings"], 1))
        condition = "all of them" if len(item["strings"]) <= 2 else "2 of them"  # noqa: PLR2004
        status = "tested" if checks.get(name, {}).get("result") == "passed" else "untested draft"
        text = (f"rule {name}\n{{\n    meta:\n        description = \"Analyst-supplied strings from one sample; {status}\"\n"
                f"        sample_sha256 = \"{item['sha256']}\"\n        reference = \"{_yara_string(item['reference'])}\"\n"
                f"        date = \"{context.now.date().isoformat()}\"\n        status = \"{status}\"\n"
                f"    strings:\n{strings}\n    condition:\n        {condition}\n}}\n")
        rules.append({"id": name, "kind": "yara", "status": status, "text": text, "source": f"assertion:{item['id']}"})
    return rules


@element(
    "yara_rules",
    "YARA rules",
    (A,),
    ("analyst-supplied strings (`report yara`)",),
    markdown=_rules_md("YARA Rules", "yara", "Built only from strings the analyst supplied from the named sample; untested until validated."),
    description="YARA rules from analyst-supplied sample strings, with sample hash and reference, untested until validated.",
)
def build_yara_rules(context: ReportContext) -> ElementResult:
    rules = yara_rules(context)
    spec = _spec("yara_rules")
    if not rules:
        return spec.result(ElementStatus.EMPTY, {"rules": []},
                           gaps=["No sample strings supplied (`report yara <sha256> | <reference> | <string>; <string>`)."])
    return spec.result(ElementStatus.COMPLETE, {"rules": rules}, citations=[r["source"] for r in rules])


def _validation_md(result: ElementResult, output: OutputFormat) -> str:
    rows = result.content.get("rules", [])
    lines = ["## Validation", ""]
    if not rows:
        return "\n".join([*lines, "_Nothing to validate._"])
    lines += ["| Rule or query | Kind | Result | What was tested |", "|---|---|---|---|"]
    lines += [f"| `{r['id']}` | {r['kind']} | {r['result']} | {md(r['note'])} |" for r in rows]
    return "\n".join(lines)


@element(
    "validation_notes",
    "Validation",
    (A,),
    ("report validate records",),
    markdown=_validation_md,
    description="For each generated rule and query: whether it was tested, against what, and the result. Untested is shown as untested.",
)
def build_validation_notes(context: ReportContext) -> ElementResult:
    kinds = blockable(context)
    checks = validations(context.analysis)
    items = [(r["id"], f"sigma/{r['kind']}") for r in sigma_rules(context, kinds)]
    items += [(r["id"], f"suricata/{r['kind']}") for r in suricata_rules(context, kinds)]
    items += [(r["id"], "yara") for r in yara_rules(context)]
    items += [(q["id"], q["language"]) for q in hunt_queries(kinds, 30)]
    rows = [
        {"id": rule_id, "kind": kind, "result": checks.get(rule_id, {}).get("result", "not tested"), "note": checks.get(rule_id, {}).get("note", "—")}
        for rule_id, kind in items
    ]
    spec = _spec("validation_notes")
    if not rows:
        return spec.result(ElementStatus.EMPTY, {"rules": []}, gaps=["No rules or queries to validate."])
    untested = sum(1 for r in rows if r["result"] == "not tested")
    return spec.result(ElementStatus.PARTIAL if untested else ElementStatus.COMPLETE, {"rules": rows},
                       citations=[f"assertion:{c['id']}" for c in checks.values()],
                       gaps=[f"{untested} of {len(rows)} rules and queries are not tested."] if untested else [])


def native_rules(report: Any, element_id: str) -> str:
    """The rule texts of one element, for the Sigma, Suricata and YARA downloads."""

    result = report.element(element_id)
    rules = result.content.get("rules", []) if result else []
    if not rules:
        raise ValueError(f"{report.type_id} has no {element_id.replace('_', ' ')} to export")
    separator = "---\n" if element_id == "sigma_rules" else "\n" if element_id == "suricata_rules" else "\n"
    return separator.join(rule["text"].rstrip() + "\n" for rule in rules)
