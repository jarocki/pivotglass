# AP Project -- Operational Rules

Project-specific overrides for the global Claude Code instructions. The
global ~/.claude/CLAUDE.md takes precedence on architecture; this file
adds AP-specific operational rules.

## Backlog discipline (DEC-BACKLOG-DISCIPLINE-001)

@decision DEC-BACKLOG-DISCIPLINE-001
@title Every new GitHub issue must be scheduled-or-closed within 24h of filing
@status accepted
@rationale 06-29 reckoning Confront #2 documented that AP's OPEN-unscheduled
  backlog grew from ~5 to ~18 issues in 20 days because "file the issue,
  don't schedule it" became the default response. The strict alternative:
  every new issue lands either with a milestone/label assignment within 24h
  of filing, or gets closed. This forces the operator (human or agent) to
  make a real disposition at capture-time instead of using the backlog as
  procrastination storage.

  Rule:
  - Every newly-filed issue must be tagged with at least one of: a
    target-phase label (e.g. "phase-18"), a milestone, or a triage label
    ("triage-stale", "triage-defer", "triage-accept").
  - If no label/milestone applies within 24h, close the issue as
    "wontfix" or "not-planned" with a one-line comment. It can be
    reopened later if circumstances change.
  - Stale-budget: max 30 days as "triage-defer" before the issue is
    closed.

  The reckoning skill is the audit authority. Each reckoning checks
  unscheduled-issue count and flags the rule's adherence.

## Other AP-specific rules

(none yet -- this file grows as new project-specific decisions accumulate.)
