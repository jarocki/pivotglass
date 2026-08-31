# Pivotglass v0.9.5 quality record

**Release date:** 2026-08-31

**Release branch:** `codex/v0.9.5-closure`

**Focus:** browser document/candidate preview, hostile-input boundaries, and
pre-1.0 stable/preview/deferred closure

## Candidate verification

- Complete Python suite: **4,135 passed, 2 skipped**. The one warning is the
  existing Python 3.12+ SQLite datetime-adapter deprecation exercised by the
  schema-v7 presentation-layout reconciliation test; it is not a failure.
- Repository-wide Python static analysis across `src/`, `tests/`, and
  `scripts/`: passed.
- Browser preview, document parser, and entity-extraction focused suite:
  **49 passed** before hostile-input additions; the frozen document-authority,
  hostile-input, workspace, and release-contract group passed **160 tests**.
- TypeScript check and Next.js 16.3.0 production static export passed for the
  candidate-preview interface.
- Five visualization behavior tests passed.
- Production npm vulnerability audit reported zero known vulnerabilities; all
  **31 packages** had verified registry signatures and **17** had verified
  provenance attestations.
- Release-contract version synchronization and static diff hygiene passed.
- Wheel and source archive built successfully:
  - `adversary_pursuit-0.9.5.tar.gz` — SHA-256
    `bfb00cf45b3e0285da5b5df669b96c52e394c74b450b7423383277e627f75d5e`
  - `adversary_pursuit-0.9.5-py3-none-any.whl` — SHA-256
    `c5d5db49d2a5e960183c3e9f2456b4232331590f53f305209f7413e14153479c`

The clean-checkout and fresh browser-interaction gates remain open until run
against the frozen v0.9.5 candidate.

## Browser preview receipt

- One explicit local file selection produces a bounded parser preview and a
  bounded temporary candidate set in the same disclosure.
- Candidate rows expose raw/normalized values, type, character and UTF-8 byte
  offsets, line and column, and deterministic rule/version.
- The server caps extraction at 2,000 candidates and the browser renders the
  first 100. A visible message reports additional candidates instead of
  silently dropping the count.
- Parser and candidate truth boundaries state that source text and matches are
  not admitted evidence, entities, graph nodes, relationships, verdicts, or
  attribution.
- Routine workspace polling remains free of parser output and candidate text.

## Explicit deferred closures

These are not v0.9.5 stable capabilities:

- PDF text extraction and OCR;
- Office documents, images, scanned documents, and archive expansion;
- URL/RSS retrieval and batch or drag/drop admission;
- persistent browser document admission, portable document-byte export,
  retention, and purge;
- browser review/materialization of model-assisted proposals;
- SCOT4 or Synapse as a stable authority backend;
- Plotly or editable-office Flint output;
- measured large-workspace, graph-rendering, batch, memory, cancellation, and
  export-time limits.

The [compatibility matrix](COMPATIBILITY.md) and [data-safety guide](DATA_SAFETY.md)
carry the same boundary so the product, help, and release story do not imply
completion by association.

## Remaining v1.0 gates

- no-key synthetic golden-path workspace and recovery walkthrough;
- fresh browser QA for document file selection, candidate disclosure, phone,
  laptop, Day/Night, keyboard, focus restoration, and no overflow;
- supported clean-machine install/update/uninstall and clean-checkout launch;
- SBOM, checksums, signed release artifacts, third-party license inventory,
  and public readback;
- measured capacity and failure-recovery receipts;
- security diff scan with no unresolved critical/high findings;
- owner-reviewed repository security policy (the policy draft requires
  explicit scope and accepted-risk approval before it can be written);
- explicit SCOT/Synapse stable-versus-preview release decision.
