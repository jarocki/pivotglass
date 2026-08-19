# Investigation graph

Pivotglass has one evidence substrate and two graph lenses over it. It does not
copy evidence into a second graph database merely to draw a diagram.

## Entity layer

Entity nodes are stored STIX objects labeled with the actual indicator or
entity value. An **observed** edge comes from a stored STIX Relationship Object
and retains the relationship record or its immutable observation as
provenance. A **derived navigation** edge is a conservative pivot based on a
strongly typed property, such as an exact hash or explicit reference. It is
visually and structurally distinct from an observed relationship.

Broad similarities such as a shared country or provider do not create edges.

## Epistemic layer

The epistemic layer projects the records that explain how the analyst knows—or
does not know—something:

- immutable observations;
- investigation questions;
- assertions, including exposed assumptions;
- competing hypotheses;
- support and contradiction links;
- framework mappings and supersession;
- confidence and likelihood assessments attached to their target judgment.

Bridge edges connect an observation to the normalized entity it observed and a
structured assertion to its subject or object entity. Every edge has one or
more provenance references and a plain-language rationale.

## Current command

```text
graph          # existing indicator-first relationship view
graph layers   # investigation-graph-1.0 entity + epistemic projection
```

`graph layers` is deterministic and read-only. It does not invoke a model,
infer a new relationship, or modify workspace state.

## Current boundary

The v0.9 foundation defines and verifies the projection contract. The editable
workspace remains open work: saved layouts, pinning, multiselect, annotations,
manual assertion/link creation, undo/redo, filters, and layered exports must
write only through their existing authorities. Node position is presentation
state and must never alter evidence.

The web cockpit does not yet add a separate download of the complete layered
provenance graph. Remote Pivotglass sessions may be configured without access
control, so that export must wait for an authenticated or explicitly local-only
boundary. The existing workspace exports remain available through their
documented command and data-handling contract.
