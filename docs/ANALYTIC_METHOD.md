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
- **Investigation lifecycle item:** an organizing link from one scientific
  investigation to an existing question, hypothesis, assertion, or method run,
  or a native planning record such as a prediction, signpost, collection
  requirement, stop condition, conclusion, limitation, or knowledge gap.

Character narration and model synthesis are presentation. Neither becomes an
observation or accepted hypothesis automatically.

## Local commands

These commands run without an LLM and are shared by the TUI and Pivotglass:

```text
analysis show
analysis lifecycle
analysis methods
analysis contradictions
analysis priorities
analysis question Who controls the observed infrastructure?
analysis assumption Certificate reuse implies common control.
analysis assertion inferred The certificate was reused across both hosts.
analysis hypothesis <question-id> A single operator controls both hosts.
analysis prediction A second independently sourced certificate match will appear.
analysis signpost An unrelated provider confirms the certificate match.
analysis collect Obtain contemporaneous hosting-allocation records.
analysis requirement Obtain independently sourced allocation records. | {"decision_impact":4,"discriminating_power":4,"time_sensitivity":2,"feasibility":3}
analysis prioritize <requirement-item-id> 75
analysis stop Stop after two independent sources agree or the timebox expires.
analysis limitation Historical allocation records may no longer exist.
analysis gap The hosting tenant during the observed interval is unknown.
analysis confidence hypothesis <hypothesis-id> low Only one source supports this. | {"source_quality":"direct API record","source_independence":"one dependence group","corroboration":"not corroborated","assumptions":["certificate reuse implies control"],"knowledge_gaps":["tenant unknown"],"analytic_rigor":"alternative retained"}
analysis likelihood hypothesis <hypothesis-id> unlikely Shared hosting remains plausible.
analysis accept <hypothesis-id>
analysis reject <hypothesis-id>
analysis suspend <hypothesis-id>
analysis contradiction assertion <left-id> assertion <right-id> The tenancy judgments conflict. | Obtain allocation records.
analysis resolve <contradiction-id> Provider records confirm shared tenancy.
```

New hypotheses begin as `proposed`. Only an explicit human command can retain,
reject, or suspend one. A model may propose structured work, but it cannot
disposition it.

## Priority intelligence requirements

`analysis priorities` ranks the active investigation's recorded collection
requirements and displays bounded next-best-information suggestions. The policy
is deterministic and versioned as `pivotglass-information-value-v1`.

An explicit analyst priority from 1 through 100 is authoritative. A priority of
0 clears that override. Without an override, Pivotglass computes information
value from four analyst-declared factors, each scored from 0 through 4:

| Factor | Weight | Meaning |
| --- | ---: | --- |
| Decision impact | 30% | Could the answer change an analytic judgment or action? |
| Discriminating power | 30% | Could it distinguish among competing explanations? |
| Time sensitivity | 20% | Would delay materially reduce its value? |
| Feasibility | 20% | Can the information be obtained within current constraints? |

Missing factors score zero; Pivotglass does not infer convenient values. An
unscored `analysis collect` record remains valid but ranks at zero until the
analyst supplies factors or an explicit priority.

Open contradictions, unsupported hypotheses, knowledge gaps, and missing
analytic safeguards can produce **Next Best Information** suggestions. Each
suggestion exposes its score, rationale, and source record IDs. It is method
output, not evidence, and is not persisted as a requirement until the analyst
chooses **Adopt as Requirement** or records it explicitly. Reports preserve the
same distinction.

Analytic confidence requires six explicit factors: source quality, source
independence, corroboration, assumptions, knowledge gaps, and analytic rigor.
An unknown factor must be written as unknown; it cannot be omitted. Likelihood
continues to use a separate standardized probability vocabulary.

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

The command form is deliberately explicit and accepts JSON method records:

```text
analysis method start <question-id> key_assumptions_check {"assumptions":["<assertion-id>"]}
analysis method complete <run-id> {"challenged_assumptions":["<assertion-id>"],"implications":["Seek independent tenancy evidence."]}
analysis method accept|reject|revise <run-id>
analysis method list [question-id]
```

Pivotglass presents the same records as a Scientific Notebook. Its ACH matrix
uses only explicit evidence links; an empty cell means no recorded relationship,
not neutral evidence. The exported workspace archive and generated Markdown
report include the lifecycle, method runs, confidence basis, contradictions,
limitations, and unresolved gaps.
