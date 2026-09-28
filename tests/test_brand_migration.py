"""Release rename, preservation, and explicit migration contracts."""
from __future__ import annotations

import json
import stat
import tomllib
from pathlib import Path

import pytest

from pivotglass import __main__, __version__
from pivotglass.core.legacy_migration import migrate_home, normalize_extensions
from pivotglass.core.workspace import WorkspaceManager
from pivotglass.dossier.export import export_dossier
from pivotglass.dossier.import_ import import_dossier
from pivotglass.models.database import StixObject


def test_distribution_exposes_only_pivotglass_command():
    project = tomllib.loads(Path("pyproject.toml").read_text())["project"]
    assert project["name"] == "pivotglass"
    assert project["scripts"] == {"pivotglass": "pivotglass.__main__:main"}
    assert project["version"] == __version__ == "0.9.8"


def test_version_names_public_product(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["pivotglass", "--version"])
    __main__.main()
    assert capsys.readouterr().out == "pivotglass 0.9.8\n"


def test_home_copy_preserves_source_and_secret_modes(tmp_path):
    source = tmp_path / "old-home"
    source.mkdir()
    secret = source / "config.toml"
    secret.write_text("credential = 'test-fixture'\n")
    secret.chmod(0o600)
    destination = migrate_home(source, tmp_path / "new-home")
    assert secret.read_bytes() == (destination / "config.toml").read_bytes()
    assert stat.S_IMODE((destination / "config.toml").stat().st_mode) == 0o600
    assert stat.S_IMODE(destination.stat().st_mode) == 0o700
    with pytest.raises(ValueError, match="already exists"):
        migrate_home(source, destination)


def test_migration_requires_stopped_acknowledgment(monkeypatch, tmp_path):
    monkeypatch.setattr("sys.argv", ["pivotglass", "migrate-home", "--from", str(tmp_path)])
    with pytest.raises(SystemExit) as exc:
        __main__.main()
    assert exc.value.code == 2


def test_migration_rejects_symlinks_and_nested_destinations(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    with pytest.raises(ValueError, match="outside"):
        migrate_home(source, source / "nested")
    (source / "external").symlink_to(tmp_path / "other")
    with pytest.raises(ValueError, match="symbolic links"):
        migrate_home(source, tmp_path / "dest")
    assert not (tmp_path / "dest").exists()


def test_legacy_projection_keeps_original_and_current_value_wins():
    original = {"x_ap_fetched_at": "old", "x_pivotglass_fetched_at": "current",
                "objects": [{"x_ap_source_module": "test/source"}]}
    result = normalize_extensions(original)
    assert original["objects"][0] == {"x_ap_source_module": "test/source"}
    assert result["x_pivotglass_fetched_at"] == "current"
    assert result["objects"] == [{"x_pivotglass_source_module": "test/source"}]
    assert "x_ap_fetched_at" not in result


def test_legacy_workspace_provenance_read_without_database_rewrite(tmp_path):
    wm = WorkspaceManager(workspace_dir=tmp_path)
    wm.create("migration")
    wm.switch("migration")
    wm.store_stix_objects([{"type": "ipv4-addr", "value": "192.0.2.7"}], "test/source", "192.0.2.7")
    with wm.get_session() as session:
        row = session.query(StixObject).one()
        blob = dict(row.json_blob)
        legacy = {key.replace("x_pivotglass_", "x_ap_"): value for key, value in blob.items()}
        row.json_blob = legacy
        session.commit()
    projected = wm.get_stix_objects()[0]
    assert projected["x_pivotglass_source_module"] == "test/source"
    with wm.get_session() as session:
        assert session.query(StixObject).one().json_blob == legacy


def test_legacy_dossier_import_restores_current_metadata(tmp_path):
    wm = WorkspaceManager(workspace_dir=tmp_path)
    wm.create("migration")
    wm.switch("migration")
    bundle_json = export_dossier(wm, "review-actor")
    raw = json.loads(bundle_json)
    legacy_json = json.dumps(raw).replace("x_pivotglass_", "x_ap_")
    imported = import_dossier(legacy_json)
    assert imported.actor_identifier == "review-actor"
    assert imported.metadata["x_pivotglass_dossier_schema_version"] == "1"


def test_renamed_banner_uses_readable_wordmark_in_narrow_terminal(monkeypatch):
    from io import StringIO

    from rich.console import Console

    from pivotglass.agent.banner import render_boot_banner

    monkeypatch.delenv("PIVOTGLASS_NO_BANNER", raising=False)
    monkeypatch.setattr("pivotglass.agent.banner.time.sleep", lambda _: None)
    output = StringIO()
    render_boot_banner(Console(file=output, width=32, force_terminal=False))
    assert "PIVOTGLASS" in output.getvalue()
