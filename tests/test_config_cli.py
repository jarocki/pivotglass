"""`pivotglass config` CLI and remediation text that names real commands (#19)."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

from pivotglass.agent.model_control import (
    ModelControl,
    credential_fields_for,
    execute_configuration_command,
    set_service_credentials,
)
from pivotglass.core.config import ConfigManager
from pivotglass.core.module_config import credential_remedy

SOURCE_ROOT = Path(__file__).parents[1] / "src" / "pivotglass"
CONFIG_SUBCOMMANDS = {"show", "list", "set", "check", "enable", "disable", "repair"}


def test_service_ids_and_stored_key_names_resolve_to_credential_fields():
    assert credential_fields_for("censys_pat") == [
        ("censys_pat", "Personal Access Token", True),
        ("censys_org_id", "Organization ID (optional for Free accounts)", False),
    ]
    assert [key for key, _, _ in credential_fields_for("threatfox")] == ["abusech"]
    assert [key for key, _, _ in credential_fields_for("ABUSECH")] == ["abusech"]
    assert credential_fields_for("rdap") == []  # keyless
    assert credential_fields_for("nosuch") == []


def test_set_stores_the_prompted_value_and_never_echoes_it(tmp_path: Path):
    control = ModelControl(ConfigManager(config_dir=tmp_path))
    prompts: list[str] = []
    code, message = set_service_credentials(
        control, "urlhaus", lambda prompt: prompts.append(prompt) or "secret-auth-key"
    )
    assert code == 0
    assert "secret-auth-key" not in message
    assert "ThreatFox" in message and "MalwareBazaar" in message  # the key is shared
    assert "`pivotglass config check urlhaus`" in message
    assert prompts == ["abuse.ch Auth-Key (shared with ThreatFox and MalwareBazaar): "]
    assert ConfigManager(config_dir=tmp_path).get_api_key("abusech") == "secret-auth-key"


def test_set_saves_nothing_without_a_required_value(tmp_path: Path):
    control = ModelControl(ConfigManager(config_dir=tmp_path))
    code, message = set_service_credentials(control, "censys_pat", lambda prompt: "")
    assert code == 1 and "nothing was saved" in message
    assert ConfigManager(config_dir=tmp_path).get_api_key_source("censys_pat") in {"missing", "environment"}


def test_command_bar_refuses_secrets_and_points_to_safe_paths(tmp_path: Path):
    text = execute_configuration_command(("set", "shodan", "abc"), ModelControl(ConfigManager(config_dir=tmp_path)))
    assert "never typed into a command line" in text and "pivotglass config set <service>" in text


def test_cli_config_set_reads_stdin_and_show_reports_the_source(tmp_path: Path):
    env = {**os.environ, "HOME": str(tmp_path)}
    env.pop("PIVOTGLASS_OTX_API_KEY", None)
    env.pop("OTX_API_KEY", None)
    run = lambda *args, stdin="": subprocess.run(  # noqa: E731
        [sys.executable, "-m", "pivotglass", "config", *args],
        input=stdin, capture_output=True, text=True, env=env, timeout=120,
    )
    saved = run("set", "otx", stdin="otx-test-key\n")
    assert saved.returncode == 0, saved.stderr
    assert "otx-test-key" not in saved.stdout + saved.stderr
    shown = run("show")
    assert re.search(r"otx\s+config", shown.stdout)
    assert run("set").returncode == 2  # the key is never an argument
    assert run("set", "nosuch").returncode == 2


def test_every_remediation_command_in_the_source_exists():
    """Messages may only name `pivotglass config <sub> [target]` forms that the CLI accepts."""
    pattern = re.compile(r"pivotglass config ([a-z]+)(?: ([a-z_<>{}\[\]().\-]+))?")
    found = []
    for path in SOURCE_ROOT.rglob("*.py"):
        for sub, target in pattern.findall(path.read_text(encoding="utf-8")):
            found.append((path.name, sub, target))
            assert sub in CONFIG_SUBCOMMANDS, f"{path.name}: pivotglass config {sub}"
            if sub == "set" and target and not target.startswith(("<", "{")) and target.upper() != "SERVICE":
                assert credential_fields_for(target), f"{path.name}: pivotglass config set {target}"
    assert found  # the scan is live


def test_remedy_names_the_real_command_and_env_var():
    assert credential_remedy("abusech").endswith(
        "run `pivotglass config set abusech`, or set PIVOTGLASS_ABUSECH_API_KEY."
    )
    assert "PIVOTGLASS_CENSYS_PAT" in credential_remedy("censys_pat")
