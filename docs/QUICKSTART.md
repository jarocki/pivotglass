# Pivotglass Quick Start

Threat investigations rarely fail because no data exists. They fail because
evidence arrives as disconnected facts. Pivotglass keeps each result with its
source and time, connects only what the evidence supports, and leaves
unanswered questions visible.

This guide takes you from a clean installation to a small investigation, a
graph review, and a report.

## 1. Install Pivotglass

You need Python 3.12 or newer and Git. A dedicated virtual environment keeps
Pivotglass separate from the system Python.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install "adversary-pursuit[agent] @ git+https://github.com/jarocki/pivotglass.git@v0.8.0"
ap --version
```

The final command should report:

```text
adversary-pursuit 0.8.0
```

For a source checkout, use [uv](https://docs.astral.sh/uv/):

```bash
git clone --branch v0.8.0 --depth 1 https://github.com/jarocki/pivotglass.git
cd pivotglass
uv sync --extra agent
uv run ap --version
```

The release contains the built browser interface. Node.js 20.9 or newer is
needed only when changing or rebuilding that interface.

## 2. Start the browser interface

```bash
ap
```

From a source checkout, use `uv run ap`. Pivotglass opens in the browser. If it
does not open automatically, visit:

```text
http://127.0.0.1:8765
```

The server listens only on the local computer by default.

Other interfaces remain available:

```text
ap tui      Full-screen terminal interface
ap chat     Alias for the terminal interface
ap basic    Direct module-control console
ap repl     Alias for the direct console
```

## 3. Configure intelligence and AI services

Open **CONFIGURATION** in Pivotglass.

### Intelligence services

For each service you intend to use:

1. Find the service under **INTELLIGENCE APIS**.
2. Enter the required credential fields.
3. Choose **SAVE + TEST**.
4. Leave the service disabled if you do not want Pivotglass to use it.

WHOIS and crt.sh work without API credentials. Most other integrations require
an account or key. Checks occur only when you request them.

### Optional model synthesis

Pivotglass can collect and organize evidence without a model. To enable
synthesis:

1. Choose a model provider.
2. Enter a credential if the provider requires one.
3. Choose **SAVE + TEST**.
4. Choose **VIEW AVAILABLE MODELS**.
5. Review the recorded strengths and limitations.
6. Choose **SELECT** beside the model you want.

A successful check proves that the provider accepted the credential and
returned the model in its catalog. It does not prove available quota, low
latency, answer quality, or suitability for a particular investigation.

Newly entered secrets exist transiently in the masked password field and the
explicit local save/test request. Stored secrets are not returned during
routine polling or repopulated into the form. Do not put secrets in the command
field, notes, exports, or screenshots.

You can inspect the same masked state with:

```text
model show
model check
model repair
config show
config repair
```

![Model selection and capability notes](media/pivotglass-model-catalog-v0.7.0.png)

## 4. Create a learning workspace

In the Pivotglass command field, enter:

```text
workspace create quickstart
```

Now enter the documentation domain:

```text
example.com
```

`example.com` is reserved for examples. Enabled services may still receive the
value, so review their terms and data handling first. Results are not
guaranteed; empty results are valid.

Submitting the first indicator starts the applicable enrichment work. The
activity feed shows each job moving through planned, queued, running, and a
terminal state such as succeeded, empty, failed, skipped, or canceled. These
states describe the enrichment job—not whether the indicator is malicious.

**Enrichment Activity** keeps recent indicators as rows and enrichment sources
as columns, newest activity first. Each large cell contains a three-channel
8-bit LED. Green `[0,255,0]` means the enrichment completed, black `[0,0,0]`
means no result is mapped, and gray `[128,128,128]` marks partial coverage.
Symbols and text repeat every status; color is never the only cue.

Run `challenges` to see source-grounded goals for the current pursuit and
`badges` to review earned milestones. Pivotglass includes 40 graduated badges;
their shapes identify the achievement family and their labeled color tier marks
common, uncommon, rare, epic, or legendary awards.

For meaningful research, create a separate workspace and submit only
indicators you are authorized to send to the enabled services.

> An indicator is not the answer. It is the first node.

## 5. Read the Investigation Constellation

Open **VISUAL ANALYSIS**, then choose **Investigation Constellation**.

Each row is a stored indicator. Each column is one of the nine Dossier
dimensions. The newest indicators appear first. Filter or sort by value, type,
completeness, first seen, last seen, or direct relationship to another
indicator.

Select an indicator to open its evidence. Select a cell to see why that
dimension is filled, partial, empty, or deferred. The overall mapped value is a
navigation aid, not confidence or a verdict.

The Constellation compresses those states into a child's Lite Brite motif so
all nine Dossier dimensions remain scannable beside each indicator: a bright
starburst is filled, a striped round peg is partial, a concentric octagonal peg
is deferred, and a dark recessed peg is empty. Shape repeats color, and hover,
keyboard focus, and selection expose the complete status and evidence count.

> A blank cell is not missing interface. It is visible uncertainty.

![Investigation Constellation](media/pivotglass-constellation-v0.7.0.png)

## 6. Pivot to related evidence

When enrichment discovers another indicator:

1. Open its evidence details.
2. Review its source, normalized fields, collection history, and relationships.
3. Choose **+ QUEUE** if it is worth investigating.
4. Choose **RUN NEXT** for one queued indicator or **RUN ALL** to process the
   queue in order.

The first indicator entered in the command field starts immediately. **RUN
NEXT** and **RUN ALL** apply to later indicators you explicitly queue.

Most integrations query intelligence already held by a provider. Pivotglass
does not issue a direct DNS query from the operator host. URLScan is different:
it can submit a URL or domain to an external browser-scanning service. Review
the enabled service before sending private or embargoed indicators.

## 7. Explore the relationship graph

In **VISUAL ANALYSIS**, choose **Evidence relationships**.

You can search by indicator or type, drag nodes, pan and zoom, select a node to
highlight its visible neighbors, and choose **OPEN EVIDENCE** to inspect its
provenance.

Edges represent stored or explicitly labeled conservative relationships.
Moving nodes changes only the layout. If no supported edge exists, Pivotglass
shows unconnected indicators rather than implying a relationship from visual
proximity.

> The graph is useful because it refuses to connect what the evidence does not.

![Evidence-backed relationship graph](media/pivotglass-graph-v0.7.0.png)

The `graph` command opens the deterministic graph summary:

```text
graph
```

## 8. Report and export

Generate the current Dossier report:

```text
report generate
```

The report is built from the active workspace. Use **PRINT / SAVE PDF** in the
report dialog to print it or save a PDF.

Download investigation data with:

```text
export json
export csv
export stix
export gexf
```

Use STIX for structured exchange and GEXF for tools such as Gephi. Every Visual
Analysis view also offers **EXPORT EXACT DATA**, which downloads the rows or
nodes and edges used for that view.

Before sharing any export, remember that it can contain raw indicators and
source-derived information.

## 9. Change character and presentation

Open **DECK** to choose a character, Day or Night display, contrast, motion,
narration, and music. You can also use:

```text
mode list
mode Default (Analyst)
mode Sherlock Holmes
mode Neuromancer
```

Music begins off. If enabled, the choice persists when the character changes.
The browser schedules ahead, caches its instrument and percussion material,
and cross-fades between movements so interface work cannot create gaps or hard
audio edges. The terminal score uses short edge fades when it stops and starts
the new movement. Music, character narration, visual effects, scores, and
mini-games never alter evidence or investigation state.

With Narration enabled, the active character may offer a non-modal next-step
idea after an extended pause in meaningful work. Full mode waits five minutes;
Brief waits eight, and suggestions are at least fifteen minutes apart. Typing,
clicking, scrolling, new evidence, or investigation activity resets the timer.
The Analyst Advisor appears near
the top of the current viewport, never steals focus, and is always labeled
**Narration, not evidence**. Its artwork combines the active character with the
kind of advice being offered. Choose its action, select **Read Aloud**, dismiss
it, or turn Narration off from **DECK**. Automatic Advisor voice audio is a
separate opt-in setting; it uses a browser or operating-system voice with
character-specific pacing and pitch, not a cloned actor or character voice.

In the terminal interface, `Alt-M` toggles music immediately.

## Troubleshooting

### The wrong version starts

```bash
command -v ap
ap --version
```

From a source checkout, `uv run ap --version` bypasses an older global
installation.

### The browser interface is missing or stale

Source checkouts that change `web/app/` must rebuild the static interface:

```bash
cd web
npm ci
npm run build
cd ..
uv run ap
```

### A model or intelligence service does not work

```text
model show
model repair
model check
config show
config repair
```

The repair commands explain non-destructive next steps. Change secrets only in
Configuration.

### WHOIS is unavailable

The keyless WHOIS module uses the system `whois` command. Install it with your
operating system's package manager or leave that source disabled.

### Terminal music is silent

Terminal playback needs one supported local player: `afplay` on macOS, or
`aplay`/`paplay` on Linux. The browser uses its own local audio engine.

### The graph has nodes but no edges

Pivotglass has evidence but no supported relationship in scope. Inspect the
provenance, collect additional authorized enrichment, or add an analyst note.
The interface deliberately does not draw a persuasive but unsupported edge.

## Continue learning

- [User Guide](USER_GUIDE.md) — full workflow and command reference
- [Documentation index](README.md) — current guides and historical records
- [Web supply chain](WEB_SUPPLY_CHAIN.md) — packaged interface verification
- [Procedural music](PROCEDURAL_MUSIC.md) — score behavior and safety boundary
- [Changelog](../CHANGELOG.md) — release history
- [Philosophy](../PHILOSOPHY.md) — evidence, judgment, and collaboration principles
