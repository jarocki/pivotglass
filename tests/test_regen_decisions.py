"""Tests for scripts/regen_decisions.py.

Covers:
- Fixture directory round-trip: @decision blocks (docstring + inline-comment forms)
  produce correct DecisionEntry objects grouped by component.
- Idempotency: running render_decisions_md twice on the same entries produces
  byte-identical output modulo the timestamp line.
- Malformed annotation: missing @title emits a WARN to stderr but does not crash,
  and the malformed entry still appears (using DEC-ID as fallback title).
- CLI dry-run: exit code 0 and stdout begins with "# Decision Registry".
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Module loader — import the script without installing it as a package.
# ---------------------------------------------------------------------------

_SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "regen_decisions.py"
_PROJECT_ROOT = _SCRIPT_PATH.parent.parent


def _load_regen() -> object:
    """Load scripts/regen_decisions.py as a module and return it.

    The module must be registered in sys.modules before exec_module so that
    @dataclass (and any other decorator that inspects cls.__module__) can
    resolve the module dict via sys.modules[cls.__module__].
    """
    spec = importlib.util.spec_from_file_location("regen_decisions", str(_SCRIPT_PATH))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["regen_decisions"] = mod
    spec.loader.exec_module(mod)
    return mod


regen = _load_regen()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_fixture_tree(tmp_path: Path) -> Path:
    """Create a minimal src/adversary_pursuit/ tree with @decision annotations.

    Returns the tmp_path root (acts as project root for scan_source_tree).
    """
    src = tmp_path / "src" / "adversary_pursuit"

    # Component 1: gamification — docstring-style annotation
    gamification = src / "gamification"
    gamification.mkdir(parents=True)
    (gamification / "__init__.py").write_text("")
    (gamification / "modes.py").write_text(
        '''\
"""Gamification modes.

@decision DEC-GAMIFICATION-001
@title streak reset policy on workspace clear
@status accepted
@rationale Streak is tied to workspace; clearing workspace resets streak to avoid phantom counts.
"""

def get_modes():
    return []
''',
        encoding="utf-8",
    )

    # Component 2: dossier — inline-comment-style annotation
    dossier = src / "dossier"
    dossier.mkdir(parents=True)
    (dossier / "__init__.py").write_text("")
    (dossier / "state.py").write_text(
        """\
# Regular module comment

# @decision DEC-DOSSIER-042
# @title DossierState uses SQLite for persistence
# @status accepted
# @rationale Flat-file alternatives were considered but SQLite allows atomic multi-row transactions.

class DossierState:
    pass
""",
        encoding="utf-8",
    )

    # Component 3: core — two annotations in one file
    core = src / "core"
    core.mkdir(parents=True)
    (core / "__init__.py").write_text("")
    (core / "workspace.py").write_text(
        '''\
"""Core workspace module.

@decision DEC-CORE-001
@title workspace singleton scope
@status accepted
@rationale One workspace per process avoids shared-state races.

@decision DEC-CORE-002
@title workspace path defaults to ~/.ap/workspaces
@status accepted
@rationale XDG-compatible default; overridable via AP_WORKSPACE_PATH.
"""

class Workspace:
    pass
''',
        encoding="utf-8",
    )

    return tmp_path


# ---------------------------------------------------------------------------
# Test 1: fixture round-trip — docstring and inline-comment forms both parsed
# ---------------------------------------------------------------------------


def test_fixture_round_trip(tmp_path):
    """scan_source_tree finds all 4 DEC-IDs in the fixture tree and groups them correctly."""
    project_root = _write_fixture_tree(tmp_path)
    entries = regen.scan_source_tree(project_root)

    dec_ids = {e.dec_id for e in entries}
    assert "DEC-GAMIFICATION-001" in dec_ids, f"Missing DEC-GAMIFICATION-001, got: {dec_ids}"
    assert "DEC-DOSSIER-042" in dec_ids, f"Missing DEC-DOSSIER-042, got: {dec_ids}"
    assert "DEC-CORE-001" in dec_ids, f"Missing DEC-CORE-001, got: {dec_ids}"
    assert "DEC-CORE-002" in dec_ids, f"Missing DEC-CORE-002, got: {dec_ids}"

    # Component grouping
    assert "GAMIFICATION" in {e.component for e in entries if e.dec_id == "DEC-GAMIFICATION-001"}
    assert "DOSSIER" in {e.component for e in entries if e.dec_id == "DEC-DOSSIER-042"}

    # Title and status populated
    gam_entry = next(e for e in entries if e.dec_id == "DEC-GAMIFICATION-001")
    assert gam_entry.title == "streak reset policy on workspace clear"
    assert gam_entry.status == "accepted"

    doss_entry = next(e for e in entries if e.dec_id == "DEC-DOSSIER-042")
    assert doss_entry.title == "DossierState uses SQLite for persistence"


# ---------------------------------------------------------------------------
# Test 2: idempotency — same entries produce byte-identical output modulo timestamp
# ---------------------------------------------------------------------------


def test_idempotency(tmp_path):
    """render_decisions_md is idempotent: same entries + same timestamp → same bytes."""
    project_root = _write_fixture_tree(tmp_path)
    entries = regen.scan_source_tree(project_root)

    timestamp = "2026-06-09 12:00"
    output_a = regen.render_decisions_md(entries, timestamp)
    output_b = regen.render_decisions_md(entries, timestamp)
    assert output_a == output_b, "render_decisions_md is not idempotent with the same inputs"

    # Different timestamps differ only on the timestamp line
    output_c = regen.render_decisions_md(entries, "2026-06-10 08:00")
    lines_a = output_a.splitlines()
    lines_c = output_c.splitlines()
    assert len(lines_a) == len(lines_c), "Line count changed with different timestamp"
    differing = [(i, la, lc) for i, (la, lc) in enumerate(zip(lines_a, lines_c)) if la != lc]
    assert len(differing) == 1, (
        f"Expected exactly 1 differing line (timestamp), got {len(differing)}: {differing}"
    )
    assert "Last updated" in differing[0][1], (
        f"Differing line is not the timestamp line: {differing[0]}"
    )


# ---------------------------------------------------------------------------
# Test 3: malformed annotation — missing @title → WARN on stderr, no crash
# ---------------------------------------------------------------------------


def test_malformed_annotation_no_title(tmp_path, capsys):
    """A @decision block without @title emits a WARN to stderr and uses DEC-ID as title fallback."""
    src = tmp_path / "src" / "adversary_pursuit" / "core"
    src.mkdir(parents=True)
    (src / "__init__.py").write_text("")
    (src / "bad.py").write_text(
        '''\
"""Module with malformed annotation — no @title.

