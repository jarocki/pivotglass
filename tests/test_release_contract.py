"""Tests for the preventive feature/version release contract."""

from scripts.check_release_contract import (
    current_versions,
    is_feature_bearing_path,
    parse_semver,
    validate,
)


def test_release_version_surfaces_and_operator_docs_are_consistent() -> None:
    versions = current_versions()
    assert set(versions.values()) == {"0.9.4"}
    assert validate() == []


def test_semver_comparison_preserves_release_order() -> None:
    assert parse_semver("0.9.4") > parse_semver("0.9.3")


def test_feature_paths_cover_shipped_behavior_not_documentation() -> None:
    assert is_feature_bearing_path("src/adversary_pursuit/core/workspace.py")
    assert is_feature_bearing_path("web/app/page.tsx")
    assert is_feature_bearing_path("scripts/validate_synapse_contract.py")
    assert not is_feature_bearing_path("docs/USER_GUIDE.md")
    assert not is_feature_bearing_path("tests/test_workspace.py")
