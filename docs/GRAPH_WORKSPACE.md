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

## Commands

```text
graph          # existing indicator-first relationship view
graph layers   # investigation-graph-1.0 entity + epistemic projection
graph layout list
graph layout show Triage view
graph layout save Triage view | {"positions":{},"pinned_refs":[],"filters":{},"viewport":{"x":0,"y":0,"scale":1}}
graph layout delete Triage view --confirm Triage view
graph annotate entity:domain-name--... | Why this node matters
graph annotations entity:domain-name--...
```

`graph layers` is deterministic and read-only. It does not invoke a model,
infer a new relationship, or modify workspace state.

## Saved graph workspace

Workspace schema v6 stores named graph presentation layouts. A layout contains
validated positions, pinned node references, allow-listed filters, and a pan/
zoom viewport. Saving or reopening a layout cannot modify graph nodes, edges,
observations, assertions, mappings, confidence, or likelihood.

Pivotglass exposes the same authority through the relationship view. Analysts
can name and save a view, reopen it, pin the selected node, and undo or redo
view changes. An annotation resolves through a node in the current graph and is
stored by the existing analyst-note authority. It is labeled analyst-authored
context, not observed evidence.

## Current boundary

The v0.9 foundation now defines and verifies the projection and saved-layout
contracts. Expand/collapse, multiselect, manual assertion/link creation, richer
typed filters, and complete layered exports remain open. Manual relationships
must use the analytic assertion authority; a screen position or annotation can
never manufacture an edge. Node position remains presentation state and never
alters evidence.

The web cockpit does not yet add a separate download of the complete layered
provenance graph. Remote Pivotglass sessions may be configured without access
control, so that export must wait for an authenticated or explicitly local-only
boundary. The existing workspace exports remain available through their
documented command and data-handling contract.
