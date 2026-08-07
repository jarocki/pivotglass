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
receipt so the empty workspace remains safely openable.
- Portable schema-v4 JSON exports include scientific lifecycle roots and links;
  model proposals retain their pending analyst disposition.

Migration support is forward-only. Downgrading an upgraded workspace in place
is not supported; use the preserved backup with the older release instead.
