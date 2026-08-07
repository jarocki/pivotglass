"""v0.8 epistemic-storage, migration, and analytic-ledger contracts."""

from __future__ import annotations

import json
import sqlite3

import pytest
from sqlalchemy import inspect, text

from adversary_pursuit.agent.repl_verbs import dispatch_repl_verb, parse_repl_verb
from adversary_pursuit.core.analytic_commands import execute_analysis_command
from adversary_pursuit.core.analytic_ledger import (
    AnalystDisposition,
    AnalyticLedger,
    AssertionType,
    AuthorKind,
    ConfidenceLevel,
    ContradictionStatus,
    EvidenceStance,
    HypothesisStatus,
    InvestigationStatus,
    LifecycleItemStatus,
    LifecycleItemType,
    LikelihoodTerm,
    Materiality,
)
from adversary_pursuit.core.command_completion import command_completions
from adversary_pursuit.core.structured_analysis import (
    StructuredAnalysisWorkbench,
    StructuredTechnique,
)
from adversary_pursuit.core.workspace import WorkspaceManager
from adversary_pursuit.core.workspace_admin import export_workspace, merge_workspaces
from adversary_pursuit.core.workspace_migrations import (
    CURRENT_WORKSPACE_SCHEMA_VERSION,
    get_workspace_schema_version,
)


def _workspace(tmp_path) -> WorkspaceManager:
    manager = WorkspaceManager(tmp_path)
    manager.create("case")
    manager.switch("case")
    return manager


def test_fresh_workspace_is_stamped_at_current_schema(tmp_path):
    manager = _workspace(tmp_path)
    assert get_workspace_schema_version(manager._engine) == CURRENT_WORKSPACE_SCHEMA_VERSION

    tables = set(inspect(manager._engine).get_table_names())
    assert {
        "workspace_schema_version",
        "evidence_sources",
        "evidence_observations",
        "evidence_observation_dispositions",
        "investigation_questions",
        "analytic_assertions",
        "analytic_hypotheses",
        "analytic_evidence_links",
        "analytic_method_runs",
        "analytic_investigations",
        "analytic_lifecycle_items",
        "analytic_confidence_assessments",
        "likelihood_assessments",
        "analytic_contradictions",
    }.issubset(tables)
    status = manager.get_workspace_schema_status()
    assert status["valid"] is True
    assert status["requires_migration"] is False
    assert status["sqlite_integrity"] == "ok"


def test_legacy_workspace_migrates_with_backup_and_observation_backfill(tmp_path):
    db_path = tmp_path / "legacy.db"
    connection = sqlite3.connect(db_path)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute(
        """
        CREATE TABLE stix_objects (
            id VARCHAR PRIMARY KEY,
            type VARCHAR NOT NULL,
            value VARCHAR,
            json_blob JSON NOT NULL,
            created_at DATETIME NOT NULL
        )
        """
    )
    blob = {
        "type": "domain-name",
        "id": "domain-name--legacy",
        "value": "legacy.example",
        "x_ap_source_module": "osint/legacy",
        "x_ap_source_url": "https://user:secret@example.test/v1?q=token",
        "x_ap_api_version": "v1",
        "x_ap_fetched_at": "2025-01-01T00:00:00Z",
    }
    connection.execute(
        "INSERT INTO stix_objects VALUES (?, ?, ?, ?, ?)",
        (
            blob["id"],
            blob["type"],
            blob["value"],
            json.dumps(blob),
            "2025-01-01 00:00:00",
        ),
    )
    connection.commit()

    manager = WorkspaceManager(tmp_path)
    manager.switch("legacy")
    connection.close()

    backup_path = tmp_path / "legacy.db.pre-v1-backup"
    assert backup_path.is_file()
    backup = sqlite3.connect(backup_path)
    assert backup.execute("SELECT value FROM stix_objects").fetchone() == ("legacy.example",)
    backup.close()
    assert get_workspace_schema_version(manager._engine) == CURRENT_WORKSPACE_SCHEMA_VERSION
    observations = manager.get_observations(entity_ref="domain-name--legacy")
    assert len(observations) == 1
    assert observations[0]["source_module"] == "osint/legacy"
    assert observations[0]["source_endpoint"] == "https://example.test/v1"
    assert observations[0]["fetched_at"] == "2025-01-01T00:00:00Z"


