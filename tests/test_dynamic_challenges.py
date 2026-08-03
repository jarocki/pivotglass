"""Hunt-specific, evidence-grounded challenge and badge behavior."""

import sqlite3

from adversary_pursuit.core.workspace import WorkspaceManager
from adversary_pursuit.gamification.challenges import ChallengeManager
from adversary_pursuit.gamification.dynamic_challenges import (
    generate_hunt_challenges,
    refresh_hunt_challenges,
)


def _workspace(tmp_path):
    manager = WorkspaceManager(tmp_path)
    manager.create("case")
    manager.switch("case")
    return manager


def _report(manager, module, dependence):
    manager.store_stix_objects(
        [
            {
                "type": "domain-name",
                "value": "bad.example",
                "x_tf_malware": "ExampleRAT",
            }
        ],
        module_name=module,
        target="bad.example",
        source_dependence_group=dependence,
    )


def test_dynamic_challenges_are_target_specific_stable_and_have_artwork(tmp_path):
    manager = _workspace(tmp_path)
    _report(manager, "osint/threatfox", "abuse-ch")

    first = generate_hunt_challenges(manager, "bad.example")
    second = generate_hunt_challenges(manager, "bad.example")

    assert [item["id"] for item in first] == [item["id"] for item in second]
    assert all(item["subject_value"] == "bad.example" for item in first)
    assert all(item["badge_id"] and item["badge_artwork"] and item["badge_glyph"] for item in first)
    malware = next(item for item in first if item["badge_artwork"] == "malware-signature")
    assert malware["evidence_basis"][0]["source"] == "osint/threatfox"
    assert malware["evidence_basis"][0]["field"] == "x_tf_malware"


def test_independent_source_challenge_rejects_dependent_duplicates(tmp_path):
    manager = _workspace(tmp_path)
    _report(manager, "osint/threatfox", "shared-feed")
    _report(manager, "osint/urlhaus", "shared-feed")

    records = refresh_hunt_challenges(manager, "bad.example")
    witness = next(item for item in records if item["name"] == "Independent Witnesses")
    assert witness["progress_current"] == 1
    assert witness["status"] == "active"


def test_completion_persists_and_awards_badge_exactly_once(tmp_path):
    manager = _workspace(tmp_path)
    _report(manager, "osint/threatfox", "abuse-ch")
    _report(manager, "osint/otx", "alienvault")

    records = refresh_hunt_challenges(manager, "bad.example")
    witness = next(item for item in records if item["name"] == "Independent Witnesses")
    assert witness["status"] == "completed"
    awards = manager.get_awarded_badges()
    matching = [item for item in awards if item["challenge_id"] == witness["id"]]
    assert len(matching) == 1
    assert matching[0]["badge_artwork"] == "crossbeam"

    restarted = ChallengeManager(manager)
    restarted.refresh_for_hunt("bad.example")
    matching = [
        item for item in manager.get_awarded_badges() if item["challenge_id"] == witness["id"]
    ]
    assert len(matching) == 1


def test_challenge_command_list_combines_starters_and_hunt_context(tmp_path):
    manager = _workspace(tmp_path)
    _report(manager, "osint/threatfox", "abuse-ch")
    records = ChallengeManager(manager).refresh_for_hunt("bad.example")
    assert len(records) > 5
    assert all(item["badge"]["badge_artwork"] for item in records)
    domain_hunter = next(item for item in records if item["id"] == "ch-002")
    assert (domain_hunter["progress_current"], domain_hunter["progress_target"]) == (1, 5)


def test_schema_v2_migrates_to_persisted_challenges_with_backup(tmp_path):
    manager = _workspace(tmp_path)
    manager._engine.dispose()
    database = tmp_path / "case.db"
    with sqlite3.connect(database) as connection:
        connection.execute("DROP TABLE hunt_challenges")
        connection.execute("UPDATE workspace_schema_version SET version = 2 WHERE id = 1")
        connection.commit()

    reopened = WorkspaceManager(tmp_path)
    reopened.switch("case")
    assert "hunt_challenges" in reopened.get_workspace_table_counts()
    assert (tmp_path / "case.db.pre-v2-backup").exists()
