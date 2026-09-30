# Launch checklist and claims matrix

The repository materials are draft public copy. This checklist controls a
publication pass; a completed document alone is not a public release or a
permission to send a message on someone else's behalf.

## Before sharing

- [ ] Confirm the public release tag, GitHub Release, artifacts, checksums, and
  public readback required by [release discipline](../RELEASING.md).
- [ ] Confirm the advertised version matches the release, install commands,
  manifests, and dated changelog.
- [ ] Open every destination link in the public repository. Links to `main`
  must resolve to published material; use release-tag links for reproducible
  release-specific claims when available.
- [ ] Verify the final Overview MP4 link in both [social](SOCIAL_POST.md) and
  [LinkedIn](LINKEDIN.md), plus the repository-page link in the
  [Signal blurb](SIGNAL.md). Attach the approved logo and synthetic-case
  graphics with their alt text; do not upload a historical draft image.
- [x] Read the [compatibility matrix](../COMPATIBILITY.md),
  [data safety](../DATA_SAFETY.md), and [capacity](../CAPACITY.md) against the copy.
  Keep qualified, preview, and deferred capabilities distinct.
- [x] Verify diagrams, screenshots, and the guided demo against the shipped
  interface. Label synthetic data and older media with their actual version.
  Do not imply a historical screenshot shows the current interface.
- [x] Verify no credential, personal information, live-case indicator, private
  hostname, or unapproved evidence appears in public media.
- [x] Read the copy as a first-time analyst: can the reader identify a starting
  point, the meaning of unfamiliar terms, and what the next action will do?
- [x] Have a subject-matter reviewer challenge attribution, confidence,
  independence, method, and collection claims. Have a newcomer reviewer check
  pacing, clarity, emotional tone, uncertainty, and permission language.
- [x] Record actual reviewer findings, edits, and unresolved limitations in the
  release record. Do not portray simulated/editorial review as a user study.
- [ ] Check Mastodon length and the destination instance's URL-counting rules.
- [ ] Have the account/site owner authorize and perform external publication.
  Drafts in this directory do not send posts, messages, or website updates.

## Launch verification — 2026-09-29

This pass reviewed the current working tree, including the owner's uncommitted
edits to [Signal](SIGNAL.md) and [LinkedIn](LINKEDIN.md). Those edits were
preserved. The checked boxes above mean the stated review was performed; they
do not imply a public release or independent human endorsement.

