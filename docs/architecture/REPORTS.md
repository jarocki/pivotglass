# Intelligence Requirements and Reports

Design for v1.5.0 issues #50–#60. This note states the contract; the code
annotations (`@decision`) and the report-type definitions are the authority
once they exist. When this note and the code disagree, the code wins and the
note is corrected.

## Purpose

A hunt should end in a defined outcome: an answer to a stated question, in a
form its audience can act on. Two inputs make that explicit:

- **The PIR** (#60): what the analyst needs to know, typed by category and
  intelligence tier.
- **The report type** (#50–#57): the form the answer takes, from a one-page
  flash alert to a Sigma/Suricata bundle.

Pivotglass already holds most of the content these reports need: evidence
observations, STIX objects, dossier slots, the analytic ledger, framework
projections, structured techniques and the investigation graph. What it lacks
is a way to assemble that content into more than one report, with each part
honest about where it came from.

## Concepts

| Concept | Meaning | Authority |
|---|---|---|
| PIR | The investigation's question, with a category and a tier | `AnalyticInvestigation` (new fields) + `reports/pir.py` definitions |
| Report type | An audience, a tier and an ordered list of elements | `src/pivotglass/reports/types/*.yaml` |
| Element | One section or artifact, built from existing authorities | `src/pivotglass/reports/elements/` |
| Provenance class | Where an element's content comes from | `reports/contract.py` |
| Issued report | A rendered, versioned report with its marking and hash | new `ReportIssue` table |

## PIR (#60)

`AnalyticInvestigation` gains two fields:

- `requirement_category`: one of seven, or `unspecified` for existing
  investigations;
- `intelligence_level`: `tactical`, `operational` or `strategic`.

Each category definition (`reports/pir.py`, one table) names:

- the dossier slots that matter, and the sources to pivot through first;
- the lifecycle items required before the PIR counts as answered. These are
  seeded as `stop_condition` items, so the existing lifecycle and Pursuit Brief
  measure progress without a second tracker;
- default report types per tier (table below);
- `collection_fit`: `strong`, `good`, `partial` or `weak`, stated honestly.
  A `weak` category still runs. Its report says plainly that Pivotglass
  collection cannot answer the question, and lists what would be needed. A
  model is never asked to fill that gap.

**Verdict.** Every report opens with the PIR and a deterministic verdict:

| Verdict | Rule |
|---|---|
| Answered | Every required stop condition is resolved, and there is at least one accepted conclusion |
| Partially answered | Some stop conditions are resolved, or a conclusion exists with open knowledge gaps |
| Not answered by available collection | None of the above; the gaps are listed |

Priority ranking remains DEC-INFORMATION-REQUIREMENTS-001. The PIR does not
re-rank requirements.

### Default report types by category and tier

| Category | Collection fit | Tactical | Operational | Strategic |
|---|---|---|---|---|
| Threat actor and campaign tracking | strong | 4 | 5, 11, 8 | 7, 1 |
| TTPs | strong | 17 | 13, 16, 12 | 10, 18 |
| Brand, VIP and digital footprint | good | 4, 17 | 11, 5 | 1 |
| Vulnerability and exploitation | partial (good after #58) | 4, 17 | 6, 16 | 1, 3 |
| Third-party and supply chain | partial | 4 | 5 | 3, 1 |
| Geopolitical and regulatory | weak | — | 2 | 1, 2 |
| Strategic and M&A | weak | — | 3 | 3, 1 |

Type 9 (ACH) is suggested for any category once the investigation has two or
more competing hypotheses. The analyst can choose any type for any PIR. The
defaults are only suggestions.

## Elements (#50)

An element has:

- an `id`, a title, and a **provenance class**;
- the authorities it reads from;
- a builder: `build(context) -> ElementResult`.

`ElementResult` carries:

- `status`: `complete`, `partial` or `empty`;
- structured `content`, validated by a per-element pydantic model;
- `citations`: observation, STIX or ledger record ids;
- `gaps`: what is missing, and why.

Renderers consume `content`. They never call authorities themselves.

### Provenance classes

| Class | Meaning | Rendering rule |
|---|---|---|
| `evidence` | Collected and cited | Citations are required; an element with none is `empty` |
| `method` | A deterministic transform of evidence (Pyramid tier, generated rule, computed choke point) | Names the method and its version |
| `analyst` | Written by the analyst | Shows the author and the time |
| `model_draft` | Drafted by a model from cited evidence | Labelled "Model draft". It follows the existing proposal flow (`AuthorKind.MODEL` with `AnalystDisposition`). A report with pending drafts can only be issued as `DRAFT`. |
| `org_input` | Organisation data Pivotglass cannot collect (#59) | When absent, it renders as an explicit empty slot naming what is required. It is never model-filled. |

An element may combine classes. For example, the exposure element joins
`org_input` tech-stack data with `evidence` matches. Each part of the content
then carries its own class.

### Completeness

Each report type marks its elements as required or optional. An issued report
states `Complete`, or `Incomplete` with the missing required elements listed.
The alternative, a report that silently omits a section, misleads its audience.

## Report contract (#51)

One module, `reports/contract.py`, owns every vocabulary that renderers and
validation share. It reuses the ledger's existing scales rather than defining
new ones.

| Vocabulary | Values | Source |
|---|---|---|
| Likelihood | ICD 203 seven-term scale with probability ranges | existing `LikelihoodTerm`, `LIKELIHOOD_RANGES` |
| Confidence | High / Moderate / Low, defined | existing `ConfidenceLevel` |
| Source reliability | Admiralty A–F | new |
| Information credibility | Admiralty 1–6 | new |
| TLP | TLP 2.0: CLEAR, GREEN, AMBER, AMBER+STRICT, RED | new |
| PAP | CLEAR, GREEN, AMBER, RED | new |
| Severity | Critical / High / Medium / Low / Informational | new |
| Control status | Not observed, Logged, Detected, Blocked, Prevented, Missed, Not applicable (each defined) | new |
| Gap status | Derived by a stated rule from the visibility, alerting and prevention scores. Never entered by hand. | new |

**Shared header.** Every report carries:

- the report ID (`PG-<TYPE>-<YYYY>-<NNNN>`, unique per workspace), version,
  status (`DRAFT` / `FINAL`) and revision history;
- the issue time (UTC), TLP and PAP;
- the audience and the PIRs addressed;
- a validity or expiry date and the producer;
- the source list, with reliability and credibility ratings.

**Mandatory sections.** Every type includes *Gaps and Limitations*. It is built
from `knowledge_gap` and `limitation` lifecycle items, plus every required
element that came back `empty` or `partial`.

**Judgments.** A key judgment carries a likelihood term and a confidence level,
stated separately: likelihood is how probable the event is; confidence is how
good the evidence is.

**Defanging.** Human-readable renderings defang indicator values with the
existing `defang_indicator_value`. Machine-readable renderings (JSON, STIX,
CSV, Navigator, Sigma, Suricata, YARA) never defang.

**Example data.** Template examples use only reserved values:

- RFC 2606 / RFC 6761 names (`.example`, `example.com`);
- RFC 5737 IPv4 (`192.0.2.0/24`, `198.51.100.0/24`, `203.0.113.0/24`);
- RFC 3849 IPv6 (`2001:db8::/32`).

A test rejects any other value in the examples.

## Report types (#52–#57)

A report type is a YAML file, validated by pydantic at load:

```yaml
id: threat-activity-alert
number: 4
title: Threat Activity Alert
domain: operational
audience: [SOC analysts, incident responders]
tier: tactical
default_marking: {tlp: AMBER, pap: AMBER}
validity_days: 30
elements:
  - {id: header, required: true}
  - {id: pir_verdict, required: true}
  - {id: threat_summary, required: true}
  - {id: delivery_vector, required: true}
  - {id: triage_actions, required: true}
  - {id: ioc_table, required: true, options: {min_confidence: high, ttl: true}}
  - {id: gaps_limitations, required: true}
  - {id: sources, required: true}
formats: [markdown, json, stix]
```

The per-type reference pages under `docs/reports/`, and a worked example of
each type, are generated from these definitions and a fixture workspace by
`scripts/gen_report_docs.py`. `scripts/check_documentation.py` fails if they
drift.

The 18 starting templates in `cti-output-templates/` are source material and
stay unchanged. #52 lists their defects. The definitions supersede them.

### Element catalogue

| Element | Provenance | Built from | Types |
|---|---|---|---|
| header, revision_history | method | `ReportIssue`, contract | all |
| pir_verdict | method | investigation, lifecycle | all |
| gaps_limitations | method + analyst | lifecycle gaps and limitations, element results | all |
| sources | method | module runs, source ratings | all |
| bluf, situational_overview, threat_summary | model_draft or analyst | cited evidence | 1, 4, 5 |
| key_judgments | analyst or model_draft | assertions with likelihood and confidence | 1, 2, 5, 7, 9 |
| recommendations | analyst | owner, action, due date, expected outcome | 1, 2, 3, 5 |
| org_exposure, sector_targeting | org_input + evidence | org profile matched against observations | 1, 2, 3 |
| macro_trends, emerging_ttps | analyst or model_draft + evidence | framework mappings over the period | 2 |
| scenarios | analyst | likelihood terms, signposts (`indicators_and_signposts`) | 2 |
| defensive_roadmap | analyst | — | 2 |
| asset_profile, business_impact | org_input | org profile (#59) | 3 |
| actor_matrix | evidence + analyst | hypotheses, Nucleotide aliases, dossier Capability | 3, 7 |
| attack_surface | evidence + org_input | Shodan, Censys, InternetDB against org assets | 3 |
| risk_scenarios | analyst | likelihood, impact, control | 3 |
| delivery_vector | evidence | Initial Access framework mappings, observations | 4, 5 |
| triage_actions | method + analyst | IOC-type playbook templates, edited by the analyst | 4 |
| ioc_table | evidence | STIX objects, confidence, first/last seen, TTL | 4, 5, 17 |
| victimology | analyst + evidence | dossier Targeting slot | 5, 7 |
| attack_narrative | model_draft | collection timeline, framework mappings | 5 |
| infrastructure_breakdown | evidence | ASN, hosting, certificate, passive DNS observations | 5, 7 |
| remediation | analyst | — | 5, 6 |
| vuln_metadata, exploitation_status | evidence | NVD, EPSS, KEV (#58) | 6 |
| adversary_adoption | evidence + analyst | ThreatFox and OTX tags, hypotheses | 6 |
| technical_mechanism | analyst or model_draft | NVD description and references | 6 |
| patch_guidance | evidence + analyst | NVD references | 6 |
| actor_identity, motivation, historical_timeline, arsenal | evidence | dossier slots, Nucleotide | 7 |
| infra_opsec | evidence + method | registration, hosting and naming patterns | 7 |
| attack_matrix | evidence | accepted ATT&CK mappings with procedures | 7, 13 |
| diamond_events, activity_threads | evidence | Diamond framework projection | 8 |
| ach_matrix, ach_judgment | analyst + method | `analysis_of_competing_hypotheses` method runs | 9 |
| capability_radar | analyst + org_input | per-axis rubric scores with citations; benchmark from #59 | 10 |
| infra_graph | evidence + method | investigation graph, clusters, edge time bounds | 11 |
| kill_chain_table | evidence + org_input | Kill Chain projection; control status from #59 | 12 |
| break_chain_recommendations | analyst | — | 12 |
| navigator_layer | method | accepted mappings, pinned ATT&CK v19.2 | 13 |
| attack_tree, choke_points | org_input + method | environment model (#59), computed convergence | 14 |
| forensic_timeline, dwell_metrics | org_input + method | telemetry import (#59) | 15 |
| hunt_hypothesis | analyst | ledger hypotheses | 16 |
| hunt_data_sources | method | ATT&CK data components for the techniques | 16 |
| hunt_queries | method | SPL, KQL and EQL generated from IOCs and techniques | 16 |
| baseline_false_positives, triage_playbook, hunt_outcome | analyst | — | 16 |
| pyramid_of_pain | method | indicator types | 17 |
| sigma_rules, suricata_rules | method | IOCs (network and host artifacts) | 17 |
| yara_rules | analyst | analyst-supplied strings or sample features; untested drafts | 17 |
| validation_notes | analyst | what was and was not tested | 17 |
| control_matrix | org_input | control inventory (#59) | 18 |
| gap_list | method | control matrix and the gap rule | 18 |
| emulation_plan | method | technique to Atomic Red Team test id, from a pinned index | 18 |

## Rendering

| Format | Content | Notes |
|---|---|---|
| Markdown | the full report | defanged; provenance shown per element |
| JSON | the full report, schema-validated | not defanged; the schema is published with the docs |
| STIX 2.1 bundle | indicators, observed data, relationships, a `report` SDO, TLP 2.0 marking definitions | only what STIX can represent |
| Navigator layer | type 13 | layer 4.5, Navigator 5.3.2, ATT&CK 19.2 (the pinned manifest) |
| Sigma | type 17 | ISO dates; `status: experimental` until validation notes say otherwise |
| Suricata | type 17 | `sid` in the local range 1000000–1999999; `metadata` and `reference` present |
| YARA | type 17 | sample hash and reference in `meta`; untested drafts are marked |
| Mermaid | types 11, 14 | the attack tree shows AND/OR gates explicitly |

## Issuing and history

Issuing a report renders it and records a `ReportIssue` row: id, type,
version, status, marking, PIR, the element statuses, a content hash and the
JSON rendering. A reissue increments the version and appends a
revision-history entry. Issued content is immutable. This gives every report a
verifiable identity and a real revision history, instead of a hand-typed one.

Decisions made while building it (#50, #51):

- **Preview and issue are separate.** `report` and `report <type>` build a
  preview and write nothing; the header says it is not issued (no ID, version
  0). Only `report issue` writes. The LLM tool `preview_report` can preview but
  never issue: issuing is an analyst act.
- **Reissue scope.** A reissue appends to the latest report of the same type
  for the same active investigation; a different investigation gets a new ID.
  The marking carries over unless the analyst changes it.
- **Header, sources and gaps are built last**, after every other element, so
  the header lists the sources and the gaps section lists every element that
  came back empty or partial. They and `pir_verdict` are mandatory, and the
  header must be the first element; the loader rejects a type that breaks this.
- **Failures are reported, not hidden.** An authority that cannot be read and an
  element builder that raises both become entries in Gaps and Limitations.
- **Issued reports survive `workspace clear`**, like external-publication
  receipts: a disseminated report stays accountable after its sources go. They
  are exported, and merged by row id; IDs are not renumbered on merge.
- **Source ratings.** Pivotglass records no Admiralty ratings yet, so every
  source renders as F6 and the Sources element is `partial` with that gap.
- **PAP in STIX.** STIX has no PAP marking definition; the bundle carries it as
  `x_pivotglass_pap` on the report object.

## Organisation input (#59)

The workspace stores organisation data with provenance `org_input`:

- the organisation profile;
- the control inventory;
- imported telemetry;
- the environment model.

None of it is sent to a model unless the analyst allows it.

## Removal of the superseded path

Done in #50. `generate_dossier_report` became the `investigation-report`
type. Its output for a rich fixture workspace was captured before deletion
(`tests/fixtures/reports/investigation-report.legacy.md`), and a golden test
checks that every line of it is still present in the new report. The
`report` command with no argument produces that report.

## Delivery order

1. #60 PIR fields, definitions, picker, verdict.
2. #50 and #51: the element runtime, the contract module, `ReportIssue`, the
   renderers, and the migration of the current report.
3. #52: the 18 definitions, rewritten, with generated docs and examples.
4. #55 (domain 3) and #54 (domain 2): they rest on the strongest existing
   authorities.
5. #57 (domain 5) with the detection generators; #58 (vulnerability sources)
   before type 6.
6. #59 organisation input, then #53 (domain 1) and #56 (domain 4).
7. The remaining v1.5.0 issues.

The version is bumped and the release prepared only after all of these are
done.

## Open questions resolved by evidence during build

- Whether pinned ATT&CK v19.2 content carries usable data components for
  `hunt_data_sources`. It is a STIX bundle; this must be checked in the
  content itself.
- Pinning Atomic Red Team: which index file to use, its hash, and its licence
  terms, before `emulation_plan` ships.
