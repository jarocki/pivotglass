# Pivotglass v1.0.0 release qualification

Date: 2026-09-29. The repository owner approved the bounded local,
single-analyst v1.0.0 scope described in the
[final assurance review](../v0.9.9/FINAL_ASSURANCE_REVIEW.md) and directed public
GitHub publication after the [launch checklist](../../marketing/LAUNCH_CHECKLIST.md).
This receipt qualifies the source candidate; the public release, signature,
tag, and downloadable readback require a separate publication receipt.

## Scope and carried-forward evidence

The stable core includes deliberate source admission and collection, local
workspace persistence and recovery, provenance, bounded evidence views,
analyst-authored structured analysis, and report/export. SCOT4 and Vertex
Synapse remain previews; PDF recognition remains a preview; OCR, Office and
archive parsing, URL/RSS intake, and authenticated multiuser serving remain
deferred. There is no measured productivity, correctness, or training-outcome
claim. The [final assurance review](../v0.9.9/FINAL_ASSURANCE_REVIEW.md)
records the earlier correctness, resilience, efficiency, security, and
usability evidence and its limits.

## Exact v1.0.0 candidate checks

| Check | Result |
| --- | --- |
| Six machine version surfaces, README, Quick Start, dated changelog, and tag contract | `python scripts/check_release_contract.py --base origin/main --tag v1.0.0` passed |
| Python lock consistency | `UV_CACHE_DIR=/tmp/pivotglass-uv-cache uv lock --check` passed, resolving 78 packages |
| Python suite with loopback integration access | **4,277 passed, 2 skipped** in 241.43 seconds; one existing SQLite datetime-adapter deprecation warning |
| Focused media, branding, release contract and trust tests | 32 passed |
| Browser tests | 58 passed |
| TypeScript lint and production browser build | Passed |
| Ruff | Passed for `src`, `tests`, and `scripts` |
| Locked npm install and advisory audit | `npm --prefix web ci` succeeded; `npm --prefix web audit --audit-level=moderate` found zero vulnerabilities |
| Documentation links and headings | 92 Markdown files checked; zero broken local links or anchors |
| Media integrity | Four renamed v1.0.0 MP4s retain the exact bytes and SHA-256 values in the series verification record; all edit-manifest capture references resolve |
| Diff hygiene | `git diff --check` passed before packaging |

The initial browser test invocation overlapped a versioned test-fixture edit
and reported two filename mismatches. Re-running the final v1.0.0 test tree
passed all 58 tests. A focused Python invocation likewise found one hard-coded
old media stem during the rename; it was corrected before the 32 focused tests
and full suite passed. These were candidate migration issues, not shipped
failures.

## Publication boundary

The source archive and wheel must be built from the exact committed tree. The
SBOM, license inventory, SHA256SUMS and owner-key detached signature must bind
those immutable archives. Public `main`, the tag, Release metadata, and
downloaded files must then be read back and agree. Until that happens this is
a qualified candidate, not a completed public release.