| Checklist items | Result and evidence | Remaining action |
| --- | --- | --- |
| Release, version, public links (1–3) | Public `main` and the latest GitHub Release are still v0.9.8. [PR #9](https://github.com/jarocki/pivotglass/pull/9) is a draft v0.9.9 candidate. Local Python and web manifests say v0.9.9; Signal's v1.0.0 wording is launch copy for a later approved release. Direct public-repository readback found `docs/QUICKSTART.md`, `docs/LEARNING_WORKSPACE.md`, `docs/USER_GUIDE.md`, and `docs/DATA_SAFETY.md`; it returned 404 for the Overview MP4, logo, and `docs/operations/IMPLEMENTATION.md` on `main`. | Approve the final assurance scope, create and publish the versioned release and trust artifacts, then repeat readback on the exact published tag and every destination. |
| Video, repository link, graphics (4) | The repository page is the intended Signal destination. The social and LinkedIn drafts use the same Overview URL, which is currently unavailable on public `main`. The approved logo and two synthetic-case social graphics are present locally and visually match their alt text. All four local MP4 sizes and SHA-256 hashes match `series-v1.0.0/verification.json`. | Confirm the Overview plays from the public release link and attach the approved images and alt text at posting time. |
| Claims and capability limits (5) | Reviewed current [compatibility](../COMPATIBILITY.md), [data safety](../DATA_SAFETY.md), and [capacity](../CAPACITY.md) against the marketing copy. It presents local practice, analyst judgment, provenance, and visualizations as mechanisms, without measured speed or learning claims. Preview integrations and deferred intake remain outside stable claims. | Keep the same limits in any final v1.0.0 copy and release notes. |
| Media fidelity and disclosure (6–7) | The four edit manifests use only existing brand art and current synthetic-case capture files. The relationship image visibly distinguishes stored edges from dotted analyst grouping; the ACH image shows recorded support and unassessed cells. The series and source README state that the videos are edited captures, not continuous recordings. OCR screening of all 42 referenced-source PNGs and review of all four transcripts found no apparent credential, private hostname, real personal data, or live-case indicator. A configuration capture shows only public provider endpoints and missing-key state. The screenshots have synthetic names and `.example` domains. | Recheck the final uploaded assets. OCR and manual inspection are disclosure screening, not a guarantee against every hidden datum. |
| Analyst and editorial reads (8–10) | First-time path: the repository and website copy point to the synthetic offline case, Quick Start, and User Guide. Agent-assisted subject-matter and newcomer passes checked evidence/inference separation, grouping versus relationship, source selection, uncertainty, jargon, pacing, and handoff. The owner's revised Signal and LinkedIn wording was preserved. The LinkedIn phrase “choose IoCs to ingest” is conversational but the product's precise sequence is preview source → ingest source → admit selected candidate indicators; explanatory docs retain that distinction. Existing [expert](../releases/v0.9.9/EXPERT_EDITORIAL_REVIEW.md) and [newcomer](../releases/v0.9.9/NEWCOMER_REVIEW.md) reviews predate the owner's two edits. This pass is not a new independent human review or user study. | If the owner wants more precise LinkedIn terminology, change that phrase before posting; no copy change is required for the release gate. |
| Mastodon (11) | The draft is 417 Unicode characters including its URL, below 500 even without a shortened-link allowance. | Confirm the chosen instance's actual limit and URL handling before posting. No destination instance was specified. |
| Publication authority (12) | No social post, Signal message, or website update was sent by this pass. [Final assurance](../releases/v0.9.9/FINAL_ASSURANCE_REVIEW.md) still requires the owner's v1.0.0 scope decision, followed by signed release and public readback. | Owner authorizes the final release scope and performs or explicitly authorizes each external publication after the links work. |

**Launch state:** Six review items complete; six publication/link/account items
remain open. Do not publish Signal's “v1.0.0 release” wording until v1.0.0 is
actually public and verified. The marketing files are drafts, not proof of
distribution.

## Claims and their supporting authority

The matrix describes implemented mechanisms or documented boundaries. It is
not evidence that users achieved a measured operational outcome.

| Public claim | Supporting repository source | Safe wording and limit |
| --- | --- | --- |
| Persistent local case workspace | [Architecture](../architecture/README.md), [Data safety](../DATA_SAFETY.md) | “Local workspace.” Enabled remote services can receive selected request data. |
| Question-to-report investigative loop | [User Guide](../USER_GUIDE.md), [Worked example](../analysis/WORKED_EXAMPLE.md) | “Connect the question, evidence, explanations, and report.” Do not claim correctness is automatic. |
| Deliberate collection and admission | [Data safety](../DATA_SAFETY.md), [User Guide](../USER_GUIDE.md) | “Choose collection and review candidates.” Admission is not a maliciousness finding. |
| Source provenance and workflow history | [Visualization guide](../VISUALIZATION_GUIDE.md), [Architecture](../architecture/README.md) | “Inspect the source and analytical path.” Workflow edges are not adversary relationships. |
| Relationship graphs and analyst grouping | [Visualization examples](../analysis/VISUALIZATIONS.md), [Visualization guide](../VISUALIZATION_GUIDE.md) | “See labeled edge bases.” Grouping or a shared property alone does not prove common control. |
| Competing explanations and structured analysis | [Analytic method](../ANALYTIC_METHOD.md), [Methodology](../analysis/README.md) | “Record and challenge explanations.” Techniques discipline reasoning, not guarantee conclusions. |
| Novice Q&A and reflection | [Learning](../analysis/LEARNING.md), [User Guide](../USER_GUIDE.md) | “Support practice.” No measured OJT benefit, competence certification, or automatic expertise declaration. |
| Fewer repeated handling steps by design | [Architecture](../architecture/README.md), [User Guide](../USER_GUIDE.md) | “Designed to reduce repeated navigation and data handling.” No time-saving percentage or causal performance claim. |
| AI-augmented analysis under human judgment | [Architecture](../architecture/README.md), [Data safety](../DATA_SAFETY.md) | “Optional model synthesis.” Model narration is not observed evidence. |
| Offline synthetic evaluation without provider keys | [Learning workspace](../LEARNING_WORKSPACE.md), [Quick Start](../QUICKSTART.md) | “Try the synthetic offline case without a provider account.” Live collection can require accounts and network access. |
| Reports and structured exports | [User Guide](../USER_GUIDE.md), [Analytic method](../ANALYTIC_METHOD.md) | “Reviewable handoff.” The analyst remains responsible for assessment, redaction, and handling. |
| Bounded capacity and explicit omissions | [Capacity](../CAPACITY.md), [Compatibility](../COMPATIBILITY.md) | “Documented local envelope.” Measurements are scenario-specific; no enterprise-scale claim. |
| External integrations | [Compatibility](../COMPATIBILITY.md), [Integration contract](../EXTERNAL_INTEGRATIONS.md) | “SCOT4 and Vertex Synapse previews.” Do not claim production-qualified live round trips. |
| Supported document intake | [Compatibility](../COMPATIBILITY.md), [Data safety](../DATA_SAFETY.md) | Name qualified formats and limits. PDF recognition is not extraction; OCR, Office parsing, URL/RSS intake, and archive expansion are deferred. |
| v1.0.0 enablement materials | [Implementation](../operations/IMPLEMENTATION.md), [Infrastructure](../operations/INFRASTRUCTURE.md), [Operations](../operations/OPERATIONS.md) | “Guidance for evaluation and operation.” A checklist is not proof every environment has been qualified. |

## Claims requiring new evidence

Do not publish claims such as “reduces investigation time by X%,” “improves
accuracy,” “trains novices to expert level,” “enterprise ready,” or “production
qualified integration” from feature existence alone.

A future evaluation should define the comparison workflow, representative
cases, participant experience, outcome measures, supervision, and limitations.
Keep task completion, analytical quality, and learning retention separate. The
[learning guide](../analysis/LEARNING.md) explains mentor review without treating
practice participation as competence.

## Release status language

The owner approved the bounded v1.0.0 scope on 2026-09-29. Use **v1.0.0
release candidate** until the approved, signed release is on public `main`
with downloaded readback. The earlier 2026-09-29 audit above describes the
state before this approval; the public link and artifact checks must be
repeated after publication.
