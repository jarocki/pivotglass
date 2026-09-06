# Data ownership, network use, and recovery

Pivotglass is local-first. Local-first is a deployment boundary, not a promise
that no data ever leaves the computer: enabled intelligence services, model
providers, SCOT, and Synapse receive only the values submitted through their
explicit commands or workflows.

## Local data

- Configuration and credentials live beneath `~/.ap/` unless the operator
  chooses another configuration directory.
- Workspaces are SQLite databases beneath `~/.ap/workspaces/` by default.
- Workspace migrations create a sibling pre-migration backup before the first
  schema change.
- The v0.9.5 browser document path is temporary preview. It does not store the
  selected file, parsed text, candidates, evidence, relationships, or model
  prompts.
- The internal document authority has a content-addressed `<workspace>.content`
  store and database receipts. Persistent browser admission and portable
  document-byte export remain deferred. Exact-confirmed `workspace clear` and
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

## Backup and recovery

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

## v0.9.5 document-lifecycle boundary

Document-byte export and persistent browser admission are deliberately not
exposed. The public intake UI remains preview-only, so selecting a document
there creates no stored document state. Existing internal document state can be
purged only through an explicit, confirmed workspace clear or delete; neither
operation removes separately generated reports or migration backups. Persistent
browser admission must add its own visible retention, export, and purge controls
before it can be called stable.
