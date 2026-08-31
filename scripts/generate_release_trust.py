#!/usr/bin/env python3
"""Generate deterministic Pivotglass release trust artifacts from lockfiles.

The generated files are publication artifacts, not evidence embedded in the
source archive. Run this only after the wheel and source archive are final.
"""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import importlib.metadata
import json
import re
import subprocess
import sys
import tomllib
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote

PROJECT_NAME = "Pivotglass"
PYTHON_DISTRIBUTION = "adversary-pursuit"
SBOM_FILENAME = "pivotglass.cdx.json"
LICENSE_FILENAME = "THIRD_PARTY_LICENSES.csv"
CHECKSUM_FILENAME = "SHA256SUMS"

# These packages are locked for platforms or interpreter configurations that
# are not installed on every release host. The values are exact-version
# declarations from their upstream package metadata, not inferred licenses.
CONDITIONAL_PYTHON_LICENSES: dict[tuple[str, str], tuple[str, str]] = {
    ("colorama", "0.4.6"): (
        "BSD-3-Clause",
        "curated-upstream-metadata:https://pypi.org/project/colorama/0.4.6/",
    ),
    ("greenlet", "3.5.0"): (
        "MIT AND PSF-2.0",
        "curated-upstream-metadata:https://pypi.org/project/greenlet/3.5.0/",
    ),
    ("pyreadline3", "3.5.4"): (
        "BSD",
        "curated-upstream-metadata:https://pypi.org/project/pyreadline3/3.5.4/",
    ),
}

CLASSIFIER_LICENSES = {
    "Apache Software License": "Apache-2.0",
    "BSD License": "BSD",
    "GNU Lesser General Public License v3 (LGPLv3)": "LGPL-3.0-only",
    "ISC License (ISCL)": "ISC",
    "MIT License": "MIT",
    "Mozilla Public License 2.0 (MPL 2.0)": "MPL-2.0",
    "Python Software Foundation License": "PSF-2.0",
}


@dataclass(frozen=True)
class InventoryRow:
    ecosystem: str
    name: str
    version: str
    scope: str
    license: str
    license_evidence: str
    source: str
    bom_ref: str
    digest_algorithm: str = ""
    digest: str = ""

    def csv_row(self) -> dict[str, str]:
        return {
            "ecosystem": self.ecosystem,
            "name": self.name,
            "version": self.version,
            "scope": self.scope,
            "license": self.license,
            "license_evidence": self.license_evidence,
            "source": self.source,
            "digest_algorithm": self.digest_algorithm,
            "digest": self.digest,
        }


def _canonical_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _read_version(project_root: Path) -> str:
    data = tomllib.loads((project_root / "pyproject.toml").read_text(encoding="utf-8"))
    return str(data["project"]["version"])


