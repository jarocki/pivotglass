# Worked example: a connected cluster is not proof of control

[Analytic method](README.md) · [Visual analysis](VISUALIZATIONS.md) · [Learning workspace reference](../LEARNING_WORKSPACE.md)

This exercise uses reserved synthetic training data. It makes no statement about
real infrastructure or a real adversary. It runs through the actual workspace,
evidence, graph, and analytic authorities without API keys or model requests.

## 1. Create a separate learning case

Start `pivotglass`. Enter the following in its command field, using a new name:

```text
workspace learn first-case
```

The command creates and activates a workspace. Its receipt identifies it as
synthetic and reports zero network and model requests. If `first-case` already
exists, use another new name; do not clear a valuable workspace to run a lesson.

The fixture contains four entities, three directional relationship records,
eight observations in two named synthetic source groups, one investigative
question, and two hypotheses. The same domain appears in two observations;
normalizing its entity identity does not erase the separate source histories.

## 2. Read the question before reading the graph

```text
analysis show
analysis lifecycle
```

The recorded question is: “Does the observed reuse indicate one operator or
shared infrastructure?” The hypotheses are:

- **Common control:** one operator controls the file, domain, URL, and address cluster.
- **Shared or repurposed infrastructure:** the observed overlap has another explanation.

Both are proposed explanations. The seeded training assessments are system
records for the exercise, not judgments automatically earned from the graph.

## 3. Trace the observations

Open Evidence and inspect `beacon-check.example`. Locate its source labels,
collection times, response digests, and synthetic handling marking. Compare the
two synthetic dependence groups. In a real case, two labels alone would not
prove independent sourcing; ask whether both reports originate upstream from
the same collector.

The fixture uses `198.51.100.42`, a reserved documentation address, and a synthetic
file named `invoice-viewer.bin`. Do not submit the exercise indicators to live
providers. The point is to practice the reasoning with local data.

## 4. Follow the graph and test your interpretation

```text
graph
graph clusters
graph layers
```

In the browser, open Evidence relationships. Follow the file's
`communicates-with` link to the domain, then the domain's `resolves-to` link to
the address and `hosts` link to the URL. The [visual analysis guide](VISUALIZATIONS.md)
shows the actual v0.9.8 synthetic graph screenshot and its reading limits.

Ask: “Which part of this supports common control?” The topology is consistent
with that hypothesis, but shared infrastructure can produce the same shape.
The fixture explicitly links the connected-cluster assertion as supporting
both hypotheses. This is why a connected component alone is weakly diagnostic.

## 5. Inspect the unresolved problem

```text
analysis contradictions
analysis priorities
```

The fixture records a high-materiality conflict between the explanations and
requires independently sourced ownership, tenancy, and temporal-allocation
evidence to resolve it. It also records a knowledge gap, collection requirement,
prediction, and timeboxed stop condition.

The common-control hypothesis has **Low confidence** because topology is
corroborated but control is not. Its separate likelihood is **roughly even
chance**. Neither value comes from node position or coverage percentage.

A useful next step is information that could distinguish the hypotheses. More
unrelated reputation hits may increase volume while leaving the control
question unanswered. Ask whether the proposed source can establish who used
the address during the relevant interval, and whether collection is authorized.

## 6. Practice a Key Assumptions Check

The next commands add your own training records. They are optional and local.
Copy the real IDs returned by each command rather than typing the placeholders.

```text
analysis assumption Connected infrastructure implies exclusive common control.
analysis method start <question-id> key_assumptions_check {"assumptions":["<assumption-id>"]}
analysis method complete <run-id> {"challenged_assumptions":["<assumption-id>"],"implications":["A shared service can create the same topology. Seek time-bounded independent tenancy evidence before judging control."]}
analysis method accept <run-id>
```

This records your method inputs, result, and review. It does not automatically
change the hypothesis status or manufacture tenancy evidence. The analyst has
to assess whether the stated implication is well founded.

For a second practice pass, use Devil's Advocacy to develop the strongest
shared-infrastructure explanation. Then perform a Premortem: assume the
common-control judgment was wrong and identify what source or temporal mistake
could have produced it. The [method guide](README.md) lists each protocol's
required fields.

## 7. Communicate what remains unanswered

```text
report generate
workspace export first-case
graph export gexf all
graph export json epistemic
```

Replace `first-case` if you chose another name. Review the report for the
question, source basis, alternative, confidence, contradiction, and unresolved
gaps. Do not rewrite an inconclusive record into a confident attribution story.
The exported graph layers and analytic records let another analyst inspect the
reasoning. A JSON workspace export carries metadata and records, not original
raw document bytes; this fixture does not ingest a real document.

## 8. Check persistence and reflect

Close and restart Pivotglass, then enter:

```text
workspace switch first-case
analysis contradictions
```

Verify the unresolved contradiction remains. This is persisted analytical work,
not session decoration. If you added a method run, inspect it with `analysis
method list`.

Before moving to real work, answer:

1. Which fact supported both hypotheses and therefore did little to distinguish them?
2. What source could establish time-bounded control rather than simple co-location?
3. What visibility gap could make the earliest collected event misleading?
4. Why are confidence, likelihood, and investigation coverage different?
5. What would you tell the decision-maker if the timebox expired today?

Create a separate authorized real workspace when ready. Review provider data
handling and scope before collecting. The learning fixture never enables a
provider, saves a credential, accepts a hypothesis, or publishes data for you.
