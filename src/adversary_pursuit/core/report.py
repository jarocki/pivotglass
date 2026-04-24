"""Interview-based report generation.

Generates a Markdown report from workspace data with guided analyst questions.
The interview questions come directly from the README vision to ensure every
investigation ends with a structured debrief.

Questions from the original README vision:
- "Why did you start this pursuit?"
- "How did you find the first indicator?"
- "What is the single most important thing you learned?"
- "How could someone interrupt this adversary's operation?"
- "What is the next step?"

@decision DEC-REPORT-001
@title Interview-first report structure — questions drive the narrative
@status accepted
@rationale Adversary pursuit investigations are high-tempo and often lack
           documentation. Forcing analysts through 5 specific questions
           (from the README vision) captures the tacit knowledge that would
           otherwise be lost. Questions were chosen to produce an operationally
           useful artifact: context (why/how), insight (most important learning),
           action (disrupt, next step). The report is auto-generated from workspace
           data plus the interview answers — analysts don't write prose from scratch.

@decision DEC-REPORT-002
@title Markdown output over PDF/HTML for v1
@status accepted
@rationale Markdown is diff-friendly, git-committable, and renderable in every
           modern tool (GitHub, VS Code, Obsidian). PDF/HTML generation adds
           dependencies (weasyprint, pandoc) with significant packaging overhead.
           Markdown is the right v1 choice; a future DEC can layer rendering on top.

@decision DEC-REPORT-003
@title ReportGenerator holds interview state; does not persist it to the DB
@status accepted
@rationale Interview answers are session-level state — analyst enters them via
           `report interview`, then calls `report generate`. Persisting answers to
           the database would require a new schema migration (DEC-DB-002: no
           migrations v1) and adds complexity for little gain. If the session ends,
           answers are lost; analysts can re-run the interview. The report artifact
           (the Markdown file) is what persists to disk.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from adversary_pursuit.core.workspace import WorkspaceManager
    from adversary_pursuit.gamification.scoring import ScoringEngine


@dataclass
class ReportSection:
    """A single interview question and analyst answer pair.

    Parameters
    ----------
    question:
        The question text shown to the analyst.
    answer:
        The analyst's answer. Empty string until set_answer() is called.
    """

    question: str
    answer: str = ""


class ReportGenerator:
    """Generates investigation reports from workspace data.

    Combines workspace STIX objects, module run history, and scoring data
    with analyst interview answers to produce a structured Markdown report.

    Usage
    -----
    rg = ReportGenerator(workspace_mgr)
    rg.set_answer(0, "Tip from partner about APT41 infrastructure")
    rg.set_answer(1, "WHOIS lookup on spearphish domain")
    rg.set_answer(2, "C2 beacon interval is 10 minutes with jitter")
    rg.set_answer(3, "Sinkhole the C2 domain")
    rg.set_answer(4, "Pivot to the ASN block and find more IPs")
    report = rg.generate()
    rg.save(Path("reports/apt41-2026.md"))
    """

    INTERVIEW_QUESTIONS: list[str] = [
        "Why did you start this pursuit?",
        "How did you find the first indicator?",
        "What is the single most important thing you learned?",
        "How could someone interrupt this adversary's operation?",
        "What is the next step?",
    ]

    def __init__(
        self,
        workspace_mgr: "WorkspaceManager",
        scoring_engine: "ScoringEngine | None" = None,
    ) -> None:
        """Initialise with a WorkspaceManager and optional ScoringEngine.

        Parameters
        ----------
        workspace_mgr:
            Active WorkspaceManager instance. Must have an active workspace
            (i.e., workspace_mgr.active must not raise RuntimeError).
        scoring_engine:
            Optional ScoringEngine for score context. If None, score is read
            directly from workspace_mgr.get_total_score().
        """
        self.workspace_mgr = workspace_mgr
        self.scoring_engine = scoring_engine

        # Initialise one section per question with empty answers
        self.sections: list[ReportSection] = [
            ReportSection(q) for q in self.INTERVIEW_QUESTIONS
        ]

        # Free-form notes beyond the structured interview
        self.custom_notes: list[str] = []

    # ------------------------------------------------------------------
    # Answer management
    # ------------------------------------------------------------------

    def set_answer(self, question_index: int, answer: str) -> None:
        """Set the analyst's answer for an interview question.

        Parameters
        ----------
        question_index:
            Index into self.sections (0-4). Raises IndexError if out of range.
        answer:
            The analyst's answer text.

        Raises
        ------
        IndexError
            If question_index is not in range(len(self.sections)).
        """
        if question_index < 0 or question_index >= len(self.sections):
            raise IndexError(
                f"question_index {question_index} out of range "
                f"(0-{len(self.sections) - 1})"
            )
        self.sections[question_index].answer = answer

    # ------------------------------------------------------------------
    # Report generation
    # ------------------------------------------------------------------

    def generate(self) -> str:
        """Generate the full Markdown investigation report.

        Reads live data from the active workspace: STIX objects, module runs,
        and score events. Combines with in-memory interview answers.

        Returns
        -------
        str
            Complete Markdown report as a string.
        """
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        try:
            workspace_name = self.workspace_mgr.active
        except RuntimeError:
            workspace_name = "(unknown)"

        total_score = self.workspace_mgr.get_total_score()
        stix_objects = self.workspace_mgr.get_stix_objects()
        module_runs = self.workspace_mgr.get_module_runs()
        type_counts = self.workspace_mgr.get_stix_type_counts()

        total_indicators = len(stix_objects)
        modules_used = len({r["module_name"] for r in module_runs})

        lines: list[str] = []

        # Title
        lines.append("# Investigation Report")
        lines.append("")

        # Metadata
        lines.append("## Metadata")
        lines.append("")
        lines.append(f"- **Workspace:** {workspace_name}")
        lines.append(f"- **Date:** {now}")
        lines.append(f"- **Total Score:** {total_score}")
        lines.append(f"- **Modules Used:** {modules_used}")
        lines.append(f"- **Total Indicators:** {total_indicators}")
        lines.append("")

        # Executive Summary
        lines.append("## Executive Summary")
        lines.append("")
        if total_indicators == 0:
            lines.append("No indicators collected. Investigation workspace is empty.")
        else:
            lines.append(
                f"This investigation collected **{total_indicators} indicator(s)** "
                f"across **{modules_used} module(s)**. "
                f"Total pursuit score: **{total_score} pts**."
            )
            if type_counts:
                breakdown = ", ".join(
                    f"{t}: {c}" for t, c in sorted(type_counts.items())
                )
                lines.append(f"Indicator types: {breakdown}.")
        lines.append("")

        # Timeline
        lines.append("## Timeline")
        lines.append("")
        lines.append(self.generate_timeline())
        lines.append("")

        # Indicators of Compromise
        lines.append("## Indicators of Compromise")
        lines.append("")
        lines.append(self.generate_ioc_table())
        lines.append("")

        # Interview Notes
        lines.append("## Interview Notes")
        lines.append("")
        for section in self.sections:
            lines.append(f"**Q: {section.question}**")
            answer = section.answer.strip() if section.answer else "_No answer provided._"
            lines.append(f"A: {answer}")
            lines.append("")

        # Analyst Notes (from workspace)
        lines.append("## Analyst Notes")
        lines.append("")
        lines.append(self._generate_analyst_notes())
        lines.append("")

        # Statistics
        lines.append("## Statistics")
        lines.append("")
        lines.append(f"- Total indicators: {total_indicators}")
        if type_counts:
            lines.append("- By type:")
            for t, c in sorted(type_counts.items()):
                lines.append(f"  - {t}: {c}")
        else:
            lines.append("- By type: (none)")
        lines.append(f"- Total score: {total_score}")
        lines.append("")

        return "\n".join(lines)

    def generate_ioc_table(self) -> str:
        """Generate a Markdown IOC table from workspace STIX objects.

        Returns
        -------
        str
            A Markdown table with columns: Type | Value | First Seen.
            Returns a placeholder message if no objects are stored.
        """
        stix_objects = self.workspace_mgr.get_stix_objects()
        if not stix_objects:
            return "_No indicators collected._"

        rows: list[tuple[str, str, str]] = []
        for obj in stix_objects:
            obj_type = obj.get("type", "")
            # Most SCOs use 'value' as the primary field (IP, domain, URL, email).
            value = str(obj.get("value", obj.get("id", "")))
            # 'created' is a STIX timestamp string; truncate to date for readability.
            created = str(obj.get("created", ""))[:10] or "unknown"
            rows.append((obj_type, value, created))

        lines: list[str] = []
        lines.append("| Type | Value | First Seen |")
        lines.append("|------|-------|------------|")
        for obj_type, value, created in rows:
            # Escape pipe characters in values to avoid breaking the Markdown table.
            safe_value = value.replace("|", "\\|")
            lines.append(f"| {obj_type} | {safe_value} | {created} |")

        return "\n".join(lines)

    def generate_timeline(self) -> str:
        """Generate a chronological timeline from module runs.

        Returns
        -------
        str
            A Markdown-formatted timeline. Each entry is a bullet with
            timestamp, module name, target, and result count.
            Returns a placeholder message if no module runs exist.
        """
        runs = self.workspace_mgr.get_module_runs()
        if not runs:
            return "_No module runs recorded._"

        lines: list[str] = []
        for run in runs:
            ts = str(run.get("timestamp", ""))[:16]
            if "T" in ts:
                ts = ts.replace("T", " ")
            ts = ts or "unknown"
            module = run.get("module_name", "unknown")
            target = run.get("target", "unknown")
            count = run.get("result_count", 0)
            lines.append(f"- `{ts}` — **{module}** on `{target}` -> {count} object(s)")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, output_path: Path) -> Path:
        """Generate the report and save it to a file.

        Creates parent directories if they do not exist.

        Parameters
        ----------
        output_path:
            Target file path. Will be created (or overwritten) with UTF-8 encoding.

        Returns
        -------
        Path
            The output_path that was written to (for chaining / display).
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        content = self.generate()
        output_path.write_text(content, encoding="utf-8")
        return output_path

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _generate_analyst_notes(self) -> str:
        """Retrieve analyst notes from the workspace database.

        Accesses the workspace SQLAlchemy engine directly to query AnalystNote rows.
        Falls back to a placeholder if the engine is unavailable or notes table is empty.

        Returns
        -------
        str
            Bullet-list of notes, or '_No analyst notes._' placeholder.
        """
        try:
            from sqlalchemy import select
            from sqlalchemy.orm import Session
            from adversary_pursuit.models.database import AnalystNote

            # Access engine via workspace manager's internal attribute.
            engine = self.workspace_mgr._engine
            if engine is None:
                return "_No analyst notes._"

            with Session(engine) as session:
                rows = session.execute(
                    select(AnalystNote).order_by(AnalystNote.id)
                ).scalars().all()

            if not rows:
                return "_No analyst notes._"

            lines = []
            for row in rows:
                ts = str(row.created_at)[:16] if row.created_at else ""
                link = f" (linked to `{row.stix_object_id}`)" if row.stix_object_id else ""
                lines.append(f"- [{ts}]{link} {row.content}")
            return "\n".join(lines)

        except Exception:  # noqa: BLE001
            return "_No analyst notes._"
