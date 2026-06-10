"""Tests for dossier library helpers in export.py.

Covers DEC-M9-LIBRARY-LOCATION-001 (default/override path),
DEC-M9-LIBRARY-OPTIN-001 (AP_DOSSIER_PUBLISH gate),
DEC-M9-PRIVACY-001 (no redaction; user consent at env-var boundary),
and filesystem permission 0o700 on the library directory.

@decision DEC-M9-TEST-LIBRARY-001
@title Library test suite verifies opt-in gate, directory permissions, CRUD operations
@status accepted
@rationale Tests verify the complete consent boundary: publish without env var raises
    RuntimeError; with env var the file is written, dir is 0o700 (or chmod'd if
    pre-existing); list_library and load_from_library work unconditionally; invalid
    actor_identifiers are rejected at both publish and load boundaries.
"""

from __future__ import annotations

import stat
from pathlib import Path

import pytest

from adversary_pursuit.dossier.export import (
    library_publish_enabled,
    library_root,
    list_library,
    load_from_library,
    publish_to_library,
)

# ---------------------------------------------------------------------------
# library_root — default and AP_DOSSIER_LIBRARY override
# ---------------------------------------------------------------------------


class TestLibraryRoot:
    """library_root() returns correct path per DEC-M9-LIBRARY-LOCATION-001."""

    def test_default_root_is_home_ap_dossier_library(self, monkeypatch):
        monkeypatch.delenv("AP_DOSSIER_LIBRARY", raising=False)
        root = library_root()
        assert root == Path.home() / ".ap" / "dossier_library"

    def test_env_override_honored(self, tmp_path: Path, monkeypatch):
        override = str(tmp_path / "custom_library")
        monkeypatch.setenv("AP_DOSSIER_LIBRARY", override)
        assert library_root() == Path(override)

    def test_env_override_empty_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv("AP_DOSSIER_LIBRARY", "")
        root = library_root()
        assert root == Path.home() / ".ap" / "dossier_library"


# ---------------------------------------------------------------------------
# library_publish_enabled — opt-in gate (DEC-M9-LIBRARY-OPTIN-001)
# ---------------------------------------------------------------------------


class TestLibraryPublishEnabled:
    def test_unset_returns_false(self, monkeypatch):
        monkeypatch.delenv("AP_DOSSIER_PUBLISH", raising=False)
        assert library_publish_enabled() is False

    def test_on_lowercase_returns_true(self, monkeypatch):
        monkeypatch.setenv("AP_DOSSIER_PUBLISH", "on")
        assert library_publish_enabled() is True

    def test_on_uppercase_returns_true(self, monkeypatch):
        monkeypatch.setenv("AP_DOSSIER_PUBLISH", "ON")
        assert library_publish_enabled() is True

    def test_off_returns_false(self, monkeypatch):
        monkeypatch.setenv("AP_DOSSIER_PUBLISH", "off")
        assert library_publish_enabled() is False

    def test_yes_returns_false(self, monkeypatch):
        monkeypatch.setenv("AP_DOSSIER_PUBLISH", "yes")
        assert library_publish_enabled() is False

    def test_true_returns_false(self, monkeypatch):
        monkeypatch.setenv("AP_DOSSIER_PUBLISH", "true")
        assert library_publish_enabled() is False


# ---------------------------------------------------------------------------
# publish_to_library — consent gate, file write, permissions
# ---------------------------------------------------------------------------