def test_schema_v3_migrates_analytic_records_and_predictions_without_rewriting_source(
    tmp_path,
):
    manager = WorkspaceManager(tmp_path)
    manager.create("v3")
    connection = sqlite3.connect(tmp_path / "v3.db")
    connection.execute("DROP TABLE analytic_lifecycle_items")
    connection.execute("DROP TABLE analytic_investigations")
    connection.execute("UPDATE workspace_schema_version SET version = 3 WHERE id = 1")
    connection.execute(
        """
        INSERT INTO investigation_questions
            (id, text, status, created_by, created_at, closed_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            "question-v3",
            "What would falsify the leading explanation?",
            "open",
            "human",
            "2026-08-01 00:00:00",
            None,
        ),
    )
    prediction_payload = {
        "schema_version": 2,
        "predictions": [
            {
                "prediction_id": "prediction-v3",
                "text": "A second independently sourced certificate will appear.",
                "status": "pending",
                "slot": "infrastructure",
                "expected_evidence": {"type": "x509-certificate"},
            }
        ],
    }
    connection.execute(
        """
        INSERT INTO score_events
            (action, points, indicator, module_run_id, timestamp)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            "_predictions_log",
            0,
            json.dumps(prediction_payload),
            None,
            "2026-08-01 00:01:00",
        ),
    )
    connection.commit()
    connection.close()

    manager.switch("v3")

    assert (tmp_path / "v3.db.pre-v3-backup").is_file()
    assert get_workspace_schema_version(manager._engine) == CURRENT_WORKSPACE_SCHEMA_VERSION
    snapshot = AnalyticLedger(manager).snapshot()
    assert snapshot["investigations"][0]["primary_question_id"] == "question-v3"
    linked = {
        (item["item_type"], item["record_kind"], item["record_id"])
        for item in snapshot["lifecycle_items"]
    }
    assert ("question", "question", "question-v3") in linked
    assert ("prediction", "legacy_prediction", "prediction-v3") in linked
    with manager.get_session() as session:
        original = session.execute(
            text("SELECT indicator FROM score_events WHERE action = '_predictions_log'")
        ).scalar_one()
    assert json.loads(original) == prediction_payload


def test_schema_v2_workspace_uses_backup_first_complete_forward_path(tmp_path):
    manager = WorkspaceManager(tmp_path)
    manager.create("v2")
    connection = sqlite3.connect(tmp_path / "v2.db")
    connection.execute("UPDATE workspace_schema_version SET version = 2 WHERE id = 1")
    connection.commit()
    connection.close()

    manager.switch("v2")

    backup_path = tmp_path / "v2.db.pre-v2-backup"
    assert backup_path.is_file()
    backup = sqlite3.connect(backup_path)
    assert backup.execute(
        "SELECT version FROM workspace_schema_version WHERE id = 1"
    ).fetchone() == (2,)
    backup.close()
    assert get_workspace_schema_version(manager._engine) == CURRENT_WORKSPACE_SCHEMA_VERSION
    assert manager.get_workspace_schema_status()["valid"] is True


def test_duplicate_entity_preserves_every_observation_and_source(tmp_path):
    manager = _workspace(tmp_path)
    first_count = manager.store_stix_objects(
        [{"type": "ipv4-addr", "value": "198.51.100.42"}],
        module_name="osint/source-a",
        target="198.51.100.42",
        source_url="https://api-a.example/v1/lookup?key=secret",
        fetched_at="2026-01-01T00:00:00Z",
    )
    second_count = manager.store_stix_objects(
        [{"type": "ipv4-addr", "value": "198.51.100.42"}],
        module_name="osint/source-b",
        target="198.51.100.42",
        source_url="https://api-b.example/v2/lookup?token=secret",
        fetched_at="2026-01-02T00:00:00Z",
    )

    assert first_count == second_count == 1
    entities = manager.get_stix_objects()
    assert len(entities) == 1
    observations = manager.get_observations(entity_ref=entities[0]["id"])
    assert len(observations) == 2
    assert {row["source_module"] for row in observations} == {
        "osint/source-a",
        "osint/source-b",
    }
    assert {row["source_endpoint"] for row in observations} == {
        "https://api-a.example/v1/lookup",
        "https://api-b.example/v2/lookup",
    }
    assert entities[0]["x_ap_source_url"] == "https://api-a.example/v1/lookup"
    assert "secret" not in json.dumps(entities)


