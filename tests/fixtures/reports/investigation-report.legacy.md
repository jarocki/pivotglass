# Threat Actor Dossier Report

## Priority Intelligence Requirement

**Question:** Who controls the observed infrastructure?

- **Category:** Threat actor and campaign tracking · **Tier:** Operational (Threat hunters and vulnerability management)
- **Verdict:** Not answered by available collection
- **Stop conditions met:** 0 of 4 · **Accepted conclusions:** 0
- **Collection fit (strong):** Infrastructure pivots (passive DNS, certificates, registration, hosting) and CTI feeds tie indicators to campaigns. Naming the actor behind them is still an analyst judgment.

Still needed for an answer:
- Infrastructure linked to the activity is enumerated, and each link cites its source (passive DNS, certificate, registration, or hosting).
- At least two competing explanations of who operates the infrastructure have been tested against the evidence.
- The campaign's first and last observed activity are established from sourced observations.
- The attribution judgment states its likelihood and confidence, or records why the evidence does not support attribution.

Open knowledge gaps:
- Contemporaneous hosting allocation records are unavailable.

## Overview

- **Workspace:** case
- **Date:** 2026-11-26 22:30 UTC
- **Total Score:** 300
- **Modules Used:** 1
- **Total Indicators:** 6
- **Analytic Status:** framing
- **Open Contradictions:** 1

## Scientific Investigation

### Who controls the observed infrastructure?

- **Purpose:** Answer an evidence-grounded analytic question.
- **Scope:** Active workspace evidence and analyst-defined boundaries.
- **State:** framing
- **Authority:** system

### Investigation Questions

- **OPEN** — Who controls the observed infrastructure?

### Assumptions and Assertions

- **ASSUMED · ACTIVE · HUMAN** — Certificate reuse implies common control.
- **JUDGMENT · ACTIVE · HUMAN** — The certificate was supplied by shared hosting.

### Competing Hypotheses

| Hypothesis | Status | Author | Confidence | Likelihood |
|---|---|---|---|---|
| A common operator controls the infrastructure. | proposed | human | low | roughly_even_chance |
| Unrelated tenants share a hosting reseller. | proposed | human | not assessed | not assessed |

### Evidence Tests

Evidence links below are explicit analytic relationships. They do not change the underlying observation.

| Source record | Stance | Target record | Rationale |
|---|---|---|---|
| _No explicit evidence tests recorded._ | — | — | — |

### Predictions, Signposts, Collection, and Stopping Rules

- **STOP CONDITION · OPEN** — Infrastructure linked to the activity is enumerated, and each link cites its source (passive DNS, certificate, registration, or hosting).
- **STOP CONDITION · OPEN** — At least two competing explanations of who operates the infrastructure have been tested against the evidence.
- **STOP CONDITION · OPEN** — The campaign's first and last observed activity are established from sourced observations.
- **STOP CONDITION · OPEN** — The attribution judgment states its likelihood and confidence, or records why the evidence does not support attribution.
- **PREDICTION · OPEN** — An independently sourced certificate match will appear.

### Priority Intelligence Requirements and Next Best Information

Recorded requirements are ranked by explicit analyst priority when present. Otherwise the versioned deterministic information-value policy is used; missing factors score zero.

| Rank | Requirement | Score | Authority |
|---:|---|---:|---|
| — | _No priority intelligence requirements recorded._ | — | — |

**Method-derived suggestions (not evidence):**

- **95/100 · CONTRADICTION RESOLUTION** — Obtain contemporaneous allocation records.
  - Rationale: Resolving an explicit contradiction can change the analytic judgment.
- **78/100 · HYPOTHESIS DISCRIMINATION** — Seek independently sourced evidence that could support or contradict: A common operator controls the infrastructure.
  - Rationale: The hypothesis has no explicitly linked supporting or contradicting evidence.
