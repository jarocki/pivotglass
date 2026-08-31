# Pivotglass v0.9.2 quality record

**Release date:** 2026-08-31

**Release branch:** `codex/v0.9.1-analyst-flow`

**Focus:** Flint 0.4 qualification, evidence-cluster navigation, and bounded
local document preview

## Verified release candidate

- Complete Python suite: **4,111 passed, 2 skipped**. The one warning is the
  existing Python 3.12+ SQLite datetime-adapter deprecation exercised by the
  schema-v7 presentation-layout reconciliation test; it is not a failure.
- Repository-wide Python static analysis across `src/`, `tests/`, and
  `scripts/`: passed.
- Focused document-ingestion, evidence-cluster, and web-service suite:
  **45 passed**.
- Focused visualization and release-matrix suite: **40 passed**.
- Shared web/TUI evidence-cluster command coverage passed.
- Python static analysis for every added or changed document, cluster, web,
  model, and test module passed.
- TypeScript check and five visualization-behavior tests passed.
- Next.js 16.3.0 production static export passed and was regenerated.
- Production npm vulnerability audit reported zero known vulnerabilities.
- All **31 npm packages** had verified registry signatures and **17** had
  verified provenance attestations.
- Wheel and source archive built as
  `adversary_pursuit-0.9.2-py3-none-any.whl` and
  `adversary_pursuit-0.9.2.tar.gz`.
- Release-contract version synchronization passed: Python, web, lockfiles,
  executable output, installation guidance, and changelog agree on 0.9.2.

The clean-checkout launch remains a final release gate. The Codex in-app
browser could not attach a fresh local QA tab during this run, so the browser
walkthrough was not silently counted as passed. The prior direct interaction
receipt for the same visualization implementation remains below; the new
document-preview interaction still requires a fresh browser pass.

## Browser and visualization interaction receipt

Before candidate freeze, the production interface was exercised at
**1280 × 720**. Visualize opened as a full-width workspace with zero horizontal
document overflow, and the Constellation held **166 indicators / 1,494 cells**
inside a 387-pixel sticky-header scroll region.

- Exactly one Constellation cell was in the Tab order. Arrow Right and Arrow
  Down moved to adjacent cells, retained one Tab stop, and announced the full
  indicator, dimension question, state meaning, and evidence count.
- All nine abbreviated headings had complete accessible names. Selecting a peg
  set `aria-pressed`, retained a visible marker, and pinned its explanation.
- Matrix, bar, and force-directed graph views exposed the correct chart family
  plus distinct **Why this fits** and **How to read it** guidance.
- Fresh interaction QA for the document-preview disclosure, file chooser,
  local result, mobile fit, and focus restoration remains open; service tests
  and the production build pass, but they are not substitutes for that check.

## Flint 0.4 qualification

- `flint-chart` is pinned to exactly 0.4.0 with registry SHA-512 integrity.
- Seeded histogram, bar, line, scatter, and radar intents retained analytical
  configuration parity with 0.3.0 after excluding Flint-owned typography and
  derived layout metadata.
- Pivotglass's exact plotted-data exports are owned outside Flint and remained
  unchanged in the focused tests.
- The 0.4.0 visualization tests, TypeScript check, production build, and npm
  vulnerability audit passed.
- An isolated 0.3.0 rollback rehearsal passed the visualization tests and
  TypeScript check. The build reached static page generation; its complete
  final route summary was not captured, so rollback remains a release-gate
  rehearsal rather than a published production receipt.
- Plotly and editable-office output are not qualified Pivotglass backends.

## Evidence and document boundaries

- Evidence clusters use only nodes and edges already admitted by the graph
  authority. Stable cluster IDs are derived from sorted entity references;
  isolated entities remain visible without fabricated edges.
- Cluster output retains edge truth classes, provenance references and
  sources, observed-time bounds, accepted framework mappings, and Dossier
  gaps. It explicitly says that connectedness is not attribution.
- Document preview is non-mutating and network-free. It sanitizes filenames,
  bounds input and output, strips active HTML, preserves malformed-parser
  failure, and lists skipped email attachments and unqualified PDF extraction.
- Duplicate stored bytes reuse a content hash while each source occurrence and
  parser run receives a separate receipt. Persistent admission is an internal
  foundation in v0.9.2; the browser exposes only temporary preview.
- Portable document export, document deletion/purge, PDF text extraction, OCR,
  Office files, URL/RSS retrieval, archive expansion, entity admission, and
  relationship proposals remain explicitly deferred to later 0.9 releases.

## Migration receipt

- Workspace schema v8 migrates backup-first to v9 before document tables are
  added.
- The migration is additive and does not rewrite STIX evidence, graph edges,
  scientific records, framework mappings, or saved presentation state.
- Persistent document bytes are not yet part of portable workspace export;
  the public browser therefore does not expose document admission in v0.9.2.
