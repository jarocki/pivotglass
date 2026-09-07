# Pivotglass compatibility and maturity

This matrix separates the supported local core from qualified previews and
planned work. A dependency being installed does not make every capability it
contains a supported Pivotglass path.

| Surface | v0.9.6 status | Supported boundary |
|---|---|---|
| Python | Stable core | Python 3.12 or newer; tested release gates use the locked environment |
| Browser cockpit | Stable local core | Static Next.js export served by Pivotglass on loopback by default |
| Terminal interfaces | Stable local core | `ap tui` and `ap basic` share workspaces and deterministic command authorities |
| Workspace schema | Stable forward migration | Schema v12, backup-first; in-place downgrade is not supported |
| Flint | Qualified core | Exactly 0.4.0 for current bar, line, scatter, histogram, and radar intent paths |
| Plotly / editable Office charts | Not qualified | Presence in Flint 0.4 does not enable these backends |
| Text, Markdown, HTML | Qualified local intake | Preview first; explicit admission up to 10 MiB; active HTML not run |
| CSV, JSON, JSONL | Qualified local intake | Bounded rows, nesting, text output, exact skipped/error state, persistent receipt |
| RFC 5322 email | Qualified local intake | Message text and headers; attachments are named but not parsed |
| PDF | Recognition preview | Type/hash only; no text extraction or OCR claim |
| Office documents, images, archives | Deferred | No qualified parser, macro execution, archive expansion, or OCR |
| URL and RSS intake | Deferred | No browser document-preview network retrieval or SSRF surface |
| Entity candidates | Qualified review input | Deterministic exact spans; admission persists candidates but never auto-promotes them to evidence |
| Document library | Qualified local core | Display-safe inventory, content hashes, parser/extraction receipts, verified workspace merge; raw bytes stay local |
| Pivot trail | Qualified local core | Append-only workflow history and timeline; never presented as a threat relationship |
| Model-assisted proposals | Internal authority | Span-grounded immutable records and human review exist; live browser/model workflow is deferred |
| SCOT4 | Preview integration | Governed read/publication planning; stable status requires disposable live round-trip and recovery |
| Vertex Synapse | Preview integration | Governed MCP/model/view planning; not the v1.0 primary graph backend yet |
| go-roast / Nucleotide | Preview analysis | Bounded local adapters and proposals; no automatic control deployment or attribution |

## Capacity envelope

These limits are enforced and fail visibly or degrade to an explicitly bounded
view:

- browser document request: 14 MiB JSON envelope;
- raw document preview: 10 MiB;
- browser parser output: 100,000 characters;
- browser candidate extraction: 2,000 candidates and 60 characters of context
  on each side;
- internal parser output: 2,000,000 characters unless a lower limit is chosen;
- internal extraction: 10,000 candidates unless a lower limit is chosen;
- cluster snapshot: 50,000 nodes and 100,000 edges;
- one visualization intent: 5,000 combined rows, nodes, and edges;
- relationship visualization: 1,000 nodes within the combined record limit;
- Investigation Constellation: 555 indicators / 4,995 dimension rows, with an
  exact omitted count beyond that boundary;
- force-layout canvas: 48 filtered nodes at a time.

The [capacity envelope](CAPACITY.md) records the reproducible 5,000-entity
storage/export and 1,000-node connected-graph qualification measurements.
Batch-document intake, workspaces beyond 5,000 entities, and active-provider
cancellation latency remain unqualified. Pivotglass must not silently omit data
when a limit is exceeded.

The [failure and recovery guide](FAILURE_RECOVERY.md) defines terminal-state,
data-preservation, and next-action behavior for local and optional-provider
failures.

## Release rule

Preview means the truth and safety boundary is implemented and tested, but the
end-to-end operational path is not yet stable. Deferred means the product does
not claim the capability. A v1.0 feature may remain preview only when the UI,
help, exports, and release notes all say so consistently.
