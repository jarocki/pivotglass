# v0.9.9 expert editorial and operations review

Date: 2026-09-28. Reviewer perspective: AI security/threat-intelligence editorial
role, continuing the owner-requested editorial crew. This is not a human expert
endorsement, measured usability study, production security qualification, or
approval of v1.0.0.

## Delivered implementation and operations material

- [Implementation plan and acceptance](../../operations/IMPLEMENTATION.md): scope,
  owner responsibilities, tagged-source installation, prior-home migration,
  synthetic acceptance, authorized collection, handoff, and recovery.
- [Infrastructure requirements](../../operations/INFRASTRUCTURE.md): actual runtime,
  local deployment, network boundary, storage, browser/build/test distinction,
  measured-capacity limits, and unqualified workloads.
- [Operations runbook](../../operations/OPERATIONS.md): session checks, ownership and
  cadence, stopped-home backups, isolated recovery, upgrade/rollback, read-only
  automation candidates, retention, and incident handling.

The guides use the existing product commands and public Python authorities.
They do not invent a service installer, automatic backup manager, scheduler,
remote authentication, resource minimum, or production backend qualification.
The v0.9.9 install examples explicitly require a published/read-back tag; a
candidate checkout is not presented as an already public release.

## Substantive documentation corrections

| Finding | Correction and evidence |
| --- | --- |
| Framework reference claimed fresh schema 11 | Updated to schema 12, matching `CURRENT_WORKSPACE_SCHEMA_VERSION` and current workspace migrations |
| Capacity table said candidate overflow fails | Corrected to explicit partial extraction when the configured candidate limit is reached, matching the extractor's receipt state |
| Dated measurements read as current qualification | Capacity now names historical qualification and distinguishes it from a fresh v0.9.9 performance run |
| Database recovery used overwrite-capable copy | Learning/migration examples use exclusive creation; full documentary backup links include sibling raw content |
| File export implied complete original-source backup | Operations/data-safety/recovery explicitly distinguish JSON records, SQLite, content stores, generated artifacts, and browser-local drafts |
| Graph reference omitted joint admission meaning | Added recorded analyst-group edges and workflow provenance limits; neither implies common control or attack sequence |
| Target Synapse/SCOT architecture could read as current instructions | Added current SQLite authority and explicit cutover/scope/qualification gate |
| Frontend minimum engine confused with test runtime | Infrastructure separates Node 20.9+ build engine from direct-TypeScript test-harness support; current host is Node 26.3.0 |
| ACH method JSON confused with ledger evidence links | Explained persisted authored method output separately from actual support/contradiction links and visual projection |

The evidence-link authoring gap was escalated and closed during this candidate.
The governed `analysis link` command now uses the canonical ledger, validates
record kinds and IDs, stance, and rationale, and runs through the browser command
bar/terminal cyberdeck. Documentation now explains this operator path and its
local-only assessment boundary. The classic basic/repl console remains outside
this shared dispatch path. Command regression and release qualification receipts
are owned by the implementing agent and release lead.

## Executable verification performed

The Python recovery block was extracted from the published Markdown and run
against a temporary synthetic learning workspace plus one admitted source.
It returned one question, two hypotheses, one contradiction, one validated
document, and SQLite integrity `ok`. The script validates supported schema,
required tables, and each source content hash in an isolated temporary copy.

A negative replay intentionally altered the disposable backup's raw document.
The recipe rejected it with `Restored source bytes failed hash validation`.
The original backup database's SHA-256 remained unchanged. These are runbook
checks, not a demonstration that every possible corruption or storage failure
is recoverable.

The public documentation checker passed at the review checkpoint: 78 Markdown
files and zero broken local links/anchors. This result changes as the crew adds
material; the final release lead reruns it against the complete candidate.
The checker inventories all public root and `docs/` Markdown, excluding protected
private/independent material. It checks local paths and anchors, not prose truth,
external websites, production access, or human comprehension.