- **78/100 · HYPOTHESIS DISCRIMINATION** — Seek independently sourced evidence that could support or contradict: Unrelated tenants share a hosting reseller.
  - Rationale: The hypothesis has no explicitly linked supporting or contradicting evidence.
- **60/100 · KNOWLEDGE GAP** — Resolve the recorded intelligence gap: Contemporaneous hosting allocation records are unavailable.
  - Rationale: The analyst explicitly recorded this unresolved gap.

### Structured Analytic Technique Runs

Recorded method work is authored analysis, not observed evidence or automatic approval.
- **Key Assumptions Check v1.0** — complete; analyst disposition: pending

**Recorded inputs:**

```json
{
  "assumptions": [
    "Shared hosting implies control."
  ]
}
```


**Recorded outputs:**

````json
{
  "challenged_assumptions": [
    "No exclusive control observed. ``` Close?"
  ],
  "implications": [
    "Collect independent tenancy evidence."
  ]
}
````


### Contradictions

- **HIGH · UNRESOLVED** — Common control and shared hosting are competing explanations.
  - Resolution required: Obtain contemporaneous allocation records.

### Conclusions, Limitations, and Intelligence Gaps

- **KNOWLEDGE GAP · OPEN** — Contemporaneous hosting allocation records are unavailable.
- **LIMITATION · OPEN** — Only one passive DNS provider was queried.

### Confidence Basis

- **hypothesis:hypothesis-83d9e64d-4282-4785-ac1f-2585e1c19200 — LOW confidence**: The current evidence comes from one source.
  - Factors: `{'source_quality': 'one API source with direct access', 'source_independence': 'one dependence group', 'corroboration': 'not corroborated', 'assumptions': ['certificate reuse implies control'], 'knowledge_gaps': ['hosting allocation unavailable'], 'analytic_rigor': 'competing explanation retained'}`

## Executive Summary

This investigation collected **6 indicator(s)** across **1 module(s)**. Total pursuit score: **300 pts**.
Indicator types: domain-name: 1, email-addr: 1, file: 1, ipv4-addr: 1, ipv6-addr: 1, url: 1.

## Dossier State

| Slot | Status | Evidence Count | Contributing Types |
|------|--------|----------------|--------------------|
| Identity | PARTIAL | 1 | email-addr |
| Ttps | FILLED | 2 | file, url |
| Infrastructure | FILLED | 3 | domain-name, ipv4-addr, ipv6-addr |
| Timing | PARTIAL | 7 | timestamp |
| Targeting | DEFERRED | 0 |  |
| Capability | PARTIAL | 1 | osint/whois_lookup |
| Motivation | EMPTY | 0 |  |
| Predictions | DEFERRED | 0 |  |
| Denial | EMPTY | 0 |  |

## Predictions

_Legacy Dossier Predictions Log. Schema-v4 scientific predictions and signposts are reported in Scientific Investigation above._

**Summary:** 1 validated, 1 pending, 0 falsified

### Validated Predictions

- **[Infrastructure]** Actor will reuse .example infrastructure _(validated 2026-06-08)_

### Pending Predictions

- **[Identity]** Actor uses targeted spearphishing

## Analyst Notes

- [2026-11-26 22:30] Certificate overlap with a prior cluster
- [2026-11-26 22:30] Hosting looks like a single reseller

## Indicators of Compromise

| Type | Value | First Seen |
|------|-------|------------|
| email-addr | operator@mail.example | unknown |
| url | https://login.example.com/c2 | unknown |
| ipv4-addr | 192.0.2.44 | unknown |
| domain-name | c2.example.net | unknown |
| ipv6-addr | 2001:db8::44 | unknown |
| file | aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa | unknown |

## Investigation Timeline

- `2026-11-26 22:30` — **osint/whois_lookup** on `c2.example.net` -> 6 object(s)

## Statistics

- Total indicators: 6
- By type:
  - domain-name: 1
  - email-addr: 1
  - file: 1
  - ipv4-addr: 1
  - ipv6-addr: 1
  - url: 1
- Total score: 300