def _release_timestamp(project_root: Path, explicit: str | None) -> str:
    if explicit:
        parsed = datetime.fromisoformat(explicit.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("--timestamp must include a timezone")
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    result = subprocess.run(
        ["git", "show", "-s", "--format=%cI", "HEAD"],
        cwd=project_root,
        check=True,
        capture_output=True,
        text=True,
    )
    parsed = datetime.fromisoformat(result.stdout.strip())
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _python_license(name: str, version: str) -> tuple[str, str]:
    try:
        distribution = importlib.metadata.distribution(name)
    except importlib.metadata.PackageNotFoundError:
        override = CONDITIONAL_PYTHON_LICENSES.get((_canonical_name(name), version))
        if override:
            return override
        raise RuntimeError(
            f"locked Python package {name}=={version} is not installed and has no reviewed "
            "conditional-package license record"
        ) from None

    if distribution.version != version:
        raise RuntimeError(
            f"installed {name} version {distribution.version} does not match lockfile {version}"
        )
    metadata = distribution.metadata
    expression = (metadata.get("License-Expression") or "").strip()
    if expression:
        return expression, "installed-package:License-Expression"
    declared = (metadata.get("License") or "").strip()
    if declared and len(declared) <= 160 and "\n" not in declared:
        return declared, "installed-package:License"
    if declared.startswith("MIT License"):
        return "MIT", "installed-package:License-text-header"
    classifiers = [
        item.split(" :: ")[-1]
        for item in metadata.get_all("Classifier", [])
        if item.startswith("License ::")
    ]
    normalized = sorted({CLASSIFIER_LICENSES[item] for item in classifiers if item in CLASSIFIER_LICENSES})
    if normalized:
        return " OR ".join(normalized), "installed-package:Classifier"
    raise RuntimeError(f"locked Python package {name}=={version} has no usable license declaration")


def _uv_hash(package: dict[str, Any]) -> tuple[str, str]:
    candidates: list[dict[str, Any]] = []
    if isinstance(package.get("sdist"), dict):
        candidates.append(package["sdist"])
    candidates.extend(package.get("wheels", []))
    for artifact in candidates:
        value = artifact.get("hash", "")
        if ":" in value:
            algorithm, digest = value.split(":", 1)
            return algorithm.upper().replace("SHA", "SHA-"), digest
    return "", ""


def _dependency_scopes(
    packages: dict[str, dict[str, Any]],
    seeds: dict[str, str],
) -> dict[str, str]:
    priority = {"development": 1, "optional": 2, "runtime": 3}
    scopes: dict[str, str] = {}
    queue: deque[tuple[str, str]] = deque(seeds.items())
    while queue:
        name, scope = queue.popleft()
        name = _canonical_name(name)
        if name not in packages:
            continue
        previous = scopes.get(name)
        if previous and priority[previous] >= priority[scope]:
            continue
        scopes[name] = scope
        for dependency in packages[name].get("dependencies", []):
            queue.append((_canonical_name(dependency["name"]), scope))
    return scopes


def python_inventory(
    project_root: Path,
) -> tuple[list[InventoryRow], dict[str, list[str]], list[str]]:
    lock = tomllib.loads((project_root / "uv.lock").read_text(encoding="utf-8"))
    all_packages = {
        _canonical_name(package["name"]): package for package in lock["package"]
    }
    root = all_packages.get(PYTHON_DISTRIBUTION)
    if not root:
        raise RuntimeError(f"uv.lock has no {PYTHON_DISTRIBUTION} root package")

    seeds = {_canonical_name(item["name"]): "runtime" for item in root.get("dependencies", [])}
    for dependencies in root.get("optional-dependencies", {}).values():
        for item in dependencies:
            seeds.setdefault(_canonical_name(item["name"]), "optional")
    for dependencies in root.get("dev-dependencies", {}).values():
        for item in dependencies:
            seeds.setdefault(_canonical_name(item["name"]), "development")
    scopes = _dependency_scopes(all_packages, seeds)

    rows: list[InventoryRow] = []
    dependencies: dict[str, list[str]] = {}
    for name, package in sorted(all_packages.items()):
        if name == PYTHON_DISTRIBUTION:
            continue
        version = str(package["version"])
        license_name, evidence = _python_license(name, version)
        source = package.get("sdist", {}).get("url", "") or package.get("source", {}).get(
            "registry", ""
        )
        algorithm, digest = _uv_hash(package)
        bom_ref = f"pkg:pypi/{quote(name)}@{quote(version)}"
        rows.append(
            InventoryRow(
                ecosystem="PyPI",
                name=name,
                version=version,
                scope=scopes.get(name, "locked-unselected"),
                license=license_name,
                license_evidence=evidence,
                source=source,
                bom_ref=bom_ref,
                digest_algorithm=algorithm,
                digest=digest,
            )
        )
        dependencies[bom_ref] = [
            f"pkg:pypi/{quote(_canonical_name(item['name']))}@{quote(str(all_packages[_canonical_name(item['name'])]['version']))}"
            for item in package.get("dependencies", [])
            if _canonical_name(item["name"]) in all_packages
            and _canonical_name(item["name"]) != PYTHON_DISTRIBUTION
        ]
    refs_by_name = {row.name: row.bom_ref for row in rows}
    direct_refs = sorted(refs_by_name[name] for name in seeds if name in refs_by_name)
    return rows, dependencies, direct_refs


def _npm_name(path: str) -> str:
    if "node_modules/" not in path:
        raise ValueError(f"not an npm package path: {path}")
    return path.rsplit("node_modules/", 1)[1]


def _npm_hash(integrity: str) -> tuple[str, str]:
    if not integrity or "-" not in integrity:
        return "", ""
    algorithm, encoded = integrity.split("-", 1)
    try:
        digest = base64.b64decode(encoded, validate=True).hex()
    except ValueError as exc:
        raise RuntimeError(f"invalid npm integrity value: {integrity}") from exc
    return algorithm.upper().replace("SHA", "SHA-"), digest


def _resolve_npm_dependency(
    package_path: str,
    dependency_name: str,
    packages: dict[str, dict[str, Any]],
) -> str | None:
    base = package_path
    while True:
        candidate = f"{base}/node_modules/{dependency_name}" if base else f"node_modules/{dependency_name}"
        if candidate in packages:
            return candidate
        if "/node_modules/" not in base:
            if base.startswith("node_modules/"):
                base = ""
                continue
            return None
        base = base.rsplit("/node_modules/", 1)[0]


def node_inventory(
    project_root: Path,
) -> tuple[list[InventoryRow], dict[str, list[str]], list[str]]:
    lock = json.loads((project_root / "web" / "package-lock.json").read_text(encoding="utf-8"))
    packages: dict[str, dict[str, Any]] = lock["packages"]
    root = packages[""]
    direct_runtime = set(root.get("dependencies", {}))
    direct_development = set(root.get("devDependencies", {}))

    path_to_ref: dict[str, str] = {}
    for path, package in sorted(packages.items()):
        if not path:
            continue
        name = _npm_name(path)
        version = str(package["version"])
        path_token = hashlib.sha256(path.encode()).hexdigest()[:12]
        bom_ref = f"pkg:npm/{quote(name, safe='/')}@{quote(version)}?path={path_token}"
        path_to_ref[path] = bom_ref

    rows: list[InventoryRow] = []
    dependencies: dict[str, list[str]] = {}
    for path, package in sorted(packages.items()):
        if not path:
            continue
        name = _npm_name(path)
        version = str(package["version"])
        license_name = str(package.get("license", "")).strip()
        if not license_name:
            raise RuntimeError(f"locked npm package {name}@{version} has no license declaration")
        algorithm, digest = _npm_hash(str(package.get("integrity", "")))
        if not digest:
            raise RuntimeError(f"locked npm package {name}@{version} has no verifiable integrity")
        if name in direct_runtime:
            scope = "runtime"
        elif name in direct_development:
            scope = "development"
        elif package.get("dev"):
            scope = "development"
        elif package.get("optional"):
            scope = "runtime-optional"
        else:
            scope = "transitive"
        bom_ref = path_to_ref[path]
        rows.append(
            InventoryRow(
                ecosystem="npm",
                name=name,
                version=version,
                scope=scope,
                license=license_name,
                license_evidence="package-lock.json:license",
                source=str(package.get("resolved", "")),
                bom_ref=bom_ref,
                digest_algorithm=algorithm,
                digest=digest,
            )
        )
        refs: list[str] = []
        for dependency_name in {
            **package.get("dependencies", {}),
            **package.get("optionalDependencies", {}),
        }:
            resolved_path = _resolve_npm_dependency(path, dependency_name, packages)
            if resolved_path:
                refs.append(path_to_ref[resolved_path])
        dependencies[bom_ref] = sorted(set(refs))
    direct_names = direct_runtime | direct_development
    direct_refs = sorted(
        path_to_ref[f"node_modules/{name}"]
        for name in direct_names
        if f"node_modules/{name}" in path_to_ref
    )
    return rows, dependencies, direct_refs


def _component(row: InventoryRow) -> dict[str, Any]:
    component: dict[str, Any] = {
        "type": "library",
        "bom-ref": row.bom_ref,
        "name": row.name,
        "version": row.version,
        "purl": row.bom_ref.split("?path=", 1)[0],
        "scope": "excluded" if row.scope == "development" else "required",
        "licenses": [{"license": {"name": row.license}}],
        "properties": [
            {"name": "pivotglass:ecosystem", "value": row.ecosystem},
            {"name": "pivotglass:dependency-scope", "value": row.scope},
            {"name": "pivotglass:license-evidence", "value": row.license_evidence},
        ],
    }
    if row.digest:
        component["hashes"] = [{"alg": row.digest_algorithm, "content": row.digest}]
    if row.source:
        component["externalReferences"] = [{"type": "distribution", "url": row.source}]
    return component


def build_sbom(
    *,
    version: str,
    timestamp: str,
    rows: list[InventoryRow],
    dependency_map: dict[str, list[str]],
    root_dependencies: list[str],
    lock_digest: str,
) -> dict[str, Any]:
    root_ref = f"pkg:pypi/{PYTHON_DISTRIBUTION}@{quote(version)}"
    serial_seed = f"{PROJECT_NAME}:{version}:{lock_digest}"
    all_refs = {row.bom_ref for row in rows}
    dependencies = [
        {"ref": root_ref, "dependsOn": sorted(set(root_dependencies) & all_refs)},
        *[
            {"ref": ref, "dependsOn": sorted(item for item in values if item in all_refs)}
            for ref, values in sorted(dependency_map.items())
        ],
    ]
    return {
        "$schema": "https://cyclonedx.org/schema/bom-1.5.schema.json",
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, serial_seed)}",
        "version": 1,
        "metadata": {
            "timestamp": timestamp,
            "tools": {
                "components": [
                    {
                        "type": "application",
                        "name": "Pivotglass release trust generator",
                        "version": version,
                    }
                ]
            },
            "component": {
                "type": "application",
                "bom-ref": root_ref,
                "name": PROJECT_NAME,
                "version": version,
                "purl": root_ref,
                "licenses": [{"license": {"id": "MIT"}}],
            },
            "properties": [
                {"name": "pivotglass:lockfiles", "value": "uv.lock;web/package-lock.json"},
                {"name": "pivotglass:inventory-count", "value": str(len(rows))},
            ],
        },
        "components": [_component(row) for row in rows],
        "dependencies": dependencies,
    }


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def generate(
    *,
    project_root: Path,
    output_dir: Path,
    artifacts: Iterable[Path],
    timestamp: str | None = None,
) -> dict[str, Any]:
    project_root = project_root.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    checksum_inputs = [Path(item).resolve() for item in artifacts]
    if not checksum_inputs:
        raise ValueError("at least one final release artifact is required")
    missing = [str(path) for path in checksum_inputs if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"release artifacts do not exist: {', '.join(missing)}")
    artifact_names = [path.name for path in checksum_inputs]
    if len(artifact_names) != len(set(artifact_names)):
        raise ValueError("release artifact basenames must be unique")
    reserved_names = {SBOM_FILENAME, LICENSE_FILENAME, CHECKSUM_FILENAME}
    if reserved_names & set(artifact_names):
        raise ValueError("release artifact basename collides with a generated trust artifact")
    version = _read_version(project_root)
    release_timestamp = _release_timestamp(project_root, timestamp)
    python_rows, python_dependencies, python_direct = python_inventory(project_root)
    node_rows, node_dependencies, node_direct = node_inventory(project_root)
    rows = sorted(
        [*python_rows, *node_rows],
        key=lambda row: (row.ecosystem.lower(), row.name.lower(), row.version, row.bom_ref),
    )
    lock_digest = hashlib.sha256(
        (project_root / "uv.lock").read_bytes()
        + (project_root / "web" / "package-lock.json").read_bytes()
    ).hexdigest()
    sbom = build_sbom(
        version=version,
        timestamp=release_timestamp,
        rows=rows,
        dependency_map={**python_dependencies, **node_dependencies},
        root_dependencies=[*python_direct, *node_direct],
        lock_digest=lock_digest,
    )

    sbom_path = output_dir / SBOM_FILENAME
    license_path = output_dir / LICENSE_FILENAME
    checksum_path = output_dir / CHECKSUM_FILENAME
    sbom_path.write_text(json.dumps(sbom, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with license_path.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = list(rows[0].csv_row())
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(row.csv_row() for row in rows)

    checksum_inputs.extend([sbom_path.resolve(), license_path.resolve()])
    names = [path.name for path in checksum_inputs]
    if len(names) != len(set(names)):
        raise ValueError("release artifact basenames must be unique")
    checksum_path.write_text(
        "".join(f"{_file_sha256(path)}  {path.name}\n" for path in sorted(checksum_inputs, key=lambda p: p.name)),
        encoding="utf-8",
    )
    return {
        "version": version,
        "timestamp": release_timestamp,
        "python_components": len(python_rows),
        "node_components": len(node_rows),
        "total_components": len(rows),
        "sbom": str(sbom_path),
        "licenses": str(license_path),
        "checksums": str(checksum_path),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--artifact",
        type=Path,
        action="append",
        required=True,
        help="final immutable release artifact to include in SHA256SUMS (repeatable)",
    )
    parser.add_argument(
        "--timestamp",
        help="ISO-8601 timestamp; defaults to the checked-out commit timestamp",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        receipt = generate(
            project_root=args.project_root,
            output_dir=args.output_dir,
            artifacts=args.artifact,
            timestamp=args.timestamp,
        )
    except (FileNotFoundError, RuntimeError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"release trust generation failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
