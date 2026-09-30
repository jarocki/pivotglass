# Implement Pivotglass deliberately

[Documentation home](../README.md) · [Infrastructure](INFRASTRUCTURE.md) · [Operations](OPERATIONS.md) · [Quick Start](../QUICKSTART.md)

Use this guide to establish an accountable local analyst workspace, verify it
with synthetic data, and introduce authorized real collection. It is an
implementation plan for the current product. It does not establish production
qualification of optional integrations or approve the future v1.0 release.

## 1. Choose a bounded first use

A useful initial scope is one analyst, one workstation account, and one small
case with a named decision-maker. Examples are checking an infrastructure
relationship, comparing explanations for a suspicious connection, or organizing
a threat report for a defensible handoff.

Agree on the question, time window, allowed sources, data sensitivity,
collection authority, report audience, and stop condition before enabling
services. Choose a source that can change the decision rather than connecting
every available service simply because it exists.

| Responsibility | Owner | Initial decision |
| --- | --- | --- |
| Investigative purpose and actions | Case owner / analyst lead | Question, scope, containment or collection decision |
| Workstation and installation | Local administrator | Supported runtime, account, storage, update window |
| Data handling | Data owner | Permitted provider submissions, report audience, retention |
| Service and model credentials | Credential owner | Least necessary provider access and approved context |
| Recovery | Local administrator with case owner | Backup location, retention, restoration test |
| Release acceptance | Repository/release owner | Verified version and gates; final v1.0 approval remains separate |

One person can hold multiple roles; record who has authority for each decision.

## 2. Install the selected release

The reproducible path is the source tag and committed lockfile. Python 3.12+
Git, and uv are required. The release contains the built browser interface;
Node.js is needed only for browser development/rebuild. Read
[Infrastructure](INFRASTRUCTURE.md) for boundaries and prerequisites.

The commands below select the v1.0.0 release. Run them only after that tag has
been published and read back. Until then, use the actual reviewed candidate
checkout with its status recorded; do not invent a public tag.

```bash
git clone --branch v1.0.0 --depth 1 https://github.com/jarocki/pivotglass.git
cd pivotglass
uv sync --extra agent --frozen
uv run pivotglass --version
uv run pivotglass --help
```

The version must match the selected tag. Run `uv run pivotglass` from this
checkout to start the local browser cockpit. Visit `http://127.0.0.1:8765` if
it does not open. Keep the launch terminal available to stop the server.

A wheel has compatible dependency ranges and can resolve a different set from
the exact release lock. A successful wheel install is a packaging receipt;
it does not make that resolver's dependency selection the qualified source
lock. Follow [Release trust](../RELEASE_TRUST.md) to verify downloaded artifacts
and the signing fingerprint through an independently trusted channel.

## 3. Preserve an earlier installation

Stop all processes using the old data directory. Make a separate backup before
using a new release. The explicit migration copies into a new absent directory,
refuses merges and symbolic links, and preserves the source:

```bash
uv run pivotglass migrate-home --from /absolute/path/to/previous-data --confirm-stopped
```

Its default destination is `~/.pivotglass`. If that directory already exists,
the command fails rather than merging cases. Resolve the intended source and
destination deliberately. `--to /absolute/path/to/new-copy` controls the copy
location; it does not reconfigure where ordinary launches read application data.

The copy preserves database files and sibling raw-document content stores.
Workspace schema migration is a separate forward-only process when a workspace
is opened. Update launchers, custom module registration, and credential
environment variables to `pivotglass` and `PIVOTGLASS_*`; the old command is
not a supported alias. Review [Migration](../WORKSPACE_MIGRATIONS.md).

## 4. Prove the no-key workflow

In the cockpit command field, enter a new workspace name:

```text
workspace learn implementation-check
workspace schema implementation-check
analysis lifecycle
analysis contradictions
graph clusters
report generate
workspace export implementation-check
```

Confirm the learning receipt reports synthetic data, zero network requests, and
zero model requests. Review four entities, three relationships, two hypotheses,
an unresolved conflict, and the report's explicit uncertainty. Open the
relationship graph and inspect an edge's truth class and source basis.

Restart the application and use `workspace switch implementation-check`.
Verify the case and conflict survive. Preserve the receipt for implementation
acceptance. This demonstrates the local path; it does not test a live provider,
a remote backend, or operational containment.

Continue with [the worked case](../analysis/WORKED_EXAMPLE.md), then use
[Novice Q&A](../analysis/LEARNING.md) to practice question framing. Browser-local
answers and reflections are separate from database-backed saved questions.

## 5. Introduce real sources and services

Create a separate real workspace with `workspace create authorized-case`.
Review enabled services in Configuration. Configure only approved providers;
a status label can describe configuration without proving working access.
**SAVE + TEST** or a provider check is an explicit network action. Model
synthesis is optional; local analysis and evidence navigation do not require it.

Preview a supported local report. Verify its hash, parser warnings, and exact
candidate spans. Explicitly admit the source alone or source plus selected
entities. This does not enrich the admitted indicators. Choose the appropriate
indicator and explicitly begin collection only after reviewing where it will
be sent. A source claim, text match, or analyst admission group does not establish
maliciousness or common control.

For one bounded authorized collection, confirm the task reaches a truthful
terminal state and its results retain source/time metadata. Record failures or
partial results rather than rewriting them as successful coverage. The owner
must decide whether any provider is acceptable for private indicators; local-first
operation does not mean every service action stays local.

## 6. Establish handoff and recovery

Give a reviewer the question, sourced reasoning, alternatives, confidence basis,
material conflicts, and unresolved collection requirements. A report may be
shareable while raw evidence is restricted; apply the data owner's handling
requirements to both.

Test a full stopped-home backup and isolated restoration using
[Operations](OPERATIONS.md#backup-and-restoration). JSON workspace exports
contain records and metadata, not original raw document bytes. A case with
admitted documents requires the sibling content store as well as its database.
Browser local storage requires separate handling if coaching drafts matter.

## Acceptance checklist

| Gate | Evidence to retain | What failure means |
| --- | --- | --- |
| Installation | Tag/commit, lock, version/help output | Wrong environment or unverified install |
| Local launch | Cockpit and loopback health | Resolve launch or stale-build problem |
| Synthetic workflow | Learning receipt, graph, report | Local analytical path not yet accepted |
| Restart | Same persisted question/conflict | Persistence needs investigation |
| Data migration | Source preserved, copy and schema validation | Stop before using valuable data |
| Real collection | Authorized bounded attempt and truthful terminal state | Provider not qualified for the selected workflow |
| Handoff | Peer can trace conclusion and gaps | Documentation or analytic record needs revision |
| Recovery | Restored copied database/content and reviewed record | Backup not yet demonstrated recoverable |
| Ownership | Named case, data, credential, and recovery owners | Deployment responsibilities remain incomplete |

These gates are local implementation acceptance. Public release readback and the
future final correctness, resilience, efficiency, security, and usability pass
have their own [roadmap](../plans/V0.9.8_TO_1.0_ROADMAP.md).
