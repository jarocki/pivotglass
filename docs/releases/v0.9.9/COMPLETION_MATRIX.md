# v0.9.9 request and completion matrix

Prepared 2026-09-28 for the current candidate. This reconciles the original
v0.9.8 release request and the subsequent v0.9.9 marketing/enablement scope.
The owner identified the current demo and substantive documentation as
unfinished after v0.9.8 publication. This matrix records the concrete completion
work; it does not retrospectively declare those deliverables complete in v0.9.8.

**Status definitions:** delivered means repository material or executable
behavior exists; qualified means a recorded check covers the current candidate;
published means public objects and downloaded bytes were verified. These are
separate states. The [QA checkpoint](QA.md) records current test evidence and open final-media
and publication gates; do not substitute prior-release counts.

## Original v0.9.8 instructions

| Requested outcome | Delivered artifact or behavior | Qualification and limits |
| --- | --- | --- |
| Run all existing tests and add necessary tests | Full Python and browser suites; regression coverage for renamed entrypoints, explicit home migration, evidence links, analyst-group graph state, and media/docs links | Current complete-suite results belong in the final QA receipt. Focused checks alone do not satisfy the full-suite gate. |
| Replace product/command references with Pivotglass | Installed `pivotglass` command, `pivotglass` distribution/import package, `PIVOTGLASS_*` configuration names; [migration guide](../../QUICKSTART.md#preserve-data-from-an-earlier-installation) | Legacy stored-extension reading and explicit migration preserve historical user data. Legitimate unrelated terms are not renamed. Protected/private contexts retain their preservation boundaries. |
| Document plan and changes | [Completion plan](../../plans/V0.9.9_COMPLETION_PLAN.md), [roadmap](../../plans/V0.9.8_TO_1.0_ROADMAP.md), [Changelog](../../../CHANGELOG.md) | Plans state intent; QA/public readback establish execution. |
| Review documentation as a coherent product story | [Landing story](../../../README.md), [documentation paths](../../README.md), [User Guide](../../USER_GUIDE.md), [Quick Start](../../QUICKSTART.md) | Experienced-analysis and newcomer editorial roles challenge evidence claims, usability, pacing, and missing executable routes. These are agent-assisted reviews, not a real-user outcome study. |
| Explain effectiveness, efficiency, and learning | [Product story](../../../README.md#why-it-exists), [analytical method](../../analysis/README.md), [learning and reflection](../../analysis/LEARNING.md) | Explain inspectable reasoning and reduced repeated handling as design mechanisms; no measured productivity or training-effectiveness claim. |
| Provide architectural diagrams and workflow graphs | [Architecture](../../architecture/README.md), [scientific process](../../analysis/README.md#the-scientific-investigation-loop), [landing workflow](../../../README.md#the-investigation-loop) | Logical diagrams identify authorities and boundaries; target integrations remain distinct from current deployment. |
| Show visualizations and their analytical use | [Visual reading guide](../../analysis/VISUALIZATIONS.md), current graph/coverage/history screenshots, exact-data interface | Graph edge bases, grouping, coverage, confidence, and likelihood remain distinct. Layout is not analytical truth. |
| Walk through SATs and the scientific process | [Method guide](../../analysis/README.md), [executable worked case](../../analysis/WORKED_EXAMPLE.md), [operator evidence linking](../../USER_GUIDE.md#record-how-evidence-bears-on-an-explanation) | Required-field checks preserve authored protocols; argument quality and judgments are analyst responsibilities. |
| Provide a comprehensive usable Markdown guide | [User Guide](../../USER_GUIDE.md) includes novice/experienced routes, intake, notebook, correction, recovery, handoff, commands, accessibility, and audio | Current media and exact commands accompany the guide; no Word/PDF source-document requirement. |
| Use experienced and newcomer editorial perspectives | [Expert review](EXPERT_EDITORIAL_REVIEW.md) plus [newcomer review](NEWCOMER_REVIEW.md); corrections to link creation, full backups, graph media, and historical references | Review findings are artifact-backed; no invented human reviewers or endorsements. |
| Reorganize repository for navigation | [Repository map](../../development/REPOSITORY_MAP.md), `src/pivotglass/`, role-oriented docs, dated `docs/releases/`, plans, and development records | Preserve source authority and protected local work; reorganize navigation without discarding design history. |
| Refresh the current demonstration | [v0.9.9 narrated tour](../../media/pivotglass-guided-demo-v0.9.9.mp4), [captions](../../media/pivotglass-guided-demo-v0.9.9.vtt), [transcript](../../media/pivotglass-guided-demo-transcript-v0.9.9.md), [chapter manifest](../../media/pivotglass-guided-demo-manifest-v0.9.9.json) | Actual synthetic UI captures, real Descript Jesse neural speech, and speech-timed chapters. Complete 300.16-second decode passed; all 648 spoken words have captions. Owner listening review and public release verification remain open. |
| Make the official public release at the requested version | v0.9.8 historical public checkpoint; v0.9.9 closes the owner-identified gaps | Current candidate publication requires the complete [release trust ceremony](../../RELEASE_TRUST.md) and downloaded readback. |

## Original v0.9.9 instructions and specified channels

| Requested outcome | Delivered repository artifact | Boundary |
| --- | --- | --- |
| Elevator pitches and product explanation | [Pitches](../../marketing/ELEVATOR_PITCHES.md), [one-pager](../../marketing/PRODUCT_ONE_PAGER.md), [website copy](../../marketing/WEBSITE_COPY.md) | Audience-specific, source-grounded claims; no invented adoption, outcome, or scale evidence. |
| Implementation guides | [Implementation](../../operations/IMPLEMENTATION.md) | Local setup, explicit data migration, synthetic acceptance, provider choice, and controlled introduction of real work. |
| Infrastructure requirements | [Infrastructure](../../operations/INFRASTRUCTURE.md) | Runtime/build dependencies, storage, network boundaries, optional services, and measured capacity; no unsupported enterprise deployment claim. |
| Operations and maintenance | [Operations](../../operations/OPERATIONS.md) | Owners, cadence, stopped-copy backups, restore verification, updates, diagnostics, recovery, and handling. |
| Automation tasks and documentation | [Operations](../../operations/OPERATIONS.md), [implementation](../../operations/IMPLEMENTATION.md) | Exact supported command paths and external scheduling boundaries; no claimed built-in scheduler or unattended judgment approval. |
| LinkedIn materials | [LinkedIn drafts](../../marketing/LINKEDIN.md) | Repository drafts; outbound account publication is separate. |
| Mastodon materials | [Mastodon drafts](../../marketing/MASTODON.md) | Check instance limits and destination before posting. |
| Signal materials | [Signal share draft](../../marketing/SIGNAL.md) | No message sent to a contact or group by creating the draft. |
| jarocki.org website materials | [Website copy](../../marketing/WEBSITE_COPY.md) | No website change implied by repository copy. |
| Launch checks and claim support | [Marketing overview](../../marketing/README.md), [launch checklist](../../marketing/LAUNCH_CHECKLIST.md) | Track drafts in Git and verify public links and maturity claims before external use. |

## Current executable corrections found during completion

- **Evidence linking:** `analysis link` now exposes canonical ledger linking to
  the browser and full-screen terminal, with real IDs and required rationale.
  It records analyst interpretation, not collection or automatic acceptance.
- **Joint-admission graph:** degree summaries exclude group markers from stored
  indicator rows while counting explicit membership edges for stored-entity
  endpoints, preventing a group ID from breaking state refresh. The actual synthetic
  demonstration shows six entities plus one group and five styled edges.
- **Media content:** current captures show full graph canvas/legend, provenance
  branches, complete URL values, intake receipts, and the local evidence-link
  receipt. Captions must match visible content rather than only a toolbar.

## Separate v1.0.0 gate

The final correctness, resilience, efficiency, security, and usability review is
still future work. Its evidence and unresolved findings must be presented for
owner approval. This candidate does not assign, approve, or publish v1.0.0.
See the [roadmap](../../plans/V0.9.8_TO_1.0_ROADMAP.md#final-quality-pass--prerequisite-to-v100).
