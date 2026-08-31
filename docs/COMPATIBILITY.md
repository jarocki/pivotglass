# Pivotglass compatibility and maturity

This matrix separates the supported local core from qualified previews and
planned work. A dependency being installed does not make every capability it
contains a supported Pivotglass path.

| Surface | v0.9.5 status | Supported boundary |
|---|---|---|
| Python | Stable core | Python 3.12 or newer; tested release gates use the locked environment |
| Browser cockpit | Stable local core | Static Next.js export served by Pivotglass on loopback by default |
| Terminal interfaces | Stable local core | `ap tui` and `ap basic` share workspaces and deterministic command authorities |
| Workspace schema | Stable forward migration | Schema v11, backup-first; in-place downgrade is not supported |
| Flint | Qualified core | Exactly 0.4.0 for current bar, line, scatter, histogram, and radar intent paths |
| Plotly / editable Office charts | Not qualified | Presence in Flint 0.4 does not enable these backends |
| Text, Markdown, HTML | Qualified preview | Explicit local file, 10 MiB maximum, active HTML not run |
| CSV, JSON, JSONL | Qualified preview | Bounded rows, nesting, text output, and exact skipped/error state |
| RFC 5322 email | Qualified preview | Message text and headers; attachments are named but not parsed |
| PDF | Recognition preview | Type/hash only; no text extraction or OCR claim |
| Office documents, images, archives | Deferred | No qualified parser, macro execution, archive expansion, or OCR |
| URL and RSS intake | Deferred | No browser document-preview network retrieval or SSRF surface |
| Entity candidates | Qualified preview | Deterministic exact spans; temporary browser output and internal persistence authority only |
| Model-assisted proposals | Internal authority | Span-grounded immutable records and human review exist; live browser/model workflow is deferred |
| SCOT4 | Preview integration | Governed read/publication planning; stable status requires disposable live round-trip and recovery |
| Vertex Synapse | Preview integration | Governed MCP/model/view planning; not the v1.0 primary graph backend yet |
| go-roast / Nucleotide | Preview analysis | Bounded local adapters and proposals; no automatic control deployment or attribution |

## Capacity envelope

These limits are enforced and fail visibly:

- browser document request: 14 MiB JSON envelope;
- raw document preview: 10 MiB;
- browser parser output: 100,000 characters;
- browser candidate extraction: 2,000 candidates and 60 characters of context
  on each side;
- internal parser output: 2,000,000 characters unless a lower limit is chosen;
- internal extraction: 10,000 candidates unless a lower limit is chosen;
- cluster snapshot: 50,000 nodes and 100,000 edges.

Large-scale graph rendering, workspace/database size, batch-document intake,
cancellation latency, memory, and export-time envelopes still require measured
v1.0 receipts. Pivotglass must not silently omit data when a limit is exceeded.

## Release rule

Preview means the truth and safety boundary is implemented and tested, but the
end-to-end operational path is not yet stable. Deferred means the product does
not claim the capability. A v1.0 feature may remain preview only when the UI,
help, exports, and release notes all say so consistently.
