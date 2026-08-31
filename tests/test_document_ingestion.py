"""Governed document intake, parser receipts, and content-addressing."""

from __future__ import annotations

import sqlite3

import pytest
from sqlalchemy import inspect, select

from adversary_pursuit.core.document_ingestion import (
    DocumentIntakeService,
    DocumentLimits,
    preview_document,
)
from adversary_pursuit.core.workspace import WorkspaceManager
from adversary_pursuit.core.workspace_migrations import CURRENT_WORKSPACE_SCHEMA_VERSION
from adversary_pursuit.models.database import (
    DocumentContent,
    DocumentOccurrence,
    DocumentParserReceipt,
)


def _workspace(tmp_path):
    manager = WorkspaceManager(workspace_dir=tmp_path)
    manager.create("documents")
    manager.switch("documents")
    return manager


def test_text_preview_is_non_mutating_and_states_truth_boundary(tmp_path) -> None:
    manager = _workspace(tmp_path)
    preview = DocumentIntakeService(manager).preview_bytes(
        b"Observed 192.0.2.8 in source reporting.",
        filename="report.txt",
    )

    assert preview.state == "parsed"
    assert preview.output_text == "Observed 192.0.2.8 in source reporting."
    assert "not proof" in preview.truth_boundary
    assert manager.get_workspace_table_counts()["document_occurrences"] == 0


def test_html_preview_does_not_run_or_emit_active_content() -> None:
    preview = preview_document(
        b"<h1>Finding</h1><script>stealSecrets()</script><p>example.test</p>",
        filename="report.html",
    )

    assert preview.state == "parsed"
    assert "Finding" in preview.output_text
    assert "example.test" in preview.output_text
    assert "stealSecrets" not in preview.output_text
    assert any("not run" in warning for warning in preview.warnings)


def test_structured_preview_is_bounded_and_malformed_input_fails() -> None:
    limited = preview_document(
        b"a,b\n1,2\n3,4\n",
        filename="rows.csv",
        limits=DocumentLimits(max_rows=1),
    )
    malformed = preview_document(b'{"unterminated":', filename="bad.json")

    assert limited.state == "partial"
    assert limited.output_text == "a\tb"
    assert any("row limit" in warning for warning in limited.warnings)
    assert malformed.state == "failed"
    assert malformed.errors


def test_jsonl_and_email_preview_keep_locations_and_attachments_explicit() -> None:
    jsonl = preview_document(b'{"ip":"192.0.2.1"}\n{"ip":"192.0.2.2"}\n', filename="feed.jsonl")
    email = preview_document(
        b"From: source@example.test\nTo: analyst@example.test\nSubject: report\n"
        b"MIME-Version: 1.0\nContent-Type: multipart/mixed; boundary=x\n\n"
        b"--x\nContent-Type: text/plain\n\nBody indicator.example\n"
        b"--x\nContent-Type: application/octet-stream\n"
        b"Content-Disposition: attachment; filename=sample.bin\n\nAAAA\n--x--\n",
        filename="report.eml",
    )

    assert jsonl.state == "parsed"
    assert jsonl.output_text.count("\n") == 1
    assert email.state == "partial"
    assert "Body indicator.example" in email.output_text
    assert any("sample.bin" in item for item in email.skipped)


def test_store_reuses_content_but_preserves_each_occurrence_and_receipt(tmp_path) -> None:
    manager = _workspace(tmp_path)
    service = DocumentIntakeService(manager)
    first = service.store_bytes(
        b"same source bytes",
        filename="first.txt",
        operator="analyst",
        source_uri="file:///private/cases/first.txt",
    )
    second = service.store_bytes(
        b"same source bytes",
        filename="second.txt",
        operator="analyst",
        source_uri="https://user:secret@example.test/report?token=secret#fragment",
    )

    assert first.reused_content is False
    assert second.reused_content is True
    assert first.storage_ref == second.storage_ref
    assert first.occurrence_id != second.occurrence_id
    content_path = (
        tmp_path
        / "documents.content"
        / "sha256"
        / first.preview.content_sha256[:2]
        / first.preview.content_sha256
    )
    assert content_path.read_bytes() == b"same source bytes"
    assert content_path.stat().st_mode & 0o777 == 0o600

    with manager.get_session() as session:
        assert len(session.execute(select(DocumentContent)).scalars().all()) == 1
        occurrences = session.execute(
            select(DocumentOccurrence).order_by(DocumentOccurrence.filename)
        ).scalars().all()
        assert len(occurrences) == 2
        assert occurrences[0].source_uri == "file:first.txt"
        assert occurrences[1].source_uri == "https://example.test/report"
        assert len(session.execute(select(DocumentParserReceipt)).scalars().all()) == 2


def test_store_refuses_failed_parse_and_oversized_input(tmp_path) -> None:
    manager = _workspace(tmp_path)
    service = DocumentIntakeService(manager)

    with pytest.raises(ValueError, match="parser failed"):
        service.store_bytes(b"{bad", filename="bad.json", operator="analyst")
    with pytest.raises(ValueError, match="configured limit"):
        service.preview_bytes(
            b"0123456789",
            filename="large.txt",
            limits=DocumentLimits(max_bytes=5),
        )
    assert manager.get_workspace_table_counts()["document_contents"] == 0


def test_schema_v8_migrates_document_tables_backup_first(tmp_path) -> None:
    manager = _workspace(tmp_path)
    manager._engine.dispose()
    manager._engine = None
    manager._active = None
    db_path = tmp_path / "documents.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute("DROP TABLE document_parser_receipts")
        connection.execute("DROP TABLE document_occurrences")
        connection.execute("DROP TABLE document_contents")
        connection.execute("UPDATE workspace_schema_version SET version = 8 WHERE id = 1")

    migrated = WorkspaceManager(workspace_dir=tmp_path)
    migrated.switch("documents")
    tables = set(inspect(migrated._engine).get_table_names())
    assert {"document_contents", "document_occurrences", "document_parser_receipts"} <= tables
    assert migrated.get_workspace_schema_status()["to_version"] == CURRENT_WORKSPACE_SCHEMA_VERSION
    assert (tmp_path / "documents.db.pre-v8-backup").is_file()
