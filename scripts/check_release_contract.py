#!/usr/bin/env python3
"""Enforce Pivotglass version and release-document consistency."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEMVER_RE = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")


def parse_semver(value: str) -> tuple[int, int, int]:
    """Return a comparable strict semantic-version tuple."""
    match = SEMVER_RE.fullmatch(value)
    if match is None:
        raise ValueError(f"expected a stable X.Y.Z semantic version, got {value!r}")
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


def version_from_pyproject(content: str) -> str:
    """Read the project version from pyproject text."""
    return str(tomllib.loads(content)["project"]["version"])


def current_versions(root: Path = ROOT) -> dict[str, str]:
    """Read every release-bearing machine manifest."""
    pyproject = root.joinpath("pyproject.toml").read_text(encoding="utf-8")
    init_text = root.joinpath("src/adversary_pursuit/__init__.py").read_text(
        encoding="utf-8"
    )
    init_match = re.search(r'^__version__\s*=\s*"([^"]+)"', init_text, re.MULTILINE)
    if init_match is None:
        raise ValueError("src/adversary_pursuit/__init__.py has no __version__")
    web_package = json.loads(root.joinpath("web/package.json").read_text(encoding="utf-8"))
    web_lock = json.loads(
        root.joinpath("web/package-lock.json").read_text(encoding="utf-8")
    )
    uv_lock = root.joinpath("uv.lock").read_text(encoding="utf-8")
    uv_match = re.search(
        r'(?ms)^name = "adversary-pursuit"\nversion = "([^"]+)"', uv_lock
    )
    if uv_match is None:
        raise ValueError("uv.lock has no adversary-pursuit version")
    return {
        "pyproject.toml": version_from_pyproject(pyproject),
        "src/adversary_pursuit/__init__.py": init_match.group(1),
        "uv.lock": uv_match.group(1),
        "web/package.json": str(web_package["version"]),
        "web/package-lock.json": str(web_lock["version"]),
        "web/package-lock.json root package": str(web_lock["packages"][""]["version"]),
    }


def is_feature_bearing_path(path: str) -> bool:
    """Return whether a changed path can alter shipped product behavior."""
    return (
        path.startswith("src/")
        or path.startswith("scripts/")
        or path.startswith("web/app/")
        or path.startswith("web/public/")
        or path.startswith("web/scripts/")
        or path in {"pyproject.toml", "web/package.json", "web/package-lock.json"}
    )


def git_text(ref: str, path: str) -> str:
    result = subprocess.run(
        ["git", "show", f"{ref}:{path}"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def changed_paths(base: str) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [line for line in result.stdout.splitlines() if line]


def validate(*, base: str | None = None, tag: str | None = None) -> list[str]:
    """Return release-contract violations without mutating the repository."""
    errors: list[str] = []
    versions = current_versions()
    declared = versions["pyproject.toml"]
    try:
        declared_key = parse_semver(declared)
    except ValueError as exc:
        errors.append(str(exc))
        declared_key = (0, 0, 0)

    for surface, value in versions.items():
        if value != declared:
            errors.append(f"{surface} declares {value}; expected {declared}")

    readme = ROOT.joinpath("README.md").read_text(encoding="utf-8")
    quickstart = ROOT.joinpath("docs/QUICKSTART.md").read_text(encoding="utf-8")
    changelog = ROOT.joinpath("CHANGELOG.md").read_text(encoding="utf-8")
    if f"Current release: **v{declared}" not in readme:
        errors.append(f"README.md does not identify v{declared} as the current release")
    source_install = (
        f"--branch v{declared}" in quickstart
        and "uv sync --extra agent --frozen" in quickstart
    )
    package_install = f"@v{declared}" in quickstart
    if (
        not (source_install or package_install)
        or f"adversary-pursuit {declared}" not in quickstart
    ):
        errors.append(
            f"docs/QUICKSTART.md does not install and verify v{declared} "
            "through a version-pinned path"
        )
    if f"## [{declared}]" not in changelog:
        errors.append(f"CHANGELOG.md has no release section for {declared}")

    if base:
        base_version = version_from_pyproject(git_text(base, "pyproject.toml"))
        paths = changed_paths(base)
        feature_paths = [path for path in paths if is_feature_bearing_path(path)]
        if feature_paths:
            try:
                if declared_key <= parse_semver(base_version):
                    sample = ", ".join(feature_paths[:5])
                    errors.append(
                        "feature-bearing changes require a version greater than "
                        f"{base_version}; found {declared} ({sample})"
                    )
            except ValueError as exc:
                errors.append(f"base version is invalid: {exc}")

    if tag and tag != f"v{declared}":
        errors.append(f"release tag {tag!r} does not match declared version v{declared}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", help="base commit for pull-request comparison")
    parser.add_argument("--tag", help="release tag expected to match the version")
    args = parser.parse_args()
    try:
        errors = validate(base=args.base, tag=args.tag)
    except (OSError, KeyError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"release contract could not be evaluated: {exc}", file=sys.stderr)
        return 2
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"release contract satisfied for v{current_versions()['pyproject.toml']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
