#!/usr/bin/env python3
"""Check repository Markdown links and emit a complete documentation inventory."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r"\]\(([^\s)]+)\)")
FENCE = re.compile(r"^(`{3,}|~{3,}).*?^\1\s*$", re.MULTILINE | re.DOTALL)


def markdown_files(root: Path) -> list[Path]:
    """Inventory public Markdown, excluding private/independent project material."""
    return sorted([*root.glob("*.md"), *root.joinpath("docs").rglob("*.md")])


def anchors(text: str) -> set[str]:
    result: set[str] = set()
    counts: dict[str, int] = {}
    for heading in re.findall(r"^#{1,6}\s+(.+?)\s*#*\s*$", FENCE.sub("", text), re.MULTILINE):
        slug = re.sub(r"[^\w\- ]", "", heading.lower()).replace(" ", "-")
        index = counts.get(slug, 0)
        counts[slug] = index + 1
        result.add(f"{slug}-{index}" if index else slug)
    result.update(re.findall(r'<(?:a|h[1-6])[^>]+(?:id|name)=[\"\']([^\"\']+)', text))
    return result


def check_links(root: Path) -> list[str]:
    failures: list[str] = []
    for path in markdown_files(root):
        for target in LINK.findall(FENCE.sub("", path.read_text(encoding="utf-8"))):
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc:
                continue
            destination = (path.parent / unquote(parsed.path)).resolve() if parsed.path else path
            label = str(path.relative_to(root))
            if not destination.exists():
                failures.append(f"{label}: missing local target {target}")
            elif parsed.fragment and destination.suffix == ".md":
                if unquote(parsed.fragment) not in anchors(destination.read_text(encoding="utf-8")):
                    failures.append(f"{label}: missing heading anchor {target}")
    return failures


def inventory(root: Path, *, json_output: bool = False) -> str:
    """Emit a dated candidate checkpoint using the public discovery authority."""
    generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    files = []
    for path in markdown_files(root):
        data = path.read_bytes()
        files.append({
            "path": path.relative_to(root).as_posix(),
            "line_count": len(data.splitlines()),
            "sha256": hashlib.sha256(data).hexdigest(),
        })
    limits = [
        "Candidate checkpoint only; not a frozen release or publication receipt.",
        "Hashes identify file bytes at generation time; later edits make records stale.",
        "Scope is root Markdown and docs/**/*.md; protected/private context and the independent career project are excluded.",
        "Inventory and local link checks do not prove semantic correctness, exhaustive editorial review, or human usability.",
        "Historical test counts, public objects, remote websites, live integrations, and media/audio qualification are not independently verified by this inventory.",
    ]
    if json_output:
        return json.dumps({
            "schema": "pivotglass-documentation-inventory-1.0",
            "status": "candidate_checkpoint",
            "generated_at": generated_at,
            "file_count": len(files),
            "qualification_limits": limits,
            "files": files,
        }, indent=2, ensure_ascii=False) + "\n"
    rows = [
        "# Documentation inventory", "", f"Candidate checkpoint generated {generated_at}.", "",
        "Generated from every public Markdown file in the candidate tree. Hashes identify",
        "the inspected bytes; link checks are mechanical evidence, not a substitute",
        "for editorial or factual review.", "", "## Qualification limits", "",
        *(f"- {limit}" for limit in limits), "",
        "| Path | Lines | SHA-256 |", "|---|---:|---|",
    ]
    rows.extend(f"| `{record['path']}` | {record['line_count']} | `{record['sha256']}` |" for record in files)
    return "\n".join(rows) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, help="write a dated candidate checkpoint: JSON for .json suffix, Markdown otherwise; keep output outside inventoried Markdown")
    args = parser.parse_args()
    errors = check_links(ROOT)
    if args.inventory:
        args.inventory.write_text(
            inventory(ROOT, json_output=args.inventory.suffix.casefold() == ".json"),
            encoding="utf-8",
        )
    for error in errors:
        print(error)
    print(f"Checked {len(markdown_files(ROOT))} Markdown files; {len(errors)} broken local links/anchors.")
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