def test_observation_corrections_are_append_only_and_preserve_source_dependence(tmp_path):
    manager = _workspace(tmp_path)
    for fetched_at in ("2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z"):
        manager.store_stix_objects(
            [{"type": "domain-name", "value": "correction.example"}],
            module_name="osint/reseller-feed",
            target="correction.example",
            fetched_at=fetched_at,
            source_dependence_group="upstream-provider-a",
            transformation_id="normalizer-v2",
            raw_artifact_ref="artifact://sha256/example",
        )
    observations = manager.get_observations()
    original, replacement = observations

    disposition_id = manager.record_observation_disposition(
        original["id"],
        action="corrected",
        replacement_observation_id=replacement["id"],
        reason="The provider corrected its earlier timestamp.",
    )

    assert len(manager.get_observations()) == 2
    assert replacement["source_dependence_group"] == "upstream-provider-a"
    assert replacement["transformation_id"] == "normalizer-v2"
    assert replacement["raw_artifact_ref"] == "artifact://sha256/example"
    dispositions = manager.get_observation_dispositions(original["id"])
    assert dispositions == [
        {
            "id": disposition_id,
            "observation_id": original["id"],
            "action": "corrected",
            "replacement_observation_id": replacement["id"],
            "reason": "The provider corrected its earlier timestamp.",
            "recorded_by": "human",
            "created_at": dispositions[0]["created_at"],
        }
    ]


def test_failed_future_schema_switch_preserves_active_workspace(tmp_path):
    manager = _workspace(tmp_path)
    manager.create("future")
    connection = sqlite3.connect(tmp_path / "future.db")
    connection.execute("UPDATE workspace_schema_version SET version = 999 WHERE id = 1")
    connection.commit()
    connection.close()

    with pytest.raises(RuntimeError, match="newer than this Pivotglass build"):
        manager.switch("future")

    assert manager.active == "case"
    assert manager.get_workspace_stats()["total_indicators"] == 0


def test_malformed_source_endpoint_is_omitted_and_raw_paths_are_rejected(tmp_path):
    manager = _workspace(tmp_path)
    manager.store_stix_objects(
        [{"type": "domain-name", "value": "malformed.example"}],
        module_name="osint/source",
        target="malformed.example",
        source_url="https://[malformed?secret=key",
    )
    entity = manager.get_stix_objects()[0]
    assert "x_ap_source_url" not in entity
    assert manager.get_observations()[0]["source_endpoint"] is None

    with pytest.raises(ValueError, match="opaque artifact"):
        manager.store_stix_objects(
            [{"type": "domain-name", "value": "path.example"}],
            module_name="osint/source",
            target="path.example",
            raw_artifact_ref="/Users/analyst/private/provider-response.json",
        )


def test_analysis_command_is_shared_with_local_repl_and_completion(tmp_path):
    manager = _workspace(tmp_path)

    created = execute_analysis_command(
        ("question", "Which", "hypothesis", "best", "explains", "the", "activity?"),
        manager,
    )
    question_id = created["data"]["question_id"]
    hypothesis = execute_analysis_command(
        ("hypothesis", question_id, "The", "activity", "is", "opportunistic."),
        manager,
    )
    hypothesis_id = hypothesis["data"]["hypothesis_id"]

    verb = parse_repl_verb(f"analysis accept {hypothesis_id}")
    assert verb is not None
    response = dispatch_repl_verb(verb, None, None, manager)
    assert '"status": "retained"' in response
    completions = command_completions("analysis m")
    assert "analysis methods" in completions
    assert "analysis method start " in completions

    snapshot = execute_analysis_command(("show",), manager)["data"]
    assert snapshot["questions"][0]["text"] == "Which hypothesis best explains the activity?"
    assert snapshot["hypotheses"][0]["status"] == "retained"