@decision DEC-CORE-BAD-001
@status accepted
@rationale This annotation intentionally has no @title to test the warning path.
"""
''',
        encoding="utf-8",
    )

    entries = regen.scan_source_tree(tmp_path)
    captured = capsys.readouterr()

    # Should have emitted a WARN to stderr
    assert "WARN" in captured.err, f"Expected WARN in stderr, got: {captured.err!r}"
    assert "DEC-CORE-BAD-001" in captured.err, (
        f"Expected DEC-ID in WARN message, got: {captured.err!r}"
    )
    assert "no @title" in captured.err.lower() or "@title" in captured.err, (
        f"WARN should mention @title, got: {captured.err!r}"
    )

    # The entry should still be present with DEC-ID as fallback title
    dec_ids = {e.dec_id for e in entries}
    assert "DEC-CORE-BAD-001" in dec_ids, "Malformed entry should still appear in output"
    bad_entry = next(e for e in entries if e.dec_id == "DEC-CORE-BAD-001")
    assert bad_entry.title == "DEC-CORE-BAD-001", (
        f"Fallback title should be DEC-ID, got: {bad_entry.title!r}"
    )


# ---------------------------------------------------------------------------
# Test 4: malformed annotation — suspicious DEC-ID pattern → WARN but kept
# ---------------------------------------------------------------------------


def test_malformed_dec_id_pattern(tmp_path, capsys):
    """A @decision with a lowercase/non-standard DEC-ID emits a WARN but is kept."""
    src = tmp_path / "src" / "adversary_pursuit" / "core"
    src.mkdir(parents=True)
    (src / "__init__.py").write_text("")
    (src / "odd.py").write_text(
        '''\
"""Module with suspicious DEC-ID casing.

@decision DEC-core-weirdformat
@title some odd decision
@status accepted
@rationale Testing that a lowercase DEC-ID issues a warning but is still captured.
"""
''',
        encoding="utf-8",
    )

    entries = regen.scan_source_tree(tmp_path)
    captured = capsys.readouterr()

    assert "WARN" in captured.err, "Expected WARN in stderr for bad DEC-ID pattern"
    dec_ids = {e.dec_id for e in entries}
    assert "DEC-core-weirdformat" in dec_ids, (
        "Entry with suspicious DEC-ID should still be included"
    )


# ---------------------------------------------------------------------------
# Test 5: render output structure — section headers present for each component
# ---------------------------------------------------------------------------


def test_render_output_structure(tmp_path):
    """render_decisions_md produces well-formed Markdown with the expected section headers."""
    project_root = _write_fixture_tree(tmp_path)
    entries = regen.scan_source_tree(project_root)
    content = regen.render_decisions_md(entries, "2026-06-09 12:00")

    assert content.startswith("# Decision Registry"), "Must start with '# Decision Registry'"
    assert "## By Component" in content
    assert "### GAMIFICATION" in content
    assert "### DOSSIER" in content
    assert "### CORE" in content

    # Each DEC-ID should appear as a bold entry
    assert "**DEC-GAMIFICATION-001**" in content
    assert "**DEC-DOSSIER-042**" in content


# ---------------------------------------------------------------------------
# Test 6: CLI dry-run — exit 0, stdout begins with "# Decision Registry"
# ---------------------------------------------------------------------------


def test_cli_dry_run():
    """python3 scripts/regen_decisions.py --dry-run exits 0 and prints Decision Registry header."""
    result = subprocess.run(
        [sys.executable, str(_SCRIPT_PATH), "--dry-run"],
        cwd=str(_PROJECT_ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"--dry-run exited {result.returncode}; stderr: {result.stderr}"
    assert result.stdout.startswith("# Decision Registry"), (
        f"stdout should start with '# Decision Registry', got: {result.stdout[:200]!r}"
    )
