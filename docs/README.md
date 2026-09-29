# Pivotglass documentation

Use this index to choose a complete path rather than assemble a workflow from
release notes. These guides describe the v0.9.9 source tree. Published release
status comes from [GitHub Releases](https://github.com/jarocki/pivotglass/releases);
a version string or development plan is not publication evidence.

## Four ways through the looking glass

Start with the [flashy Overview](media/series-v0.9.9/pivotglass-overview-v0.9.9.mp4), then choose the [Analyst Walkthrough](media/series-v0.9.9/pivotglass-analyst-v0.9.9.mp4), [PIVOT Glass](media/series-v0.9.9/pivotglass-pivot-v0.9.9.mp4), or [Visualization and Reporting](media/series-v0.9.9/pivotglass-visualization-v0.9.9.mp4). Each has real Descript narration, original generative music, captions and a transcript in the [series guide](media/series-v0.9.9/README.md).

## Choose a path

| Your role or task | Reading path | Outcome to check |
| --- | --- | --- |
| New user | [Quick Start](QUICKSTART.md) → [offline learning case](LEARNING_WORKSPACE.md) → [User Guide](USER_GUIDE.md) | Create a synthetic case, trace a source, explain an unresolved gap, and produce a report without provider access |
| Analyst learning the method | [Scientific analysis](analysis/README.md) → [worked example](analysis/WORKED_EXAMPLE.md) → [visual reading exercises](analysis/VISUALIZATIONS.md) → [reflection](analysis/LEARNING.md) | Test an alternative, preserve uncertainty, and explain why a judgment changed |
| Experienced analyst | [Bounded investigation](USER_GUIDE.md#experienced-path-a-bounded-investigation) → [source admission](USER_GUIDE.md#preview-ingest-and-revisit-a-document) → [correction and handoff](USER_GUIDE.md#review-correct-and-hand-off-a-case) | Make collection and judgment reviewable by the next analyst |
| Implementation owner | [Implementation](operations/IMPLEMENTATION.md) → [infrastructure](operations/INFRASTRUCTURE.md) → [architecture](architecture/README.md) | Select an appropriate local deployment, handling boundary, and acceptance checks |
| Operator | [Operations](operations/OPERATIONS.md) → [failure and recovery](FAILURE_RECOVERY.md) → [data safety](DATA_SAFETY.md) | Verify a stopped backup, recover a copy, maintain versions, and handle failures without losing the case |
| Communicator | [Marketing overview](marketing/README.md) → [product one-pager](marketing/PRODUCT_ONE_PAGER.md) → [elevator pitches](marketing/ELEVATOR_PITCHES.md) | Explain the value in terms appropriate to the audience and qualify the claims |
| Contributor or release maintainer | [Repository map](development/REPOSITORY_MAP.md) → [governance](../AGENTS.md) → [release discipline](RELEASING.md) → [release trust](RELEASE_TRUST.md) | Find the authority for a change, run gates, and verify public artifacts |

## Current demonstration

- [Narrated v0.9.9 MP4](media/pivotglass-guided-demo-v0.9.9.mp4)
- [WebVTT captions](media/pivotglass-guided-demo-v0.9.9.vtt)
- [Transcript and chapter times](media/pivotglass-guided-demo-transcript-v0.9.9.md)
- [Caption-enabled player instructions](QUICKSTART.md#watch-with-captions)
- [Chapter manifest and recording method](media/pivotglass-guided-demo-manifest-v0.9.9.json)

The narrated tour combines actual UI captures of synthetic case data with
Descript’s Jesse neural voice. The written walkthroughs supply the executable practice,
reasoning, correction, and recovery details. Older demos remain historical
assets and are not the current tour.

## User and analysis guides

- [Quick Start](QUICKSTART.md): installation, offline first investigation,
  questions, evidence, analytical challenge, reports, and restart checks.
- [User Guide](USER_GUIDE.md): interface navigation, intake, graphs, notebook,
  correction, handoff, command reference, accessibility, and audio.
- [Offline learning case](LEARNING_WORKSPACE.md): exact fixture and persistence exercise.
- [Scientific method and Structured Analytic Techniques](analysis/README.md):
  reasoning stages, technique protocols, and the distinction between recorded
  inputs and a sound argument.
- [Worked example](analysis/WORKED_EXAMPLE.md): why a connected synthetic
  infrastructure cluster does not establish common control.
- [Visualizations](analysis/VISUALIZATIONS.md): analytical questions, chart
  interpretation, exact data, and overclaiming traps.
- [Learning through practice](analysis/LEARNING.md): Novice Q&A, independent
  framing, reflection, and mentor feedback without automatic certification.

## Implementation and operation

- [Implementation guide](operations/IMPLEMENTATION.md): preparation, configuration,
  rollout, acceptance, and authority boundaries.
- [Infrastructure requirements](operations/INFRASTRUCTURE.md): runtime dependencies,
  storage, network/provider choices, capacity limits, and local service assumptions.
- [Operations and maintenance](operations/OPERATIONS.md): startup, shutdown,
  backup/restore, update, diagnostics, and explicit automation boundaries.
- [Architecture](architecture/README.md): logical components, data flows,
  analytical authority, optional services, and extension paths.
- [Data ownership and safety](DATA_SAFETY.md): user data, credentials, network
  actions, LAN exposure, and sharing.
- [Compatibility and maturity](COMPATIBILITY.md): stable, preview, and deferred contracts.
- [Capacity envelope](CAPACITY.md): measured scale, enforced bounds, and unqualified limits.
- [Failure and recovery](FAILURE_RECOVERY.md): truthful lifecycle states and safe recovery.
- [Support](../SUPPORT.md): version support and safe issue reporting.

## Detailed reference contracts

- [Analytic records and commands](ANALYTIC_METHOD.md)
- [Visualization selection and rendering](VISUALIZATION_GUIDE.md)
- [Layered investigation graph](GRAPH_WORKSPACE.md)
- [Framework projections](FRAMEWORK_PROJECTIONS.md)
- [Synapse, SCOT4, go-roast, and Nucleotide](EXTERNAL_INTEGRATIONS.md)
- [Workspace schema migration and recovery](WORKSPACE_MIGRATIONS.md)
- [Procedural music](PROCEDURAL_MUSIC.md)
- [Web supply chain](WEB_SUPPLY_CHAIN.md)

The user guide explains actions; the analysis guides explain reasoning. Reference
contracts describe implemented boundaries. An integration architecture labeled
as a target does not establish a completed production cutover.

## Release assurance and history

- [v0.9.9 completion plan](plans/V0.9.9_COMPLETION_PLAN.md): scope, owners, and verification work.
- [v0.9.9 request completion matrix](releases/v0.9.9/COMPLETION_MATRIX.md): delivered artifacts, remaining qualification, and public-release gates.
- [Release records](releases/README.md): dated QA receipts, handoffs, and prior release documents.
- [Release discipline](RELEASING.md): version, changelog, checks, tag, and publication.
- [Release trust](RELEASE_TRUST.md): SBOM, licenses, checksums, signatures, and public readback.
- [Changelog](../CHANGELOG.md): user-visible changes.
- [Development history](plans/MASTER_PLAN.md) and [decision index](development/DECISIONS.md).
- [Project philosophy](../PHILOSOPHY.md) and [contributor governance](../AGENTS.md).

Historical screenshots, walkthroughs, quality counts, and plans describe their
dated checkpoints. They remain useful for traceability, but are not current
interface instructions or evidence that a later release passed the same checks.
Mock editorial or usability exercises are labeled simulations; they are not
endorsements from real users or measured outcome studies.