def test_analysis_commands_cover_lifecycle_contradictions_and_sat_runs(tmp_path):
    manager = _workspace(tmp_path)
    question_id = execute_analysis_command(
        ("question", "Which", "operator", "controls", "the", "infrastructure?"),
        manager,
    )["data"]["question_id"]
    assumption_id = execute_analysis_command(
        ("assumption", "Certificate", "reuse", "implies", "common", "control."),
        manager,
    )["data"]["assertion_id"]
    judgment_id = execute_analysis_command(
        ("assertion", "judgment", "The", "hosting", "is", "shared."),
        manager,
    )["data"]["assertion_id"]
    prediction_id = execute_analysis_command(
        ("prediction", "A", "second", "certificate", "match", "will", "appear."),
        manager,
    )["data"]["item_id"]
    execute_analysis_command(
        ("signpost", "An", "independent", "provider", "confirms", "the", "match."),
        manager,
    )
    contradiction_id = execute_analysis_command(
        (
            "contradiction",
            "assertion",
            assumption_id,
            "assertion",
            judgment_id,
            "Dedicated",
            "control",
            "conflicts",
            "with",
            "shared",
            "hosting",
            "|",
            "Obtain",
            "allocation",
            "records.",
        ),
        manager,
    )["data"]["contradiction_id"]
    execute_analysis_command(
        ("resolve", contradiction_id, "Provider", "records", "show", "shared", "tenancy."),
        manager,
    )
    run_id = execute_analysis_command(
        (
            "method",
            "start",
            question_id,
            "key_assumptions_check",
            json.dumps({"assumptions": [assumption_id]}),
        ),
        manager,
    )["data"]["run_id"]
    execute_analysis_command(
        (
            "method",
            "complete",
            run_id,
            json.dumps(
                {
                    "challenged_assumptions": [assumption_id],
                    "implications": ["Seek independent tenancy evidence."],
                }
            ),
        ),
        manager,
    )
    execute_analysis_command(("method", "revise", run_id), manager)
    execute_analysis_command(("item", prediction_id, "satisfied", "revised"), manager)

    lifecycle = execute_analysis_command(("lifecycle",), manager)["data"]
    assert len(lifecycle["investigations"]) == 1
    assert {item["item_type"] for item in lifecycle["items"]}.issuperset(
        {"question", "assumption", "assertion", "prediction", "signpost", "method_run"}
    )
    snapshot = execute_analysis_command(("show",), manager)["data"]
    assert snapshot["contradictions"][0]["status"] == "resolved"
    method_item = next(item for item in lifecycle["items"] if item["record_id"] == run_id)
    assert method_item["analyst_disposition"] == "revised"


def test_portable_export_and_merge_preserve_complete_analytic_record(tmp_path):
    manager = WorkspaceManager(tmp_path)
    manager.create("source")
    manager.create("destination")
    manager.switch("source")
    source_ledger = AnalyticLedger(manager)
    question_id = source_ledger.create_question("What explains the shared infrastructure?")
    source_ledger.create_hypothesis(question_id, "A common operator controls it.")
    manager.store_stix_objects(
        [{"type": "domain-name", "value": "source.example"}],
        module_name="osint/source",
        target="source.example",
    )

    payload = export_workspace(manager, "source")
    assert payload["format"] == "pivotglass-workspace-v4"
    assert payload["schema_version"] == CURRENT_WORKSPACE_SCHEMA_VERSION
    assert payload["tables"]["investigation_questions"][0]["id"] == question_id
    assert payload["tables"]["analytic_investigations"][0]["primary_question_id"] == (question_id)
    assert payload["tables"]["evidence_observations"][0]["observed_blob"]["value"] == (
        "source.example"
    )

    manager.switch("destination")
    manager.store_stix_objects(
        [{"type": "domain-name", "value": "destination.example"}],
        module_name="osint/destination",
        target="destination.example",
    )
    counts = merge_workspaces(manager, "source", "destination")
    assert counts["investigation_questions"] == 1
    assert counts["analytic_investigations"] == 1
    assert counts["analytic_lifecycle_items"] == 2
    assert counts["evidence_observations"] == 1

    manager.switch("destination")
    merged = AnalyticLedger(manager).snapshot()
    assert merged["questions"][0]["id"] == question_id
    source_observation = manager.get_observations(source_module="osint/source")[0]
    module_runs = manager.get_module_runs()
    assert source_observation["module_run_id"] == 2
    assert module_runs[1]["module_name"] == "osint/source"


