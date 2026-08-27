# Pivotglass v0.9.0 quality record

**Release date:** 2026-08-26

**Release branch:** `codex/v0.9.0-release`

**Focus:** evidence-backed framework perspectives, editable two-layer graph,
question-first visualization, governed external integrations, and release
discipline

## Verified release candidate

- Complete Python suite: **4,090 passed, 2 skipped**. The one warning is the
  documented Python 3.12+ SQLite datetime-adapter deprecation exercised by the
  schema-v7 layout reconciliation test; it is not a test failure.
- Python static analysis across `src/`, `tests/`, and `scripts/`: passed.
- Release-contract and version-consistency subset: **5 passed**; every machine
  manifest and current operator guide reports **0.9.0**.
- `uv lock --check`: passed.
- Wheel and source archive: built as
  `adversary_pursuit-0.9.0-py3-none-any.whl` and
  `adversary_pursuit-0.9.0.tar.gz`; package metadata reports version 0.9.0.
- Installed command path: `.venv/bin/ap --version` reports
  `adversary-pursuit 0.9.0`.
- TypeScript check: passed.
- Web behavior suites: **13 passed** across Advisor idleness, character arcade,
  and visualization-intent behavior.
- Next.js 16.3.0 production export: passed and committed.
- Live loopback smoke test: the rebuilt cockpit started, `/api/health` returned
  the expected Pivotglass response, and the stale-export check was false.
- Full and production npm audits: zero known vulnerabilities after replacing
  the Nano ID 3.3.17 override with 3.3.18.
- npm provenance: **31 verified registry signatures** and **17 verified
  attestations**.
- Redacted current-tree and reachable-Git-history secret scan:
  `TOTAL_FINDINGS=0`. Focused tests confirm real assignments and
  credential-bearing non-test URLs remain detected.
- Static diff hygiene: passed.
- The tracked pre-push guard was exercised with an annotated `v0.9.0` tag
  object and correctly resolved it to the checked-out release commit before
  applying the tag/version contract.

## Capability receipts

- One workspace evidence substrate feeds ATT&CK 19.2, Cyber Kill Chain, and
  Diamond Model projections; mappings retain their evidence references,
  versions, provenance, disposition, and gaps.
- The investigation graph separates entity, epistemic, and bridge layers.
  Observed, inferred, manual, and derived-navigation edges remain visibly
  distinct and retain provenance.
- Saved layouts, annotations, manual relation correction history, layer
  filtering, branch collapse, multiselect, undo/redo, and exact JSON/CSV/GEXF
  exports are presentation or governed-judgment features; they do not rewrite
  observations.
- Question-first visualization includes exact-data and accessible alternatives
  for framework views, coverage PCA, competing hypotheses, investigation
  hierarchy, likelihood intervals, distributions, and the relationship graph.
- Synapse, SCOT4, go-roast, and Nucleotide operations use bounded transports,
  exact plans or receipts, explicit analyst disposition, and fail-closed
  authority checks.

## Explicit external-system deferrals

No disposable live Synapse or SCOT deployment was supplied for this release
cut. Therefore this record does **not** claim live end-to-end Synapse cutover,
SCOT publication, SCOT-side pivot UI, recovery rehearsal, reviewed shadow
merge, or conflict-disposition testing. Protocol fixtures and local contract
tests passed, but fixtures are not live-system evidence.

These deferrals do not silently authorize remote mutation. Synapse cutover and
SCOT publication readiness continue to report their missing receipts; remote
writes retain exact short-lived human approval and mandatory readback; Synapse
primary-backend cutover remains a v1.0 gate.

## Release integrity policy

The repository now documents and tests the rule that feature-bearing changes
must advance the product version before merge. The tracked pre-push guard
compares direct `main` publication with its remote base and rejects an unchanged
or lower version; pull-request review must record the same explicit contract
check. A release is complete only after public `main`, the matching tag, the
GitHub Release, and its downloadable artifacts are read back and agree.
