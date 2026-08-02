# Pivotglass User Guide

Pivotglass is a local-first investigation workspace for collecting, connecting,
and testing cyber-threat evidence. The installed command remains `ap`. The
browser interface is the default; the terminal interface and direct
module-control console share the same underlying workspaces and evidence.

Start with the [Quick Start](QUICKSTART.md) if this is your first session.

[![Watch the guided workflow](media/pivotglass-guided-demo-poster.png)](media/pivotglass-guided-demo-v0.7.0.mp4)

[Watch or download the walkthrough](media/pivotglass-guided-demo-v0.7.0.mp4) ·
[Read the transcript](media/pivotglass-guided-demo-transcript.md)

## Choose an interface

```bash
ap             # Local Pivotglass browser interface
ap web         # Same as bare ap
ap tui         # Full-screen terminal interface
ap chat        # Alias for the terminal interface
ap basic       # Direct module-control console
ap repl        # Alias for the direct console
```

Pivotglass prints its local address when it starts and opens the browser when
the platform permits. It listens on `127.0.0.1` by default and serves packaged
local assets; no hosted UI is required.

## The investigation workflow

1. Select or create a workspace.
2. Enter an IP address, domain, URL, email address, or file hash.
3. Pivotglass classifies the indicator and immediately starts the applicable
   enabled enrichment work.
4. Review lifecycle state and returned evidence. A completed job is not a
   threat verdict.
5. Use the Investigation Constellation to see coverage and gaps for every
   indicator.
6. Use Visual Analysis and the relationship graph to understand distributions,
   activity, and supported relationships.
7. Queue a newly discovered indicator only after reviewing its provenance and
   relevance.
8. Add analyst notes, answer Dossier gaps, and generate a report or export.

Natural-language questions go to the configured model only when deterministic
local routing cannot answer them. Direct tools and stored evidence remain the
source of observed facts. Character narration, music, effects, scores, and
mini-games carry no analytical meaning.

## Workspaces

Each investigation has an isolated SQLite workspace under `~/.ap/`. Workspaces
store normalized STIX objects, relationships, module runs, notes, score events,
badges, and Dossier state.

```text
workspace list
workspace create <name>
workspace switch <name>
workspace export <name>
workspace merge <source> <destination>
workspace delete <name> --confirm <name>
```

Creating a workspace also switches to it. A merge adds evidence to the
destination without deleting either source. Deletion requires the exact
workspace name and cannot remove the active workspace; switch first.

## Enrichment and lifecycle state

The first indicator submitted in the command field starts applicable
enrichment immediately. Later indicators discovered in evidence can be added
to the investigation queue with **+ QUEUE**. **RUN NEXT** processes one queued
indicator; **RUN ALL** processes the queue in order.

The authoritative lifecycle is:

```text
planned → queued → running → succeeded | empty | failed | skipped | canceled
```

Lifecycle describes work, not the indicator. `succeeded` means the source
returned successfully. `empty` means it returned no usable result. Neither
state proves that an indicator is safe or malicious.

Most integrations query intelligence already held by a provider. Pivotglass
does not issue direct DNS queries from the operator host. URLScan can submit a
URL or domain for an external browser scan. Review each provider's terms,
quotas, and handling before submitting sensitive or embargoed indicators.

During a terminal investigation, these yield controls remain available:

```text
stop             Stop after the current enrichment finishes
focus <source>   Move one source to the front of the pending queue
add <source>     Add a source to the pending queue
skip <source>    Remove a source from the pending queue
```

## Evidence and provenance

Evidence details show the actual indicator, STIX type, normalized fields,
source, query target, collection time, stored relationships, and available
source metadata. Long values are shortened only in the middle in compact
views; the complete value remains available in details and accessible labels.

Country flags and known-malware marks appear only when stored source data
supports them. Analyst notes are labeled as analyst-authored context. Inference
details identify their supporting evidence. Missing provenance remains visibly
unavailable rather than being reconstructed by a model.

## The Dossier

The Dossier is a coverage summary, not a threat score. Its nine dimensions are:

| Dimension | Question |
| --- | --- |
| Identity | Who or what does the evidence identify? |
| TTPs | What techniques, tools, and tradecraft appear? |
| Infrastructure | What hosting, registration, certificate, or network habits appear? |
| Timing | When does activity occur? |
| Targeting | Which victims, sectors, or geographies appear? |
| Capability | What level and limits of capability does the evidence support? |
| Motivation | What motive, if any, is supported? |
| Predictions | What testable expectations have been recorded? |
| Denial | What deception or counter-analysis behavior appears? |

A dimension may be:

