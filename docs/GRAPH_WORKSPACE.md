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
graph layout list
graph layout show Analyst-view
graph layout delete Analyst-view --confirm Analyst-view
```

`graph layers` is deterministic and read-only. It does not invoke a model,
infer a new relationship, or modify workspace state.

## Saved presentations

In Pivotglass, open **Evidence relationships** under **Charts & Evidence**.
Drag nodes, pan or zoom, optionally filter the visible subset, pin important
nodes in view, and collapse or expand a selected node's direct connections.
Collapsed nodes remain in the exact-data inventory and exports. Enter a layout
name and choose **Save view**. The presentation is stored in the active
workspace and survives refreshes and restarts. It is included in portable
workspace exports and merges.

A saved presentation contains only bounded node coordinates, viewport, filter
text, and optional display labels. It cannot contain nodes, edges, evidence, or
relationships. Loading a layout resolves it against the current graph and
reports new or absent nodes instead of hiding graph drift. Deleting a layout
deletes only this presentation record.

## Current boundary

The v0.9 foundation defines and verifies the projection contract and durable
saved layouts. Drag, pan, zoom, text filtering, pinning, presentation labels,
evidence drill-down, multiselect, annotated manual assertions, correction
history, direct-connection collapse/expand, named presentation management, and
layered exports are implemented. General presentation undo/redo and richer
relationship filters remain open; they must write only through their existing
authorities. Node position and collapsed visibility are presentation state and
never alter evidence.

The governed layered graph can be exported through the shared `graph export`
command as JSON, CSV, or GEXF. Remote Pivotglass sessions may be configured
without access control, so operators must treat exports according to their
workspace's data-handling requirements.
