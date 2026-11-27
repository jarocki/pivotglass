"""Write or check the report reference in docs/reports/ (generated from src/pivotglass/reports/).

Usage:
    uv run python scripts/gen_report_docs.py          # write the pages
    uv run python scripts/gen_report_docs.py --check  # exit 1 if any page is stale
"""

from __future__ import annotations

import sys
from pathlib import Path

import re
import tempfile
from datetime import datetime, timezone

from pivotglass.reports.docs import GENERATED, reference_docs

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs" / "reports"
FIXED_NOW = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)


def _normalise(text: str) -> str:
    """Replace values that change on every run (ids, collection times) with stable placeholders."""

    text = re.sub(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", "00000000-0000-0000-0000-000000000000", text)
    text = re.sub(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|\+00:00)?", "2026-11-20 12:00", text)
    today = datetime.now(timezone.utc).date().isoformat()
    return text.replace(today, "2026-11-20")


def examples() -> dict[str, str]:
    """A worked example of every type, built from the test fixture workspace (reserved values only)."""

    import sys

    sys.path.insert(0, str(ROOT))
    from pivotglass.reports.engine import build_report
    from pivotglass.reports.registry import report_types
    from pivotglass.reports.render import render_markdown
    from tests.report_fixtures import build_strategic_workspace

    with tempfile.TemporaryDirectory(dir=ROOT / "tmp" if (ROOT / "tmp").is_dir() else None) as scratch:
        wm = build_strategic_workspace(Path(scratch), "example")
        pages = {}
        for type_id in report_types():
            body = _normalise(render_markdown(build_report(wm, type_id, now=FIXED_NOW)))
            pages[f"examples/{type_id}.md"] = (
                f"{GENERATED}\n\n_Worked example built from the synthetic test workspace (tests/report_fixtures.py). "
                "Every indicator is a reserved documentation value; identifiers and collection times are normalised._\n\n" + body
            )
        return pages


def all_pages() -> dict[str, str]:
    return {**reference_docs(), **examples()}


def stale() -> list[str]:
    pages = all_pages()
    problems = [name for name, text in pages.items() if not (DOCS / name).is_file() or (DOCS / name).read_text(encoding="utf-8") != text]
    extra = [
        str(path.relative_to(DOCS))
        for path in DOCS.rglob("*.md")
        if str(path.relative_to(DOCS)) not in pages and path.read_text(encoding="utf-8").startswith(GENERATED)
    ]
    return problems + [f"{name} (no longer generated)" for name in extra]


def main() -> int:
    if "--check" in sys.argv:
        problems = stale()
        for name in problems:
            print(f"stale: docs/reports/{name}; run `uv run python scripts/gen_report_docs.py`")
        return 1 if problems else 0
    pages = all_pages()
    for name, text in pages.items():
        (DOCS / name).parent.mkdir(parents=True, exist_ok=True)
        (DOCS / name).write_text(text, encoding="utf-8")
    for name in stale():
        if name.endswith("(no longer generated)"):
            (DOCS / name.split(" ")[0]).unlink()
    print(f"wrote {len(pages)} pages to {DOCS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