def test_analytic_ledger_keeps_evidence_judgment_confidence_and_likelihood_distinct(tmp_path):
    manager = _workspace(tmp_path)
    manager.store_stix_objects(
        [{"type": "domain-name", "value": "example.test"}],
        module_name="osint/source",
        target="example.test",
        fetched_at="2026-01-01T00:00:00Z",
    )
    observation_id = manager.get_observations()[0]["id"]
    ledger = AnalyticLedger(manager)

    question_id = ledger.create_question("Who operates the observed infrastructure?")
    hypothesis_id = ledger.create_hypothesis(
        question_id,
        "The infrastructure is operated by actor A.",
        author_kind=AuthorKind.MODEL,
    )
    assertion_id = ledger.create_assertion(
        "The domain reused a certificate associated with actor A.",
        assertion_type=AssertionType.INFERRED,
        method="certificate-pivot",
    )
    ledger.link_evidence(
        source_kind="observation",
        source_id=observation_id,
        target_kind="assertion",
        target_id=assertion_id,
        stance=EvidenceStance.SUPPORTS,
        rationale="The certificate fingerprint is present in the collected record.",
    )
    ledger.link_evidence(
        source_kind="assertion",
        source_id=assertion_id,
        target_kind="hypothesis",
        target_id=hypothesis_id,
        stance=EvidenceStance.SUPPORTS,
        rationale="Certificate reuse is consistent with the candidate operator.",
    )
    with pytest.raises(ValueError, match="missing required fields"):
        ledger.assess_confidence(
            target_kind="hypothesis",
            target_id=hypothesis_id,
            level=ConfidenceLevel.LOW,
            rationale="A rationale alone does not expose the confidence basis.",
            factors={"source_quality": "one API source"},
        )
    ledger.assess_confidence(
        target_kind="hypothesis",
        target_id=hypothesis_id,
        level=ConfidenceLevel.LOW,
        rationale="The evidence is single-source and infrastructure may be shared.",
        factors={
            "source_quality": "one API source with direct access",
            "source_independence": "one dependence group",
            "corroboration": "not corroborated",
            "assumptions": ["certificate reuse implies control"],
            "knowledge_gaps": ["hosting allocation unknown"],
            "analytic_rigor": "alternative explanation retained",
        },
    )
    ledger.assess_likelihood(
        target_kind="hypothesis",
        target_id=hypothesis_id,
        term=LikelihoodTerm.UNLIKELY,
        rationale="The candidate explanation currently fits only a minority of observations.",
    )

    snapshot = ledger.snapshot()
    assert snapshot["hypotheses"][0]["status"] == HypothesisStatus.PROPOSED.value
    assert snapshot["confidence"][0]["level"] == ConfidenceLevel.LOW.value
    assert "term" not in snapshot["confidence"][0]
    assert snapshot["likelihood"][0]["term"] == LikelihoodTerm.UNLIKELY.value
    assert snapshot["likelihood"][0]["probability_min"] == 0.20
    assert "level" not in snapshot["likelihood"][0]

    with pytest.raises(ValueError, match="Only an explicit human action"):
        ledger.set_hypothesis_status(
            hypothesis_id,
            HypothesisStatus.RETAINED,
            decided_by=AuthorKind.MODEL,
        )
    ledger.set_hypothesis_status(hypothesis_id, HypothesisStatus.RETAINED)
    assert ledger.snapshot()["hypotheses"][0]["status"] == "retained"
    hypothesis_link = next(
        item for item in ledger.snapshot()["lifecycle_items"] if item["record_id"] == hypothesis_id
    )
    assert hypothesis_link["status"] == LifecycleItemStatus.SATISFIED.value


