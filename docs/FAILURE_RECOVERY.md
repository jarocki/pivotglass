# Failure and recovery guide

Pivotglass should fail as a local investigation tool, not as a slot machine:
the state must say what failed, stored evidence must remain intact, and the
next safe action must be visible. A failed provider request is not an empty
result, and a canceled investigation is not a success.

## Recovery contract

| Failure | Authoritative result | What remains usable | Next safe action |
|---|---|---|---|
| Missing API credential | Service is `missing`; no request is made | Workspaces, evidence, graph, notes, reports, keyless sources | Open Configuration, add and test the credential, or leave the service disabled |
| Disabled service | Service is `disabled`; work is skipped | All local investigation functions | Enable deliberately if needed |
| Model unavailable or unlisted | Selection/check fails visibly | Deterministic collection, provenance, analysis, graph, report, export | Run `model show`, `model check`, or `model repair`; select only a provider-listed model |
| Provider/network failure | Enrichment event is `failed`, retryable, and appears in Attention Needed | Prior and partial evidence, notes, exports, other sources | Inspect sanitized detail, restore connectivity or configuration, then retry |
| Empty provider result | Enrichment event and all-source terminal state are `empty` | Entire local case | Treat as an observed lack of usable result, not success or safety |
| Operator cancellation | Request is acknowledged while the active call finishes; terminal state becomes `cancelled` and remaining work is skipped | Evidence already committed before cancellation | Review completed evidence; retry or queue only what is still needed |
| Stale browser build in a source checkout | Launch stops with an exact rebuild instruction | TUI/basic interfaces and workspace files | Run the documented web build, then relaunch |
| Failed or future-schema migration | Candidate switch fails; prior active workspace remains selected; pre-migration backup is preserved | Prior workspace and backup | Preserve both files, validate a copy, use the older compatible version if necessary |
| Malformed, hostile, encrypted, or oversized document | Preview fails, skips, or truncates with exact warnings | Workspace truth is unchanged because preview admits nothing | Inspect warnings; convert to a qualified format or reduce the file deliberately |
| SCOT4/Synapse/MCP outage or budget exhaustion | Preview/integration command fails with a bounded receipt; session cleanup is attempted | Local SQLite authority and all local analysis | Restore the preview integration, rerun a bounded read, and review before any approved write |

## Provider loss and retry

When an enrichment raises a network or provider exception, Pivotglass records a
source-fault event with **Retry** and **Details** actions. If no source produced
new evidence and any source failed, the investigation's terminal state is
`failed`—not `empty`. Stored evidence is append-only and remains available for
notes, graph review, report generation, and export.

Retry is a new execution attempt with its own lifecycle. It does not erase the
failed event or make the earlier request look successful.

## Cancellation

Cancellation is cooperative. The browser sets `cancel_requested` and adds an
operator-action event immediately. Pivotglass does not kill a provider client
while it may be committing a response. The active enrichment returns safely,
then the investigation becomes `cancelled`; queued enrichments receive
cancelled events and do not start.

This release does not promise a fixed cancellation latency because the active
provider timeout remains part of that duration. The [capacity envelope](CAPACITY.md)
keeps that boundary explicit.

## Workspace migration or corruption

Before opening a valuable older case:

```text
workspace schema case-name
```

The command checks schema and integrity and previews migration state. A normal
forward migration writes a sibling `pre-vN-backup` before changing the
workspace. Pivotglass validates a candidate connection before replacing the
active workspace, so a rejected future schema does not strand the session.

If integrity fails, stop Pivotglass and preserve the database and every backup.
Do not experiment on the only copy and do not downgrade an upgraded database
in place. Follow [workspace migration and recovery](WORKSPACE_MIGRATIONS.md).

## Stale browser assets

In an editable source checkout, Pivotglass compares the browser source and
static export. If the export is older, `ap` refuses to serve it and instructs
you to run:

```bash
cd web
npm ci
npm run build
cd ..
uv run ap
```

An installed wheel contains its qualified static export and does not need
Node.js at runtime.

## Verification receipt

The v0.9.5 failure/recovery group passed 44 focused tests covering masked and
missing configuration, keyless readiness, model selection and repair, provider
loss, retry, cancellation during the final active enrichment, stale static
assets, backup-first migrations from multiple schema generations, rejected
future schemas, hostile documents, parser exhaustion, bounded MCP responses,
compressed/oversized MCP cleanup, Synapse cancellation budgets, and TUI error
recovery cards.

The provider-loss rehearsal preserved existing evidence, accepted a local note,
produced a portable workspace export, kept the full cockpit usable, and
successfully ran a later retry. The final-enrichment cancellation rehearsal
ended `cancelled`, closing the previous last-loop lifecycle gap.