class TestPublishToLibrary:
    """publish_to_library requires AP_DOSSIER_PUBLISH=on (DEC-M9-LIBRARY-OPTIN-001)."""

    def test_raises_runtime_error_without_publish_env(self, tmp_path: Path, monkeypatch):
        monkeypatch.delenv("AP_DOSSIER_PUBLISH", raising=False)
        monkeypatch.setenv("AP_DOSSIER_LIBRARY", str(tmp_path / "lib"))
        with pytest.raises(RuntimeError, match="AP_DOSSIER_PUBLISH"):
            publish_to_library('{"type":"bundle"}', "test-actor")

    def test_raises_runtime_error_with_off(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("AP_DOSSIER_PUBLISH", "off")
        monkeypatch.setenv("AP_DOSSIER_LIBRARY", str(tmp_path / "lib"))
        with pytest.raises(RuntimeError):
            publish_to_library('{"type":"bundle"}', "test-actor")

    def test_writes_file_with_publish_on(self, tmp_path: Path, monkeypatch):
        lib_dir = tmp_path / "lib"
        monkeypatch.setenv("AP_DOSSIER_PUBLISH", "on")
        monkeypatch.setenv("AP_DOSSIER_LIBRARY", str(lib_dir))
        content = '{"type":"bundle","spec_version":"2.1","objects":[]}'
        dest = publish_to_library(content, "fancy-bear")
        assert dest.exists()
        assert dest.read_text(encoding="utf-8") == content

    def test_returns_path_to_written_file(self, tmp_path: Path, monkeypatch):
        lib_dir = tmp_path / "lib"
        monkeypatch.setenv("AP_DOSSIER_PUBLISH", "on")
        monkeypatch.setenv("AP_DOSSIER_LIBRARY", str(lib_dir))
        dest = publish_to_library('{"type":"bundle"}', "apt28")
        assert dest.name == "apt28.json"
        assert dest.parent == lib_dir

    def test_directory_created_with_0o700(self, tmp_path: Path, monkeypatch):
        lib_dir = tmp_path / "lib_perms"
        monkeypatch.setenv("AP_DOSSIER_PUBLISH", "on")
        monkeypatch.setenv("AP_DOSSIER_LIBRARY", str(lib_dir))
        publish_to_library('{"type":"bundle"}', "perms-test")
        mode = stat.S_IMODE(lib_dir.stat().st_mode)
        assert mode == 0o700, f"Expected 0o700 directory permissions, got {oct(mode)}"

    def test_preexisting_0o755_dir_is_chmod_to_0o700(self, tmp_path: Path, monkeypatch):
        lib_dir = tmp_path / "existing_lib"
        lib_dir.mkdir(mode=0o755)
        monkeypatch.setenv("AP_DOSSIER_PUBLISH", "on")
        monkeypatch.setenv("AP_DOSSIER_LIBRARY", str(lib_dir))
        publish_to_library('{"type":"bundle"}', "chmod-test")
        mode = stat.S_IMODE(lib_dir.stat().st_mode)
        assert mode == 0o700, f"Expected dir chmod'd to 0o700, got {oct(mode)}"

    def test_invalid_actor_identifier_raises_value_error(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("AP_DOSSIER_PUBLISH", "on")
        monkeypatch.setenv("AP_DOSSIER_LIBRARY", str(tmp_path / "lib"))
        with pytest.raises(ValueError):
            publish_to_library('{"type":"bundle"}', "../../etc/passwd")

    def test_overwrite_existing_file(self, tmp_path: Path, monkeypatch):
        lib_dir = tmp_path / "lib"
        monkeypatch.setenv("AP_DOSSIER_PUBLISH", "on")
        monkeypatch.setenv("AP_DOSSIER_LIBRARY", str(lib_dir))
        publish_to_library('{"version":"1"}', "overwrite-test")
        publish_to_library('{"version":"2"}', "overwrite-test")
        dest = lib_dir / "overwrite-test.json"
        assert dest.read_text(encoding="utf-8") == '{"version":"2"}'


# ---------------------------------------------------------------------------
# list_library — unconditional reads
# ---------------------------------------------------------------------------


class TestListLibrary:
    """list_library() is unconditional (no opt-in required)."""

    def test_empty_when_dir_not_exists(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("AP_DOSSIER_LIBRARY", str(tmp_path / "nonexistent"))
        assert list_library() == []

    def test_lists_json_files(self, tmp_path: Path, monkeypatch):
        lib_dir = tmp_path / "lib"
        lib_dir.mkdir()
        (lib_dir / "actor1.json").write_text("{}", encoding="utf-8")
        (lib_dir / "actor2.json").write_text("{}", encoding="utf-8")
        monkeypatch.setenv("AP_DOSSIER_LIBRARY", str(lib_dir))
        files = list_library()
        names = {f.name for f in files}
        assert names == {"actor1.json", "actor2.json"}

    def test_returns_sorted_paths(self, tmp_path: Path, monkeypatch):
        lib_dir = tmp_path / "lib"
        lib_dir.mkdir()
        (lib_dir / "zebra.json").write_text("{}", encoding="utf-8")
        (lib_dir / "apple.json").write_text("{}", encoding="utf-8")
        monkeypatch.setenv("AP_DOSSIER_LIBRARY", str(lib_dir))
        files = list_library()
        assert files[0].name == "apple.json"
        assert files[1].name == "zebra.json"

    def test_non_json_files_excluded(self, tmp_path: Path, monkeypatch):
        lib_dir = tmp_path / "lib"
        lib_dir.mkdir()
        (lib_dir / "actor1.json").write_text("{}", encoding="utf-8")
        (lib_dir / "readme.txt").write_text("notes", encoding="utf-8")
        monkeypatch.setenv("AP_DOSSIER_LIBRARY", str(lib_dir))
        files = list_library()
        assert len(files) == 1
        assert files[0].name == "actor1.json"

    def test_no_publish_env_required_for_list(self, tmp_path: Path, monkeypatch):
        """list_library works without AP_DOSSIER_PUBLISH."""
        monkeypatch.delenv("AP_DOSSIER_PUBLISH", raising=False)
        lib_dir = tmp_path / "lib"
        lib_dir.mkdir()
        (lib_dir / "apt28.json").write_text("{}", encoding="utf-8")
        monkeypatch.setenv("AP_DOSSIER_LIBRARY", str(lib_dir))
        files = list_library()
        assert len(files) == 1


# ---------------------------------------------------------------------------
# load_from_library — unconditional reads, loud failure on missing
# ---------------------------------------------------------------------------


class TestLoadFromLibrary:
    """load_from_library() reads unconditionally; raises on missing file."""

    def test_loads_existing_file(self, tmp_path: Path, monkeypatch):
        lib_dir = tmp_path / "lib"
        lib_dir.mkdir()
        content = '{"type":"bundle","spec_version":"2.1","objects":[]}'
        (lib_dir / "apt28.json").write_text(content, encoding="utf-8")
        monkeypatch.setenv("AP_DOSSIER_LIBRARY", str(lib_dir))
        assert load_from_library("apt28") == content

    def test_raises_file_not_found_for_missing_actor(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("AP_DOSSIER_LIBRARY", str(tmp_path / "lib"))
        with pytest.raises(FileNotFoundError):
            load_from_library("nonexistent-actor")

    def test_invalid_actor_identifier_raises_value_error(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("AP_DOSSIER_LIBRARY", str(tmp_path / "lib"))
        with pytest.raises(ValueError):
            load_from_library("../../etc/passwd")

    def test_no_publish_env_required_for_load(self, tmp_path: Path, monkeypatch):
        """load_from_library works without AP_DOSSIER_PUBLISH."""
        monkeypatch.delenv("AP_DOSSIER_PUBLISH", raising=False)
        lib_dir = tmp_path / "lib"
        lib_dir.mkdir()
        content = '{"type":"bundle"}'
        (lib_dir / "actor.json").write_text(content, encoding="utf-8")
        monkeypatch.setenv("AP_DOSSIER_LIBRARY", str(lib_dir))
        assert load_from_library("actor") == content


# ---------------------------------------------------------------------------
# End-to-end: publish -> list -> load cycle
# ---------------------------------------------------------------------------


class TestLibraryCycle:
    """Full write-then-read cycle through the library helpers."""

    def test_publish_list_load_cycle(self, tmp_path: Path, monkeypatch):
        lib_dir = tmp_path / "cycle_lib"
        monkeypatch.setenv("AP_DOSSIER_PUBLISH", "on")
        monkeypatch.setenv("AP_DOSSIER_LIBRARY", str(lib_dir))

        content = '{"type":"bundle","spec_version":"2.1","objects":[]}'
        publish_to_library(content, "cycle-actor")

        listed = list_library()
        assert len(listed) == 1
        assert listed[0].name == "cycle-actor.json"

        loaded = load_from_library("cycle-actor")
        assert loaded == content