def test_scientific_lifecycle_preserves_model_proposals_for_human_disposition(tmp_path):
    ledger = AnalyticLedger(_workspace(tmp_path))
    investigation_id = ledger.create_investigation(
        "Certificate reuse",
        purpose="Determine whether certificate reuse links the observed infrastructure.",
        scope="Observed domains and certificates collected in this workspace.",
    )
    question_id = ledger.create_question(
        "Does certificate reuse indicate common control?",
        investigation_id=investigation_id,
    )
    prediction_id = ledger.add_lifecycle_item(
        investigation_id,
        LifecycleItemType.PREDICTION,
        "A second independently sourced certificate match will appear.",
        criteria={"minimum_independent_sources": 2},
        author_kind=AuthorKind.MODEL,
    )
    ledger.add_lifecycle_item(
        investigation_id,
        LifecycleItemType.STOP_CONDITION,
        "Stop collection after two independent providers agree or the timebox expires.",
    )

    snapshot = ledger.snapshot()
    assert snapshot["investigations"][0]["primary_question_id"] == question_id
    prediction = next(item for item in snapshot["lifecycle_items"] if item["id"] == prediction_id)
    assert prediction["analyst_disposition"] == AnalystDisposition.PENDING.value
    with pytest.raises(ValueError, match="Only an explicit human action"):
        ledger.update_lifecycle_item(
            prediction_id,
            disposition=AnalystDisposition.ACCEPTED,
            decided_by=AuthorKind.MODEL,
        )
    ledger.update_lifecycle_item(
        prediction_id,
        disposition=AnalystDisposition.REVISED,
        status=LifecycleItemStatus.SATISFIED,
    )
    ledger.set_investigation_status(investigation_id, InvestigationStatus.ANALYZING)
    updated = ledger.snapshot()
    assert updated["investigations"][0]["status"] == "analyzing"
    prediction = next(item for item in updated["lifecycle_items"] if item["id"] == prediction_id)
    assert prediction["analyst_disposition"] == "revised"
    assert prediction["status"] == "satisfied"


def test_contradiction_is_persistent_and_requires_resolution_information(tmp_path):
    ledger = AnalyticLedger(_workspace(tmp_path))
    left_id = ledger.create_assertion(
        "The IP was dedicated infrastructure.",
        assertion_type=AssertionType.JUDGMENT,
    )
    right_id = ledger.create_assertion(
        "The IP was shared hosting.",
        assertion_type=AssertionType.JUDGMENT,
    )
    contradiction_id = ledger.record_contradiction(
        left_kind="assertion",
        left_id=left_id,
        right_kind="assertion",
        right_id=right_id,
        summary="The infrastructure tenancy assessments conflict.",
        materiality=Materiality.HIGH,
        resolution_required="Obtain contemporaneous hosting allocation evidence.",
    )
    contradiction = ledger.snapshot()["contradictions"][0]
    assert contradiction["status"] == "unresolved"
    assert contradiction["materiality"] == "high"

    ledger.resolve_contradiction(
        contradiction_id,
        "Provider records confirm shared tenancy during the observed interval.",
        status=ContradictionStatus.RESOLVED,
    )
    resolved = ledger.snapshot()["contradictions"][0]
    assert resolved["status"] == "resolved"
    assert resolved["resolved_at"] is not None


