# Data ownership, network use, and recovery

Pivotglass is local-first. Local-first is a deployment boundary, not a promise
that no data ever leaves the computer: enabled intelligence services, model
providers, SCOT, and Synapse receive only the values submitted through their
explicit commands or workflows.

## Local data

- Configuration and credentials live beneath `~/.pivotglass/` unless the operator
  chooses another configuration directory.
- Workspaces are SQLite databases beneath `~/.pivotglass/workspaces/` by default.
- Workspace migrations create a sibling pre-migration backup before the first
  schema change.
- The browser document path previews first and stores only after the
  analyst chooses a source-only or source-plus-selected-entities admission.
  Preview alone stores nothing.
- Explicit admission writes original bytes to the content-addressed
  `<workspace>.content` store and writes occurrence, parser, extraction, and
  candidate receipts to the workspace database. Ordinary browser state and
  library polling never return the original bytes. Exact-confirmed `workspace clear` and
  `workspace delete` do remove any existing internal raw-document bytes and
  their managed database records.
- Logs and browser diagnostics are sanitized, but an operator should still
  review support artifacts before sharing them.

## Secrets

Credentials are masked by default and are not returned by routine state
polling. Do not put keys, authorization headers, private report text, or secret
URLs in the command field, notes, screenshots, exports, or model prompts.
Document-model proposal receipts retain hashes rather than raw prompts and
responses.

## Network actions

Local preview and deterministic candidate extraction make no network or model
request. Enrichment and external integrations are separate actions. URLScan
may submit an indicator to an external browser service; model synthesis may
send selected context to the configured provider; SCOT and Synapse operations
use their documented preview, approval, and receipt gates.

The browser server listens on `127.0.0.1` by default. Binding it to a LAN
address exposes the unauthenticated HTTP interface to devices that can reach
that network. Use LAN exposure only on a trusted network, stop the service when
finished, and do not treat HTTP as encrypted transport.

The optional advisor voice uses AI-generated speech through the configured
OpenAI key when available: narrated text is sent to OpenAI. A device voice is
the fallback. Voice and procedural music start disabled; choose them explicitly.
Music synthesis is local presentation and sends no case data. Character speech,
guidance, and music never establish evidence or confidence.

## Browser-local learning drafts

Novice Q&A answers, edited drafts, and reflections stay in this browser's local
storage for the workspace. Only explicitly saved questions enter the analytic
ledger; those answers are reported context, not verified observations. Clear
local drafts separately when using a shared browser. Practice counters record
participation and do not certify analyst expertise or change guidance levels.

## Backup and recovery

Use the [stopped-home backup and isolated restoration runbook](operations/OPERATIONS.md#backup-and-restoration)
for a case with original source bytes. A database-only copy or JSON record
export is not a full document-library backup.

Run `workspace schema` before opening a valuable older workspace. Keep its
`pre-vN-backup` file until the migrated workspace passes integrity checks and a
portable export has been reviewed. Clear and delete deliberately do not remove
sibling `*.pre-vN-backup` migration backups or generated `<workspace>-report.md`
files; those are separate recovery and publication artifacts. Review and manage
them explicitly after the workspace operation. If migration fails, preserve both files and
open a copy of the backup with the older Pivotglass version; do not downgrade
the upgraded database in place.

Large views keep an exact omission count and leave omitted evidence in the
workspace. Use the complete export rather than treating a bounded browser view
as the whole case. See the [capacity envelope](CAPACITY.md).

Provider loss, cancellation, stale browser assets, hostile input, and
integration outages do not authorize deletion or rewriting of local evidence.
See the [failure and recovery guide](FAILURE_RECOVERY.md).

## Document and entity lifecycle boundary

Persistent browser admission is explicit and produces a visible receipt.
Selecting or previewing a file still creates no stored state. Admitted source
bytes and their database records are purged only through an explicit, confirmed
workspace clear or delete; neither operation removes separately generated
reports or migration backups. Workspace merge verifies each content hash before
copying original bytes. Portable JSON export contains document metadata,
parser/extraction receipts, candidates, and pivot events, but not raw source
bytes; preserve or merge the sibling content store when exact originals must
move with the investigation.

Candidate strings do not become entities merely because a source is stored.
The analyst must select them. Each browser selection is bound to the reviewed
source hash, exact parser span, normalized value, extraction rule, and rule
version. A stale or altered selection fails before storage. Selected entities
enter the same STIX and immutable-observation authority as other workspace
entities and retain the source hash and parser transformation as provenance.
This admission records an analyst decision; it does not assign a verdict,
validate the source's claim, fabricate a relationship, or attribute an actor.

## Rendering untrusted sources

Through v1.2.0 the browser never received source bytes or source markup; it
showed only parser text. From v1.3.0, indicator focus mode shows sources as
their authors laid them out, which changes that boundary. The change is
deliberate and bounded:

| Format | What reaches the browser | Containment |
| --- | --- | --- |
| Text, CSV, JSON, JSONL, email | Parser text only, unchanged from v1.2.0 | Rendered as text; no markup is interpreted |
| HTML, Markdown | Markup rebuilt by the server from an allowlist (`core/document_rendering.py`) | No script, event handler, style attribute, form, frame, object, image source, or link target survives. Displayed in an `<iframe sandbox="allow-same-origin">` without `allow-scripts`, under a `default-src 'none'` policy |
| PDF | The original bytes, verified against their SHA-256 | Served only from `/api/documents/<id>/source`, only for PDFs, with `Content-Security-Policy: sandbox` and `Content-Disposition: attachment`. pdf.js 6 draws pages onto a canvas; its scripting sandbox is not loaded, so PDF JavaScript and XFA never run |

A rendering cannot make a network request: there is no attribute or style
left that names a URL. Link targets and image alt text remain visible to the
analyst as inert labels. An unstored preview is rendered from the copy sent
for preview (PDF: the browser's own copy) and leaves nothing behind.

## Indicator tags

Tags are analyst classification, stored as append-only events in the active
workspace (`indicator_tag_events`, schema v13). They are keyed by indicator
type and value, so they follow an indicator across sources and through
admission. They are included in workspace export and merge. A tag never
becomes evidence and is never sent to an enrichment provider.