## Coverage, historical preservation, and open work

Current references reviewed for operational/analytical contracts:
`ANALYTIC_METHOD`, `CAPACITY`, `COMPATIBILITY`, `DATA_SAFETY`,
`EXTERNAL_INTEGRATIONS`, `FAILURE_RECOVERY`, `FRAMEWORK_PROJECTIONS`,
`GRAPH_WORKSPACE`, `LEARNING_WORKSPACE`, `PROCEDURAL_MUSIC`, `RELEASE_TRUST`,
`RELEASING`, `VISUALIZATION_GUIDE`, `WEB_SUPPLY_CHAIN`, and
`WORKSPACE_MIGRATIONS`; plus architecture/analysis pages and actual command,
workspace, ingestion, extraction, and migration authorities.

README, Quick Start, User Guide, documentation index, marketing material,
release plan/QA, and the new current video are owned by the other editorial
crew members and release lead. Their completion must be recorded in the
consolidated candidate receipt; this document does not substitute for that work.

The prior expert review records bounded historical release-reading and whole-file
plan inventories. Historical records remain dated evidence of what was claimed
or tested at the time. They are not rewritten to imply current tests, public
readback, media coverage, or integration success. Full independent verification
of every old test count, commit hash, or release object is not claimed.

Known review limits and remaining release responsibilities:

- Current full narrated walkthrough, captions, transcript, and media readback
  are the release lead's explicit first carryover obligation.
- The complete candidate needs full-suite, browser/package/migration, link,
  security/supply-chain, release-contract, and publication receipts.
- Production integrations, broad parser formats, remote multi-user serving,
  and measured training effectiveness remain unqualified unless separately
  completed with their own evidence and approved scope.
- Final correctness, resilience, efficiency, security, and usability assurance
  plus owner approval remain prerequisites to v1.0.0.

No protected `storyboard/` or `reckonings/UX-team.md` context, separate career
project, workspace evidence, or user credential was modified by this review.

## Final editorial coverage inventory and freeze handoff

Coverage categories apply to all public root and `docs/` Markdown inventoried
by `scripts/check_documentation.py`, not to every ignored local file:

| Category | Coverage and authority |
| --- | --- |
| Current product/operator references | Expert review of the topical contracts listed above and their executable authorities; newcomer/editor review of README, Quick Start, User Guide, and index |
| Current architecture, analysis, learning, operations | Authored and reviewed against actual behavior; conceptual versus synthetic diagrams explicitly labeled; recovery example executed |
| Current marketing and website copy | Crew review against delivered product and explicit limits; website fragment checked against the supplied current HTML `rows/row/key/val` structure; no publication |
| Current release plans, qualification, and media | Release lead owns carryover disposition, full-suite/package/browser evidence, refreshed video/captions/transcript, and public-object readback |
| Dated QA, announcements, handoffs, research reviews, and media transcripts | Reviewed as historical records with version/date and research provenance; neither old measurements nor old video are presented as fresh qualification |
| Long retained plans and generated decision history | Whole-file inventories and targeted substantive section review for current-versus-planned conflicts; no independent recertification of every historical hash, test count, private path, or dated decision |
| Protected/independent material | `storyboard/`, `reckonings/UX-team.md`, and `career-narrative/` are excluded from edits; ignored private context is not a public guide |

The mechanical inventory identifies each public file and checks local links and
anchors. It is not semantic proof that every sentence is correct, a human panel
review, or a replay of every historical receipt. The consolidated release
receipt must identify the final inventory and any remaining obligations rather
than converting this bounded editorial method into exhaustive verification.

At freeze handoff the three operations guides, topical corrections, executable
linking walkthroughs, and ready HTML fragment are complete. Remaining release
checks belong to the release lead: final complete tests, media readback,
publication/signature/checksum verification, and public readback. Production
integration qualification, expanded parsers, human training-outcome research,
and the approval-gated v1.0 assurance pass are not claimed complete here.
