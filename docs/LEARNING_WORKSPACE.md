# Offline learning investigation

`workspace learn <name>` creates a complete synthetic investigation without an
API key, model, account, or network request. It uses Pivotglass's real
workspace, provenance, graph, analytic-ledger, report, export, restart, and
recovery paths. It is not a recorded animation and it does not bypass the
product's authorities.

Every value uses an IANA-reserved example domain, address, or a synthetic file
hash. Every observation is marked `TLP:CLEAR // SYNTHETIC TRAINING DATA`. The
case is useful for learning the workflow; it is not threat intelligence.

## Create the case

Start Pivotglass, then enter:

```text
workspace learn first-case
```

Pivotglass creates and switches to `first-case`. The receipt reports zero
network and model requests and lists useful next commands. The workspace
contains:

- four entities and three directional relationships;
- two separately identified synthetic source groups and eight immutable
  observations;
- one question and two competing hypotheses;
- source-linked assertions, formal confidence, and a separate likelihood
  assessment;
- one unresolved high-materiality contradiction;
- a prioritized knowledge gap, collection requirement, prediction, and stop
  condition.

The fixture is deliberately incomplete. A useful investigation should expose
what evidence cannot yet answer.

## Follow the evidence

Inspect the stored facts and collection history:

```text
status
search
timeline
```

Open **Evidence** in Pivotglass and select an entity. Confirm that its detail
names the synthetic source, collection time, response digest, and handling
marking. The same normalized domain appears in two observations because entity
deduplication must not erase source history.

## Pivot through the graph

Open **Visualize**, then **Evidence relationships**, or enter:

```text
graph
graph clusters
graph layers
```

The file, domain, URL, and IPv4 address form one connected component because
the fixture stores three explicit relationships. Their proximity is not the
reason they are connected; the persisted edges are. The cluster is navigation,
not actor attribution.

## Review the analysis rather than accepting it

Enter:

```text
analysis lifecycle
analysis show
analysis contradictions
analysis priorities
```

Compare the common-control and shared-infrastructure hypotheses. Both can fit
the topology. Pivotglass therefore records low confidence and roughly-even
likelihood for common control, preserves the alternative, and asks for
contemporaneous ownership or tenancy evidence. Confidence describes the basis
of the judgment; likelihood describes the proposition. They are not one score.

This is the key learning moment: a connection is not control, and a coherent
story is not proof.

## Report and export

Generate a source-grounded report:

```text
report generate
```

Export the portable workspace and graph:

```text
workspace export first-case
graph export gexf all
graph export json epistemic
```

The workspace export includes evidence, provenance, questions, hypotheses,
assertions, confidence, likelihood, contradictions, and open work. GEXF is for
graph tools such as Gephi. The epistemic JSON layer keeps reasoning records
distinct from observed entities.

## Prove restart and recovery

Close Pivotglass, start it again, then enter:

```text
workspace switch first-case
analysis contradictions
graph clusters
```

The contradiction and graph are persisted; they are not session decoration.

For a non-destructive file-level recovery rehearsal, stop Pivotglass and copy
the workspace under a new name:

```bash
cp ~/.ap/workspaces/first-case.db ~/.ap/workspaces/first-case-recovered.db
```

Restart Pivotglass and enter:

```text
workspace switch first-case-recovered
workspace schema first-case-recovered
analysis show
```

The copied case should validate and contain the same analytic record. This
rehearsal leaves the original untouched. For schema-migration recovery, follow
the [workspace migration and recovery guide](WORKSPACE_MIGRATIONS.md).

## Start real work deliberately

Create a separate workspace before submitting a real indicator:

```text
workspace create authorized-case
```

Review enabled services, provider terms, data sensitivity, and authority before
collecting. The offline learning command never enables a provider, saves a
credential, submits an indicator, accepts an analytic proposal, or publishes
data.
