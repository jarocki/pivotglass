#!/usr/bin/env python3
"""Redacted credential scan for Git blobs and the current worktree."""

from __future__ import annotations

import hashlib
import math
import os
import re
import subprocess
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent
MAX_BLOB = 5_000_000

PATTERNS = {
    "aws_access_key": re.compile(rb"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    "github_token": re.compile(
        rb"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b"
    ),
    "openai_key": re.compile(rb"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"),
    "slack_token": re.compile(rb"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
    "stripe_live_key": re.compile(rb"\b(?:sk|rk)_live_[A-Za-z0-9]{16,}\b"),
    "google_api_key": re.compile(rb"\bAIza[0-9A-Za-z_-]{30,}\b"),
    "private_key": re.compile(
        rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"
    ),
    "uri_credentials": re.compile(
        rb"\b[a-z][a-z0-9+.-]{1,20}://[^/\s:@]{2,}:[^/\s@]{6,}@",
        re.IGNORECASE,
    ),
}

ASSIGNMENT = re.compile(
    rb"""(?ix)
    \b(?:api[_-]?key|secret(?:[_-]?key)?|access[_-]?token|auth[_-]?token|
       client[_-]?secret|password|passwd|private[_-]?key)\b
    \s*(?:=|:)\s*
    ["']?([A-Za-z0-9+/_.:@=-]{12,})["']?
    """
)

PLACEHOLDER_PARTS = (
    b"example",
    b"placeholder",
    b"changeme",
    b"your_",
    b"your-",
    b"test",
    b"dummy",
    b"fake",
    b"none",
    b"null",
    b"${",
    b"os.environ",
    b"getenv",
)


def entropy(value: bytes) -> float:
    if not value:
        return 0.0
    counts = Counter(value)
    return -sum(
        (count / len(value)) * math.log2(count / len(value))
        for count in counts.values()
    )


def scan_bytes(source: str, data: bytes) -> list[tuple[str, str, int, str]]:
    if b"\0" in data or len(data) > MAX_BLOB:
        return []
    findings: list[tuple[str, str, int, str]] = []
    for line_number, line_data in enumerate(data.splitlines(), start=1):
        if len(line_data) > 200_000:
            continue
        for category, pattern in PATTERNS.items():
            for match in pattern.finditer(line_data):
                fingerprint = hashlib.sha256(match.group(0)).hexdigest()[:12]
                findings.append((source, category, line_number, fingerprint))
        for match in ASSIGNMENT.finditer(line_data):
            candidate = match.group(1)
            lowered = candidate.lower()
            if any(part in lowered for part in PLACEHOLDER_PARTS):
                continue
            if len(set(candidate)) < 7 or entropy(candidate) < 3.25:
                continue
            fingerprint = hashlib.sha256(candidate).hexdigest()[:12]
            findings.append(
                (source, "assigned_secret", line_number, fingerprint)
            )
    return findings


def git_history() -> list[tuple[str, str, int, str]]:
    listed = subprocess.run(
        ["git", "rev-list", "--objects", "--all"],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
    ).stdout.splitlines()
    objects: list[tuple[str, str]] = []
    for row in listed:
        sha, _, raw_path = row.partition(b" ")
        if not raw_path:
            continue
        objects.append((sha.decode("ascii"), raw_path.decode("utf-8", "replace")))

    findings: list[tuple[str, str, int, str]] = []
    for sha, path in objects:
        kind = subprocess.run(
            ["git", "cat-file", "-t", sha],
            cwd=ROOT,
            check=True,
            stdout=subprocess.PIPE,
        ).stdout.strip()
        if kind != b"blob":
            continue
        size = int(
            subprocess.run(
                ["git", "cat-file", "-s", sha],
                cwd=ROOT,
                check=True,
                stdout=subprocess.PIPE,
            ).stdout
        )
        if size > MAX_BLOB:
            continue
        data = subprocess.run(
            ["git", "cat-file", "blob", sha],
            cwd=ROOT,
            check=True,
            stdout=subprocess.PIPE,
        ).stdout
        findings.extend(scan_bytes(f"git:{sha[:12]}:{path}", data))
    return findings


def worktree() -> list[tuple[str, str, int, str]]:
    findings: list[tuple[str, str, int, str]] = []
    for directory, dirs, files in os.walk(ROOT):
        dirs[:] = [
            name
            for name in dirs
            if name
            not in {
                ".claude",
                ".git",
                ".worktrees",
                ".venv",
                "career-narrative",
                "dist",
                "node_modules",
                ".next",
                "tmp",
                "__pycache__",
                ".pytest_cache",
            }
        ]
        for name in files:
            path = Path(directory, name)
            if path == Path(__file__).resolve():
                continue
            try:
                if path.stat().st_size > MAX_BLOB:
                    continue
                data = path.read_bytes()
            except (OSError, PermissionError):
                continue
            rel = path.relative_to(ROOT)
            findings.extend(scan_bytes(f"worktree:{rel}", data))
    return findings


def main() -> int:
    findings = git_history() + worktree()
    seen: set[tuple[str, str, int, str]] = set()
    for item in findings:
        if item in seen:
            continue
        seen.add(item)
        source, category, line, fingerprint = item
        print(
            f"{source}\tcategory={category}\tline={line}\t"
            f"fingerprint={fingerprint}"
        )
    print(f"TOTAL_FINDINGS={len(seen)}")
    return 1 if seen else 0


if __name__ == "__main__":
    raise SystemExit(main())
