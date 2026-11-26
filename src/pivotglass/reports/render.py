"""Report renderers: Markdown, JSON and STIX 2.1 (#50).

Renderers read a built :class:`~pivotglass.reports.engine.Report` and nothing
else. Markdown is for people and defangs indicators; JSON and STIX are for
machines and never do (DEC-REPORT-CONTRACT-001).
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from pivotglass.reports.contract import PROVENANCE_LABELS, OutputFormat, Tlp
from pivotglass.reports.elements import ELEMENTS, ElementStatus, load_builtin_elements
from pivotglass.reports.engine import Report
from pivotglass.reports.registry import get_report_type

# FIRST TLP 2.0 marking definitions, as published by OASIS in
# cti-stix-common-objects/extension-definition-specifications/tlp-2.0/examples.
TLP2_EXTENSION = "extension-definition--60a3c5c5-0d10-413e-aab3-9e08dde9e88d"
TLP2_MARKING_IDS = {
    Tlp.CLEAR: "marking-definition--94868c89-83c2-464b-929b-a1a8aa3c8487",
    Tlp.GREEN: "marking-definition--bab4a63c-aed9-4cf5-a766-dfca5abac2bb",
    Tlp.AMBER: "marking-definition--55d920b0-5e8b-4f79-9ee9-91f868d9b421",
    Tlp.AMBER_STRICT: "marking-definition--939a9414-2ddd-4d32-a0cd-375ea402b003",
    Tlp.RED: "marking-definition--e828b379-4e03-4974-9ac4-e53a884c97c1",
}
_NAMESPACE = uuid.UUID("6f1e3c0a-2b52-4b8e-9d0f-5f3a1c7e9b21")  # Pivotglass report objects (uuid5)


def tlp2_marking_definition(tlp: Tlp) -> dict[str, Any]:
    return {
        "type": "marking-definition",
        "spec_version": "2.1",
        "id": TLP2_MARKING_IDS[tlp],
        "created": "2022-10-01T00:00:00.000Z",
        "name": f"TLP:{tlp.value}",
        "extensions": {TLP2_EXTENSION: {"extension_type": "property-extension", "tlp_2_0": tlp.value.lower()}},
    }


def render(report: Report, output: OutputFormat | str = OutputFormat.MARKDOWN) -> str:
    output = OutputFormat(output)
    report_type = get_report_type(report.type_id)
    if output not in report_type.formats:
        supported = ", ".join(f.value for f in report_type.formats)
        raise ValueError(f"{report_type.title} renders as {supported}, not {output.value}")
    if output is OutputFormat.MARKDOWN:
        return render_markdown(report)
    if output is OutputFormat.JSON:
        return json.dumps(report.model_dump(mode="json"), indent=2, ensure_ascii=False)
    if output is OutputFormat.STIX:
        return json.dumps(render_stix(report), indent=2, ensure_ascii=False)
    raise ValueError(f"no renderer for {output.value} yet")


def render_markdown(report: Report) -> str:
    load_builtin_elements()
    blocks: list[str] = []
    for result in report.elements:
        blocks.append(ELEMENTS[result.element_id].markdown(result, OutputFormat.MARKDOWN))
        if result.element_id == "header":
            blocks.append(_completeness(report))
        else:
            blocks[-1] = f"{blocks[-1]}\n\n{_provenance_note(result)}"
    return "\n\n".join(block.rstrip() for block in blocks) + "\n"


def _completeness(report: Report) -> str:
    if report.complete:
        state = "**Complete:** every required element has content."
    else:
        titles = ", ".join(next(e.title for e in report.elements if e.element_id == m) for m in report.missing_required)
        state = f"**Incomplete:** no content for {titles}. See Gaps and Limitations."
    if report.pending_model_drafts:
        state += f" {report.pending_model_drafts} model draft(s) await analyst review."
    return state


def _provenance_note(result: Any) -> str:
    labels = " + ".join(PROVENANCE_LABELS[p] for p in result.provenance)
    status = "" if result.status is ElementStatus.COMPLETE else f" · {result.status.value}"
    return f"<sub>Provenance: {labels}{status}</sub>"


def render_stix(report: Report) -> dict[str, Any]:
    """A STIX 2.1 bundle: the report SDO, a producer identity, the TLP 2.0 marking and the indicators' SCOs.

    Only what STIX represents is included: the SCOs are re-emitted with their
    collected ids so a consumer can join them to a workspace STIX export.
    PAP has no STIX marking definition; it is carried as ``x_pivotglass_pap``.
    """

    header = report.header
    marking = tlp2_marking_definition(header.tlp)
    seed = header.report_id or f"preview:{header.type_id}:{header.issued_at.isoformat()}"
    stamp = header.issued_at.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    identity = {
        "type": "identity",
        "spec_version": "2.1",
        "id": f"identity--{uuid.uuid5(_NAMESPACE, header.producer)}",
        "created": stamp,
        "modified": stamp,
        "name": header.producer,
        "identity_class": "system",
    }
    observables = []
    iocs = report.element("ioc_table")
    for row in (iocs.content.get("indicators", []) if iocs else []):
        sco = _sco(row)
        if sco:
            sco["object_marking_refs"] = [marking["id"]]
            observables.append(sco)
    report_sdo = {
        "type": "report",
        "spec_version": "2.1",
        "id": f"report--{uuid.uuid5(_NAMESPACE, f'{seed}:v{header.version}')}",
        "created": stamp,
        "modified": stamp,
        "created_by_ref": identity["id"],
        "name": f"{header.title} {header.report_id or '(preview)'}",
        "description": "; ".join(header.pirs) or header.title,
        "published": stamp,
        "report_types": ["threat-report"],
        "object_refs": [obj["id"] for obj in observables] or [identity["id"]],
        "object_marking_refs": [marking["id"]],
        "external_references": [{"source_name": "pivotglass", "external_id": header.report_id or "preview"}],
        "x_pivotglass_pap": header.pap.value,
        "x_pivotglass_report_status": header.status.value,
        "x_pivotglass_report_version": header.version,
        "x_pivotglass_complete": report.complete,
    }
    return {
        "type": "bundle",
        "id": f"bundle--{uuid.uuid5(_NAMESPACE, report_sdo['id'])}",
        "objects": [marking, identity, report_sdo, *observables],
    }


_STIX_VALUE_TYPES = {"ipv4-addr", "ipv6-addr", "domain-name", "url", "email-addr", "mac-addr"}


def _sco(row: dict[str, Any]) -> dict[str, Any] | None:
    kind, value, stix_id = row["type"], row["value"], row.get("stix_id")
    if kind in _STIX_VALUE_TYPES:
        sco = {"type": kind, "spec_version": "2.1", "value": value}
    elif kind == "file":
        key = {64: "SHA-256", 40: "SHA-1", 32: "MD5"}.get(len(value))
        sco = {"type": "file", "spec_version": "2.1", **({"hashes": {key: value}} if key else {"name": value})}
    else:
        return None
    sco["id"] = stix_id if isinstance(stix_id, str) and stix_id.startswith(f"{kind}--") else f"{kind}--{uuid.uuid5(_NAMESPACE, value)}"
    return sco