- **filled** — the implemented inference path has substantial supporting evidence;
- **partial** — some supporting evidence exists;
- **empty** — the implemented path found no support; or
- **deferred** — no applicable automated inference path exists yet.

These are coverage states. They are not confidence, severity, attribution, or a
malware verdict.

## Investigation Constellation

The Investigation Constellation is the persistent coverage table in Visual
Analysis. Stored indicators form rows, and the nine Dossier dimensions form
columns. The initial order is newest last-seen first.

You can filter or sort by:

- indicator value;
- indicator type;
- mapped completeness;
- first seen;
- last seen; and
- direct relationship to a selected indicator.

Each row is calculated from the indicator and evidence in its direct graph
neighborhood. Relationship filters use only edges admitted by the graph
authority. Selecting an indicator opens its evidence; selecting a cell explains
the dimension state.

The overall mapped value is navigation help, not confidence or a verdict.

![Investigation Constellation](media/pivotglass-constellation-v0.7.0.png)

## Visual Analysis

Visual Analysis starts with the analyst question rather than a preferred chart
type. Pivotglass currently provides:

- stored evidence types, compiled through Flint as a bar chart;
- one-Dossier completeness, compiled through Flint as a radar chart on an
  explicit 0–100 display scale;
- investigation activity by UTC calendar day;
- the Investigation Constellation;
- indicator-by-enrichment lifecycle activity; and
- the force-directed relationship graph.

Every view states its source scope and missing-data policy. **View exact data
and caveats** opens the accessible table behind the visual. **Export exact
data** downloads the same plotted rows as CSV, or the complete relationship
nodes and edges as JSON.

Deferred dimensions remain in the table but are omitted from the radar shape
because they do not have an inference path. Radar values 0, 50, and 100 map to
empty, partial, and filled; they are not confidence scores.

## Relationship graph

The relationship graph uses actual indicator values for node labels and
directional relationships for edges. Stored STIX relationships and conservative
property pivots are visually distinguished. Select a node to highlight its
neighbors; double-click it, or choose **OPEN EVIDENCE**, to inspect the stored
record.

Dragging, panning, zooming, filtering, centering, and selecting change only the
saved presentation. They do not alter evidence. Large workspaces use a bounded
overview. If no supported edge exists, Pivotglass says so and keeps the
evidence unconnected rather than manufacturing a relationship from proximity.

![Evidence-backed relationship graph](media/pivotglass-graph-v0.7.0.png)

## Reports and exports

```text
report
report generate
export json
export csv
export stix
export gexf
```

Reports are generated from the active workspace. They summarize current
evidence and visible gaps; they do not turn absent data into findings. The
report dialog can print or save PDF through the browser.

JSON and CSV support inspection and downstream analysis. STIX supports
structured exchange. GEXF supports graph tools such as Gephi. Exports can
contain raw indicators and provider-derived information; review them before
sharing.

![Dossier report](media/pivotglass-report-v0.7.0.png)

## Configuration and models

Configuration is stored under `~/.ap/config.toml` with restrictive permissions.
The Pivotglass **CONFIGURATION** dialog can inspect masked state, save and test
credentials, enable or disable intelligence sources, enable or disable model
synthesis, list account-visible models, and select a model.

A secret typed into Configuration exists transiently in the password field and
explicit local save/test request. Stored secrets are not returned by routine
polling or repopulated into the form. Environment-owned credentials remain
read-only. Secrets must not enter command history, notes, exports, screenshots,
or model prompts.

The model catalog combines a provider's availability response with local
LiteLLM capability metadata when available. Strengths and limitations are
evidence-proportional notes, not rankings. A visible model can still lack
quota, perform poorly for a case, respond slowly, or change at the provider.

### Model commands

```text
model show
model providers
model list
model check
model select [provider] <provider-model-id>
model enable
model disable
model repair
model configure
model advisor on
model advisor off
```

`model show`, enable/disable, and repair use local state. `model list`, check,
selection, and **SAVE + TEST** contact the selected provider only when
explicitly requested.

When enabled, the Configuration Advisor periodically offers one non-modal,
character-voiced suggestion based only on masked local state. It is labeled
**Narration**, makes no model request, spends no tokens, adds no evidence, and
does not take focus.

### Intelligence-service commands

```text
config show
config check <service>
config enable <service>
config disable <service>
config repair
config configure
```

Disabling a source prevents it from running while preserving its stored
credential. WHOIS and crt.sh require no API credential; the system WHOIS module
does require a local `whois` executable.

Common non-interactive overrides include:

```bash
export AP_MODEL=anthropic/claude-sonnet-4-5
export AP_ANTHROPIC_API_KEY=...
export AP_SHODAN_API_KEY=...
ap
```

