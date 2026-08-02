# Analytic method in Pivotglass

Pivotglass uses a scientific investigation loop: state the question, propose
competing and falsifiable explanations, identify what would support or weaken
them, collect evidence, retain contradictions, and revise the judgment. The
software structures this work; it does not decide attribution for the analyst.

## Records that must remain distinct

- **Observation:** immutable output accepted from a named source at a recorded
  time. Two sources reporting the same domain are two observations.
- **Assertion:** a contestable statement derived from observation, assumption,
  inference, or judgment.
- **Hypothesis:** a candidate answer to an investigation question.
- **Evidence link:** an explicit statement that an observation or assertion
  supports or contradicts an assertion or hypothesis, with a rationale.
- **Likelihood:** a standardized probability term for the proposition.
- **Analytic confidence:** the analyst's Low, Moderate, or High confidence in
  the evidence and reasoning. It is not probability or Dossier completeness.
- **Contradiction:** a persistent conflict that records its materiality and the
  evidence needed to resolve it.

Character narration and model synthesis are presentation. Neither becomes an
observation or accepted hypothesis automatically.

## Local commands

These commands run without an LLM and are shared by the TUI and Pivotglass:

```text
analysis show
analysis methods
analysis contradictions
analysis question Who controls the observed infrastructure?
analysis assertion inferred The certificate was reused across both hosts.
analysis hypothesis <question-id> A single operator controls both hosts.
analysis confidence hypothesis <hypothesis-id> low Only one source supports this.
analysis likelihood hypothesis <hypothesis-id> unlikely Shared hosting remains plausible.
analysis accept <hypothesis-id>
analysis reject <hypothesis-id>
analysis suspend <hypothesis-id>
```

New hypotheses begin as `proposed`. Only an explicit human command can retain,
reject, or suspend one. A model may propose structured work, but it cannot
disposition it.

## Structured Analytic Techniques

`analysis methods` lists the versioned protocols and their required inputs and
outputs. The initial workbench includes:

- Quality of Information Check;
- Key Assumptions Check;
- Analysis of Competing Hypotheses;
- Indicators and Signposts;
- Devil's Advocacy;
- Premortem Analysis;
- Chronology and Timeline Analysis.

Every method run records its protocol version, inputs, outputs, author, state,
and analyst disposition. This makes the method reviewable even if the model or
conversation that helped draft it is no longer available.
