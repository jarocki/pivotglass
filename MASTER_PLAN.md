# MASTER_PLAN.md -- Adversary Pursuit v1

## Original Intent

> Adversary Pursuit is a gamified framework for hunting, pivoting, and discovery of actor infrastructure, indicators, and TTPs. "Taking maximum advantage of every mistake, and celebrating with epic memes."
>
> Goals: Make it fun. Gamify. Different modes. Graph of pursuit progress. Teaching moments at dead ends. Meme/DALL-E generator for celebrations. Final report generation (interview-based). Standardize hunting and pursuit techniques, crowdsource pursuit, competition and ranking for career development.
>
> Interface should feel like a combination of Metasploit and CTFd. Move straight to v1 multi-platform Python. Reference CTI and OSINT awesome lists for data sources. Priority integrations: VirusTotal, Shodan, PassiveTotal, Censys, URLScan, HaveIBeenPwned, AbuseIPDB, AlienVault OTX, plus Maltego-style transforms and OSINT Tool aggregators.

## Context

Adversary Pursuit (AP) is a gamified framework for hunting, pivoting, and discovering adversary infrastructure, indicators, and TTPs. The vision: make threat intelligence gathering **fun**, combining the tactical CLI experience of Metasploit with the gamified progression of CTFd.

**Problem:** CTI/OSINT analysts navigate a fragmented landscape of disconnected scripts, web portals, and APIs. Learning curves are steep. There's no unified framework that makes the process engaging, educational, and competitive.

**Solution (v1, revised 2026-04-29):** A multi-platform Python CLI application whose **primary user-facing interface is an agentic AI chat** (`ap chat`, smolagents/litellm-driven). The agent discovers and invokes modular OSINT/CTI integrations as tools, gathers STIX 2.1 evidence into per-investigation workspaces, and observes scoring/celebration/badge/hint events as part of the chat experience. A Metasploit-like cmd2 REPL (`ap`) ships alongside as a power-user surface for direct `use → set → run` workflows; it is supporting infrastructure, not the primary UX.

**Target:** v1 -- multi-platform Python CLI (skipping Jupyter prototype). The agentic chat is the entry point users are expected to reach for first; the cmd2 REPL is the "manual transmission" alternative for power users.

### Interface Model (Revised 2026-04-29)

