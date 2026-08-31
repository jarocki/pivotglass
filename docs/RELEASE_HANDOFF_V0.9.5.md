# Pivotglass v0.9.5 release handoff

**Candidate branch:** `codex/v0.9.5-closure`

**Candidate state:** locally frozen; not merged, tagged, pushed, signed, or
published

**Public readback at 2026-08-31 02:05 MDT:** public `main` is
`f50864ff864863689ed10b04e24e0ee56bbc2abb`; the latest GitHub Release is
`v0.9.0`, published 2026-08-26, with its wheel, source archive, and checksum
manifest. No external state was changed while preparing this handoff.

## Release decision

The candidate is ready for owner review as a truthful v0.9.5 early-availability
checkpoint. It is not a completed public release. From this handoff forward,
the branch should accept only release hygiene, an explicitly approved fix for
the open low-severity security finding, or a correction required by a failed
gate. New capability belongs in a later version.

## Completed receipts

| Obligation | Receipt |
|---|---|
| Version and identity | `pyproject.toml`, runtime package, Python lock, npm manifests, README, Quick Start, and changelog agree on 0.9.5; `ap`, `adversary-pursuit`, and `~/.ap/` remain compatibility names |
| No-key learning path | `workspace learn <name>` completes an offline synthetic evidence-to-report workflow with provenance, alternatives, contradiction, gaps, export, restart, and file-copy recovery; a socket guard proves creation makes no network connection |
| Stable/preview/deferred boundary | `docs/COMPATIBILITY.md`, product text, data-safety guidance, and the quality record agree; SCOT4, Synapse, go-roast, Nucleotide, document preview, and model proposals do not silently become stable authorities |
| Capacity | Reproducible 5,000-entity storage/export and 1,000-node graph receipts; overflow remains visible and stored evidence is not deleted |
| Failure and recovery | Provider failure, retry, cooperative cancellation, stale assets, migration failure, hostile input, and integration outage paths preserve local work and expose next actions |
| Python | One unrestricted complete replay passed **4,148 tests**, skipped 2 platform/availability cases, and emitted one known SQLite adapter deprecation warning |
| Web and static checks | Python static analysis, TypeScript, advisor/arcade/visualization tests, production export, lock checks, and npm vulnerability/provenance gates passed as recorded in `docs/QA_V0.9.5.md` |
| Browser interaction | Phone, laptop, and desktop replay verified no document overflow, local document/candidate preview, Help fit, Escape restoration, command focus, and Day/Night modes |
| Package lifecycle | Clean archive and disposable installed-wheel checks cover version, packaged web root/health, offline learning fixture, upgrade from v0.9.0, and uninstall. The wheel resolved newer compatible dependencies, so the tagged source checkout with `uv sync --frozen` remains the supported exact-lock install |
| Security diff | Every worklist row completed; no critical, high, or medium finding; one reproducible low local/LAN availability finding remains open and visible |
| Release trust | The exact lockfiles generate a deterministic CycloneDX 1.5 SBOM and CSV inventory for **77 Python + 63 npm** components. An exact-commit candidate build produced a 140-component SBOM, 141 dependency records, zero missing license declarations, and four verified SHA-256 entries |

## Explicit release boundaries

These are not v0.9.5 stable claims:

- PDF text extraction/OCR, Office/image/archive parsing, URL/RSS/batch intake,
  and persistent browser admission/export/purge;
- live browser model-proposal submission and disposition;
- SCOT4 or Synapse as a production authority backend;
- live disposable SCOT4/Synapse round-trip, conflict, outage, and rollback
  qualification;
- Plotly/editable-Office Flint output;
- active-provider cancellation within a fixed latency, multi-user remote
  serving, or capacity beyond the published local envelope; and
- a match-or-exceed claim against SCOT4 or Synapse on the planned shared
  document corpus.

The original document-ingestion target remains in
`docs/plans/V0.9.5_DOCUMENT_INGESTION.md` for traceability. Its header now
points to the narrower executable v0.9.5 contract and carries the remainder as
v1.0 gates.

## Owner decisions and external gates

1. **Security fix approval.** The completed diff scan found one low-severity
   request-thread availability weakness: a negative `Content-Length` reaches
   `read(-1)` until peer EOF. The scan workflow requires explicit approval
   before changing the reviewed diff. If approved, reject negative lengths,
   add a raw-socket regression, rerun focused/full tests, and rerun the final
   security diff scan.
2. **Security policy.** GitHub private vulnerability reporting is currently
   disabled and no owner-approved `SECURITY.md` route exists. Before v1.0, the
   owner must approve scope, supported versions, private contact, response and
   disclosure expectations, exclusions, and accepted risks; then enable and
   verify the selected private route.
3. **Signing identity.** Select an owner-controlled signing key, verify its full
   fingerprint, and publish the fingerprint through an independently
   controlled channel. No private key belongs in the repository or a model
   prompt.
4. **Publication authority.** Merge, tag, push, GitHub Release creation, and
   upload are external writes and were not performed by this overnight local
   burndown.

## Publication sequence after approval

1. Resolve or explicitly disposition the low security finding without hiding
   it.
2. Run all gates from a clean archive of the final reviewed commit.
3. Build the wheel and source archive into a new empty directory.
4. Generate SBOM, license inventory, and checksums with
   `scripts/generate_release_trust.py`.
5. Review the inventory and sign `SHA256SUMS` using the approved owner key.
6. Merge the reviewed branch to public `main`.
7. Create annotated tag `v0.9.5` at that exact merge commit and verify the tag
   before pushing it.
8. Publish all six release artifacts: wheel, source archive, SBOM, CSV license
   inventory, checksum manifest, and detached signature.
9. Download the public assets into a new directory; verify the signature and
   every checksum.
10. Read back public `main`, tag target, release metadata, wheel metadata, and
    source archive. They must all resolve to version 0.9.5 and the intended
    release commit before announcing completion.

The exact commands and truth boundary are in
[Release trust artifacts and public readback](RELEASE_TRUST.md).
