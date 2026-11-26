"""Write or check the report reference in docs/reports/ (generated from src/pivotglass/reports/).

Usage:
    uv run python scripts/gen_report_docs.py          # write the pages
    uv run python scripts/gen_report_docs.py --check  # exit 1 if any page is stale
"""

from __future__ import annotations

import sys
from pathlib import Path

from pivotglass.reports.docs import GENERATED, reference_docs

DOCS = Path(__file__).resolve().parent.parent / "docs" / "reports"


def stale() -> list[str]:
    pages = reference_docs()
    problems = [name for name, text in pages.items() if not (DOCS / name).is_file() or (DOCS / name).read_text(encoding="utf-8") != text]
    extra = [
        path.name
        for path in DOCS.glob("*.md")
        if path.name not in pages and path.read_text(encoding="utf-8").startswith(GENERATED)
    ]
    return problems + [f"{name} (no longer generated)" for name in extra]


def main() -> int:
    if "--check" in sys.argv:
        problems = stale()
        for name in problems:
            print(f"stale: docs/reports/{name}; run `uv run python scripts/gen_report_docs.py`")
        return 1 if problems else 0
    DOCS.mkdir(parents=True, exist_ok=True)
    for name, text in reference_docs().items():
        (DOCS / name).write_text(text, encoding="utf-8")
    for name in stale():
        if name.endswith("(no longer generated)"):
            (DOCS / name.split(" ")[0]).unlink()
    print(f"wrote {len(reference_docs())} pages to {DOCS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