The original 2026-04-05 plan said the v1 interface should "feel like a combination of Metasploit and CTFd" and named cmd2 (issue #2) as the heart of the application. After Phase 1-4 landed and smolagents support was added in #25 (`707f956`, `17120e7`), the user clarified that the v1 vision is an **agentic AI chat** as the primary interface — the cmd2 REPL is supporting/secondary. That clarification is captured here as `ADR-010` and supersedes the v1 Non-Goal language about "Machine-assisted features" to the extent that LLM-driven tool selection over the AP module catalog is now in scope.

Both layers exist because they serve different user journeys:

| Layer | Role | When users reach for it |
|-------|------|--------------------------|
| `ap chat` (agent / litellm) | **Primary v1 interface.** Conversational; the LLM chooses tools, combines results, and narrates findings. | First-time users, mixed-domain investigations, "what is this indicator?" exploratory queries. |
| `ap` (cmd2 REPL) | Supporting power-user surface. Direct, deterministic `use → set → run` over individual modules with full Rich rendering. | Power users who want explicit control, scripted/macro workflows, one-shot module runs, scenarios where determinism matters more than narration. |

Both layers share the same module catalog, workspace authority, scoring engine, and gamification primitives. Gamification observes tool execution events regardless of caller — the divergence is in **how** events are surfaced, not in **whether** they fire.

## Why Now

This project was first committed in November 2022 as a vision document -- a README capturing raw ideas about gamified threat hunting. It sat dormant for 3.5 years. What changed:

1. **The CTI tooling landscape matured.** IntelOwl, SpiderFoot, and OpenCTI proved the architectural patterns (modular analyzers, pub/sub event buses, STIX 2.1 data models) that AP's design now draws from. In 2022, some of these were less proven.
2. **AI-assisted development changes the sustainability equation.** A solo developer can now realistically implement a 24-issue plan that would have been a multi-person project in 2022.
3. **The idea survived.** Three years of latent incubation means the core conviction -- that CTI work should be fun -- isn't a passing enthusiasm. It's durable.

The risk: dormancy is a pattern. The antidote is code, not more planning. Issue #1 ships this week.

## Principles

1. **Fun is a first-class design constraint.** Gamification is not a veneer applied after the "real" tool is built. Scoring, modes, and celebrations are co-equal architectural citizens alongside the module system and data model.
2. **Metasploit UX is the interaction model.** The `use → set → run` workflow, tab completion, workspaces, and module namespaces -- users who know msfconsole should feel at home immediately.
3. **STIX 2.1 is the lingua franca.** All module output speaks STIX. This is non-negotiable for interoperability with OpenCTI, MISP, and the broader CTI ecosystem.
4. **Modules are pure data producers.** Modules query external sources and return STIX observables. They don't render output, manage state, or trigger side effects. The console orchestrates; the gamification engine observes.
5. **Playfulness and rigor are not opposites.** Bobby Hill mode and STIX 2.1 compliance coexist. The tool is simultaneously serious in its analytical capabilities and absurd in its celebration of them.

## Non-Goals (v1)

These are explicitly out of scope for v1. They may appear in future versions but will not influence v1 design decisions:

- **Web application or GUI** (v3 in README vision)
- **Mobile application** (v4 in README vision)
- **Jupyter notebook interface** (v0 -- skipped deliberately)
- **Federation** between AP instances
- **Cloud/VM hosting** (Docker, Kubernetes deployment)
- **Machine-assisted analytical features beyond conversational tool dispatch** — auto-classification of campaigns, TTP clustering, automated behavior summarization, and AI-generated narrative reports remain out of scope. *Carve-out (added 2026-04-29 per ADR-010):* LLM-driven tool selection over the AP module catalog (the `ap chat` agent) IS in scope for v1 as the primary user-facing interface. The agent dispatches tools and presents their results; it is not expected to invent classification heuristics, cluster TTPs without explicit module support, or generate analytical narratives that aren't grounded in tool output.
- **3D character rendering**, .stl files, MS Paint graphics
- **Character sheets and backstories** (beyond mode personality text)
- **Real-time collaboration** or multi-user features
- **DALL-E or AI-generated celebration images** (ASCII art in v1; AI images deferred)

---

## Plan Status (Reconciled 2026-04-28, Reframed 2026-04-29, Closed 2026-04-28)

| Phase | Status | Notes |
|-------|--------|-------|
| Phase 0 — Foundation Modules (was Phase 1) (#1-#5) | completed | All 5 issues landed; cmd2 console wires Config + Plugin + Workspace + Modes. Now reframed as supporting infrastructure for the agent. |
| Phase 1 — OSINT/CTI Modules (was Phase 2) (#6-#13) | completed | All 8 priority modules landed; plus stretch `whois_lookup`, `dns_resolve`. Modules are the uniform tool surface both interfaces share. |
| Phase 2 — Gamification (was Phase 3) (#14-#18) | completed | Scoring, Challenges, Modes, Badges, Hints all landed. Fully wired into both the cmd2 console and the agent path (all 9 W-AGENT-* slices complete). |
| Phase 3 — Auto-Pivot & Graph (was Phase 4) (#19-#20) | completed | Event bus opt-in (DEC-EVENTBUS-002); graph + GEXF + STIX bundle export. Wired into both cmd2 console and agent path (W-AGENT-AUTOPIVOT `8e48256`, W-AGENT-GRAPH-EXPORT `0b83eb2`). |
| Phase 4 — Agentic Chat Interface (#25 + W-AGENT-*) | **completed** | All 9 W-AGENT-* slices landed. 21 LLM tools covering all 10 modules + celebrations + badges + hints + modes + autopivot + challenges + graph/export + reports. Full gamification parity with cmd2 console achieved. |
| Phase 5 — Polish & Release (#21-#24) | in-progress | #21, #22, #23 done; #24 CI/CD landed, PyPI publish needs verification (W-V1-PYPI-VERIFY). |
| Phase 6 — Agent Docs (W-AGENT-DOCS) | **completed** | README rewritten for agent-first v1: `ap chat` primary interface documented, all 21 LLM tools, 8 meta-commands, 10 modes, and persona-prompt protocol. MASTER_PLAN Phase 4 status and W-AGENT-* table updated with all merge SHAs. |

**Aggregate (final):** Phases 0–4 complete; all W-AGENT-* slices landed; Phase 6 docs complete. The agentic chat (`ap chat`) is the v1 primary interface with full gamification parity. The cmd2 REPL is a supported power-user surface. The only remaining v1 item is Phase 5 PyPI publish verification (W-V1-PYPI-VERIFY).

> **Note:** The previous "Beyond v1 — smolagents" framing is retired. Agentic chat is in v1 by user direction (ADR-010). Phase numbering in this status table is the **revised** ordering; the per-phase Decision Log sections below retain their original numbering for traceability with prior plan revisions.

---

## Phase 1: Foundation (Issues #1-#5)
**Status:** completed
**Reframing (2026-04-29):** The cmd2 console (#2) was originally framed as "the heart of the application." Under the revised v1 interface model (ADR-010), the cmd2 console is **supporting infrastructure** — a power-user surface — and the `ap chat` agent is the primary UX. The Foundation work itself (Config #5, Plugin/Module system #3, Workspace+STIX #4) remains foundational and is shared by both interfaces; only the framing of the console (#2) shifts. The DEC-CONSOLE-* decisions are still accurate facts about what was built; they describe a layer that is still shipped, just no longer the front door.

### Decision Log

| Issue | Status | Merge SHA | Key Decisions |
|-------|--------|-----------|---------------|
| #1 Scaffolding | completed | (landed alongside #2-#5; pyproject.toml + `src/adversary_pursuit/` tree present) | ADR-001..ADR-009 stack instantiated as committed |
| #2 Console (cmd2 + Rich) | completed | `2114673` | DEC-CONSOLE-001 (cmd2.Cmd + Rich Console(file=StringIO)), DEC-CONSOLE-002 (asyncio.run() bridge for async hunt() in sync cmd2 handlers), DEC-CONSOLE-003 (workspace auto-init to 'default'), DEC-CONSOLE-004 (ModeManager prompt/run/celebration integration) |
| #3 Plugin/Module System | completed | `6149f9b` | DEC-PLUGIN-001 (entry_points + direct registration), DEC-PLUGIN-002 (failed loads logged, not raised), DEC-MODULE-001 (`async def hunt()` from day 1), DEC-MODULE-002 (Protocol over ABC) |
| #4 Workspace + STIX | completed | `963b89e` (+ fix `328082c` for `allow_custom=True`) | DEC-WS-001..005 (per-workspace SQLite, in-memory active, dict+stix2 inputs, ID dedup, multi-scalar stats), DEC-DB-001..005 (JSON blobs, no Alembic v1, SQLAlchemy 2.0 DeclarativeBase, ScoreEvent + BadgeEvent tables), DEC-STIX-001..002 (thin helpers over python-stix2, dict passthrough on unknown types) |
| #5 Configuration | completed | `99c7b5f` | DEC-CONFIG-002 (tomllib read + tomli_w write + Pydantic validation), DEC-CONFIG-003 (env vars applied at load time, not via BaseSettings) |

### #1 -- Project Scaffolding & Build System

Set up the Python project structure using modern packaging standards.

```
ap/
  pyproject.toml              # Build system, deps, entry points
  src/
    adversary_pursuit/
      __init__.py             # Version, package metadata
      __main__.py             # Entry point: python -m adversary_pursuit
      core/
        __init__.py
        console.py            # cmd2-based REPL (APConsole)
        config.py             # Configuration management (API keys, settings)
        workspace.py          # Workspace/investigation isolation (SQLite)
        plugin_mgr.py         # importlib.metadata entry point discovery
        event_bus.py          # asyncio event bus for auto-pivoting
      models/
        __init__.py
        stix.py               # STIX 2.1 abstraction (SDO/SCO/SRO)
        database.py           # SQLAlchemy models, migrations
      gamification/
        __init__.py
        scoring.py            # Parabolic decay scoring (CTFd model)
        challenges.py         # Challenge definitions, flag verification
        badges.py             # Achievement/badge system
        modes.py              # Character modes (ninja, drunken master, etc.)
      modules/                # Built-in module namespace
        __init__.py
        base.py               # PursuitModule Protocol + BaseModule
        osint/                # Public OSINT queries
          __init__.py
        cti/                  # Threat intel platform queries
          __init__.py
        pivoting/             # Multi-step transforms
          __init__.py
  tests/
    __init__.py
    conftest.py
    test_console.py
    test_scoring.py
    test_plugin_mgr.py
    test_workspace.py
```

**Tech stack:**
| Component | Choice | Rationale |
|-----------|--------|-----------|
| Python | 3.12+ | Walrus, match/case, modern typing |
| CLI core | cmd2 | Stateful REPL, tab completion, scripting, prompt_toolkit |
| Rendering | Rich | Tables, syntax highlighting, progress bars, panels |
| Plugin discovery | importlib.metadata entry_points | Modern, explicit, side-effect-free |
| Plugin contracts | typing.Protocol | Lightweight structural subtyping |
| Data model | STIX 2.1 (via python-stix2) | Industry standard, OpenCTI compatible |
| Storage | SQLite (v1) | Workspace isolation, zero-config, upgrade to PostgreSQL later |
| ORM | SQLAlchemy 2.0 | Async-ready, mature, migrations via Alembic |
| Async | asyncio | Event bus for auto-pivoting (SpiderFoot pattern) |
| Testing | pytest | Standard, fixtures, parametrize |
| Package | uv + pyproject.toml | Fast resolver, lockfiles |

**Dependencies (pyproject.toml):**
```toml
[project]
name = "adversary-pursuit"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "cmd2>=2.5",
    "rich>=13.0",
    "sqlalchemy>=2.0",
    "stix2>=3.0",
    "httpx>=0.27",
    "pydantic>=2.0",
]

[project.scripts]
ap = "adversary_pursuit.__main__:main"

[project.entry-points."adversary_pursuit.modules"]
# Built-in modules register here
```
```

### #2 -- Core Console (cmd2 + Rich)

The APConsole -- the heart of the application. Metasploit-like REPL with Rich rendering.

**Commands (msfconsole-inspired):**
| Command | Description |
|---------|-------------|
| `help` | Show available commands |
| `search <keyword>` | Find modules by name/description/tags |
| `use <module_path>` | Load a module (e.g., `use osint/shodan_ip`) |
| `show options` | Display module parameters |
| `set <var> <value>` | Set module parameter |
| `run` / `hunt` | Execute loaded module |
| `back` | Return to main console |
| `workspace` | List/create/switch workspaces |
| `sessions` | List active intelligence streams |
| `db_status` | Show database connection info |
| `score` | Show current score and rank |
| `challenges` | List active challenges |
| `pivot <entity_id>` | Auto-pivot on a discovered artifact |
| `graph` | Render text-based relationship tree |
| `export` | Export workspace data (STIX bundle, CSV, JSON) |
| `mode <name>` | Switch character mode |

**Console state machine:**
```
[main] ap> use osint/shodan_ip
[module] ap(osint/shodan_ip)> set TARGET 1.2.3.4
[module] ap(osint/shodan_ip)> run
[results displayed with Rich tables]
[gamification check runs]
[module] ap(osint/shodan_ip)> back
[main] ap>
```

**Reuse:** cmd2 provides tab completion, history, aliases, macros, scripting, and shell integration out of the box. Rich handles all formatting via Console object.

### #3 -- Plugin/Module System

**Architecture:** importlib.metadata entry points + typing.Protocol contracts.

```python
# src/adversary_pursuit/modules/base.py
from typing import Protocol, Any

class PursuitModule(Protocol):
    """Contract for all AP modules (built-in and third-party)."""
    name: str
    description: str
    author: str
    module_type: str          # "osint", "cti", "pivoting"
    options: dict[str, Any]   # Required parameters with defaults

    def initialize(self, config: dict[str, Any]) -> None:
        """Configure with API keys. No side effects."""
        ...

    def hunt(self, target: str, options: dict[str, Any]) -> list[dict]:
        """Execute and return STIX 2.1 observables."""
        ...
```

**Discovery flow:**
1. On startup, `PluginManager.load_plugins()` calls `entry_points(group="adversary_pursuit.modules")`
2. Each entry point resolves to a class implementing `PursuitModule`
3. Failed loads are logged but don't crash the console
4. Third-party plugins install via pip and declare entry points in their own `pyproject.toml`

### #4 -- Workspace & Data Model

**Workspaces** isolate investigations (like Metasploit's `msfdb` workspaces).

- Each workspace = SQLite database file in `~/.ap/workspaces/<name>.db`
- Stores STIX 2.1 objects: SDOs (Threat Actor, Malware, Attack Pattern), SCOs (IP, Domain, Hash), SROs (relationships)
- Timeline of discoveries with timestamps
- Module execution history (audit trail)

**Schema (SQLAlchemy 2.0):**
- `stix_objects` -- STIX JSON blobs with type index
- `relationships` -- SRO links between objects
- `module_runs` -- execution log (module, target, timestamp, results count)
- `notes` -- analyst annotations

### #5 -- Configuration System

- Global config: `~/.ap/config.toml` (API keys, default workspace, theme)
- Per-workspace overrides
- Environment variable fallback for API keys (`AP_VT_API_KEY`, `AP_SHODAN_API_KEY`, etc.)
- `ap config set <key> <value>` command
- Sensitive values stored with file permissions (0600)

---

## Phase 2: OSINT/CTI Modules (Issues #6-#13)
**Status:** completed

### Decision Log

All 8 priority modules landed plus 2 stretch modules (`whois_lookup`, `dns_resolve`). Each module conforms to the `PursuitModule` Protocol (DEC-MODULE-001/002) and emits STIX 2.1 observables (DEC-STIX-001/002).

| Issue | Module | Merge SHA | Notes |
|-------|--------|-----------|-------|
| #6 | `osint/shodan_ip` | `95088e0` | Host reconnaissance; IP, ports, banners, CVEs |
| #7 | `cti/virustotal` | `5f2d594` | VirusTotal v3 with auto-detection and multi-scanner verdicts |
| #8 | `osint/censys_host` | `698822a` | Service + certificate data |
| #9 | `osint/urlscan` | `251e35a` | Async submit+poll pattern |
| #10 | `osint/abuseipdb` | `0b5f53e` | Reports + confidence score (free-tier first per implementation order) |
| #11 | `osint/hibp` | `38faf03` | Breach lookup |
| #12 | `cti/otx` | `4640801` | AlienVault OTX multi-endpoint traversal |
| #13 | `cti/passivetotal` | `1f4514d` | Passive DNS + WHOIS history |
| stretch | `osint/whois_lookup` | landed (file present) | No-API-key WHOIS |
| stretch | `osint/dns_resolve` | landed (file present) | No-API-key DNS resolution |

Module-local decisions captured in `DECISIONS.md` per file (e.g., DEC-CENSYS-*, DEC-HIBP-*, DEC-URLSCAN-*, DEC-VT-*, DEC-OTX-*) — see annotated source for the runtime authority. Phase 2 ordering rationale (free-tier-first) was honored: AbuseIPDB / OTX / URLScan landed before VirusTotal / PassiveTotal.

Each module implements `PursuitModule` protocol and returns STIX 2.1 observables.

### Priority API integrations (v1):

| # | Module | API | Category | Returns |
|---|--------|-----|----------|---------|
| #6 | `osint/shodan_ip` | Shodan | Attack Surface | IP, ports, banners, CVEs |
| #7 | `cti/virustotal` | VirusTotal v3 | Reputation | File/URL/IP/domain verdicts |
| #8 | `osint/censys_host` | Censys v2 | Attack Surface | Certificates, hosts, services |
| #9 | `osint/urlscan` | URLScan.io | URL Analysis | Screenshots, DOM, requests |
| #10 | `osint/abuseipdb` | AbuseIPDB | IP Reputation | Reports, confidence score |
| #11 | `osint/hibp` | HaveIBeenPwned | Breach Data | Breaches, pastes by email |
| #12 | `cti/otx` | AlienVault OTX | TI Feed | Pulses, indicators, tags |
| #13 | `cti/passivetotal` | PassiveTotal/RiskIQ | DNS/WHOIS | Passive DNS, WHOIS history |

**Additional v1 targets (stretch):**
- `osint/whois` -- WHOIS lookup (no API key needed)
- `osint/dns` -- DNS resolution + records (no API key needed)
- `cti/misp` -- MISP instance query
- `pivoting/domain_to_ip` -- Chain DNS + reverse DNS + Shodan
- `pivoting/email_recon` -- HIBP + social + domain extraction

**Reference lists for future modules:**
- [awesome-threat-intelligence](https://github.com/hslatman/awesome-threat-intelligence)
- [awesome-osint](https://github.com/jivoi/awesome-osint)
- [OSINT Framework](https://osintframework.com/)
- Maltego transform library (TDS)
- SpiderFoot module catalog (200+ modules)

---

## Phase 3: Gamification Engine (Issues #14-#18)
**Status:** completed

### Decision Log

| Issue | Component | Merge SHA | Key Decisions |
|-------|-----------|-----------|---------------|
| #14 Scoring | `gamification/scoring.py` | `0e8b053` | DEC-SCORING-001 (CTFd parabolic decay), DEC-SCORING-002 (per-STIX-type workspace counts as solve_count) |
| #15 Challenges | `gamification/challenges.py` | `db85eff` | DEC-CHALLENGE-001 (workspace_data dict contract), DEC-CHALLENGE-002 (in-memory state, no persistence v1), DEC-CHALLENGE-003 (YAML top-level "challenges" list key) |
| #16 Character Modes | `gamification/modes.py` | `adc05ff` | DEC-MODE-001 (frozen dataclass + thin state machine ModeManager), DEC-MODE-002 (`str.format(points=N)` template, not f-string). Note: 10 modes shipped vs. 9 listed in original plan — additional `columbo` mode added at implementation time. |
| #17 Badges | `gamification/badges.py` | `81c3444` | DEC-BADGE-001 (workspace_stats dict contract), DEC-BADGE-002 (already_awarded set passed in, BadgeManager stateless), DEC-BADGE-003 (BadgeMetric enum selects evaluated stat) |
| #18 Hints | `gamification/hints.py` | `19a54b8` | DEC-HINT-001 (cost is score penalty, not a currency), DEC-HINT-002 (sequential reveal, ID set tracking), DEC-HINT-003 (free hints before paid), DEC-HINT-004 (module-specific hints keyed by base name) |

### #14 -- Scoring System

**Parabolic decay scoring** (CTFd model):
```
value = ((minimum - initial) / decay^2) * solve_count^2 + initial
```

Base scoring from README:
| Action | Points |
|--------|--------|
| Adversary mistake found | 10 |
| New IP or domain discovered | 100 |
| Deception uncovered | 200 |
| Adversary linked | 500 |
| New tool discovered | 500 |
| New dev framework discovered & described | 1000 |
| Campaign described with IOCs and TTPs | 1000 |

Points decrease with solve count (dynamic). Module results trigger automatic score evaluation.

### #15 -- Challenge System

Challenges = intelligence requirements with verifiable flags.

- **Standard:** Find specific indicator (IP, hash, domain)
- **Pivoting:** Multi-step transform chain (email -> domain -> IP -> C2 panel)
- **Discovery:** Identify a new tool, TTP, or campaign pattern
- **Timed:** Complete within time limit for bonus multiplier

Challenge packs can be loaded from YAML files or fetched from a future challenge server.

### #16 -- Character Modes

Modes affect UI personality, hints, and celebration style (from README):

| Mode | Personality |
|------|-------------|
| Ninja | Minimal output, speed bonuses, stealth tips |
| Full Troll | Maximum memes, taunt messages |
| Drunken Master | Random pivot suggestions, chaos mode |
| Sun Tzu | Strategic quotes, methodical approach rewards |
| Chuck Norris | Overpowered hints, confidence boosters |
| Bureaucrat | Office Space vibes, TPS report formatting |
| Bobby Hill | "That's my purse!" energy |
| Bruce Lee | Flow state, combo multipliers |
| Columbo | "Just one more thing..." investigative prompts |

Each mode is a configuration profile affecting: prompt style, celebration messages, hint flavor text, scoring multipliers, and suggested next actions.

### #17 -- Badges & Achievements

Awarded for behavioral milestones:
- First Blood (first to solve a challenge)
- Pivot Master (5-step chain without hints)
- Data Hoarder (1000+ indicators in workspace)
- Ghost (complete investigation without triggering active recon)
- etc.

### #18 -- Hint System

- Free hints (general guidance) and paid hints (point cost)
- Balance protection: can't unlock if score would go negative
- Hint quality varies by character mode
- Hints are contextual to current module and target

---

## Phase 4: Auto-Pivoting & Event Bus (Issues #19-#20)
**Status:** completed

### Decision Log

| Issue | Component | Merge SHA | Key Decisions |
|-------|-----------|-----------|---------------|
| #19 Event Bus | `core/event_bus.py` | `4de3fe8` | DEC-EVENTBUS-001 (pub/sub with depth-limited cascading + module whitelist), DEC-EVENTBUS-002 (disabled by default — opt-in via `autopivot` console command). Console exposes `do_autopivot` toggle. |
| #20 Graph + Visualization | `core/graph.py` | `3bd3082` | DEC-GRAPH-001 (in-memory adjacency list: `dict[stix_id, GraphNode]` + edge list), DEC-GRAPH-002 (Rich Tree widget for tree rendering, plain-text fallback via `Console(file=StringIO)`), DEC-GRAPH-003 (GEXF 1.2 export format), DEC-GRAPH-004 (`export_stix_bundle` returns plain dict, not stix2 Bundle), DEC-GRAPH-005 (unconnected nodes appear at root under 'Unconnected' branch). Console exposes `do_graph` and `do_export` (`--format gexf`, `--format stix`). |

### #19 -- Event Bus (SpiderFoot Pattern)

When a module discovers artifacts, the event bus can auto-trigger relevant modules:

```
[shodan discovers IP 1.2.3.4]
  -> event_bus publishes SCO(IPv4Address)
  -> abuseipdb module subscribes to IPv4Address
  -> virustotal module subscribes to IPv4Address
  -> auto-pivot runs both, results added to workspace
```

Configurable per-workspace: `auto_pivot = true/false`, depth limit, module whitelist.

### #20 -- Graph State & Visualization

- In-memory graph of STIX relationships (SROs)
- `graph` command renders text-based relationship tree (Rich Tree widget)
- `export --format gexf` for Gephi visualization
- `export --format stix` for STIX 2.1 bundle
- Foundation for future web UI graph visualization

---

## Phase 5: Polish & Release (Issues #21-#24)
**Status:** in-progress

### Reconciliation (2026-04-28)

| Issue | Status | Merge SHA | Notes |
|-------|--------|-----------|-------|
| #21 Report Generation | done | `9e55bca` | DEC-REPORT-001 (interview-first structure), DEC-REPORT-002 (Markdown over PDF/HTML for v1), DEC-REPORT-003 (in-memory interview state, no DB persistence). Console exposes `do_report`. |
| #22 Celebrations | done | `f175a70` | DEC-CELEBRATION-001 (4-level ASCII art keyed on points), DEC-CELEBRATION-002 (milestone messages fire at exact thresholds). |
| #23 Documentation | done | `167df88` (consolidated `8710aa0`) | README rewrite: usage, modules, plugin guide, architecture. |
| #24 PyPI Release | partial | `18a64b4` (CI/CD merged) | `.github/workflows/{ci,release}.yml` shipped; `pyproject.toml` is release-ready. **Open verification:** confirm `pip install adversary-pursuit` resolves to a published artifact (or that a release tag exists triggering the publish workflow). Recent commits `c46903f` and `5895560` fixed `[project.urls]` regressions, suggesting publish is being iterated but not yet proven landed. |

### Remaining Work (next work items)

- **W-V1-PYPI-VERIFY** — verify PyPI publish completed. Possible outcomes: (a) confirm a published version on PyPI and close #24; (b) cut a release tag to trigger `release.yml` and verify it succeeds; (c) document any blocker (missing `PYPI_API_TOKEN`, trusted-publisher OIDC config, etc.). Doc-only or workflow-only work — no source code changes expected.

### #21 -- Report Generation

Interview-based report generation (from README):
- "Why did you start this pursuit?"
- "How did you find the first indicator?"
- "What is the single most important thing you learned?"
- "How could someone interrupt this adversary's operation?"
- "What is the next step?"

Output: Markdown report with embedded graphs, timeline, IOC table.

### #22 -- Celebration System

- Meme templates for achievements (ASCII art in v1)
- Mode-specific celebration messages
- Sound effects (optional, terminal bell)
- Future: DALL-E integration for custom celebration images

### #23 -- Documentation & Examples

- `README.md` with installation, quickstart
- Module development guide (how to write plugins)
- Example challenge packs
- Example playbooks (chained module sequences)

### #24 -- PyPI Release

- Package on PyPI: `pip install adversary-pursuit`
- GitHub releases with changelog
- CI/CD via GitHub Actions (lint, test, publish)

---

## Phase 6 (new, primary v1 interface): Agentic Chat (#25 + W-AGENT-*)
**Status:** completed

> **Numbering note:** The revised Plan Status table at the top of this file lists this as "Phase 4 — Agentic Chat Interface" in user-facing ordering. In the per-phase Decision Log narrative below, where the original Phase 1-5 sections are preserved verbatim for historical traceability, the new agent work is documented here as "Phase 6" so it appends cleanly without renumbering legacy phases. Both views describe the same body of work.

### Decision Log (landed work)

| Component | Status | Merge SHA | Key Decisions |
|-----------|--------|-----------|---------------|
| #25 Agent core (`agent/` package) | landed | `17120e7` (initial) → `707f956` (consolidated) | DEC-AGENT-ARCH-001 (separate tool layer from LLM runner for testability), DEC-AGENT-CHAT-001 (minimal Rich REPL — no readline/prompt_toolkit), DEC-AGENT-RUNNER-001 (litellm for LLM-backend abstraction over direct smolagents — supports Ollama/OpenAI/Anthropic via OpenAI-compatible function-calling), DEC-AGENT-RUNNER-002 (graceful ImportError when litellm missing — `[agent]` extra optional), DEC-AGENT-TOOLS-001 (thin tool wrappers delegating to existing `PursuitModule` infra; no business-logic duplication), DEC-AGENT-TOOLS-002 (OpenAI function-calling format for tool definitions), DEC-TEST-AGENT-001 (mock `module.hunt()` at the asyncio boundary for hermetic tests). |
| `ap chat` subcommand | landed | (`__main__.py`) | Dispatches to `agent.chat.run_chat()`; falls through to cmd2 console only when no `chat` subcommand or `--version` is present. |
| 9 LLM tools at #25 landing (later grew to 21 via W-AGENT-* slices) | landed | (`agent/tools.py`) | Covers `dns_resolve`, `whois_lookup`, `check_ip_reputation` (AbuseIPDB), `shodan_host_lookup`, `check_breaches` (HIBP), `otx_threat_intel`, `scan_url` (URLScan), plus `get_workspace_summary` and `search_workspace`. |
| Scoring + workspace integration | landed | (`agent/tools.py:run_module`) | Every tool call hits `WorkspaceManager.store_stix_objects` + `ScoringEngine.score_results` + `WorkspaceManager.store_score_events`. The `+N points!` line in the tool summary is the agent's current scoring surface. |
| Workspace meta-command | landed | (`agent/chat.py:run_chat`) | `workspace <name>` is intercepted client-side and forwarded to `runner.ctx.workspace_mgr.switch()` — never sent to the LLM. |
| 41 unit tests | landed | (`tests/test_agent_tools.py`) | Cover `ToolContext` init, tool definition shape, dispatch correctness for all 7 modules, workspace meta-tools, scoring side-effects, and module-not-found error paths. |

### Gamification ↔ Agent Interface (mapping)

The original Phase 3 wired scoring/modes/celebrations/badges/hints into the cmd2 console. Under the revised interface model, every gamification touchpoint must surface through the agent path as well, because that path is now the primary UX. Status of each touchpoint:

| Touchpoint | cmd2 (`ap`) | `ap chat` agent | Action needed | Work item |
|------------|------------|------------------|---------------|-----------|
| Scoring (`ScoringEngine`) | wired (`do_run` → `_execute_hunt`) | **wired** (`tools.run_module` → `score_results` + `store_score_events`; `+N points!` in summary) | none — scoring is the one gamification surface that is already cross-cutting. | — |
| Workspace persistence | wired (`do_workspace`) | wired (`workspace <name>` meta-command in `run_chat`) | none — already symmetrical. | — |
| Character Modes (`ModeManager`) | wired (`do_mode`, prompt prefix, `run_success`, `score_celebration.format`) | **wired** (`8564d1e`) — `mode <name>` chat meta-command; persona injected via `AgentRunner.set_character`; mode-specific `score_celebration` template. | — | W-AGENT-MODES |
| Celebrations (`CelebrationEngine`) | wired (`_execute_hunt` shows ASCII art/milestones) | **wired** (`4ccc5888`) — `run_module` invokes `CelebrationEngine.celebrate(total)`; rendered via Rich panel after LLM response. | — | W-AGENT-CELEBRATIONS |
| Badges (`BadgeManager`) | wired (`do_badges`, `_check_badges_after_run`) | **wired** (`380c2f8`) — `run_module` calls `BadgeManager.check_all`; persisted via `store_badge_event`. | — | W-AGENT-BADGES |
| Hints (`HintProvider`) | wired (`do_hint`) | **wired** (`f511f06`) — `hint` / `hint buy` chat meta-command + `get_next_hint` / `buy_hint` LLM tools; balance-protected. | — | W-AGENT-HINTS |
| Auto-Pivot / Event Bus (`core/event_bus.py`) | opt-in via console `do_autopivot` toggle | **wired** (`8e48256`) — opt-in `autopivot on/off` chat meta-command; `EventBus.process_results` cascades on tool output. | — | W-AGENT-AUTOPIVOT |
| Challenges (`ChallengeManager`) | wired (`do_challenges`) | **wired** (`26fefe7`) — auto-check after each tool call; `list_challenges` + `check_challenges` LLM tools; `challenges` chat meta-command. | — | W-AGENT-CHALLENGES |
| Graph + Export (`RelationshipGraph`) | wired (`do_graph`, `do_export`) | **wired** (`0b83eb2`) — `render_graph` + `export_workspace` LLM tools (gexf/stix); `graph` + `export gexf|stix` chat meta-commands. | — | W-AGENT-GRAPH-EXPORT |
| Report Generation (`ReportEngine`) | wired (`do_report`) | **wired** (`f513c2d`) — interview-driven; 3 LLM tools (`start_report_interview` / `answer_report_question` / `generate_report`); `report` chat meta-command. | — | W-AGENT-REPORT |
| Module coverage | 10 modules | **10 modules** (`66f89dd` added VT/Censys/PT) — full parity. | — | W-AGENT-MODULES-VT-CENSYS-PT |

### Phase 6 Closeout (2026-05-01)

The agent's **dispatch + scoring + workspace** core is solid: 21 working tools, clean architectural separation between tool layer and runner. Phase 6 closeout (2026-05-01): all 9 W-AGENT-* slices landed. The agent now has full gamification parity with the cmd2 console — celebrations, badges, hints, modes, auto-pivot, challenges, graph/export, and reports all surface through the smolagents tool path. `ap chat` is no longer aspirational — it is the v1 primary interface in code as well as in plan.

### `@decision` annotation gap (informational, not blocking)

The runtime banner reports "30/39 = 76%" `@decision` coverage. Reconciliation shows the 9 unannotated files are package stubs:

```
src/adversary_pursuit/__init__.py            (2 lines, version + docstring)
src/adversary_pursuit/__main__.py            (33 lines, dispatch only — `--version`, `chat`, default REPL)
src/adversary_pursuit/core/__init__.py       (1 line docstring)
src/adversary_pursuit/gamification/__init__.py (stub)
src/adversary_pursuit/models/__init__.py     (stub)
src/adversary_pursuit/modules/__init__.py    (stub)
src/adversary_pursuit/modules/cti/__init__.py (stub)
src/adversary_pursuit/modules/osint/__init__.py (stub)
src/adversary_pursuit/modules/pivoting/__init__.py (empty namespace package)
```

These files contain no architectural decisions — they are namespace markers and a thin entry-point dispatcher. The 76% figure is an artifact of dividing by file count rather than by decision-bearing-file count. **Recommendation:** treat this as resolved; the decision-coverage metric should ignore `__init__.py` files and `__main__.py` shorter than ~50 lines unless they carry @decision themselves. No backlog item needed. (The previously listed cosmetic fix `W-COVERAGE-METRIC` is deferred — not a v1 release blocker.)

---

## Next Work Items

These are the concrete follow-ups identified by the 2026-04-28 reckoning and updated by the 2026-04-29 interface-model correction (ADR-010). Each is sized to be a single Guardian-bound work item with its own Evaluation Contract when dispatched.

### Agent gamification parity (Phase 6 follow-ups)

| ID | Title | Type | Merge SHA | Status |
|----|-------|------|-----------|--------|
| W-AGENT-MODULES-VT-CENSYS-PT | Add VirusTotal, Censys, PassiveTotal to the agent's tool catalog | source + tests | `66f89dd` | completed |
| W-AGENT-CELEBRATIONS | Wire `CelebrationEngine` into `run_module`; surface ASCII art / milestone messages via Rich panel | source + tests | `4ccc5888` | completed |
| W-AGENT-BADGES | Run `BadgeManager.check_all` after each tool call; persist and surface newly-earned badges | source + tests | `380c2f8` | completed |
| W-AGENT-MODES | Add `mode <name>` chat meta-command; wire `AgentRunner.set_character` to `ModeManager` | source + tests | `8564d1e` | completed |
| W-AGENT-HINTS | Chat meta-command `hint` / `hint buy` AND LLM tools `get_next_hint` / `buy_hint`; balance protection | source + tests | `f511f06` | completed |
| W-AGENT-AUTOPIVOT | Subscribe agent tool-execution path to `core/event_bus.py`; `autopivot on/off` meta-command | source + tests | `8e48256` | completed |
| W-AGENT-CHALLENGES | LLM tools `list_challenges` + `check_challenges`; `challenges` meta-command | source + tests | `26fefe7` | completed |
| W-AGENT-GRAPH-EXPORT | LLM tools `render_graph` + `export_workspace`; `graph` + `export gexf/stix` meta-commands | source + tests | `0b83eb2` | completed |
| W-AGENT-REPORT | LLM tools `start_report_interview` + `answer_report_question` + `generate_report`; `report` meta-command | source + tests | `f513c2d` | completed |
| W-AGENT-DOCS | README + MASTER_PLAN updated for agent-first v1; all 21 tools, 8 meta-commands, 10 modes documented | docs only | this commit | completed |

### Other v1 boundaries

| ID | Title | Type | Blocked By |
|----|-------|------|------------|
| W-V1-PYPI-VERIFY | Verify PyPI publish for #24 — either confirm an existing release or cut a tag to trigger `release.yml` | release / ops | publish credentials access |

> **Recommended next work item:** **`W-AGENT-MODULES-VT-CENSYS-PT`**. Smallest, lowest-risk, has no dependencies, restores the *catalog parity* claim (10 modules in cmd2 vs. 10 modules in chat) before the larger gamification work begins. After it lands, **`W-AGENT-CELEBRATIONS`** is the natural next slice — it's the highest-visibility gamification gap and unblocks W-AGENT-BADGES + W-AGENT-MODES (all share the same per-tool-call hook point in `run_module`).
>
> The previously listed `W-SCOPE-25` is retired by ADR-010. The previously listed `W-COVERAGE-METRIC` (cosmetic `@decision` ratio) is deferred — it is not a v1 release blocker and was always optional.

---

## Architecture Decisions

| ID | Decision | Rationale |
|----|----------|-----------|
| ADR-001 | cmd2 over Textual | Textual lacks REPL support; cmd2 provides Metasploit-like stateful console with native tab completion, history, scripting |
| ADR-002 | Rich for rendering | Tables, panels, trees, syntax highlighting, progress bars -- everything needed for a polished CLI |
| ADR-003 | importlib.metadata entry_points for plugins | Modern standard, explicit, side-effect-free loading, version-controlled via pip |
| ADR-004 | typing.Protocol for module contracts | Structural subtyping -- lighter than ABCs, enforces interface without inheritance |
| ADR-005 | STIX 2.1 as internal data model | Industry standard, interoperable with OpenCTI/MISP, graph-native (SDO/SCO/SRO) |
| ADR-006 | SQLite for v1 storage | Zero-config, portable workspaces, upgrade path to PostgreSQL |
| ADR-007 | asyncio event bus for auto-pivot | SpiderFoot-proven pattern, Python-native, enables cascading discovery |
| ADR-008 | Parabolic decay scoring | CTFd-proven formula, self-balancing difficulty valuation |
| ADR-009 | httpx over requests | Async-capable, HTTP/2, modern API |
| ADR-010 | **Agentic AI chat (`ap chat`, litellm-driven) is the v1 primary user-facing interface; the cmd2 REPL (`ap`) is a supporting power-user surface.** | Per user direction (2026-04-29). The original 2026-04-05 plan named cmd2 (#2) as "the heart of the application," but after Phase 1-4 landed and #25 introduced an agentic chat (`707f956`, `17120e7`), the user clarified that the v1 vision is conversational. Modules already form a uniform tool surface that an LLM agent can discover and invoke (DEC-AGENT-TOOLS-001/002); gamification primitives (`ScoringEngine`, `CelebrationEngine`, `BadgeManager`, `HintProvider`, `ModeManager`, event bus) are already cleanly separated from the cmd2 console and can observe tool execution events regardless of caller. Treating the agent as primary is therefore architecturally cheap; what remains is wiring the gamification touchpoints into the agent path (W-AGENT-CELEBRATIONS, W-AGENT-BADGES, W-AGENT-HINTS, W-AGENT-MODES, W-AGENT-AUTOPIVOT). Supersedes the v1 Non-Goal language about "Machine-assisted features" via a narrow carve-out for LLM-driven tool selection (see Non-Goals (v1) above). |

---

## Implementation Order

```
Phase 1 (Foundation):    #1 -> #5 -> #3 -> #4 -> #2                 [done]
Phase 2 (Modules):       #10, #12, #9 -> #11 -> #6, #8 -> #7 -> #13 [done]
Phase 3 (Gamification):  #14 -> #15 -> #16 -> #17 -> #18            [done]
Phase 4 (Auto-Pivot):    #19 -> #20                                 [done]
Phase 5 (Polish):        #21 -> #22 -> #23 -> #24                   [in-progress: PyPI verify]
Phase 6 (Agent — primary v1 interface):
                         #25 (landed) ->
                         W-AGENT-MODULES-VT-CENSYS-PT ->
                         W-AGENT-CELEBRATIONS ->
                         W-AGENT-BADGES + W-AGENT-MODES ->
                         W-AGENT-HINTS ->
                         W-AGENT-AUTOPIVOT ->
                         W-AGENT-CHALLENGES + W-AGENT-GRAPH-EXPORT + W-AGENT-REPORT ->
                         W-AGENT-DOCS
```

**Phase 1 rationale (historical):** Console (#2) was the integration point that wired together Config (#5), Plugins (#3), and Workspace (#4). Building subsystems first allowed clean interfaces and isolated testing. Console became straightforward wiring when built last. *Under ADR-010, the cmd2 console is a supporting power-user surface; the foundational subsystems it integrates are now also consumed by the agent.*

**Phase 2 rationale (historical):** Start with simplest free-tier APIs that prove distinct patterns -- AbuseIPDB (#10, single endpoint), OTX (#12, multi-endpoint), URLScan (#9, async submit+poll). Complex APIs (VirusTotal, PassiveTotal) come later.

**Phase 6 rationale (new):** Module catalog parity first (W-AGENT-MODULES-VT-CENSYS-PT — smallest, removes a misleading partial-coverage claim), then the highest-visibility gamification gap (W-AGENT-CELEBRATIONS — closes the "fun is a first-class design constraint" parity gap), then the per-tool-call hook-point siblings (W-AGENT-BADGES, W-AGENT-MODES — both naturally fit the same `run_module` integration site as celebrations), then hints (which benefit from mode-flavored phrasing), then auto-pivot (the single biggest agent-vs-cmd2 architectural gap), and finally the niche surfaces (challenges, graph/export, reports, docs).

**MLP (Minimum Lovable Product, revised 2026-04-29):**
- *Original MLP:* working cmd2 console + 3 OSINT modules + scoring.
- *Revised MLP:* working **`ap chat` agent** + 3 OSINT modules wired as agent tools + scoring + **at least one visible gamification signal in the chat path** (celebrations is the recommended one — highest signal-to-effort ratio). The cmd2 console is bundled but is not the front door.
- *MLP Status (Phase 6 closeout, 2026-05-01):* MLP threshold crossed. `ap chat` provides 10 modules, full gamification (scoring + celebrations + badges + modes + hints), auto-pivot, challenges, graph/export, and reports — exceeds the revised MLP. Remaining v1 work is Phase 5 release polish (`W-V1-PYPI-VERIFY`).

The previous "Start with #1 (scaffolding) immediately" instruction is retired — Phase 1-6 are landed. The next concrete step is `W-V1-PYPI-VERIFY`.

---

## Verification

- **Unit tests:** pytest for all core modules (scoring math, plugin discovery, STIX conversion, workspace CRUD)
- **Integration tests:** Real API calls against free-tier endpoints (AbuseIPDB, OTX have free tiers)
- **Console tests:** cmd2 provides testing utilities for command parsing and output verification
- **E2E smoke test:** `ap` launches, `search shodan` finds module, `use osint/shodan_ip` loads it, `show options` displays params, `set TARGET 1.2.3.4`, `run` returns results, `score` shows points

---

## Research

Full deep research report: `.claude/research/DeepResearch_AdversaryPursuit_2026-04-05/report.md`

---

## Completed

*(Completed phases will be compressed here)*
