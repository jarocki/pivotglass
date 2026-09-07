# Pivotglass v0.9.5 quality record

**Release date:** 2026-09-06

**Release branch:** `codex/v0.9.5-release-refresh`

**Focus:** browser document/candidate preview, hostile-input boundaries,
workspace lifecycle parity, responsive presentation, launch reliability, and
pre-1.0 stable/preview/deferred closure

## Candidate verification

- Complete Python suite after the release refresh and workspace lifecycle
  parity corrections: **4,178 passed, 2 skipped**. The one warning is the
  existing Python 3.12+ SQLite datetime-adapter deprecation exercised by the
  schema-v7 presentation-layout reconciliation test; it is not a failure.
- Repository-wide Python static analysis across `src/`, `tests/`, and
  `scripts/`: passed.
- Browser preview, document parser, and entity-extraction focused suite:
  **49 passed** before hostile-input additions; the frozen document-authority,
  hostile-input, workspace, and release-contract group passed **160 tests**.
- The final JSON/JSONL and HTTP regression replay passed **60 tests**, including
  both former recursion triggers, quote/escape-aware valid inputs, the outer
  request-envelope recursion boundary, and a successful request after every
  rejected hostile request.
- The document/workspace/UI lifecycle suite passed **289 tests**. A second
  focused confirmation after receipt wording and exact-scope refinements passed
  **265 tests**.
- TypeScript check and Next.js 16.3.0 production static export passed for the
  candidate-preview interface. The committed export contains the exact refreshed
  application source.
- Two advisor-idle, six arcade, and five visualization behavior tests passed.
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

Fresh browser interaction passed against the refreshed v0.9.5 candidate in
headless Chrome at phone, laptop, and desktop widths: **390 by 844**,
**1024 by 768**, and **1440 by 1000**. At every width, the document width
equaled the viewport width and the primary Investigate, Evidence, Visualize,
More, and Investigation Activity controls remained present. The diffuse fog
gradient stays behind content at desktop widths and creates no document
overflow. Decorative fog and ambient compositor layers are disabled at phone
width, where the command rail remains in document flow and cannot cover the
Pursuit Brief.

The same browser replay selected a local text file, invoked the explicit
**Preview locally** action, displayed both exact entity candidates and the
source/candidate truth boundaries, and preserved zero horizontal document
overflow. The Help dialog fit entirely inside the viewport; Escape closed it,
restored focus to the exact Help button, and changed the focus status from
Dialog to Cockpit. The slash shortcut restored focus to the investigation
command. Day and Night modes, normal and high contrast, and reduced effects
were exercised. The command-completion list remained inside the viewport and
was the top hit-tested layer above the Systems and Intelligence panes.

An earlier in-app browser session could not attach a new webview. That attempt
remains recorded as an environment failure; the independent Chrome DevTools
replay above is the completed product receipt.

## Release media verification

The release screenshots and guided video were recaptured from the committed
v0.9.5 static export against an isolated `ToolContext`. The capture used
`workspace learn release-tour`; the receipt recorded four reserved synthetic
entities, three source-backed relationships, eight observations, zero network
requests, and zero model requests. Every supported credential environment
variable was removed from the capture process before the Configuration screen
was recorded. No real key value or live indicator appears in the media.

The screenshot set covers the current Pursuit Brief, scientific notebook,
local document preview and temporary entity candidates, compact Investigation
Constellation, evidence relationship graph, deterministic report,
Configuration center, Sherlock and Neuromancer themes, and 390-by-844 mobile
layout. The mobile capture again measured `scrollWidth == clientWidth == 390`.

The replacement walkthrough is 121.7 seconds at 1440 by 900. It contains H.264
video, 48 kHz AAC narration/music, embedded English captions, a matching WebVTT
sidecar, and an accessible transcript. Integrated program loudness measured
-16.2 LUFS with a -0.8 dBFS true peak. Representative encoded frames at every
chapter boundary were extracted and OCR-checked for the intended current
feature label. The underscore was rendered from the current deterministic
Default, Sherlock, and Neuromancer score engines; it carries no analytical
meaning and remains beneath the narration.

## Security diff gate

The final exact-candidate Codex Security diff scan at `444c8e9` reviewed all
**40 of 40** compact worklist rows derived from **402 changed files** across the
v0.9.1–v0.9.5 release train. Scan
`f6b1b5ed-a64c-4b3b-aee5-acf8174aec82` sealed with complete coverage, no
deferred candidates, and **zero findings**.

All four findings discovered by the earlier exact-candidate scans are fixed
and independently verified:

- every POST route now rejects duplicate, signed, fractional, negative, and
  non-ASCII `Content-Length` values before reading a body while accepting
  standards-valid HTTP optional whitespace; and
- every human-review CSV cell beginning with `=`, `+`, `-`, `@`, tab, carriage
  return, or newline is emitted as inert text while the CycloneDX SBOM retains
  the exact dependency metadata; and
- JSON and each nonblank JSONL record receive a quote/escape-aware source-depth
  check before `json.loads`, followed by an iterative exact semantic-depth
  check, while outer request-object decoder recursion becomes a sanitized
  HTTP 400 response.

The regenerated candidate contains **140 components**. Its CSV has no cell
beginning with a guarded prefix; the SBOM retains the exact original values for
all **42** guarded scoped-package names. All four artifact checksums verify.

The exact original JSON and JSONL proof inputs now produce a bounded failed
preview with the configured nesting-limit message. They no longer raise
`RecursionError`, and a valid request immediately afterward succeeds. The
parser version is `pivotglass-bounded-preview-1.1` so receipts distinguish the
remediated behavior.

The scan also reproduced two product lifecycle defects: workspace clear did
not remove the approved v9-v11 document/proposal/snapshot record families, and
workspace delete left the sibling raw-document content directory. They were
rejected as security findings under the current single-user/same-account threat
model and corrected as release-blocking product behavior. Regression coverage
now proves that clear removes those records and raw bytes while preserving an
empty valid workspace, delete removes the workspace database and raw bytes,
failures produce no success receipt, and neither operation touches another
workspace.

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

## Dense visualization hover receipt

- Enrichment Activity and Investigation Constellation use the same stable
  matrix interaction: hover shows a viewport-fixed explainer without inserting
  content above the grid; click or Enter pins the detailed selection.
- Repeated real pointer movement across an indicator label and a Lite Brite
  status cell produced one stable tooltip, no hover-only selection panel, and
  identical top, left, width, and height measurements in all 16 samples.
- Pointer movement between child text nodes inside one indicator no longer
  schedules redundant whole-cockpit tooltip updates, and the status peg no
  longer changes scale on hover.

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

## Publication and v1.0 boundary

Final artifact generation, owner-key signing when an approved key is available,
GitHub Release creation, and clean public readback happen only after the source
commit is frozen; their receipts belong to the GitHub Release rather than this
source-archive member. Before v1.0, Pivotglass still requires an owner-reviewed
security policy and an explicit SCOT/Synapse stable-versus-preview decision.

The ordered publication ceremony and the one-time, owner-authorized replacement
of the earlier v0.9.5 tag are consolidated in the [v0.9.5 release
record](RELEASE_HANDOFF_V0.9.5.md).
