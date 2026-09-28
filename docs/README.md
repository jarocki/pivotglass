# Pivotglass documentation

Use the current operator guides first. Planning documents and earlier quality
records are retained for traceability, not as descriptions of the current
interface.

## Choose a reading path

**First investigation:** [Quick Start](QUICKSTART.md) →
[offline case](LEARNING_WORKSPACE.md) → [User Guide](USER_GUIDE.md).
No account or provider key is needed for the synthetic case.

**Improve analytical practice:** [scientific method and SATs](analysis/README.md) →
[worked case](analysis/WORKED_EXAMPLE.md) →
[visualization examples](analysis/VISUALIZATIONS.md) →
[learning and reflection](analysis/LEARNING.md).

**Operate or extend the product:** [architecture](architecture/README.md) →
[data safety](DATA_SAFETY.md) → [capacity](CAPACITY.md) →
[failure and recovery](FAILURE_RECOVERY.md) → [release discipline](RELEASING.md).

The user guide explains interface actions. The analysis guides explain how to
reason about what those actions produce. Reference contracts describe the
implemented boundaries. Release records describe checks at a dated checkpoint;
plans describe intended work. Keep those distinctions when citing a document.

## Current operator and reference guides

- [Quick Start](QUICKSTART.md) — install Pivotglass and complete a first investigation
- [Offline learning investigation](LEARNING_WORKSPACE.md) — complete the evidence-to-report loop with no key or network service
- [User Guide](USER_GUIDE.md) — task guidance and command reference
- [Architecture](architecture/README.md) — execution paths and policy/state authorities
- [Scientific analysis](analysis/README.md) — methodology, worked examples, visualization reading, and learning
- [Analytic method](ANALYTIC_METHOD.md) — scientific workflow, structured techniques, confidence, and contradictions
- [Visualization guide](VISUALIZATION_GUIDE.md) — deterministic chart selection, reading guidance, and analytical guardrails
- [Framework projections](FRAMEWORK_PROJECTIONS.md) — evidence-backed ATT&CK, Kill Chain, and Diamond mapping contract
- [Vertex Synapse and SCOT4 integrations](EXTERNAL_INTEGRATIONS.md) — governed MCP setup, approval gates, receipts, and authority boundaries
- [Workspace migration and recovery](WORKSPACE_MIGRATIONS.md) — preview, backup, validation, and recovery
- [Compatibility and maturity](COMPATIBILITY.md) — stable, preview, deferred, and capacity boundaries
- [Data ownership and safety](DATA_SAFETY.md) — storage, secrets, network actions, LAN exposure, backup, and recovery
- [Capacity envelope](CAPACITY.md) — enforced limits, measured local scale, graceful overflow, and unqualified boundaries
- [Failure and recovery](FAILURE_RECOVERY.md) — provider loss, cancellation, migrations, stale assets, hostile input, and integration outages
- [Support](../SUPPORT.md) — supported-version boundary, safe issue reporting, and the open private security-route gate
- [Release trust](RELEASE_TRUST.md) — SBOM, licenses, checksums, signing, publication, and public readback
- [Guided video](media/pivotglass-guided-demo-v0.9.5.mp4) — two-minute core-workflow tour from v0.9.5
- [Guided-video captions](media/pivotglass-guided-demo-v0.9.5.vtt) — English WebVTT captions
- [Video transcript](media/pivotglass-guided-demo-transcript.md) — accessible narration text
- [v0.9.7 guided-workflow screenshot](media/pivotglass-guidance-v0.9.7.png) — earlier task-relative novice guidance; the current Q&A is documented in the user guide
- [v0.9.7 JSON-intake screenshot](media/pivotglass-json-intake-v0.9.7.png) — content-detected JSON preview and candidate guidance
- [v0.9.7 announcement kit](releases/v0.9.7/ANNOUNCEMENT_V0.9.7.md) — reviewed social and community-launch drafts

## Design and release assurance

- [Mock usability review](releases/v0.9.7/MOCK_USABILITY_STUDY_V0.9.7.md) — fictional cohort, findings, implemented changes, and real-research follow-up
- [v0.9.7 quality record](releases/v0.9.7/QA_V0.9.7.md) — historical implementation receipts and open media gate at that checkpoint
- [Procedural music](PROCEDURAL_MUSIC.md) — composition, playback, and evidence boundary
- [Web supply chain](WEB_SUPPLY_CHAIN.md) — dependency integrity and release checks
- [v0.9.6 quality record](releases/v0.9.6/QA_V0.9.6.md) — prior release verification
- [v0.9.5 quality record](releases/v0.9.5/QA_V0.9.5.md) — prior release verification
- [v0.9.4 quality record](releases/v0.9.4/QA_V0.9.4.md) — prior release verification
- [v0.9.3 quality record](releases/v0.9.3/QA_V0.9.3.md) — prior release verification
- [v0.9.2 quality record](releases/v0.9.2/QA_V0.9.2.md) — prior release verification
- [v0.9.1 quality record](releases/v0.9.1/QA_V0.9.1.md) — prior release verification
- [v0.9.0 quality record](releases/v0.9.0/QA_V0.9.0.md) — prior release verification
- [Release discipline](RELEASING.md) — version, changelog, verification, tag, and publication contract
- [v0.9.6 release record](releases/v0.9.6/RELEASE_HANDOFF_V0.9.6.md) — final receipts, boundaries, artifacts, and public readback
- [v0.9.5 release record](releases/v0.9.5/RELEASE_HANDOFF_V0.9.5.md) — prior release receipts and boundaries
- [v0.8.5 quality record](releases/v0.8.5/QA_V0.8.5.md) — prior release verification
- [v0.8.0 quality record](releases/v0.8.0/QA_V0.8.0.md) — prior release verification
- [v0.8.5 UX redesign catalog](releases/v0.8.5/UX_V0.8.5.md) — clarity, workflow, and accessibility direction
- [v0.7.0 quality record](releases/v0.7.0/QA_V0.7.0.md) — prior release verification
- [Project philosophy](../PHILOSOPHY.md) — judgment framework
- [Contributor governance](../AGENTS.md) — engineering and preservation rules

## Historical records

The `QA_V*.md` files record what was checked at earlier development
checkpoints. The `plans/` directory records intended work and implementation
disposition at the time it was written. Commands and product names in historical documents have been normalized
for navigation, but their dated test counts and capability descriptions describe
the checkpoint named in the title. Do not use them as current qualification
evidence. Requirements may have been superseded.

- [v0.4.2 QA/UX plan](plans/V0.4.2_QA_UX_PLAN.md)
- [v0.6 capability plan and disposition](plans/V0.6.0_PLAN.md)
- [v0.8 through v1.0 approved roadmap](plans/V0.8_TO_1.0_ROADMAP.md)
- [v0.9.1 through v1.0 burndown](plans/V0.9.1_TO_1.0_BURNDOWN.md)
- [v0.9.5 document-ingestion plan](plans/V0.9.5_DOCUMENT_INGESTION.md)
- [v0.6 arcade synthetic review](reviews/V0.6_ARCADE_SYNTHETIC_PLAYTEST.md)
- [Development history](plans/MASTER_PLAN.md)
- [Generated decision index](development/DECISIONS.md)
