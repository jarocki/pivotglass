"""The release secret scan must distinguish values from code references."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _scanner():
    path = Path(__file__).resolve().parents[1] / ".audit_secret_scan.py"
    spec = importlib.util.spec_from_file_location("pivotglass_secret_scan", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_assignment_references_are_not_treated_as_secret_values() -> None:
    scan = _scanner()
    data = b"api_key = config_mgr.get_api_key(provider_id)\npassword:n.password\n"
    assert scan.scan_bytes("fixture", data) == []


def test_reserved_credential_uri_fixture_is_not_a_finding() -> None:
    scan = _scanner()
    assert scan.scan_bytes(
        "fixture", b'https://user:secret@example.test/path\n'
    ) == []


def test_real_secret_shapes_remain_findings() -> None:
    scan = _scanner()
    findings = scan.scan_bytes(
        "fixture",
        b'api_key = "Actual' + b'SecretValue987654"\n'
        + b"https://user:Real"
        + b"Password@example.org/path\n",
    )
    assert {finding[1] for finding in findings} == {
        "assigned_secret",
        "uri_credentials",
    }
