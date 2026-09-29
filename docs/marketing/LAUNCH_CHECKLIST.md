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
- [ ] Read the [compatibility matrix](../COMPATIBILITY.md),
  [data safety](../DATA_SAFETY.md), and [capacity](../CAPACITY.md) against the copy.
  Keep qualified, preview, and deferred capabilities distinct.
- [ ] Verify diagrams, screenshots, and the guided demo against the shipped
  interface. Label synthetic data and older media with their actual version.
  Do not imply a historical screenshot shows the current interface.
- [ ] Verify no credential, personal information, live-case indicator, private
  hostname, or unapproved evidence appears in public media.
- [ ] Read the copy as a first-time analyst: can the reader identify a starting
  point, the meaning of unfamiliar terms, and what the next action will do?
- [ ] Have a subject-matter reviewer challenge attribution, confidence,
  independence, method, and collection claims. Have a newcomer reviewer check
  pacing, clarity, emotional tone, uncertainty, and permission language.
- [ ] Record actual reviewer findings, edits, and unresolved limitations in the
  release record. Do not portray simulated/editorial review as a user study.
- [ ] Check Mastodon length and the destination instance's URL-counting rules.
- [ ] Have the account/site owner authorize and perform external publication.
  Drafts in this directory do not send posts, messages, or website updates.

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
| v0.9.9 enablement materials | [Implementation](../operations/IMPLEMENTATION.md), [Infrastructure](../operations/INFRASTRUCTURE.md), [Operations](../operations/OPERATIONS.md) | “Guidance for evaluation and operation.” A checklist is not proof every environment has been qualified. |

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

Use **v0.9.9 marketing and enablement checkpoint** only after public release
verification. Use **draft v0.9.9 materials** before then. Reserve **Pivotglass
v1.0.0** for the separately approved final quality pass and its verified public
release. Preparing these materials does not satisfy that gate.
