"""Release-bearing version surfaces must remain synchronized."""

import json
import tomllib
from pathlib import Path

from adversary_pursuit import __version__

ROOT = Path(__file__).resolve().parents[1]


def test_release_version_is_consistent_across_runtime_and_manifests():
    pyproject = tomllib.loads(ROOT.joinpath("pyproject.toml").read_text())
    web_package = json.loads(ROOT.joinpath("web/package.json").read_text())
    web_lock = json.loads(ROOT.joinpath("web/package-lock.json").read_text())

    assert pyproject["project"]["version"] == __version__
    assert web_package["version"] == __version__
    assert web_lock["version"] == __version__
    assert web_lock["packages"][""]["version"] == __version__


def test_release_version_is_present_in_current_operator_docs():
    readme = ROOT.joinpath("README.md").read_text()
    changelog = ROOT.joinpath("CHANGELOG.md").read_text()

    assert f"v{__version__}" in readme
    assert f"## [{__version__}]" in changelog
