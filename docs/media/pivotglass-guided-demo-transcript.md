# Pivotglass guided walkthrough transcript

**Runtime:** 2 minutes, 12 seconds
**Release:** v0.7.0 early availability

The demonstration uses synthetic indicators and a local mock model provider.
No real API key or external service is shown.

This is Pivotglass: a local, AI-augmented interface for threat investigation.

Starting Pivotglass opens the Default Analyst workspace. The command field
remains the fastest path, while the surrounding panels keep evidence, status,
and analytical context visible.

Configuration is available without leaving the investigation. Credentials stay
masked by default. Here, a clearly labeled demonstration key is provisioned and
tested locally.

The model catalog shows what the selected provider actually offers, including
each model's recorded strengths and limitations. The reasoning model is
selected, and Pivotglass confirms the authoritative setting.

Now an indicator is entered. Pivotglass normalizes the target and schedules
enrichment. The activity feed distinguishes completed work from pending work,
and evidence from interpretation.

The Investigation Constellation keeps every indicator visible as a row. Each
Dossier dimension becomes a status cell, with sorting and filtering available
for type, completeness, time, and relationship.

The relationship view shows indicators as nodes and source-backed
relationships as directed edges. Selecting a node reveals its immediate
neighborhood. From there, the analyst can pivot directly into the evidence and
provenance that justify the relationship.

Reporting uses the same stored evidence. The report command produces a
deterministic investigation summary that can be reviewed and exported, without
asking a model to invent missing facts.

Pivotglass can change character without changing analytical truth. Default
Analyst is quiet and direct. Sherlock Holmes uses a Victorian casebook, warm
brass tones, and deduction-first language. Neuromancer becomes a colder Sprawl
interface, with dark cyberpunk atmosphere and a more driving score.

Across every mode, the workflow stays consistent: start locally, provision
safely, choose the right model, enrich through explicit services, pivot through
evidence, graph relationships, and produce a report the analyst can defend.
