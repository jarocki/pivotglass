"""Exact-span deterministic document entity candidates."""

from __future__ import annotations

import sqlite3

import pytest
from sqlalchemy import inspect, select

from pivotglass.core.document_entity_extraction import (
    DocumentEntityExtractionService,
    EntityExtractionLimits,
    extract_entity_candidates,
)
from pivotglass.core.document_ingestion import DocumentIntakeService
from pivotglass.core.workspace import WorkspaceManager
from pivotglass.core.workspace_migrations import CURRENT_WORKSPACE_SCHEMA_VERSION
from pivotglass.models.database import (
    DocumentEntityCandidate,
    DocumentExtractionReceipt,
)


def _workspace(tmp_path):
    manager = WorkspaceManager(workspace_dir=tmp_path)
    manager.create("entity-documents")
    manager.switch("entity-documents")
    return manager


def test_candidates_retain_exact_character_byte_line_and_context_locations() -> None:
    text = "Résumé α\nObserved 198.51.100.9 and EXAMPLE.test.\n"
    address_start = text.index("198.51.100.9")

    result = extract_entity_candidates(
        text,
        occurrence_id="occurrence-1",
        parser_receipt_id="parser-1",
        input_sha256="a" * 64,
    )

    address = next(item for item in result.candidates if item.entity_type == "ipv4-addr")
    domain = next(item for item in result.candidates if item.entity_type == "domain-name")
    assert address.start_char == address_start
    assert address.end_char == address_start + len(address.raw_value)
    assert address.start_byte == len(text[:address_start].encode("utf-8"))
    assert address.end_byte == len(text[: address.end_char].encode("utf-8"))
    assert (address.start_line, address.start_column) == (2, 10)
    assert text[address.start_char : address.end_char] == address.raw_value
    assert address.raw_value in address.context
    assert domain.normalized_value == "example.test"
    assert "not admitted evidence" in address.truth_boundary


def test_precedence_avoids_nested_domain_candidates_and_normalization_is_visible() -> None:
    result = extract_entity_candidates(
        "See https://user:secret@EXAMPLE.test/path?q=1 and analyst@EXAMPLE.test.",
        occurrence_id="occurrence-1",
        parser_receipt_id="parser-1",
        input_sha256="b" * 64,
    )

    assert [item.entity_type for item in result.candidates] == ["url", "email-addr"]
    url, email = result.candidates
    assert url.normalized_value == "https://example.test/path?q=1"
    assert "credentials were omitted" in (url.normalization_note or "")
    assert email.normalized_value == "analyst@example.test"


def test_standard_defanged_indicators_are_normalized_with_exact_raw_spans() -> None:
    text = "1[.]1[.]1[.]1 http[:]//foo[.]bar john AT doe DOT org john[@]doe[.]org"
    result = extract_entity_candidates(
        text,
        occurrence_id="occurrence-defanged",
        parser_receipt_id="parser-defanged",
        input_sha256="e" * 64,
    )

    assert [(item.entity_type, item.raw_value, item.normalized_value) for item in result.candidates] == [
        ("ipv4-addr", "1[.]1[.]1[.]1", "1.1.1.1"),
        ("url", "http[:]//foo[.]bar", "http://foo.bar"),
        ("email-addr", "john AT doe DOT org", "john@doe.org"),
        ("email-addr", "john[@]doe[.]org", "john@doe.org"),
    ]
    for item in result.candidates:
        assert text[item.start_char:item.end_char] == item.raw_value
        assert item.normalization_note and "defanging" in item.normalization_note


def test_common_bracket_word_defanging_is_supported() -> None:
    result = extract_entity_candidates(
        "hxxps[://]portal[dot]example[dot]org contact analyst[at]example[dot]org",
        occurrence_id="occurrence-bracket-words",
        parser_receipt_id="parser-bracket-words",
        input_sha256="1" * 64,
    )
    assert [(item.entity_type, item.normalized_value) for item in result.candidates] == [
        ("url", "https://portal.example.org"),
        ("email-addr", "analyst@example.org"),
    ]