Pivotglass also recognizes documented vendor environment variables. Never
commit credentials to the repository.

## Command reference

Pivotglass and the terminal interface share this deterministic command grammar:

| Command | Purpose |
| --- | --- |
| `workspace list` | List workspaces |
| `workspace create <name>` | Create and switch to a workspace |
| `workspace switch <name>` | Switch workspaces |
| `workspace schema [name]` | Validate integrity and preview a migration without changing data |
| `workspace export <name>` | Export a portable workspace archive |
| `workspace merge <source> <destination>` | Add source evidence to a destination |
| `workspace delete <name> --confirm <name>` | Delete after exact confirmation |
| `mode list` / `mode <public name>` | List or select a character |
| `use <indicator>` | Set the current target |
| `search [STIX type]` | Search stored evidence, optionally by type |
| `graph` | Open a deterministic relationship summary |
| `dossier` / `gaps` | Inspect coverage and missing evidence |
| `timeline` | List stored collection events chronologically |
| `analysis show` | Inspect questions, hypotheses, assertions, confidence, likelihood, and contradictions |
| `analysis methods` | List versioned Structured Analytic Technique protocols |
| `analysis question <text>` | Record the question the investigation must answer |
| `analysis assertion <type> <text>` | Record an inferred, assumed, or judgment statement; observations come only from sources |
| `analysis hypothesis <question-id> <text>` | Propose a falsifiable candidate answer |
| `analysis accept\|reject\|suspend <hypothesis-id>` | Record an explicit analyst disposition |
| `analysis confidence <kind> <id> <level> <rationale>` | Record Low, Moderate, or High analytic confidence |
| `analysis likelihood <kind> <id> <term> <rationale>` | Record probability language separately from confidence |
| `note <text>` | Add an analyst note |
| `report` / `report generate` | Build the current Dossier report |
| `export json\|csv\|stix\|gexf` | Export investigation data |
| `hint [source]` / `challenges` | Use optional assistance |
| `autopivot on\|off` | Control event-driven pivots |
| `status` | Show current workspace and character |
| `clear` | Clear the current terminal transcript view |
| `help` / `?` | Open command and workflow help |
| `quit` / `exit` | Leave the session |

Tab completes commands and relevant arguments. In Pivotglass, arrow keys move
through suggestions and Enter accepts one. A `?` typed inside an editable field
remains text; outside an editable field it opens Help.

The TUI-only `theme light|dark|high` command changes the current terminal
palette. Use DECK controls for Day, Night, and contrast in Pivotglass.

See [Analytic Method](ANALYTIC_METHOD.md) for the record distinctions and
[Workspace Migration and Recovery](WORKSPACE_MIGRATIONS.md) before opening a
valuable workspace with a newer release.

## Terminal navigation

The terminal interface retains the complete current-session transcript until
an explicit `clear`.

- `[` / `]`, Page Up/Page Down, the mouse wheel, and the right-side scrollbar
  move through the intelligence feed. Up/Down remain command-history keys.
- `find <text>` searches the complete session transcript.
- `open <event-reference>` opens stored evidence details.
- `back` returns to the exact prior reading position and focus.
- Alt-M toggles the soundtrack.

Terminal playback requires `afplay` on macOS or `aplay`/`paplay` on Linux.

## Characters, accessibility, and sound

The public deck contains Default (Analyst), Chuck Norris, HAL9000, Troll,
Sherlock Holmes, Neuromancer, and The Matrix. Use DECK or:

```text
mode list
mode Default (Analyst)
mode Chuck Norris
mode HAL9000
mode Troll
mode Sherlock Holmes
mode Neuromancer
mode The Matrix
```

Each character changes palette, motion, narration, music, and an optional
diversion. Operational acknowledgements and errors remain deterministic.
Important Dossier breakthroughs may receive one bounded model-generated line,
but that prompt may not add facts, confidence, results, score, or control state.

Music starts off and is generated locally. The enabled state persists across
character changes. The browser cross-fades between movements; the terminal
uses short edge fades when stopping and starting the new score. Neither path
streams music or treats sound as evidence.

Pivotglass provides Day, Night, high-contrast, reduced-motion, and effects-off
controls. Terminal equivalents are:

```bash
AP_TUI_COLOR_SCHEME=light ap tui
AP_TUI_HIGH_CONTRAST=1 ap tui
```

## Safety boundary

External intelligence can be incomplete, stale, biased, or wrong. Treat source
responses as observations with provenance. Keep inference visibly separate.
Verify consequential conclusions at the originating service and preserve human
authority over pivots, publication, and other irreversible actions.

For installation and troubleshooting, return to the
[Quick Start](QUICKSTART.md). For the current documentation map, see the
[documentation index](README.md).
