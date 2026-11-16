"""Tag, context, and focus-mode endpoint contracts (#13, #15, #16)."""

from __future__ import annotations

import base64
import hashlib
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import threading

import pytest

from pivotglass.core.document_library import DocumentLibraryService, PivotTrailAuthority
from pivotglass.core.indicator_context import (
    IndicatorContextAuthority,
    document_relations,
    indicator_key,
)
from pivotglass.core.indicator_tags import IndicatorTagAuthority, dimension_catalog
from pivotglass.core.workspace import WorkspaceManager
from tests.pdf_fixture import text_pdf
from tests.test_web_server import _post_json, _service
from pivotglass.web.server import _handler


def _workspace(tmp_path) -> WorkspaceManager:
    manager = WorkspaceManager(tmp_path)
    manager.create("focus")
    manager.switch("focus")
    return manager


def _tag(entity_type, value, dimension, tag, action="add"):
    return {"entity_type": entity_type, "normalized_value": value,
            "dimension": dimension, "value": tag, "action": action}


def test_tags_follow_the_indicator_and_derive_current_state(tmp_path) -> None:
    authority = IndicatorTagAuthority(_workspace(tmp_path))
    authority.apply([_tag("domain-name", "evil.example", "role", "C2"),
                     _tag("domain-name", "evil.example", "tactic", "command-and-control"),
                     _tag("file-hash-sha256", "a" * 64, "status", "needs-pivot")],
                    operator="analyst")
    authority.apply([_tag("domain-name", "evil.example", "role", "c2", "remove"),
                     _tag("domain-name", "evil.example", "role", "staging")], operator="analyst")
    current = {(t["entity_type"], t["dimension"], t["value"]) for t in authority.current()}
    assert current == {("domain-name", "tactic", "command-and-control"),
                       ("domain-name", "role", "staging"),
                       ("file", "status", "needs-pivot")}


def test_add_then_remove_in_one_batch_keeps_submitted_order(tmp_path) -> None:
    authority = IndicatorTagAuthority(_workspace(tmp_path))
    authority.apply([_tag("ipv4-addr", "203.0.113.7", "cluster", "kit a"),
                     _tag("ipv4-addr", "203.0.113.7", "cluster", "kit a", "remove")],
                    operator="analyst")
    assert authority.current() == []


@pytest.mark.parametrize(("dimension", "value", "message"), [
    ("tactic", "pwning", "not a tactic value"),
    ("status", "maybe", "not a status value"),
    ("mood", "x", "unknown tag dimension"),
    ("cluster", "<script>", "1-64 lowercase"),
])
def test_invalid_tags_are_rejected_before_any_write(tmp_path, dimension, value, message) -> None:
    authority = IndicatorTagAuthority(_workspace(tmp_path))
    with pytest.raises(ValueError, match=message):
        authority.apply([_tag("ipv4-addr", "203.0.113.8", "role", "c2"),
                         _tag("ipv4-addr", "203.0.113.8", dimension, value)], operator="a")
    assert authority.current() == []


def test_tactic_dimension_is_ordered_attack_path() -> None:
    tactic = next(item for item in dimension_catalog() if item["name"] == "tactic")
    assert tactic["ordered"] and tactic["closed"]
    values = [item["value"] for item in tactic["values"]]
    assert values[0] == "reconnaissance" and values[-1] == "impact"
    assert values.index("initial-access") < values.index("command-and-control") < values.index("exfiltration")
    assert len(values) == 14


def test_document_relations_label_structure_and_position_separately() -> None:
    text = "Dropper at https://cdn.evil.example/a.bin talks to 203.0.113.7.\n\nAdmin: ops@evil.example\nunrelated.example.org"
    cands = []
    for entity_type, value in [("url", "https://cdn.evil.example/a.bin"), ("ipv4-addr", "203.0.113.7"),
                               ("email-addr", "ops@evil.example"), ("domain-name", "cdn.evil.example"),
                               ("domain-name", "evil.example"), ("domain-name", "unrelated.example.org")]:
        start = text.find(value)
        if start < 0:  # bare domains we inject as separate mentions on line 4
            text += "\n" + value
            start = text.rfind(value)
        cands.append({"entity_type": entity_type, "normalized_value": value,
                      "start_char": start, "start_line": text[:start].count("\n") + 1})
    rel = document_relations(cands, text)
    url = rel[indicator_key("url", "https://cdn.evil.example/a.bin")]
    assert {"key": "domain-name|cdn.evil.example", "relation": "host"} in url["structural"]
    assert {"key": "domain-name|evil.example", "relation": "parent domain"} in url["structural"]
    assert {"key": "ipv4-addr|203.0.113.7"} in url["same_line"]
    apex = rel["domain-name|evil.example"]
    assert {"key": "domain-name|cdn.evil.example", "relation": "subdomain"} in apex["structural"]
    assert {"key": "email-addr|ops@evil.example", "relation": "used by"} in apex["structural"]
    assert not rel["domain-name|unrelated.example.org"]["structural"]


