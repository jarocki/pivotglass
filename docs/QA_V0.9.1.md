# Pivotglass v0.9.1 quality record

**Release date:** 2026-08-30

**Release branch:** `codex/v0.9.1-analyst-flow`

**Focus:** lower-friction investigation flow, deterministic gap guidance,
honest progress, progressive disclosure, and low-light clarity

## Verified release candidate

- Complete Python suite: **4,096 passed, 2 skipped**. The one warning is the
  documented Python 3.12+ SQLite datetime-adapter deprecation exercised by the
  schema-v7 layout reconciliation test; it is not a test failure.
- Focused Pursuit Brief, web-state, scaffold, and release-contract suite:
  **45 passed**.
- Repository-wide Python static analysis across `src/`, `tests/`, and
  `scripts/`: passed.
- Release contract against `v0.9.0`: passed; manifests, operator guides, and
  changelog agree on **0.9.1**.
- `uv lock --check`: passed.
- Wheel and source archive: built as
  `adversary_pursuit-0.9.1-py3-none-any.whl` and
  `adversary_pursuit-0.9.1.tar.gz`.
- TypeScript check: passed.
- Web behavior suites: **13 passed** across Advisor idleness, character arcade,
  and visualization-intent behavior.
- Next.js 16.3.0 production export: passed and regenerated.
- Live loopback smoke test: `/api/health` returned
  `{"status":"ok","interface":"pivotglass-web"}` and the stale-export check
  returned `False`.
- Full npm audit: zero known vulnerabilities.
- npm provenance: **31 verified registry signatures** and **17 verified
  attestations**.
- Static diff hygiene: passed.

## Browser interaction and visual QA

The production export was exercised in the Codex in-app browser against the
local loopback service.

- At **320 × 800**, document width equaled client width, all four primary
  navigation choices remained visible, and the recommended action was visible
  in the first viewport. Mobile explanatory copy renders at 14px or larger.
- At **1024 × 768**, document width equaled client width, the Pursuit Brief was
  visible, and the on-demand inspector was closed by default.
- **Evidence** opened the inspector; **Investigate** closed it and restored the
  focused workflow.
- Following the suggested action placed the exact analytical command prefix in
  the investigation field without executing it.
- **Open full workbench** expanded the complete scientific notebook and brought
  it into view.
- **More** exposed system status, the scientific workbench, command palette,
  model/API configuration, badges, themes, display settings, narration, audio,
  and character selection.
- Day and Night presentations retained legible text and stable semantic status
  colors. The global focus-visible rule supplies a three-pixel focus ring.
- The browser viewport and display preference were restored after QA; no
  investigation command was submitted.

## Analytical and safety receipts

- The Pursuit Brief is a read-only deterministic projection. State polling
  performs no write, enrichment, or network operation.
- Evidence coverage, scientific method, live enrichment, and analyst review
  remain four independent measures. There is no blended investigation score.
- Contradictions and failed work outrank optional improvement; pending analyst
  review outranks cosmetic or reward activity.
- Every next action carries a category, plain-language rationale, basis
  references, permission class, confirmation requirement, automatic-eligibility
  flag, and content classification.
- Remote enrichment, relationship creation, proposal adoption, confidence
  changes, actor attribution, and external publication retain their existing
  explicit authorities and approval gates.

## Deliberate follow-on work

Version 0.9.1 does not claim that evidence clusters are actor identities or
that unmatched behavior is a newly discovered TTP. The bounded path through
v1.0 is recorded in
[the v0.9.1 to v1.0 burndown](plans/V0.9.1_TO_1.0_BURNDOWN.md): evidence
clusters, longitudinal tracking, candidate-behavior review, and final measured
usability/accessibility closure remain separate verified releases.