def test_analysis_commands_record_structured_claims_and_explicit_materiality(tmp_path):
    manager = _workspace(tmp_path)
    left = execute_analysis_command(
        (
            "claim",
            "judgment",
            "ipv4-addr--example",
            "active_window_days",
            '{"min":1,"max":3,"unit":"days"}',
            "|",
            "The observed activity lasted one to three days.",
        ),
        manager,
    )["data"]["assertion_id"]
    right = execute_analysis_command(
        (
            "claim",
            "judgment",
            "ipv4-addr--example",
            "active_window_days",
            '{"min":7,"max":9,"unit":"days"}',
            "|",
            "The observed activity lasted seven to nine days.",
        ),
        manager,
    )["data"]["assertion_id"]
    result = execute_analysis_command(
        (
            "contradiction",
            "assertion",
            left,
            "assertion",
            right,
            "The recorded intervals do not overlap.",
            "|",
            "Obtain contemporaneous source-backed timing.",
            "|",
            "medium",
        ),
        manager,
    )

    assertions = AnalyticLedger(manager).snapshot()["assertions"]
    assert assertions[0]["object_value"] == '{"max":3,"min":1,"unit":"days"}'
    assert result["data"]["materiality"] == "medium"
    assert AnalyticLedger(manager).snapshot()["contradictions"][0]["materiality"] == "medium"


def test_workspace_clear_removes_epistemic_data_but_preserves_schema_receipt(tmp_path):
    manager = _workspace(tmp_path)
    ledger = AnalyticLedger(manager)
    ledger.create_question("What changed?")
    manager.store_stix_objects(
        [{"type": "domain-name", "value": "clear.example"}],
        module_name="osint/source",
        target="clear.example",
    )

    deleted = manager.clear()
    assert deleted["investigation_questions"] == 1
    assert deleted["analytic_investigations"] == 1
    assert deleted["analytic_lifecycle_items"] == 1
    assert deleted["evidence_observations"] == 1
    assert deleted["evidence_sources"] == 1
    assert all(count == 0 for count in manager.get_workspace_table_counts().values())
    assert get_workspace_schema_version(manager._engine) == CURRENT_WORKSPACE_SCHEMA_VERSION


def test_structured_analysis_run_is_versioned_bounded_and_human_dispositioned(tmp_path):
    manager = _workspace(tmp_path)
    ledger = AnalyticLedger(manager)
    question_id = ledger.create_question("Which hypothesis best explains the infrastructure?")
    hypothesis_a = ledger.create_hypothesis(question_id, "Actor A operates it.")
    hypothesis_b = ledger.create_hypothesis(question_id, "A reseller operates it.")
    workbench = StructuredAnalysisWorkbench(manager)

    with pytest.raises(ValueError, match="missing required fields"):
        workbench.start(
            question_id,
            StructuredTechnique.COMPETING_HYPOTHESES,
            {"hypothesis_ids": [hypothesis_a, hypothesis_b]},
        )

    run_id = workbench.start(
        question_id,
        StructuredTechnique.COMPETING_HYPOTHESES,
        {
            "hypothesis_ids": [hypothesis_a, hypothesis_b],
            "evidence_ids": [],
        },
        created_by=AuthorKind.MODEL,
    )
    with pytest.raises(ValueError, match="missing required fields"):
        workbench.complete(run_id, {"matrix": []})

    workbench.complete(
        run_id,
        {
            "matrix": [],
            "least_inconsistent": hypothesis_b,
            "sensitivity": "No diagnostic evidence has been collected yet.",
        },
    )
    run = workbench.list_runs(question_id=question_id)[0]
    assert run["technique"] == "analysis_of_competing_hypotheses"
    assert run["technique_version"] == "1.0"
    assert run["analyst_disposition"] == "pending"
    method_link = next(
        item for item in ledger.snapshot()["lifecycle_items"] if item["record_id"] == run_id
    )
    assert method_link["status"] == LifecycleItemStatus.SATISFIED.value
    assert method_link["analyst_disposition"] == AnalystDisposition.PENDING.value

    with pytest.raises(ValueError, match="Only an explicit human action"):
        workbench.disposition(
            run_id,
            AnalystDisposition.ACCEPTED,
            decided_by=AuthorKind.MODEL,
        )
    workbench.disposition(run_id, AnalystDisposition.REVISED)
    assert workbench.list_runs()[0]["analyst_disposition"] == "revised"
    method_link = next(
        item for item in ledger.snapshot()["lifecycle_items"] if item["record_id"] == run_id
    )
    assert method_link["analyst_disposition"] == "revised"
