# Framework projections

Pivotglass can present the same evidence through different analytical lenses.
The framework projection layer currently provides the durable contract for
ATT&CK, Cyber Kill Chain, and Diamond Model mappings.

## What a mapping means

A mapping is a derived analytical view, not an observation. Every mapping
records:

- the framework and pinned content version;
- the framework content identifier and label;
- one or more evidence references and a plain-language basis;
- mapper identity and mapper version;
- origin (`human`, `automated`, or `model`);
- confidence and its rationale; and
- the current state (`proposed`, `accepted`, `rejected`, `superseded`, or
  `revoked`).

Model and automated mappings remain proposals until an analyst dispositions
them. A revoked mapping requires a reason. A projection never creates a
relationship, observation, hypothesis, or confidence assessment in another
part of the workspace.

## Commands

The TUI and shared command adapter expose the current records consistently:

```text
framework list
framework show attack <content-version>
framework show kill_chain <content-version>
framework show diamond <content-version>
```

`framework show` includes only the requested pinned content version and emits
gaps for requested content that has no accepted mapping. Framework content
packages and their versions are supplied by an optional adapter; Pivotglass
does not silently download or claim a current version.

## Migration and exchange

Fresh workspaces use schema v5. Existing workspaces migrate forward with the
same backup-first migration process used by v0.8. The new table is additive and
does not rewrite observations or analytic records. `framework list` exports a
secret-free envelope with schema version `framework-mappings-1.0`.

The next 0.9 slices can add pinned ATT&CK content, Kill Chain phase semantics,
Diamond events, Navigator export, and read-only Synapse/SCOT adapters while
continuing to use this mapping authority.
