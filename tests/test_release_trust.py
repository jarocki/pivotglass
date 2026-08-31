"""Release trust artifacts must be complete, deterministic, and verifiable."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from scripts.generate_release_trust import (
    CHECKSUM_FILENAME,
    LICENSE_FILENAME,
    SBOM_FILENAME,
    generate,
)

ROOT = Path(__file__).resolve().parents[1]
TIMESTAMP = "2026-08-31T07:00:00Z"


def _artifact(path: Path, content: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def test_release_trust_bundle_covers_both_exact_lockfiles(tmp_path: Path) -> None:
    wheel = _artifact(tmp_path / "adversary_pursuit-0.9.5-py3-none-any.whl", b"wheel")
    source = _artifact(tmp_path / "adversary_pursuit-0.9.5.tar.gz", b"source")
    output = tmp_path / "trust"

    receipt = generate(
        project_root=ROOT,
        output_dir=output,
        artifacts=[wheel, source],
        timestamp=TIMESTAMP,
    )

    assert receipt["version"] == "0.9.5"
    assert receipt["python_components"] == 77
    assert receipt["node_components"] == 63
    assert receipt["total_components"] == 140

    with (output / LICENSE_FILENAME).open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 140
    assert {row["ecosystem"] for row in rows} == {"PyPI", "npm"}
    assert all(row["name"] and row["version"] and row["license"] for row in rows)
    assert not any(row["license"].lower() in {"unknown", "noassertion"} for row in rows)
    assert any(row["name"] == "flint-chart" and row["version"] == "0.4.0" for row in rows)
    assert any(row["name"] == "greenlet" and row["version"] == "3.5.0" for row in rows)

    sbom = json.loads((output / SBOM_FILENAME).read_text(encoding="utf-8"))
    assert sbom["bomFormat"] == "CycloneDX"
    assert sbom["specVersion"] == "1.5"
    assert sbom["metadata"]["timestamp"] == TIMESTAMP
    assert sbom["metadata"]["component"]["version"] == "0.9.5"
    assert len(sbom["components"]) == 140
    refs = {component["bom-ref"] for component in sbom["components"]}
    assert len(refs) == 140
    assert all(dependency["ref"] not in refs or set(dependency["dependsOn"]) <= refs for dependency in sbom["dependencies"])
    assert 1 < len(sbom["dependencies"][0]["dependsOn"]) < 140

    checksums = (output / CHECKSUM_FILENAME).read_text(encoding="utf-8").splitlines()
    assert len(checksums) == 4
    expected_names = {
        wheel.name,
        source.name,
        SBOM_FILENAME,
        LICENSE_FILENAME,
    }
    observed_names = {line.split("  ", 1)[1] for line in checksums}
    assert observed_names == expected_names
    for line in checksums:
        digest, name = line.split("  ", 1)
        candidate = output / name
        if not candidate.exists():
            candidate = tmp_path / name
        assert hashlib.sha256(candidate.read_bytes()).hexdigest() == digest


def test_release_trust_bundle_is_reproducible_for_same_inputs(tmp_path: Path) -> None:
    artifact = _artifact(tmp_path / "artifact.whl", b"immutable")
    first = tmp_path / "first"
    second = tmp_path / "second"
    for output in (first, second):
        generate(
            project_root=ROOT,
            output_dir=output,
            artifacts=[artifact],
            timestamp=TIMESTAMP,
        )

    for name in (SBOM_FILENAME, LICENSE_FILENAME, CHECKSUM_FILENAME):
        assert (first / name).read_bytes() == (second / name).read_bytes()


def test_release_trust_bundle_rejects_missing_or_ambiguous_artifacts(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="at least one"):
        generate(
            project_root=ROOT,
            output_dir=tmp_path / "empty-output",
            artifacts=[],
            timestamp=TIMESTAMP,
        )

    with pytest.raises(FileNotFoundError):
        generate(
            project_root=ROOT,
            output_dir=tmp_path / "missing-output",
            artifacts=[tmp_path / "missing.whl"],
            timestamp=TIMESTAMP,
        )

    one = _artifact(tmp_path / "one" / "same.whl", b"one")
    two = _artifact(tmp_path / "two" / "same.whl", b"two")
    with pytest.raises(ValueError, match="basenames"):
        generate(
            project_root=ROOT,
            output_dir=tmp_path / "ambiguous-output",
            artifacts=[one, two],
            timestamp=TIMESTAMP,
        )


def test_release_trust_and_support_guides_preserve_publication_boundaries() -> None:
    trust = (ROOT / "docs" / "RELEASE_TRUST.md").read_text(encoding="utf-8")
    support = (ROOT / "SUPPORT.md").read_text(encoding="utf-8")
    for artifact in (
        "pivotglass.cdx.json",
        "THIRD_PARTY_LICENSES.csv",
        "SHA256SUMS",
        "SHA256SUMS.asc",
    ):
        assert artifact in trust
    assert "public `main`, the tag target, GitHub Release" in trust
    assert "only the latest published release" in support
    assert "Do not place exploit details" in support
    assert "no owner-approved `SECURITY.md`" in support
