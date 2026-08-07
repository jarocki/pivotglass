# Pivotglass v0.8.0 quality record

**Date:** 2026-08-06

**Release branch:** `codex/v0.8.0-epistemic-foundation`

## Release decision

Pivotglass v0.8.0 is ready for the initial Analytic Method and Evidence
Integrity release. The release establishes one durable scientific-investigation
record, explicit evidence/inference boundaries, versioned Structured Analytic
Techniques, formal confidence and likelihood authorities, first-class
contradictions, prioritized information requirements, and evidence-grounded
challenges.

Post-0.8 usability refinements—such as a dedicated form for every supported
analytic technique and a retention-policy convenience editor—remain documented
as refinements. They do not create a competing evidence, confidence, migration,
or relationship authority.

## Automated verification

- Complete Python suite: **3,961 passed, 2 skipped**.
- Focused analytic-rigor, migration, web-adapter, and release-matrix suite:
  **63 passed**.
- Final version and release-contract subset: **43 passed**.
- Advisor idle-policy tests: **2 passed**.
- Seeded arcade-engine tests: **6 passed**.
- Repository-wide Ruff checks: passed.
- TypeScript checking: passed.
- Optimized static build: passed with Next.js **16.3.0**.
- `uv lock --check`: passed; `ap --version` reports
  `adversary-pursuit 0.8.0`.

## Dependency and supply-chain verification

The initial production audit exposed the PostCSS source-map advisory inherited
through Next.js 16.2.12. The release candidate moved to Next.js 16.3.0 and the
fixed PostCSS 8.5.23 override before tagging.

- Production npm audit: **0 vulnerabilities**.
- Registry signatures: **31 of 31 verified**.
- Published provenance attestations: **17 verified**.
- Exact versions and integrity hashes remain locked in `web/package-lock.json`.

## Workspace migration and recovery

- Fresh workspaces are stamped at schema v4.
- Legacy v1, schema v2, and schema v3 fixtures migrate forward through the
  complete supported path.
- Every migration creates and reads back the sibling pre-migration backup.
- Legacy observations, questions, predictions, and source records remain
  present after migration; migrations organize them without rewriting their
  analytical meaning.
- The recovery procedure remains documented in `WORKSPACE_MIGRATIONS.md`.

## Browser interaction walkthrough

The live LAN release candidate was exercised at 1280×720:

- the page and main cockpit had no horizontal overflow;
- Activity & Errors rendered its pause-follow, clear-view, sanitized download,
  and operational-authority controls;
- Confidence & Contradiction Review rendered and expanded;
- the command field retained focus after typing and clearing a command;
- meaningful activity kept the Analyst Advisor hidden;
- no browser console warnings or errors were reported.

The in-app browser's temporary viewport override did not take effect during the
final 320px replay. The release therefore retains the earlier successful 320px
Activity-terminal walkthrough and the automated responsive source contract; it
does not claim a second live 320px receipt for the final dependency-only build.

## Analyst Advisor behavior

- Full narration waits five minutes of meaningful inactivity.
- Brief narration waits eight minutes.
- Suggestions are separated by a fifteen-minute minimum cooldown.
- Typing, clicking, scrolling, touch, evidence arrival, and investigation state
  changes reset the idle timer and dismiss visible suggestions.
- Advisor content remains character-voiced narration, never evidence, and no
  action runs without the analyst choosing it.

## Epistemic safeguards

- Conflict candidates are deterministic method output and require explicit
  analyst promotion to a persisted contradiction.
- Scalar disagreements and non-overlapping numeric intervals are detected only
  when subject and predicate match; incomparable units are not called conflicts.
- Confidence warnings count source-dependence groups instead of duplicate feeds
  and never silently rewrite an analyst's recorded confidence level.
- Likelihood remains a separate standardized probability judgment.
- User-facing errors expose sanitized diagnostic receipts; raw details remain in
  the fixed local log.