def test_context_reports_entities_documents_tags_and_investigations(tmp_path) -> None:
    manager = _workspace(tmp_path)
    library = DocumentLibraryService(manager)
    first = b"C2 203.0.113.7 seen with evil.example"
    second = b"Later report: 203.0.113.7 again"
    receipt = library.ingest_bytes(first, filename="a.txt", operator="analyst",
                                   expected_sha256=hashlib.sha256(first).hexdigest())
    library.ingest_bytes(second, filename="b.txt", operator="analyst",
                         expected_sha256=hashlib.sha256(second).hexdigest())
    occurrence_a = next(item.occurrence_id for item in library.list() if item.filename == "a.txt")
    candidates = library.detail(occurrence_a)["candidates"]
    library.admit_candidates(occurrence_a, [c["id"] for c in candidates if c["normalized_value"] == "203.0.113.7"],
                             operator="analyst")
    IndicatorTagAuthority(manager).apply([_tag("ipv4-addr", "203.0.113.7", "role", "c2")], operator="analyst")
    PivotTrailAuthority(manager).record_indicator("203.0.113.7")
    del receipt

    context = IndicatorContextAuthority(manager).context(
        [("ipv4-addr", "203.0.113.7"), ("domain-name", "evil.example"), ("domain-name", "never.example")],
        current_occurrence_id=occurrence_a,
    )
    ip = context["ipv4-addr|203.0.113.7"]
    assert ip["entity"]["type"] == "ipv4-addr"
    assert [d["filename"] for d in ip["documents"]] == ["b.txt"]
    assert ip["documents"][0]["copies"] == 1
    # The same bytes ingested again are one source with two stored copies.
    library.ingest_bytes(second, filename="b-again.txt", operator="analyst",
                         expected_sha256=hashlib.sha256(second).hexdigest())
    again = IndicatorContextAuthority(manager).context([("ipv4-addr", "203.0.113.7")],
                                                       current_occurrence_id=occurrence_a)
    assert [(d["copies"], d["mentions"]) for d in again["ipv4-addr|203.0.113.7"]["documents"]] == [(2, 1)]
    assert [t["value"] for t in ip["tags"]] == ["c2"]
    assert ip["investigated_at"]
    assert context["domain-name|evil.example"]["entity"] is None
    assert context["domain-name|never.example"]["documents"] == []


def _serve(service, tmp_path):
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler(service, tmp_path))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def _get(server, path):
    connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        connection.close()


def test_focus_endpoints_over_http(tmp_path) -> None:
    service = _service(tmp_path)
    server = _serve(service, tmp_path)
    try:
        workspace = service.ctx.workspace_mgr.active
        status, dims = _get(server, "/api/tags/dimensions")[0], _get(server, "/api/tags/dimensions")[2]
        assert status == 200 and b'"tactic"' in dims
        status, body = _post_json(server, "/api/tags", {"expected_workspace": workspace,
                                  "changes": [_tag("ipv4-addr", "203.0.113.9", "role", "c2")]})
        assert status == 201 and body["tags"][0]["value"] == "c2"
        status, body = _post_json(server, "/api/tags", {"expected_workspace": "other",
                                  "changes": [_tag("ipv4-addr", "203.0.113.9", "role", "c2")]})
        assert status == 400
        status, body = _post_json(server, "/api/indicators/context", {"expected_workspace": workspace,
                                  "indicators": [{"entity_type": "ipv4-addr", "normalized_value": "203.0.113.9"}]})
        assert status == 200 and body["context"]["ipv4-addr|203.0.113.9"]["tags"][0]["value"] == "c2"

        pdf = text_pdf([["C2 at 203.0.113.7"]])
        encoded = base64.b64encode(pdf).decode()
        preview = service.preview_document({"filename": "r.pdf", "content_base64": encoded})
        assert preview["rendering"]["kind"] == "pdf"
        assert "ipv4-addr|203.0.113.7" in preview["entity_extraction"]["relations"]
        service.ingest_document({"filename": "r.pdf", "content_base64": encoded,
                                 "expected_sha256": preview["content_sha256"], "operator": "a"})
        txt = b"plain 198.51.100.4"
        txt_preview = service.preview_document({"filename": "t.txt", "content_base64": base64.b64encode(txt).decode()})
        service.ingest_document({"filename": "t.txt", "content_base64": base64.b64encode(txt).decode(),
                                 "expected_sha256": txt_preview["content_sha256"], "operator": "a"})
        docs = {d["filename"]: d["occurrence_id"] for d in service.document_library()["documents"]}
        status, headers, body = _get(server, f"/api/documents/{docs['r.pdf']}/source")
        assert status == 200 and body == pdf
        assert headers["Content-Type"] == "application/pdf"
        assert "sandbox" in headers["Content-Security-Policy"]
        assert headers["Content-Disposition"] == "attachment"
        status, _headers, _body = _get(server, f"/api/documents/{docs['t.txt']}/source")
        assert status == 404
        detail = service.document_detail(docs["t.txt"])
        assert detail["rendering"]["anchoring"] == "exact"
        assert "ipv4-addr|198.51.100.4" in detail["relations"]
    finally:
        server.shutdown()
        server.server_close()


def test_blankless_text_does_not_make_the_whole_document_one_paragraph() -> None:
    lines = [f"line {index}" for index in range(30)]
    lines[2] = "first 203.0.113.1"
    lines[25] = "far away 203.0.113.2"
    text = "\n".join(lines)
    cands = [{"entity_type": "ipv4-addr", "normalized_value": value, "start_char": text.find(value),
              "start_line": text[:text.find(value)].count("\n") + 1}
             for value in ("203.0.113.1", "203.0.113.2")]
    rel = document_relations(cands, text)
    assert rel["ipv4-addr|203.0.113.1"]["same_paragraph"] == []
    short = "intro 203.0.113.1\nnext 203.0.113.2\n\nother"
    cands = [{"entity_type": "ipv4-addr", "normalized_value": v, "start_char": short.find(v),
              "start_line": short[:short.find(v)].count("\n") + 1} for v in ("203.0.113.1", "203.0.113.2")]
    assert document_relations(cands, short)["ipv4-addr|203.0.113.1"]["same_paragraph"] == [{"key": "ipv4-addr|203.0.113.2"}]
