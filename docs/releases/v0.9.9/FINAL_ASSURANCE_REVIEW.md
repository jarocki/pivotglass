# Final assurance review for the proposed Pivotglass v1.0.0

Date: 2026-09-29. Candidate reviewed: `befca6f699017a80cdad423b30e9e2f0a59e0973`
on `codex/v0.9.9-complete-documentation`, compared with public v0.9.8
`586a5f1a1309669d0a8a6e3af1ceea8a8bb5312d`. The reviewed tree declares
v0.9.9. This is the owner-facing quality gate, not a v1.0.0 release receipt.
The [release roadmap](../../plans/V0.9.8_TO_1.0_ROADMAP.md) requires owner
approval of this pass before assigning or publishing v1.0.0.

## Recommendation and stable scope

The local, single-analyst investigation core is ready for owner review as the
proposed v1.0.0 stable scope: explicit source admission and collection,
workspace persistence and recovery, provenance, bounded visualizations,
analyst-authored scientific analysis, and report/export. Keep the product's
documented [compatibility boundaries](../../COMPATIBILITY.md): SCOT4, Vertex
Synapse, and other named external integrations remain previews; PDF is a
recognition preview; OCR, Office/archive parsing, URL/RSS intake, and a
production multiuser/remote server remain deferred. Do not broaden these
capabilities by changing the version number. The owner must approve both this
scope and whether the prepared v0.9.9 work is published directly as v1.0.0.

## Evidence by assurance lens

| Lens | Verification and result | Limit |
| --- | --- | --- |
| Correctness | Full Python suite **4,277 passed, 2 skipped** in 223.85 s; browser suite **58 passed**; TypeScript lint and Ruff passed. The synthetic case retained explicit evidence links, competing explanations, SAT inputs/outputs, unresolved contradiction, and a Markdown report. | Passing tests do not prove a conclusion is correct; the analyst owns interpretation. |
| Resilience | The full suite covers workspace isolation, changed-workspace rejection, bounded document requests, invalid content length, local draft recovery, and failure/recovery contracts. The earlier [stopped-copy restore and hash-tamper exercise](QA.md#actual-interaction-and-recovery-evidence) passed. | No live SCOT4/Synapse round-trip or fixed active-provider cancellation latency is qualified. |
| Efficiency | A fresh [offline machine receipt](FINAL_QA_CAPACITY.json) stored 5,000 synthetic entities in 7.946 s; cockpit state built in 4.009 s at a 29.6 MiB traced Python peak. A 1,000-node/999-edge graph built state in 1.299 s at 20.9 MiB; no graph records were omitted. | One Apple arm64/macOS 15.7.4/Python 3.14.6 run; browser rendering, concurrency, large batch admission and live providers were not measured. See [capacity](../../CAPACITY.md). |
| Security | The sealed diff scan `f2249627-51d4-4d91-97f6-c02515765a83` covered all 23 changed source/config/test/generated-client review items against public v0.9.8 and found **zero plausible findings**. npm advisory audit reported zero vulnerabilities. `uv lock --check` passed. | A diff scan is not a whole-repository penetration test. Dependency advisories can change. The earlier 74-applicable-package Python advisory result is a dated v0.9.9 checkpoint, not a fresh independent result here. |
| Usability | In the running synthetic browser case, the report visibly offered both **PRINT / SAVE PDF** and **SAVE MARKDOWN**. The long URL wrapped across lines. The provenance history showed document ingestion, an explicitly labeled analyst group, and both admitted candidates; graph and coverage views distinguished grouping from observed relationships. The Novice Q&A and readable-value behavior also have regression and prior [interaction receipts](QA.md). | The browser check is a task walkthrough, not a user study or measured OJT outcome. The owner has accepted the logo and four videos; no new subjective audio rating is claimed. |

The initial sandboxed Python run had 17 loopback-socket `PermissionError`
failures (4,260 passed, 2 skipped). With socket access, the identical suite
passed completely. One existing SQLite datetime-adapter deprecation warning
remains. The 91-file documentation check found zero broken local
links/anchors; `git diff --check` and the release contract are separate final
publication checks.

## Packaging and release trust rehearsal

The candidate wheel and source archive built successfully. The source archive
contains all four films, both brand images, and all nine tracked marketing
documents; it excludes the separate `career-narrative/` project. The wheel
contains the packaged browser `index.html`. The unsigned trust rehearsal
generated a CycloneDX SBOM of **140 locked components** (77 Python, 63 npm),
license inventory, and checksums. These preliminary v0.9.9 archives are not
v1.0.0 artifacts and must not be signed or published as such.

Public `main` and the latest GitHub Release still identify v0.9.8. Pull request
[#9](https://github.com/jarocki/pivotglass/pull/9) is a mergeable draft at the
reviewed commit, with no remote status checks reported. The Overview link in
the social drafts points to `main` and will remain unavailable until the media
is public. Social posts, Signal messages, and `www.jarocki.org` have not been
published or updated by this repository pass.

## Owner decision and remaining publication work

1. Approve or amend the stable scope and the v1.0.0 assurance conclusion above.
2. After approval, synchronize all six machine version surfaces, README and
   Quick Start install examples, dated changelog, and marketing release-status
   language to v1.0.0. Rebuild and rerun the release contract and affected
   checks on that exact commit; repeat security review if behavior changes.
3. Build immutable v1.0.0 archives, SBOM, license inventory and checksums;
   review the bundle and sign `SHA256SUMS` with the owner-controlled release key.
4. Merge the approved release PR, tag its exact public-main commit, publish the
   GitHub Release and six trust artifacts, then download and verify the public
   signature, checksums, package version, tag target and main. Only then open
   every social/video link and publish the separate announcements.

The release remains **pending owner approval and the public trust ceremony**.
The assurance evidence supports a bounded local-core release; it does not
convert preview integrations or unmeasured outcomes into stable claims.

## Owner decision — 2026-09-29

The owner approved proceeding with v1.0.0 and directed a public GitHub push as
soon as the launch checklist is complete. The approved scope is the bounded
local, single-analyst core recommended above. External integration previews,
PDF recognition, and deferred intake/remote-server capabilities remain outside
stable qualification. This addendum records the decision; it does not rewrite
the earlier candidate evidence or claim the release ceremony has occurred.
