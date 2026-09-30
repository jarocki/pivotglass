# Pivotglass: from a clue to a defensible judgment

**A local, AI-augmented workspace for cyber-threat investigation.**

## Why it exists

An alert, a suspicious domain, or a report is a starting point. The next
questions are harder: What actually happened? Which sources support it? What
else could explain the activity? What evidence would change the assessment?
What decision does the investigation need to support?

Analysts need both collection tools and a way to make their reasoning
inspectable. Pivotglass brings these activities into a persistent local case
workspace, with human judgment remaining authoritative.

## What an analyst can do

- **Frame a useful question.** The Pursuit Brief shows the active question and
  proposed next step. Novice Q&A helps a new analyst describe available data,
  events, origins, scope, the decision, and alternative explanations.
- **Collect deliberately.** Choose provider actions and review local document
  previews and entity candidates before admission. Keep source receipts and
  enrichment work visible.
- **Inspect connections.** Relationship graphs distinguish stored relationships,
  property pivots, and analyst grouping. Provenance history shows how the analyst
  reached the current evidence. A shared property or a visual cluster alone is
  insufficient for attribution.
- **Challenge a first explanation.** Record competing hypotheses, predictions,
  contradictions, gaps, and structured analytic technique results. Distinguish
  observations, inferences, and judgments.
- **Hand off the reasoning.** Produce reports and structured exports another
  analyst can inspect, with provenance and uncertainty preserved.

These functions are designed to reduce repeated navigation and data handling,
and to strengthen the traceability of decisions. No measured productivity or
learning benefit is claimed.

## Learning during the work

Guided framing, explicit unknowns, rotating lessons, and reflection support
practice over repeated investigations. Analysts can reduce guidance when ready.
Pivotglass does not automatically declare a learner expert or substitute a
completion count for mentoring and demonstrated competence.

## An approachable evaluation

Start with the synthetic offline learning case: no provider account or API key
is needed. Try the question-to-evidence-to-report loop, then decide which
optional collection and model services fit your environment. The browser
cockpit is the primary interface; terminal interfaces share the case workspaces.

## Boundaries to know

Pivotglass stores local data and serves its browser cockpit on loopback by
default. Enabled providers and model services can receive information selected
for their requests. Optional voice narration can send text to its configured
service. Review handling rules before enabling these features.

Current local intake qualifies text, Markdown, HTML, CSV, JSON, JSONL, and email
text/headers within documented limits. PDF is recognition-only; Office parsing,
OCR, archive expansion, URL intake, and RSS intake remain deferred. SCOT4 and
Vertex Synapse remain preview integrations. Capacity limits and omitted-view
counts are explicit.

**Evaluate:** [Quick Start](../QUICKSTART.md) →
[offline learning case](../LEARNING_WORKSPACE.md) →
[implementation](../operations/IMPLEMENTATION.md).

**Inspect the boundaries:** [Compatibility](../COMPATIBILITY.md) ·
[Data safety](../DATA_SAFETY.md) · [Capacity](../CAPACITY.md) ·
[Analytical method](../analysis/README.md).