def test_defanged_forms_do_not_turn_prose_into_candidates() -> None:
    result = extract_entity_candidates(
        "Meet me at the office. The word dot is not an indicator. 999[.]999[.]999[.]999.",
        occurrence_id="occurrence-prose",
        parser_receipt_id="parser-prose",
        input_sha256="f" * 64,
    )

    assert result.candidates == ()


def test_invalid_values_are_rejected_and_candidate_limit_is_explicit() -> None:
    invalid = extract_entity_candidates(
        "Invalid 999.999.999.999 and bareword.localhost",
        occurrence_id="occurrence-1",
        parser_receipt_id="parser-1",
        input_sha256="c" * 64,
    )
    limited = extract_entity_candidates(
        "192.0.2.1 192.0.2.2 192.0.2.3",
        occurrence_id="occurrence-1",
        parser_receipt_id="parser-1",
        input_sha256="c" * 64,
        limits=EntityExtractionLimits(max_candidates=2),
    )

    assert all(item.entity_type != "ipv4-addr" for item in invalid.candidates)
    assert limited.state == "partial"
    assert len(limited.candidates) == 2
    assert "limit reached" in limited.warnings[0]


def test_hash_cve_attack_and_ipv6_rules_are_versioned() -> None:
    result = extract_entity_candidates(
        "SHA256 " + "A" * 64 + " CVE-2026-12345 T1583.001 2001:db8::8",
        occurrence_id="occurrence-1",
        parser_receipt_id="parser-1",
        input_sha256="d" * 64,
    )

    assert {item.entity_type for item in result.candidates} == {
        "file-hash-sha256",
        "vulnerability",
        "attack-pattern",
        "ipv6-addr",
    }
    assert {item.rule_version for item in result.candidates} == {"1.1"}


def test_persisted_extraction_is_idempotent_and_does_not_create_graph_entities(tmp_path) -> None:
    manager = _workspace(tmp_path)
    intake = DocumentIntakeService(manager).store_bytes(
        b"Observed 192.0.2.10 and node.example.",
        filename="report.txt",
        operator="analyst",
    )
    service = DocumentEntityExtractionService(manager)

    first = service.extract_parser_receipt(intake.parser_receipt_id)
    second = service.extract_parser_receipt(intake.parser_receipt_id)

    assert first.reused is False
    assert second.reused is True
    assert first.candidates == second.candidates
    assert manager.get_stix_objects() == []
    assert manager.get_workspace_table_counts()["relationships"] == 0
    with manager.get_session() as session:
        assert len(session.execute(select(DocumentExtractionReceipt)).scalars().all()) == 1
        assert len(session.execute(select(DocumentEntityCandidate)).scalars().all()) == 2


def test_failed_parser_receipt_cannot_be_extracted(tmp_path) -> None:
    manager = _workspace(tmp_path)
    with pytest.raises(ValueError, match="parser failed"):
        DocumentIntakeService(manager).store_bytes(
            b'{"score":NaN}',
            filename="bad.json",
            operator="analyst",
        )


def test_schema_v9_migrates_extraction_and_cluster_snapshot_tables_backup_first(tmp_path) -> None:
    manager = _workspace(tmp_path)
    manager._engine.dispose()
    manager._engine = None
    manager._active = None
    db_path = tmp_path / "entity-documents.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute("DROP TABLE evidence_cluster_snapshots")
        connection.execute("DROP TABLE document_entity_candidates")
        connection.execute("DROP TABLE document_extraction_receipts")
        connection.execute("UPDATE workspace_schema_version SET version = 9 WHERE id = 1")

    migrated = WorkspaceManager(workspace_dir=tmp_path)
    migrated.switch("entity-documents")
    tables = set(inspect(migrated._engine).get_table_names())
    assert {
        "document_extraction_receipts",
        "document_entity_candidates",
        "evidence_cluster_snapshots",
    } <= tables
    assert (
        migrated.get_workspace_schema_status()["to_version"]
        == CURRENT_WORKSPACE_SCHEMA_VERSION
    )
    assert (tmp_path / "entity-documents.db.pre-v9-backup").is_file()
