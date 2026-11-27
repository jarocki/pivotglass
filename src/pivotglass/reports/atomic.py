"""Pinned Atomic Red Team index for emulation plans (#57, type 18).

@decision DEC-ATOMIC-INDEX-001
@title Emulation steps cite Atomic Red Team test GUIDs from a pinned, hash-verified index
@status accepted
@rationale An emulation plan must name tests a purple team can run and audit, not
inline commands copied into a report. Atomic Red Team (MIT licence) publishes
an index of tests per technique. Like the ATT&CK content, the index is
operator-managed: Pivotglass never downloads it silently, and refuses a file
whose SHA-256 does not match the pinned manifest. Without the file, the plan
lists the techniques that need tests and says the index is not installed.

Install the pinned file::

    mkdir -p ~/.pivotglass/frameworks
    curl -fsSL -o ~/.pivotglass/frameworks/atomic-red-team-index-04a53f01.csv \\
      https://raw.githubusercontent.com/redcanaryco/atomic-red-team/04a53f0150b6215b5b47d2c13a3f882942fd289d/atomics/Indexes/Indexes-CSV/index.csv
"""

from __future__ import annotations

import csv
import hashlib
import io
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AtomicManifest:
    commit: str
    committed: str
    url: str
    sha256: str
    licence: str
    filename: str


ATOMIC_INDEX = AtomicManifest(
    commit="04a53f0150b6215b5b47d2c13a3f882942fd289d",
    committed="2026-11-06",
    url=(
        "https://raw.githubusercontent.com/redcanaryco/atomic-red-team/"
        "04a53f0150b6215b5b47d2c13a3f882942fd289d/atomics/Indexes/Indexes-CSV/index.csv"
    ),
    sha256="52b1686589d9ee124165c210e77ff6e41db65b6e6de87611ef2b03d98e0b4256",
    licence="MIT",
    filename="atomic-red-team-index-04a53f01.csv",
)


@dataclass(frozen=True)
class AtomicTest:
    technique: str
    number: int
    name: str
    guid: str
    executor: str


def default_index_path(manifest: AtomicManifest = ATOMIC_INDEX) -> Path:
    return Path.home() / ".pivotglass" / "frameworks" / manifest.filename


def load_index(path: Path, manifest: AtomicManifest = ATOMIC_INDEX) -> dict[str, list[AtomicTest]]:
    """Tests by technique ID from a hash-verified index file."""

    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != manifest.sha256:
        raise ValueError(f"Atomic Red Team index digest mismatch: expected {manifest.sha256}, got {digest}")
    tests: dict[str, list[AtomicTest]] = {}
    for row in csv.DictReader(io.StringIO(raw.decode("utf-8"))):
        technique = (row.get("Technique #") or "").strip().upper()
        if not technique:
            continue
        tests.setdefault(technique, []).append(
            AtomicTest(technique, int(row.get("Test #") or 0), (row.get("Test Name") or "").strip(),
                       (row.get("Test GUID") or "").strip(), (row.get("Executor Name") or "").strip())
        )
    return tests
