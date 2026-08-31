# Workspace migration and recovery

Pivotglass workspaces are durable investigation records, not disposable caches.
Beginning with the v0.8 schema, each workspace carries an explicit schema
version. Pivotglass checks that version whenever it opens the workspace.

## Preview and validate

Run this before upgrading a valuable workspace:

```text
workspace schema
workspace schema case-name
```

The command is read-only. It reports the current and target versions, whether
the migration is supported, the planned steps and backup path, SQLite's
integrity result, and any missing required tables. A future schema version is
rejected instead of being opened by an older Pivotglass build.

## What an upgrade does

The first v1-to-v2 upgrade performs these operations in order:

1. creates a sibling `NAME.db.pre-v1-backup` copy;
2. adds the epistemic-ledger tables;
3. backfills each legacy STIX object and relationship as a legacy observation;
4. writes the schema-version receipt;
5. validates the resulting schema when requested with `workspace schema`.

The normalized STIX records are not rewritten. The backfill labels unknown
legacy source details as `legacy` or `legacy/unknown`; it does not invent them.

The v2-to-v3 upgrade uses the same sibling-backup rule. It adds durable
hunt-challenge records and self-describing badge metadata: description, rarity,
simple artwork key, glyph, and originating challenge. Existing badge awards
remain valid; their new optional fields remain empty because the migration does
not invent historical context. A v1 workspace advances through both steps in a
single checked migration.

The v3-to-v4 upgrade adds the scientific-investigation root and lifecycle-link
tables. It organizes existing questions, hypotheses, assumptions, assertions,
and Structured Analytic Technique runs without copying or rewriting their
authoritative records. It also bridges the legacy Predictions Log into the
lifecycle while retaining the original log as historical input. A malformed
legacy log becomes an explicit knowledge gap instead of being silently ignored.
The backup is named `NAME.db.pre-v3-backup` when this is the first step required
for that workspace.

The v4-to-v5 upgrade adds the append-only `framework_mapping_records` table.
Mappings retain pinned framework content versions, evidence references, mapper
provenance, confidence rationale, analyst disposition, and revocation or
supersession state. Existing observations and analytic records are untouched.
The backup is named `NAME.db.pre-v4-backup` when this is the first step required
for that workspace.

The v5-to-v6 upgrade adds restart-safe, secret-safe execution claims and
receipts for explicitly approved external mutations. These records prevent a
timeout or restart from silently replaying a SCOT or Synapse write.

The v6-to-v7 upgrade adds `graph_presentation_layouts`. The v7-to-v8 step
reconciles an earlier development-only table shape and adds saved pins while
preserving bounded coordinates, viewport, and filter text. A layout holds only
node coordinates, viewport, filter text, and optional display labels. It
cannot hold evidence or relationships. The backup is named
`NAME.db.pre-v6-backup` when this is the first step required.

The v8-to-v9 upgrade adds content, occurrence, and parser-receipt tables for
governed document intake. It does not extract entities, create relationships,
or alter existing evidence. Original bytes use a separate content-addressed
store when an analyst explicitly admits a document; the v0.9.2 browser path is
preview-only and creates none of these records. The backup is named
`NAME.db.pre-v8-backup` when this is the first step required.

The v9-to-v10 upgrade adds deterministic extraction receipts, exact-span
entity candidates, and presentation-only evidence-cluster snapshots. A
candidate retains parser-output character and UTF-8 byte offsets, line and
column, context, normalization rule, and review state; it is not an admitted
STIX object or graph node. Cluster snapshots record graph presentation state
for longitudinal comparison and do not alter prior evidence. The backup is
named `NAME.db.pre-v9-backup` when this is the first step required.

The v10-to-v11 upgrade adds immutable, span-grounded entity, relationship, and
behavior proposals plus append-only human dispositions. Model proposals retain
provider/model identifiers and prompt/response hashes, not raw prompts or
responses. An accepted disposition still does not materialize an entity,
relationship, framework mapping, or publication. The backup is named
`NAME.db.pre-v10-backup` when this is the first step required.

## Recovery

If migration fails, Pivotglass leaves the prior active workspace selected and
reports the failure. Do not overwrite the failed database. Stop Pivotglass,
copy the sibling backup to a new workspace name, and open that copy with the
older release that created it. For example:

```sh
cp ~/.ap/workspaces/case.db.pre-v3-backup ~/.ap/workspaces/case-recovery.db
```

This creates a recoverable copy while preserving both the failed database and
the original backup. Keep the backup until you have validated the upgraded
workspace and exported its investigation record.

## Data handling guarantees

- Provider credentials, URL query strings, URL fragments, and embedded URL
  user information are not stored as source endpoints.
- Normalized entities may deduplicate; observations do not.
- Corrections, retractions, and supersessions are append-only disposition
  events. They do not edit the original observation.
- Clearing a workspace removes investigation content but retains the schema
  receipt and external-publication audit receipts. The latter prevent a
  cleared or restarted workspace from silently repeating remote side effects.
- Portable JSON exports include scientific lifecycle roots, links,
  framework mapping records, secret-safe integration execution receipts, and
  presentation-only graph layouts; model proposals retain their pending
  analyst disposition. Document bytes and document-receipt tables are not yet
  portable in v0.9.2, so persistent document admission remains an internal
  foundation rather than a supported browser action.

Migration support is forward-only. Downgrading an upgraded workspace in place
is not supported; use the preserved backup with the older release instead.
