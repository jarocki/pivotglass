# Pivotglass v0.9.6 release record

**Release branch:** `codex/v0.9.6-document-pivots`  
**Release state:** fully tested candidate authorized for merge, annotated tag,
public GitHub Release, and public readback

## Release decision

This is v0.9.6 because it introduces durable user-facing capabilities beyond
v0.9.5: explicit document admission, a persistent source library, governed
document/candidate/navigation graph layers, and a chronological pivot timeline.
It also fixes the cross-theme Constellation presentation and hover redraw defect.

## Completed capability receipts

- **Preview and admission are separate.** Preview remains temporary. Admission
  requires an explicit user action and a matching expected SHA-256.
- **The source library survives restart.** It lists occurrences, parser and
  extraction receipts, candidate counts, timestamps, and exact source digests
  without returning raw content during routine browser state reads.
- **Documents participate in the graph without weakening truth.** Document and
  candidate nodes use structural edges; exact normalized matches may bridge to
  independently admitted entities. No text match becomes evidence by itself.
- **The path through an investigation is visible.** Indicator, entity, and
  document navigation produces append-only `pivoted-to` events and a timeline.
  This layer is labeled derived navigation rather than observed threat relation.
- **Workspace lifecycle is complete.** Schema 12 is backup-first. Export and
  merge include the new metadata; merge copies raw bytes only after digest
  verification. Existing workspaces migrate without destructive rewriting.
- **The Constellation belongs to every theme.** All matrix surfaces use theme
  variables in seven character themes, Day and Night. Hover guidance is fixed
  to the viewport and does not cause rows to reflow.
- **Documentation and media match the implementation.** README, Quick Start,
  User Guide, migration, compatibility, safety, capacity, QA, screenshots,
  runtime version, package manifests, and changelog identify v0.9.6.

The detailed verification matrix is in [QA_V0.9.6.md](QA_V0.9.6.md).

## Publication and readback

The release is complete only when public `main`, annotated tag `v0.9.6`, the
GitHub Release, wheel metadata, source archive, checksums, and repository version
all agree on the final merge commit and version. Publication-time commit IDs,
artifact digests, and public URLs belong in the GitHub Release because adding
them here would alter the source archive being identified.

## Deferred closure

An owner-controlled detached signing identity remains an external trust gate if
no noninteractive signing key is available during publication. Pivotglass will
not fabricate a signature or store a private key in the repository. All other
release artifacts remain reproducible from the exact public tag.
