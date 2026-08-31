# Pivotglass v0.9.5 quality record

**Release date:** 2026-08-31

**Release branch:** `codex/v0.9.5-closure`

**Focus:** browser document/candidate preview, hostile-input boundaries, and
pre-1.0 stable/preview/deferred closure

## Candidate verification

- Complete Python suite: **4,148 passed, 2 skipped**. The one warning is the
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
- Wheel and source archive built successfully. Publication-time checksums are
  deliberately not embedded in a file included by the source archive: changing
  this record would change that archive. The release publication receipt must
  publish checksums calculated from the final immutable artifacts.
- A clean `git archive` export synchronized successfully, reported
  `adversary-pursuit 0.9.5`, and passed all **38** release-contract and web-server
  tests.
- The clean archive served the built cockpit root and `/api/health` over an
  ephemeral loopback port; both returned the expected v0.9.5 content.
- A disposable Python 3.14 environment installed the published v0.9.0 wheel,
  reported `adversary-pursuit 0.9.0`, upgraded in place to the frozen v0.9.5
  wheel, reported `adversary-pursuit 0.9.5`, and served both the packaged
  cockpit root and `/api/health` from that installed wheel. Uninstall removed
  the distribution, import, and `ap` entry point. A later exact-candidate wheel
  replay again reported 0.9.5, served the packaged root and health route, and
  created the complete offline learning workspace under a socket-connect guard.
  The wheel resolver selected newer compatible dependencies, confirming that
  this is a package-compatibility receipt rather than the exact lock authority.
  The tagged source checkout with `uv sync --frozen` remains the supported
  reproducible clean install, update, version-check, launch, and removal path.
- The no-key learning fixture passed deterministic core, browser command, TUI,
  chat-compatible grammar, and basic-console checks. A socket-connect guard
  proved fixture creation opens no network connection. Its portable export
  retained four entities, three relationships, eight immutable observations,
  source digests and dependence groups, two competing hypotheses, eight
  evidence links, distinct confidence and likelihood assessments, one open
  high-materiality contradiction, and explicit gap, collection, prediction,
  and stop-condition records. A new manager reopened the database unchanged;
  a file-copy recovery under a second workspace directory produced the same
  deterministic export.
- The reproducible offline capacity receipt qualified a 5,000-entity local
  storage/export scenario and a 1,000-node/999-edge connected graph. On the
  qualification host, complete cockpit state took 3.851 seconds / 28.5 MiB
  traced Python allocation peak for the storage scenario and 1.113 seconds /
  19.8 MiB for the connected graph. An explicit 1,500-node overflow rehearsal
  completed in 1.543 seconds, kept 1,000 nodes and 999 edges in the bounded
  visualization, reported 1,000 omitted records, and retained every stored
  observation. The committed benchmark reads limits from product authorities.
- The focused failure/recovery group passed 44 tests. It covered configuration
  and keyless readiness, unavailable models, provider loss and retry, final-call
  cancellation, stale browser assets, backup-first migrations, future-schema
  rejection, hostile documents, parser exhaustion, MCP cleanup and budgets,
  and terminal error recovery. An all-provider-failure run now ends `failed`
  instead of `empty`; a cancellation received during the final active
  enrichment now ends `cancelled` after that call returns. Existing evidence,
  local notes, workspace export, cockpit state, and later retry remained usable.
- Four deterministic release-trust and support-boundary tests passed. They
  generated a CycloneDX 1.5 SBOM and CSV license inventory for all **77 Python**
  and **63 npm** locked
  third-party components, rejected missing and ambiguous archives, reproduced
  identical output for identical inputs, and verified every checksum in the
  four-file unsigned manifest fixture. The publication ceremony requires the
  final immutable wheel and source archive, an owner-controlled detached
  signature, and clean public download verification.

Fresh browser interaction passed against the frozen v0.9.5 candidate in
headless Chrome at **390×844**, **1024×768**, and **1440×1000**. At every width,
the document width equaled the viewport width and the primary Investigate,
Evidence, Visualize, More, and Investigation Activity controls remained
present. The intentional blurred fog band extends beyond the viewport inside
the clipped main surface; it does not create document overflow. Small internal
lifecycle labels can overflow their own bounded cards by a few pixels, but do
not clip controls or enlarge the document.

The same browser replay selected a local text file, invoked the explicit
**Preview locally** action, displayed both exact entity candidates and the
source/candidate truth boundaries, and preserved zero horizontal document
overflow. The Help dialog fit entirely inside the 390×844 viewport; Escape
closed it and restored focus to its opener. The `/` shortcut restored focus to
the investigation command, and both Day and Night controls applied their
corresponding display modes.

An earlier in-app browser session could not attach a new webview. That attempt
remains recorded as an environment failure; the independent Chrome DevTools
replay above is the completed product receipt.

## Security diff gate

The completed Codex Security diff scan reviewed all **34 of 34** compact
worklist rows across the v0.9.1–v0.9.5 release train. It found no critical,
high, or medium findings. One low-severity availability weakness remains open:
a negative `Content-Length` can bypass the upper-only request-size check and
hold one local/LAN request thread until the client disconnects. The real HTTP
handler reproduced the behavior. Default loopback binding, rejection of
wildcard binds, and one-thread-per-connection isolation materially constrain
exposure; the release's no-critical/high gate passes, but this low finding must
remain visible until an explicitly approved patch and regression test close it.

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
- batch-document capacity, workspaces beyond 5,000 entities, graph rendering
  beyond the bounded view, and active-provider cancellation latency.

The [compatibility matrix](COMPATIBILITY.md) and [data-safety guide](DATA_SAFETY.md)
carry the same boundary so the product, help, and release story do not imply
completion by association.

## Remaining publication and v1.0 gates

- final-artifact SBOM/license/checksum generation, owner-key signature, and
  clean public readback using the now-tested release-trust procedure;
- owner-reviewed repository security policy (the policy draft requires
  explicit scope and accepted-risk approval before it can be written);
- explicit SCOT/Synapse stable-versus-preview release decision.

The frozen local-candidate state, public v0.9.0 readback, owner decisions, and
ordered publication ceremony are consolidated in the [v0.9.5 release
handoff](RELEASE_HANDOFF_V0.9.5.md).
