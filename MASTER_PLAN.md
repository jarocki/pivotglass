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

## v1 RELEASE SHIPPED (2026-05-19)

> **Stable public release: `v0.1.0` (no rc suffix), cut and verified. Pre-release flag: false.**
>
> - **Release page:** https://github.com/jarocki/ap/releases/tag/v0.1.0
> - **Annotated tag object SHA:** `e669b5df5c6bb7c98e38a84144f9bc9ab6dcc72f` (points at commit `e8e9b137e116d7a70040c6b3ab9931c08ec73fc4`)
> - **Tagged commit:** `e8e9b137e116d7a70040c6b3ab9931c08ec73fc4` (`chore(release): promote to v0.1.0 stable`)
> - **GitHub Actions workflow run:** https://github.com/jarocki/ap/actions/runs/26104027477 (status: success)
> - **Artifacts attached:** `adversary_pursuit-0.1.0-py3-none-any.whl` (176 KB) + `adversary_pursuit-0.1.0.tar.gz` (493 KB), produced by `.github/workflows/release.yml`.
> - **rc1 preserved:** `v0.1.0rc1` (tag SHA `d392debca0fed01317b0db335ee7a27f8cea9858`, commit `1af235f`) remains intact as the verification record.
> - **Stale v0.1.0 replaced:** A stale published v0.1.0 release (2026-05-02, pointing at pre-rc1 commit `1debf76`) was discovered by Guardian during tag-push and replaced with the rc1-verified stable release (DEC-V1-FINAL-SHIP-004; user-authorized destructive operation).
>
> v1 boundary is fully closed. All four v1 boundary work items — `W-V1-RELEASE-VERIFY`, `W-OTX-TIMEOUT`, `W-GREYNOISE`, and `W-V1-FINAL-SHIP` — have landed (see Phase 5 closeout, Phase 8 closeout, Phase 9 closeout, and Phase 5 Stable Closeout below).

---

## Plan Status (Reconciled 2026-04-28, Reframed 2026-04-29, v1 Closed 2026-05-18, Stable Shipped 2026-05-19)

| Phase | Status | Notes |
|-------|--------|-------|
| Phase 0 — Foundation Modules (was Phase 1) (#1-#5) | completed | All 5 issues landed; cmd2 console wires Config + Plugin + Workspace + Modes. Now reframed as supporting infrastructure for the agent. |
| Phase 1 — OSINT/CTI Modules (was Phase 2) (#6-#13) | completed | All 8 priority modules landed; plus stretch `whois_lookup`, `dns_resolve`. Modules are the uniform tool surface both interfaces share. |
| Phase 2 — Gamification (was Phase 3) (#14-#18) | completed | Scoring, Challenges, Modes, Badges, Hints all landed. Fully wired into both the cmd2 console and the agent path (all 9 W-AGENT-* slices complete). |
| Phase 3 — Auto-Pivot & Graph (was Phase 4) (#19-#20) | completed | Event bus opt-in (DEC-EVENTBUS-002); graph + GEXF + STIX bundle export. Wired into both cmd2 console and agent path (W-AGENT-AUTOPIVOT `8e48256`, W-AGENT-GRAPH-EXPORT `0b83eb2`). |
| Phase 4 — Agentic Chat Interface (#25 + W-AGENT-*) | **completed** | All 9 W-AGENT-* slices landed. 21 LLM tools covering all 10 modules + celebrations + badges + hints + modes + autopivot + challenges + graph/export + reports. Full gamification parity with cmd2 console achieved. |
| Phase 5 — Polish & Release (#21-#24) | **completed** (2026-05-18) | #21, #22, #23 done; #24 CI/CD landed. **Distribution strategy pivoted PyPI → GitHub Releases (`02fed4d`, 2026-05-03).** `W-V1-PYPI-VERIFY` retired; replaced by `W-V1-RELEASE-VERIFY` which landed at merge `cd3709a` (2026-05-18) — `v0.1.0rc1` pre-release published at https://github.com/jarocki/ap/releases/tag/v0.1.0rc1 (tag SHA `d392deb`), wheel+sdist attached, fresh-venv install with `[agent]` extras verified end-to-end. See "Phase 5 closeout" section below. |
| Phase 6 — Agent Docs (W-AGENT-DOCS) | **completed** | README rewritten for agent-first v1: `ap chat` primary interface documented, all 21 LLM tools, 8 meta-commands, 10 modes, and persona-prompt protocol. MASTER_PLAN Phase 4 status and W-AGENT-* table updated with all merge SHAs. |
| Phase 7 — Post-Phase-6 CTI Pipeline & TUI Polish (unscheduled, landed organically 2026-05-03..2026-05-15) | **completed** | ~12 user-driven commits hardening CTI reliability, setup UX, and TUI polish: setup wizard `b44968c` (#45), 3-layer key resolution `a4cc341`, Censys Platform API v3 `fef6bfd` (#43), CTI pipeline repairs `9e6daa0`, URLScan submit/poll fixes `26c5b54` + `5cc2be6`, smoke SKIP classification `137fb45` (#48), smoke ConfigManager fix `823d54e`, TUI polish `db576b9`, provider/model wizard `4e11dde`, help meta-commands `70ede27`, `AP_MODEL` env override `9129c1b`, wizard dotfile export `4b9d030`. |
| Phase 8 — Smoke Test Reliability | **completed** (W-OTX-TIMEOUT landed `b877574`, impl `72fd3eb`) | `W-OTX-TIMEOUT` added `TIMEOUT` option to `cti/otx` + classified `httpx.ReadTimeout` as a timeout-stub SCO, mirroring the URLScan transient-failure pattern (`5cc2be6`). No other smoke regressions open at v1 ship; future live-smoke regressions will be filed as discrete slices through the canonical planner chain. |
| Phase 9 — Pre-v1 Module Catalog Top-Off (W-GREYNOISE) | **completed** (2026-05-16, merge `6884317`) | Per 2026-05-16 user directive ("Is GreyNoise one of the API lookup sources? If not, please add it before we ship v1.0."), added `osint/greynoise` as the 11th catalog module using the free-tier GreyNoise Community API (`/v3/community/{ip}`). Closes the noise/RIOT classification gap in the v1 IP-reputation surface. See "Phase 9 closeout" section below. |

**Aggregate (reconciled 2026-05-19, v1 stable shipped):** Phases 0–9 complete. All W-AGENT-* slices landed; Phase 5 release path verified (`v0.1.0rc1` pre-release at `cd3709a`) then promoted to stable `v0.1.0` (`e8e9b13`, 2026-05-19); Phase 6 docs complete; Phase 7 post-polish complete; Phase 8 `W-OTX-TIMEOUT` landed (`b877574`); Phase 9 `W-GREYNOISE` landed (`6884317`); `W-V1-FINAL-SHIP` landed (`e8e9b13`). The agentic chat (`ap chat`) is the v1 primary interface with full gamification parity over 11 modules. The cmd2 REPL is a supported power-user surface. All four v1 boundary work items have landed; `v0.1.0` is stable and public. Subsequent work is post-v1 and user-determined.

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
**Status:** completed (2026-05-18 — W-V1-RELEASE-VERIFY landed; v1 release path verified end-to-end)

### Reconciliation (2026-04-28, closed 2026-05-18)

| Issue | Status | Merge SHA | Notes |
|-------|--------|-----------|-------|
| #21 Report Generation | done | `9e55bca` | DEC-REPORT-001 (interview-first structure), DEC-REPORT-002 (Markdown over PDF/HTML for v1), DEC-REPORT-003 (in-memory interview state, no DB persistence). Console exposes `do_report`. |
| #22 Celebrations | done | `f175a70` | DEC-CELEBRATION-001 (4-level ASCII art keyed on points), DEC-CELEBRATION-002 (milestone messages fire at exact thresholds). |
| #23 Documentation | done | `167df88` (consolidated `8710aa0`) | README rewrite: usage, modules, plugin guide, architecture. |
| #24 Release Distribution | **completed** | `18a64b4` (CI/CD) → `02fed4d` (PyPI → GitHub Releases pivot, 2026-05-03) → **`cd3709a` (W-V1-RELEASE-VERIFY closeout, 2026-05-18)** | `.github/workflows/{ci,release}.yml` shipped. v1 distributes via **GitHub Releases** (tagged artifact downloads + `pip install` from release URL) rather than PyPI. Rationale: reduces credential/trusted-publisher surface for a solo-maintainer pre-1.0 project; release tags remain the trigger. The earlier `[project.urls]` regressions (`c46903f`, `5895560`) were corrections during the pivot. **Verification closed:** `v0.1.0rc1` cut, `release.yml` produced wheel+sdist, public release at https://github.com/jarocki/ap/releases/tag/v0.1.0rc1, fresh-venv install + 11 entry-points + `ap chat` import all green. |

### Phase 5 Closeout — W-V1-RELEASE-VERIFY (2026-05-18)

**What shipped:**

- **Tag:** `v0.1.0rc1` (annotated, SHA `d392debca0fed01317b0db335ee7a27f8cea9858`, points at commit `1af235f` — `chore(release): bump to 0.1.0rc1 + rewrite README install for GitHub Releases`).
- **Pre-release flag:** correctly set by `release.yml`'s `prerelease` substring detection (`rc` in the tag name).
- **Release URL:** https://github.com/jarocki/ap/releases/tag/v0.1.0rc1
- **Artifacts attached:** `adversary_pursuit-0.1.0rc1-py3-none-any.whl` (176 KB) and `adversary_pursuit-0.1.0rc1.tar.gz` (489 KB), both produced by `uv build` inside `release.yml` and uploaded via `softprops/action-gh-release@v2`.
- **Closeout merge SHA on `main`:** `cd3709a11a9bd7b0bd79ea0b0163916207b16173` — `docs(release): fill v0.1.0rc1 placeholders in README install instructions`. This is the final commit on main that fills the README install block with the verified release URL after the tag cut and CI run completed.

**Fresh-venv verification evidence:**

- `pip install "adversary-pursuit[agent] @ <release-wheel-url>"` succeeded from the public URL — `[agent]` extras (litellm, prompt-toolkit) resolved and installed.
- `ap --help` runs in the installed venv; the dispatcher banner and subcommand list render correctly.
- `importlib.metadata.entry_points(group='adversary_pursuit.modules')` returns **11** entries from the installed wheel: `abuseipdb`, `censys`, `dns_resolve`, `greynoise`, `hibp`, `otx`, `passivetotal`, `shodan_ip`, `urlscan`, `virustotal`, `whois_lookup`. (Matches `[project.entry-points."adversary_pursuit.modules"]` in `pyproject.toml` 1:1.)
- `ap chat` module imports without `ImportError: litellm` — proves the `[agent]` extras install path is real, not a documentation aspiration.

**State authorities exercised (no parallel mechanism introduced):**

- `.github/workflows/release.yml` remained the **sole** authority for artifact production. No alternate build/publish script, no Makefile target, no fork.
- `pyproject.toml::[project].version` remained the **sole** authority for the package version string; the bump to `0.1.0rc1` was a single-line edit. The pre-existing local `v0.1.0` tag was preserved as-is (neither pushed nor deleted) and is out of scope for this slice.
- README's "Installation" section was promoted to be the canonical wheel-install path with the real release URL; the "Future: PyPI" subsection was reframed as deferred-rather-than-promised.

### Decision Log (Phase 5 closeout)

| Decision ID | Title | Rationale |
|-------------|-------|-----------|
| DEC-V1-RELEASE-VERIFY-001 | Cut a pre-release tag (`v0.1.0rc1`), not a final tag (`v0.1.0`), for the verification | Decouples "we proved the install path works" from "we shipped v1.0". A failed verification on an `rc` tag is recoverable; a failed verification on `v0.1.0` would burn the v1.0 namespace. The `prerelease` flag in `release.yml` correctly fires on the `rc` substring, so users browsing the releases page see a Pre-release label rather than mistaking it for stable v1.0. |
| DEC-V1-RELEASE-VERIFY-002 | Verify via fresh-venv `pip install <release-URL>` outside the worktree, not via `pip install -e .` from source | The user-facing install path IS the URL form. A source-tree editable install proves nothing the dev loop hasn't already exercised. Installing into a venv outside the worktree eliminates the chance that worktree-resident dependencies contaminate the test. |
| DEC-V1-RELEASE-VERIFY-003 | Bundle README install-block update into this slice rather than a follow-up `W-V1-DOCS` slice | The verification evidence IS the install command, so writing the README block with the verified URL in the same slice is single-authority for "the canonical v1 install command." Splitting into a follow-up would create a doc-drift window where users see an unverified install command. |
| DEC-V1-RELEASE-VERIFY-004 | Tag push to upstream (`git push origin v0.1.0rc1`) is a routine Guardian (land) operation, not a user-decision bounce | Tag-push on the established upstream is Guardian's canonical landing surface (CLAUDE.md §"Approval Gates"). It is not a force-push, not a history rewrite. Pre-asking for user approval on a routine Guardian op violates the Question Merit Test. Tag deletion as part of rollback would be destructive and would require explicit user approval — that asymmetry is preserved. |
| DEC-V1-RELEASE-VERIFY-005 | Leave the pre-existing local `v0.1.0` tag in place (neither pushed nor deleted) | The local `v0.1.0` tag was created speculatively in prior planning and never pushed. Deleting it expands scope into "cleanup of unrelated refs"; pushing it would claim "v1.0 shipped" before verification. Inert preservation is the minimum-surprise choice. A future ship-v1.0 slice will decide whether to move it to the post-verification HEAD or recreate it — that's a product decision, not a verification-mechanics decision. |
### Phase 5 Stable Closeout — W-V1-FINAL-SHIP (2026-05-19)
**Status:** completed

**What shipped:**

- **Tag:** `v0.1.0` (annotated, tag object SHA `e669b5df5c6bb7c98e38a84144f9bc9ab6dcc72f`, points at commit `e8e9b137e116d7a70040c6b3ab9931c08ec73fc4` — `chore(release): promote to v0.1.0 stable`).
- **Pre-release flag:** false (confirmed via `gh release view v0.1.0 --json isPrerelease`).
- **Release URL:** https://github.com/jarocki/ap/releases/tag/v0.1.0
- **Workflow run:** https://github.com/jarocki/ap/actions/runs/26104027477 (status: success)
- **Artifacts attached:** `adversary_pursuit-0.1.0-py3-none-any.whl` (176 KB) and `adversary_pursuit-0.1.0.tar.gz` (493 KB), produced by `uv build` inside `release.yml` and uploaded via `softprops/action-gh-release@v2`.
- **Stale release replaced:** A published v0.1.0 GitHub Release from 2026-05-02 (pointing at pre-rc1 commit `1debf76`) was discovered by Guardian during tag-push audit. It predated the GitHub Releases pivot (`02fed4d`), the URLScan poll auth fix (`5cc2be6`), OTX TIMEOUT (`b877574`), GreyNoise (`6884317`), and all Phase 5 reconciliation work. User authorized destructive replacement ("B"). `gh release delete v0.1.0 --cleanup-tag` atomically removed the stale release page and remote ref; the new `v0.1.0` was cut at `e8e9b13` and re-published via the same `release.yml` workflow.
- **rc1 preserved:** `v0.1.0rc1` (tag SHA `d392debca0fed01317b0db335ee7a27f8cea9858`, commit `1af235f`) remains intact as the verification record.

**State authorities exercised (no parallel mechanism introduced):**

- `.github/workflows/release.yml` remained the **sole** authority for artifact production. No alternate build/publish path.
- `pyproject.toml::[project].version` was the **sole** authority for the stable package version string (`0.1.0`, without rc suffix).
- The stale v0.1.0 release (download count: 0; no PyPI artifact; release was 16 days old) was removed atomically before the stable release was published — no window of dual-release ambiguity.

### Decision Log (Phase 5 stable closeout)

| Decision ID | Title | Rationale |
|-------------|-------|-----------|
| DEC-V1-FINAL-SHIP-001 | Promote directly from rc1-verified HEAD (`e8e9b13`) to stable `v0.1.0` without an additional integration period | `v0.1.0rc1` was already verified end-to-end (fresh-venv install, 11 entry-points, `ap chat` import, full pytest pass). The rc cycle existed to decouple "verify the install path" from "ship stable." That purpose was fulfilled; no new regressions were surfaced between rc1 and stable promotion. Additional waiting would manufacture a gap, not reduce risk. |
| DEC-V1-FINAL-SHIP-002 | Set the `pre-release` flag to false on the stable release (not a pre-release) | The `release.yml` workflow sets `prerelease: true` only when the tag name contains `rc`, `alpha`, or `beta`. `v0.1.0` contains none of those substrings, so the flag is false by default — no code change needed. Confirmed post-push via `gh release view v0.1.0 --json isPrerelease`. |
| DEC-V1-FINAL-SHIP-003 | Preserve `v0.1.0rc1` intact; do not delete or retag it | `v0.1.0rc1` is the verification record showing the install path was proven before the stable tag was cut. Deleting it would destroy that audit trail. It also serves as a reference for any user who pinned the rc URL. |
| DEC-V1-FINAL-SHIP-004 | Force-replaced the stale published v0.1.0 release (2026-05-02 at commit `1debf76`) with the rc1-verified stable release (2026-05-19 at commit `e8e9b13`) | The planner's #56/#57 framing assumed v0.1.0 was a local-only dangling tag, but a Guardian audit at tag-push time discovered an actual published GitHub Release from 2026-05-02 pointing at a pre-rc1 CI-fix commit (`1debf76`) — predating the GitHub Releases pivot (`02fed4d`), the URLScan poll auth fix (`5cc2be6`), OTX TIMEOUT (`b877574`), GreyNoise (`6884317`), and all Phase 5 reconciliation work. The stale release would have misled users into installing fundamentally older code with broken CTI modules. User explicitly authorized destructive replacement ("B") after Guardian surfaced the boundary. `gh release delete v0.1.0 --cleanup-tag` removed both the release page and the remote ref atomically; the new `v0.1.0` was cut at `e8e9b13` and re-published via the same `release.yml` workflow. Consumer-breakage risk was assessed as ~zero (download count was 0; no PyPI artifact exists per the pivot; release was 16 days old). `v0.1.0rc1` was preserved as the verification record. |

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

### #24 -- Release Distribution

**Pivoted 2026-05-03 (`02fed4d`): PyPI → GitHub Releases.** For v1 the canonical install path is `pip install <github-release-url>` (or `pipx install` against a tagged release artifact), not `pip install adversary-pursuit` from PyPI.

- GitHub Releases with tagged sdist + wheel artifacts (replaces PyPI for v1)
- GitHub releases with changelog
- CI/CD via GitHub Actions (lint, test, build artifact, attach to release)

PyPI distribution is deferred (not abandoned) — a credible candidate post-v1 once the project has a stable user base and a maintained trusted-publisher posture. v1 keeps the supply-chain surface small.

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

## Post-Phase 6 Maintenance Fixes (2026-05-03..2026-05-15)

After Phase 6 closeout, ~12 user-driven commits landed organically as live-use revealed CTI reliability and UX rough edges. These were not planned slices — they were reactive fixes/polish driven by smoke runs and direct user feedback. Captured here for historical traceability; the strategic pivot (`02fed4d`) is also called out separately in Phase 5.

| SHA | Title | Rationale (one-line) |
|-----|-------|----------------------|
| `02fed4d` | Replace PyPI distribution with GitHub Releases | Reduces credential/trusted-publisher surface for solo-maintainer v1; supersedes `W-V1-PYPI-VERIFY`. |
| `b44968c` | Add setup wizard for CTI credentials (closes #45) | First-run friction: users had no guided way to enter API keys; wizard collects + persists to `~/.ap/config.toml`. |
| `a4cc341` | 3-layer API key resolution (CLI → env → config) | Deterministic precedence so env-driven CI and config-driven dev/local don't surprise users. |
| `fef6bfd` | Censys Platform API v3 migration (closes #43) | Censys deprecated the v2 search endpoint; v3 Platform API + bearer token. |
| `9e6daa0` | CTI pipeline repairs (workspace bind, Censys 302, OTX timeout msg, PT error msg) | Bundle of small reliability fixes surfaced by live runs. |
| `26c5b54` | URLScan submit fix (trailing slash + 403 → AuthenticationError) | Submit endpoint required trailing slash; 403 was being swallowed as a generic error. |
| `5cc2be6` | URLScan poll auth fix (API-Key header + 403-during-poll retry) | Poll path was using a different auth shape than submit; added retry on transient 403. |
| `137fb45` | Smoke test SKIP classification (closes #48) | Smoke runs without API keys must SKIP, not FAIL — they were poisoning red/green signal. |
| `823d54e` | Smoke test ConfigManager fix | Smoke harness was instantiating ConfigManager incorrectly after the 3-layer resolution change. |
| `db576b9` | TUI polish (autocomplete, history, vi, ASCII flair) | prompt_toolkit-driven polish lifting the chat REPL to feel native. |
| `4e11dde` | Provider/model setup wizard | Mirrors the CTI credentials wizard for LLM provider selection (Ollama/OpenAI/Anthropic). |
| `70ede27` | Help / `?` meta-commands | Discoverability: users couldn't see the meta-command catalog without reading docs. |
| `9129c1b` | `AP_MODEL` env override | One-shot model selection without rewriting config. |
| `4b9d030` | Wizard dotfile export | Wizard can emit a shell dotfile snippet so env vars persist across sessions. |

These commits did not pass through canonical planner → guardian (provision) → implementer → reviewer → guardian (land) flow. They are valid landed work; the lesson for Phase 8 is that **live-smoke regressions should be filed as discrete slices** so the canonical chain owns them.

---

## Phase 8: Smoke Test Reliability — Closeout (W-OTX-TIMEOUT, 2026-05-15)
**Status:** completed

**What shipped:** `W-OTX-TIMEOUT` (workflow id `w-otx-timeout`) landed via merge `b877574` (implementer commit `72fd3eb` — `fix(otx): TIMEOUT option + httpx.TimeoutException -> stub SCO`).

`cti/otx` now accepts a `TIMEOUT` module option (seconds, configurable per call) and classifies `httpx.ReadTimeout` / `httpx.TimeoutException` as a single timeout-stub `ipv4-addr` SCO with `x_otx_status = "timeout"` rather than raising. This mirrors the URLScan transient-failure pattern (`5cc2be6` / `26c5b54`) where the agent path needs an observable to score and continue rather than a hard error that breaks the chat flow.

**Pattern established:** classify transient/timeout failures as observable stubs (`x_<vendor>_status = "timeout"` / `"unknown"`) rather than hard errors. AbuseIPDB / OTX / URLScan / GreyNoise (404) all follow this pattern now; future modules added to the catalog should adopt it by default.

**State of Phase 8 at v1 ship:** No further smoke regressions are open. Future live-smoke regressions, if surfaced, will be filed as discrete planner slices through the canonical chain rather than landed ad-hoc (the lesson from the Phase 7 organic-landing pattern).

### Decision Log (Phase 8)

| Decision ID | Title | Rationale |
|-------------|-------|-----------|
| DEC-MODULE-OTX-TIMEOUT-001 | Add a configurable `TIMEOUT` module option to `cti/otx` rather than a hardcoded constant | High-cardinality IPs (those with large pulse counts) routinely exceed any single fixed timeout. Making `TIMEOUT` a module option lets users tune for slow networks or aggressive timeouts without code edits, matching the `set TARGET ...` ergonomics they already use for other module parameters. |
| DEC-MODULE-OTX-TIMEOUT-002 | Map `httpx.ReadTimeout` / `httpx.TimeoutException` to a single timeout-stub `ipv4-addr` SCO (`x_otx_status = "timeout"`) rather than raising | Mirrors the URLScan transient-failure pattern (`5cc2be6` / `26c5b54`) and the GreyNoise 404 pattern (DEC-MODULE-GREYNOISE-002). The agent path needs an observable to score and continue the chat flow; a hard exception breaks the conversation and hides the partial signal that the host was at least reachable enough to timeout on the pulse query. The smoke runner SKIP/PASS classifier (`137fb45`) classifies timeout-stub SCOs as PASS-with-stub, preserving the SKIP-means-no-key invariant. |

---

## Phase 9: Pre-v1 Module Catalog Top-Off — Closeout (W-GREYNOISE, 2026-05-16)
**Status:** completed

**What shipped:** `W-GREYNOISE` (workflow id `w-greynoise`) landed via merge `6884317` — `feat(modules): add osint/greynoise (GreyNoise Community API IP reputation)`.

**User directive (2026-05-16, verbatim):** *"Is GreyNoise one of the API lookup sources? If not, please add it before we ship v1.0."*

**Why this was a pre-v1 catalog top-off, not a post-v1 follow-up:** GreyNoise is the canonical free-tier source for the "is this IP internet-background-noise / opportunistic scanner / known benign service / known malicious actor" (noise/RIOT) classification axis. Before this slice, the v1 IP-reputation surface covered reputation (AbuseIPDB), multi-engine verdicts (VirusTotal), attack-surface (Shodan/Censys), and passive DNS (OTX/PassiveTotal), but had no source for the noise/RIOT axis. Adding it before the v1 ship gate avoided a "we know there's a gap, but ship anyway" caveat in the release notes.

**API choice:** GreyNoise **Community API** (`GET https://api.greynoise.io/v3/community/{ip}`) — free tier, 10,000 queries/day, header `key: <api_key>` (lowercase). The Enterprise API (CVE tags, JA3 fingerprints, raw scanner traffic) was rejected for v1 because it requires a paid plan and would be unreachable in CI or for free-tier users.

**Integration surfaces extended (no parallel mechanism created):**

- Module catalog: `core/plugin_mgr.py::_BUILTIN_MODULES` + `pyproject.toml [project.entry-points."adversary_pursuit.modules"]` (both updated — dual registration is the established invariant; 11/11 modules now appear in both).
- API key config: `core/config.py::ApiKeysConfig` (new `greynoise` field) + `_AP_ENV_VAR_MAP` (`AP_GREYNOISE_API_KEY`) + `_VENDOR_ENV_VAR_MAP` (`GREYNOISE_API_KEY`).
- Agent tool catalog: `agent/tools.py` — `greynoise_lookup` tool definition + `_SERVICE_NAMES["osint/greynoise"] = "greynoise"` + `_MODULE_MAP` entry.
- Smoke test runner: `scripts/smoke_test.py` — `_run_greynoise` handler + `module_runs` row.
- Setup wizard CTI catalog: `agent/provider_setup.py::CTI_SERVICES` + `_CTI_ENV_VAR`.
- Auto-pivot subscriptions: `core/event_bus.py::DEFAULT_SUBSCRIPTIONS["osint/greynoise"] = ["ipv4-addr"]`.
- Hint catalog: `gamification/hints.py` (free + paid hints).
- REPL autocomplete: `agent/repl_input.py::_MODULE_NAMES`.

### Decision Log (Phase 9)

| Decision ID | Title | Rationale |
|-------------|-------|-----------|
| DEC-MODULE-GREYNOISE-001 | Use the free Community API (`/v3/community/{ip}`) with `key:` HTTP header (lowercase) | Free tier covers the v1 use case (single-IP lookup, one SCO per call). The lowercase `key` header is the documented auth shape and must be verbatim — `API-Key` / `Authorization: Bearer` will silently 401. Uses `httpx.AsyncClient` with 30s timeout, matching the AbuseIPDB / Shodan pattern (DEC-MODULE-ABUSEIPDB-001 / ADR-009). |
| DEC-MODULE-GREYNOISE-002 | 404 → single SCO with `x_greynoise_classification = "unknown"`; 401 → `AuthenticationError`; 429 → `RateLimitError` | Distinguishes "no data" from "no auth" so the smoke runner can classify SKIP/PASS correctly and the agent path can render "unknown" as a legitimate answer rather than an error toast. Mirrors the URLScan / OTX transient-failure pattern established by `5cc2be6` and reaffirmed by `W-OTX-TIMEOUT`. |
| DEC-MODULE-GREYNOISE-003 | Output is a single-element list with one `ipv4-addr` SCO carrying `x_greynoise_*` custom fields | One API call → one IP → one SCO is the simplest faithful representation. Custom `x_greynoise_*` fields (classification, noise, riot, name, last_seen, link) are absorbed by `dict_to_stix(allow_custom=True)` per DEC-STIX-001/002 — the same path AbuseIPDB and the other reputation modules use. |

---

## Phase 10: Friendly Errors (W-FRIENDLY-ERRORS, post-v1, 2026-05-14)
**Status:** in-progress (planner stage complete, implementer next)
**Workflow id:** `w-friendly-errors` · **Goal id:** `g-friendly-errors` · **Work item id:** `wi-friendly-errors`
**Branch:** `feature/friendly-errors` · **Worktree:** `.worktrees/feature-friendly-errors` · **Base:** `main` @ `ba32fa6`

### User directive (2026-05-14, verbatim)

> "Make sure that all errors are always caught so they are not displayed directly to the user. Instead, interpret the error, debug it, and display a fix. If you can automate the fix, prompt the player with an offer to fix it."

### Why this is post-v1, not v2

The `ap chat` REPL already has a friendly-error pipeline (`agent/error_handler.py`, DEC-AGENT-ERROR-HANDLER-001 — three-stage classify→LLM-explain→canned). That pipeline replaces raw tracebacks in the **main chat loop** but does not cover three real residual gaps that v0.1.0 users will hit:

1. **cmd2 console (`core/console.py`):** `_execute_hunt` catches `ModuleError` and generic `Exception` into red Panels, but cmd2's framework-level exception path (anything raised before our handler) prints a default traceback. There are also ~20 handler sites that render `poutput(f"Error: {exc}")` with no fix-suggestion.
2. **`ap chat` meta-command sub-handlers (`agent/chat.py` lines ~230, ~247, ~270):** these render raw `[red]Error: {e}[/red]` strings inside `hint`/`hint buy`/`score` flows, bypassing the main-loop `handle_error()` and producing no fix-suggestion, no diagnostic ID, and no debug-log entry.
3. **`scripts/smoke_test.py`:** the FAIL summary shows `httpx.ReadTimeout: ...` (concise) or a full traceback (`--verbose`) but never tells the user *what to do about it*. The user sees what broke, not how to fix it.

And the user's directive adds a new product capability that v0.1.0 simply doesn't have anywhere yet: **interactive auto-fix prompts**. When the fix is mechanically safe (rerun `ap config setup`, restore `~/.ap/config.toml.bak`, sleep-and-retry after a `Retry-After` header), the panel should offer `[y/n]` rather than make the user re-derive the command.

### Code-as-truth audit (what already exists vs. what's missing)

| Surface | Today (post-v0.1.0) | Gap closed by this slice |
|---|---|---|
| `agent/chat.py` main loop (line 689) | Protected — `handle_error()` 3-stage pipeline, Rich Panel, no traceback leaks | None (preserved) |
| `agent/chat.py` meta-command sites (lines ~230, ~247, ~270) | Raw `[red]Error: {e}[/red]` rendering | Migrated to `handle_error()` — uniform friendly-panel path |
| `core/console.py` `_execute_hunt` | Wrapped — red Panel, no traceback | Replaced with interpreter call — gains diagnostic ID + fix-suggestion + auto-fix prompt |
| `core/console.py` cmd2 framework default error | Default cmd2 behavior — prints traceback to stdout on unhandled command exceptions | Overridden via `APConsole.default_error` hook → interpreter |
| `scripts/smoke_test.py` FAIL summary | `{type}: {msg}` (concise) or `traceback.format_exc()` (`--verbose`) | Interpreter-driven summary: `[CATEGORY] fix-suggestion (diag <id>)` — `--verbose` still appends traceback |
| Debug log of full tracebacks | None — verbose-only stdout dump | New `~/.ap/debug.log` (JSONL, line-rotated to 1000, `fcntl.flock`-guarded) |
| Auto-fix prompt | None | New `AutoFix` registry + `[y/n/d]` prompt in interactive renderer |
| Mode-flavored error tone | None | Renderer accepts `CharacterMode` and reflects ninja/full_troll/sun_tzu/etc. tone in panel title |

### Architecture

**Single new authority:** `src/adversary_pursuit/core/error_interpreter.py` (~400 LOC). Placed under `core/` (not `agent/`) because it is consumed by cmd2 console, agent chat, and smoke_test alike — and must work without the `[agent]` extra installed (no litellm import). Public surface:

- `interpret(exc, *, surface, context=None) -> ErrorInterpretation`
- `render_interactive(interp, console, *, mode=None, interactive=True) -> AutoFixOutcome`
- `render_summary_line(interp) -> str` (non-interactive, no Rich markup)
- `ErrorInterpretation` and `AutoFix` frozen dataclasses
- `_CATALOG` registry — 8 entries, data-driven (each entry is a `match: Callable[[BaseException], bool]` + `interpret: Callable[[BaseException], ErrorInterpretation]` + optional `auto_fix_factory: Callable[[BaseException], AutoFix | None]`). Future catalog additions are single-tuple appends.

**Existing authority preserved:** `agent/error_handler.py` keeps its DEC-AGENT-ERROR-HANDLER-001 three-stage pipeline. Stage 1's catalog body relocates to `core/error_interpreter.py`; `classify_error()` becomes a thin delegate that returns a `FriendlyError` adapted from `ErrorInterpretation`. Stages 2 (LLM explain) and 3 (canned fallback) are **untouched** — that chat-specific behavior stays where it belongs.

**State-authority map:**

| State domain | Canonical authority | Notes |
|---|---|---|
| Error classification + fix catalog | `core/error_interpreter.py` `_CATALOG` | NEW. Sole authority. |
| Chat LLM-explain fallback | `agent/error_handler.py` `debug_llm_explain` | Unchanged. |
| Friendly panel rendering (chat) | `agent/error_handler.py` `handle_error` | Unchanged externally. |
| Friendly panel rendering (cmd2) | `core/error_interpreter.py` `render_interactive` | NEW. Wired from `APConsole.default_error`. |
| Friendly summary line (smoke) | `core/error_interpreter.py` `render_summary_line` | NEW. Wired from `_fmt_exc`. |
| Debug log (JSONL, rotated 1000 lines, `fcntl.flock`) | `~/.ap/debug.log` | NEW. Sole authority. |
| Diagnostic ID generation | `core/error_interpreter.py` `_make_diagnostic_id()` (8-hex-char `secrets.token_bytes(4)`) | NEW. Sole authority. |
| Auto-fix callable registry | `core/error_interpreter.py` `_CATALOG` entries | NEW. Sole authority. |
| Mode-flavored tone | Renderer reads `CharacterMode` fields; `gamification/modes.py` unchanged | Soft-coupled; `mode=None` falls back to neutral phrasing. |

**Removal targets (addition without subtraction is debt):**

- Catalog body in `agent/error_handler.classify_error()` — relocated, not duplicated. The function name stays so the single import site in `agent/chat.py` line 65 keeps working.
- Raw `[red]Error: {e}[/red]` and `[yellow]Warning: ...[/yellow]` `console.print` calls in `agent/chat.py` meta-command handlers (lines ~230, ~247, ~270) — migrated to `handle_error()`. No new mechanism; just stop bypassing the existing one.
- `scripts/smoke_test.py::_fmt_exc` body — becomes a thin wrapper over `render_summary_line()`. Signature preserved.

### Decisions (planner stage)

| Decision ID | Title | Rationale |
|---|---|---|
| DEC-ERROR-INTERPRETER-001 | New `core/error_interpreter.py` as sole catalog authority; `agent/error_handler.classify_error()` delegates | The existing `classify_error` is correctly factored for chat-LLM use but coupling `core/console.py` and `scripts/smoke_test.py` to an `agent/` namespace would pull litellm transitively. Placing the catalog under `core/` reflects that error interpretation is shared infrastructure. Preserves DEC-AGENT-ERROR-HANDLER-001 by extracting only stage 1; stages 2 and 3 stay in agent. Single authority avoids the parallel-catalog drift CLAUDE.md §12 forbids. |
| DEC-ERROR-INTERPRETER-002 | Debug log at user-global `~/.ap/config`-adjacent `~/.ap/debug.log`, not workspace-scoped | Errors can occur before a workspace is loaded (config corruption, plugin discovery failure). The debug log must always have a stable target. User-global also keeps the diagnostic ID copy-pasteable in bug reports regardless of which workspace was active when the error fired. |
| DEC-ERROR-INTERPRETER-003 | JSONL append with `fcntl.flock` rotation to most-recent 1000 lines | Worktree concurrency (CLAUDE.md "Worktrees Mean Concurrency") means two `ap` processes may interpret errors simultaneously. `fcntl.flock` on the log file makes append atomic. Line-count rotation (read-trim-write under lock) bounds disk use without external dependencies (logrotate / structlog handlers). 1000 entries ≈ ~500 KB ceiling. |
| DEC-ERROR-INTERPRETER-004 | 8-character lowercase hex diagnostic ID (`secrets.token_bytes(4).hex()`) | Short enough to copy-paste from a terminal without wrapping; long enough that collision in a 1000-line log is negligible (~1 in 2³². With 1000 entries, collision probability is ~1.2 × 10⁻⁷). |
| DEC-ERROR-INTERPRETER-005 | Auto-fix prompts limited to non-destructive operations behind explicit `[y/n]` confirmation | "Mechanically safe" means the operation either touches no user data (rerun `ap config setup`, sleep-and-retry on rate-limit) or restores from a known backup (`~/.ap/config.toml.bak` when present). Never auto-key-generate, never auto-delete, never auto-edit user files. Each AutoFix surfaces a label + description before the prompt so the user knows exactly what they're consenting to. |
| DEC-ERROR-INTERPRETER-006 | Renderer accepts `CharacterMode | None` for mode-flavored tone; `gamification/modes.py` is read-only consumed | The user's directive ("prompt the player") confirms the gamification framing. Mode-flavored panel titles serve that framing without coupling — passing `mode=None` (e.g., from smoke_test) yields neutral phrasing. No edits to `DEFAULT_MODES` or `CharacterMode` dataclass keep the modes authority unchanged. |
| DEC-ERROR-INTERPRETER-007 | Smoke test FAIL summary becomes `[CATEGORY] fix-suggestion (diag <id>)`; `--verbose` still appends full traceback | Concise mode tells the user what to do, not just what broke. `--verbose` retains today's traceback behavior for power-user / CI debugging. Signature of `_fmt_exc(exc, verbose)` is preserved so both call sites at `--quiet` and `--verbose` keep working. |
| DEC-ERROR-INTERPRETER-008 | Catalog v1 covers 8 known-issue patterns; unknown-fallback is mandatory | Initial coverage: missing API key, rate limit, network/connection-refused, network timeout, config TOML decode error, SQLite locked, LiteLLM/provider auth, and a mandatory unknown-fallback. The unknown-fallback must produce a friendly panel with a diagnostic ID even when no catalog entry matches — the contract is that **no Python traceback ever reaches the user without going through the interpreter**, including the case where the interpreter itself doesn't recognize the error. If the interpreter raises during interpretation, the renderer's outer-catch emits a canned "Something unexpected happened (diag &lt;id&gt;)" panel and writes a debug-log entry. |

### Work item

| ID | Title | Type | Worktree | Status |
|---|---|---|---|---|
| W-FRIENDLY-ERRORS | ErrorInterpreter: catch all errors, render friendly fix-suggestion, optional auto-apply | source + tests + evidence | `.worktrees/feature-friendly-errors` | in progress (planner complete; implementer next) |

**Implementer sub-task order** (one worktree, sequential — explicitly serial within this slice to avoid the parallel-mechanism trap):

1. WI-FE-1.1 — `core/error_interpreter.py`: dataclasses, `interpret()`, `_CATALOG` (8 entries), diagnostic-ID gen, debug-log JSONL append + flock rotation.
2. WI-FE-1.2 — `tests/test_error_interpreter.py`: 8 catalog entries, unknown fallback, diagnostic ID format, debug-log append + rotation, two-thread concurrency.
3. WI-FE-1.3 — Renderer (same module): `render_interactive()` + `render_summary_line()`; tests cover panel content, `[y/n/d]` prompt paths, mode-flavored title.
4. WI-FE-1.4 — Refactor `agent/error_handler.classify_error()` to delegate; preserve `FriendlyError` adapter; update existing `tests/test_error_handler.py` to assert delegation; add `@decision DEC-ERROR-INTERPRETER-001 (supersedes inline catalog)` annotation.
5. WI-FE-1.5 — Wire cmd2 console: override `APConsole.default_error`; replace bare `_execute_hunt` `except Exception` panel with interpreter call; extend `tests/test_console.py` with 3+ exception-injection cases asserting no `Traceback` in stdout.
6. WI-FE-1.6 — Migrate `agent/chat.py` meta-command sub-handlers to call `handle_error()`; add `tests/test_agent_chat.py` (new file — chat.py is currently only covered indirectly).
7. WI-FE-1.7 — `scripts/smoke_test.py::_fmt_exc` becomes a wrapper over `render_summary_line()`; extend `tests/test_smoke_test.py`.
8. WI-FE-1.8 — Live evidence captures in `tmp/evidence-friendly-errors/`: three transcripts (cmd2 corrupted config, chat no-provider, smoke invalid key) + a debug.log sample, all proven to contain zero `Traceback (most recent call last):` strings.
9. WI-FE-1.9 — Amend this MASTER_PLAN.md section with closeout merge SHA + evidence summary.

**Critical path:** strictly sequential 1.1 → 1.9 (each step depends on the registry built in 1.1).

### Evaluation Contract

Persisted in runtime via `cc-policy workflow work-item-set ... --evaluation-json` (9 legal keys per DEC-CLAUDEX-EVAL-CONTRACT-SCHEMA-PARITY-001). Authoritative copy lives in runtime; the canonical summary is:

- **Required tests:** 9 test scenarios spanning catalog entries, diagnostic-ID format, debug-log rotation + concurrency, renderer behavior, delegation invariant, cmd2 wiring, chat meta-command migration, smoke FAIL summary shape.
- **Required evidence:** 4 artifacts in `tmp/evidence-friendly-errors/` — three live-run transcripts + a debug-log sample, all proving zero `Traceback (most recent call last):` strings in user-facing stdout/stderr.
- **Required real-path checks:** `uv run pytest` (full suite, zero regression vs ~1497 baseline; expected delta +30 to +40 tests); `uv run ruff check` on all scope files; live cmd2 capture with corrupted config matching panel ↔ debug-log diagnostic ID.
- **Required authority invariants:** `core/error_interpreter.py` is sole catalog authority; `modules/base.py` exception types unchanged; `~/.ap/debug.log` is sole error-history authority; DEC-AGENT-ERROR-HANDLER-001 preserved; `core/error_interpreter.py` has no `litellm` dep.
- **Required integration points:** `agent/chat.py` line 693 call site unchanged; `APConsole` wires `default_error` hook; `_fmt_exc(exc, verbose)` signature preserved; `gamification/modes.py` read-only consumed.
- **Forbidden shortcuts:** no parallel catalog; no `litellm` import in `core/error_interpreter.py`; no silent exception swallowing (debug-log write failure → loud stderr fallback); no destructive auto-fix without `[y/n]`; no edits to `modules/base.py`; no parallel debug-log location; no raw `[red]Error: {e}[/red]` inside scope files.
- **Rollback boundary:** one merge revert restores prior behavior in full; no schema migrations; `~/.ap/debug.log` is purely additive (delete-to-rollback).
- **Ready-for-guardian:** pytest green + ruff green + 4 evidence artifacts present + MASTER_PLAN.md amended + reviewer `REVIEW_VERDICT=ready_for_guardian` on current HEAD.

### Scope Manifest

Persisted in runtime via `cc-policy workflow scope-sync` (work item + workflow rows, parity verified — `matches_work_item_scope: True`). Authoritative copy at `tmp/scope-w-friendly-errors.json`. Summary:

- **Allowed (12 paths):** the new `core/error_interpreter.py`, the three integration files (`core/console.py`, `agent/error_handler.py`, `agent/chat.py`), `scripts/smoke_test.py`, five test files, `tmp/evidence-friendly-errors/**`, and `MASTER_PLAN.md`.
- **Required (7 paths):** the new module, its test file, the three integration files, the smoke script, and `MASTER_PLAN.md`.
- **Forbidden (22 paths):** all `modules/**`, `models/**`, `gamification/**`, every other file in `core/` and `agent/`, `pyproject.toml`, `uv.lock`, `.github/**`, `.claude/**`, `DECISIONS.md`, `README.md`, `CLAUDE.md`, `AGENTS.md`.
- **State domains touched:** `error_classification_catalog` (new), `diagnostic_id_generation` (new), `debug_log_jsonl` (new), `friendly_panel_rendering` (extended), `cmd2_default_error_hook` (extended), `smoke_test_fail_summary` (extended).

---

## Phase 11: STIX 2.1 Spec Compliance + Per-SCO Provenance (W-59-STIX-PROVENANCE, post-v1, 2026-05-22)
**Status:** in-progress (planner stage complete, implementer next)
**Workflow id:** `w-59-stix-provenance` · **Goal id:** `g-59-stix-provenance` · **Work item id:** `wi-59-impl`
**Branch:** `feature/59-stix-provenance` · **Worktree:** `.worktrees/feature-59-stix-provenance` · **Base:** `main` @ `1ccf13b`
**Closes:** [GitHub issue #59](https://github.com/jarocki/ap/issues/59)

### User directive (verbatim, via Threat Hunter expert assessment 2026-05-22)

> "I cannot put this in an advisory. Until every result is timestamped + URL-attributed + content-hashed at the workspace layer, this is a research toy."

### Why this is a v1-hardening slice, not a v2 feature

`v0.1.0` ships with STIX 2.1 as the internal data model (ADR-005) but two real spec-compliance gaps that break the downstream-consumer story:

1. **`export_stix_bundle()` in `core/graph.py` (line 302) is not STIX 2.1 valid.** It synthesizes a random `bundle--<uuid4>` id and emits a plain dict `{type: "bundle", id, objects}` with no `spec_version` field on the objects. SCO objects in the bundle are reduced to `{type, id, value}` — missing `spec_version: "2.1"` (required for every STIX 2.1 SDO/SCO). The bundle will not round-trip through `stix2.parse()`.
2. **No provenance metadata on any SCO.** Modules produce raw SCO dicts (`{type, value, x_<vendor>_*}`), `dict_to_stix()` converts them into python-stix2 SCO objects (which DO carry deterministic content-based ids and `spec_version` thanks to the library), and `workspace.store_stix_objects()` serializes those to `stix_objects.json_blob`. But nothing records WHEN AP fetched the data, WHICH endpoint produced it, or the cryptographic hash of the raw vendor response. Downstream analysts and threat-hunter peers cannot audit the forensic chain.

This slice closes both gaps in one bounded change without rewriting any module. Module SCO production stays exactly the same; provenance is added post-hoc at the workspace storage layer (single-authority principle, CLAUDE.md §12).

### Code-as-truth audit (what already exists vs. what's missing)

| Surface | Today (post-v0.1.0) | Gap closed by this slice |
|---|---|---|
| `models/stix.py::dict_to_stix()` | Converts plain dicts into python-stix2 SCO objects with `allow_custom=True`; the resulting object already carries deterministic content-based `id` and `spec_version: "2.1"` (the library does this) | Preserved unchanged. The provenance fields are added at the storage layer, after this conversion — so the deterministic-id derivation continues to depend only on the SCO's defining-property values, not on provenance timestamps. |
| `core/workspace.py::store_stix_objects()` | Accepts `objects: list, module_name: str, target: str`. Serializes via `obj.serialize()` and stores `json_blob` keyed by `obj.id`. No provenance fields written. | Signature extended with four optional kwargs (`source_url=None`, `api_version=None`, `response_sha256=None`, `fetched_at=None`). When provided, augments the serialized `json_blob` with `x_ap_source_url`, `x_ap_api_version`, `x_ap_response_sha256`, and `x_ap_fetched_at`. `fetched_at` defaults to `datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")` when not passed. |
| `core/graph.py::export_stix_bundle()` | Returns plain dict `{type: "bundle", id: "bundle--<uuid4>", objects: [{type, id, value}, ...]}` with no `spec_version` on objects. Will not round-trip through `stix2.parse()`. | Rebuilt via `models/stix.py::create_bundle()` + the existing SCO creator helpers — reading the full `json_blob` from the workspace so provenance fields survive into the exported bundle. Returned object is still a plain dict (DEC-GRAPH-004 preserved via `.serialize()` round-trip), but it is now a `stix2.v21.Bundle`-equivalent dict that round-trips through `stix2.parse()`. |
| `tests/` | `test_workspace.py` covers store/retrieve/dedup; `test_graph.py` covers tree rendering and GEXF export. No round-trip test against python-stix2. | New `tests/test_stix_roundtrip.py` — bundle parses via `stix2.parse()` and yields a `stix2.v21.Bundle`; every SCO carries `id`, `spec_version: "2.1"`, `x_ap_fetched_at` (non-null), and pass-through provenance when supplied. Existing tests extended for the new kwargs. |
| Call sites for `store_stix_objects` (production) | `core/console.py:389` and `agent/tools.py:359` — both pass `results, module_name, target` and have no current way to surface vendor URL / API version / response hash | Both call sites updated to pass `None` for the four provenance kwargs (legacy modules don't surface this yet — surfacing through `hunt()` is a deliberate follow-up slice, see "Out-of-scope" below). This preserves the contract that the workspace is the single provenance authority and that legacy SCOs get null provenance rather than fabricated values. |

### Architecture

**Single new authority:** the `x_ap_*` provenance namespace inside `stix_objects.json_blob`, owned exclusively by `workspace.store_stix_objects()`. Modules MUST NOT emit `x_ap_*` fields. Tests assert this invariant.

**No schema migration.** `stix_objects.json_blob` is a `JSON` column (`models/database.py` line 73); the existing schema already accepts the augmented blob. Pre-existing rows (which lack `x_ap_*` fields) remain valid — the round-trip test treats `x_ap_fetched_at`-absent SCOs as a documented legacy state rather than a parse failure.

**Deterministic id mechanism:** Unchanged from current behavior. `stix2.IPv4Address(value=...)` already produces `ipv4-addr--<uuidv5(NAMESPACE_OASIS, canonical_serialization)>` via the python-stix2 library's STIX 2.1-compliant id derivation. We do NOT introduce a custom namespace UUID — the library's deterministic-id behavior is the authority (DEC-STIX-001). Critically, provenance fields are added to `json_blob` AFTER `.serialize()` so they do not feed back into id derivation. Same SCO content → same id, regardless of when it was fetched or from which endpoint. This is the property tests verify.

**Content-hash semantics for `x_ap_response_sha256`:** The hash is computed by the CALLER (the module producer or its call site) over the raw vendor response bytes, then passed to `store_stix_objects(..., response_sha256=...)`. The workspace does NOT recompute or canonicalize — it stores the hex string verbatim. This keeps the workspace stateless about response shape and lets future modules choose what "raw response" means for their wire format (JSON body, full HTTP response, etc.). Documented in DEC-59-STIX-PROVENANCE-003.

**Bundle export reconstruction strategy:** `export_stix_bundle()` rebuilds via two paths:
1. SCOs: round-trip each `json_blob` dict through `stix2.parse(blob, allow_custom=True)` to recover a typed stix2 object, then collect them.
2. Relationships: same approach using `Relationship` from the existing `models/stix.py` helpers.
3. Wrap the collection with `stix2.v21.Bundle(objects=[...])` and serialize back to dict via `json.loads(bundle.serialize())`.

This guarantees that whatever the workspace stored (provenance fields included) survives unchanged into the exported bundle, AND that the result parses via `stix2.parse()`.

**State-authority map:**

| State domain | Canonical authority | Notes |
|---|---|---|
| STIX SCO deterministic id derivation | `python-stix2` library (called via `models/stix.py::dict_to_stix()`) | Unchanged. The library is the spec-compliance authority (DEC-STIX-001). |
| STIX `spec_version` on every SCO | `python-stix2` library SCO classes (set automatically on construction) | Unchanged for SCO production; `export_stix_bundle()` newly relies on this property at export time. |
| Per-SCO provenance fields (`x_ap_*`) | `core/workspace.py::store_stix_objects()` | NEW. Sole authority. Augments `json_blob` after stix2 serialization. |
| Provenance default for `x_ap_fetched_at` | `core/workspace.py::store_stix_objects()` — `datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")` | NEW. Sole authority. Module-supplied `fetched_at` overrides the default. |
| Provenance pass-through (`x_ap_source_url`, `x_ap_api_version`, `x_ap_response_sha256`) | `core/workspace.py::store_stix_objects()` kwargs | NEW. Sole authority. Caller (console.py / agent/tools.py / direct tests) supplies; workspace stores verbatim. |
| STIX bundle construction | `core/graph.py::export_stix_bundle()` (via `stix2.v21.Bundle`) | Extended. Returns plain dict per DEC-GRAPH-004; the dict is now a parse-able STIX 2.1 bundle. |
| Bundle round-trip validation | `tests/test_stix_roundtrip.py` (new file) | NEW. Sole authority for the contract. |

**Removal targets (addition without subtraction is debt):**

- `core/graph.py::export_stix_bundle()` lines 314-340 — the hand-rolled `{type, id, value}` dict construction and the inline `uuid.uuid4()` bundle/relationship id generation. Replaced wholesale by the `stix2.v21.Bundle` round-trip path. No parallel mechanism remains.
- The unused `import uuid` inside `export_stix_bundle()` (line 314) — removed once the new path lands.

### Decisions (planner stage)

| Decision ID | Title | Rationale |
|---|---|---|
| DEC-59-STIX-PROVENANCE-001 | `workspace.store_stix_objects()` is the sole authority for the `x_ap_*` provenance namespace; modules MUST NOT emit `x_ap_*` fields | Single-source-of-truth (CLAUDE.md §12). If modules could also emit `x_ap_*`, two authorities would silently diverge: a module's `x_ap_source_url` could disagree with the workspace's record of WHO called the API. Tests assert that no production module sets `x_ap_*` fields in its `hunt()` output. The `x_ap_` prefix is reserved per STIX 2.1 custom-property naming convention (vendor-specific extensions) and is a deliberate AP-namespace choice. |
| DEC-59-STIX-PROVENANCE-002 | Provenance fields added to `json_blob` AFTER `obj.serialize()` so they do not feed back into deterministic-id derivation | The python-stix2 library derives SCO ids from a canonical content hash of the SCO's spec-defining properties (DEC-STIX-001). If provenance fields were included in that derivation, the same observable fetched at two different times would get two different ids, breaking deduplication (DEC-WS-004) and the cache-friendliness of the SCO model. Augmenting `json_blob` post-serialization keeps the id stable while preserving provenance for downstream consumers. |
| DEC-59-STIX-PROVENANCE-003 | `x_ap_response_sha256` is caller-supplied (stored verbatim); workspace does not recompute over response bodies | Different modules have different "raw response" shapes (REST JSON body, full HTTP response with headers, paginated batch). Standardizing the hash subject at the workspace layer would either be wrong for some modules or require module-specific canonicalization that the workspace shouldn't know about. The caller (module, call site, or test) computes `hashlib.sha256(raw_response_bytes).hexdigest()` and passes the hex string. Workspace stores it verbatim. Future contract: documented in module-author guide as a 64-char lowercase hex string when supplied. |
| DEC-59-STIX-PROVENANCE-004 | Legacy SCOs (no provenance kwargs supplied) get `x_ap_fetched_at` defaulted to storage-time UTC and `null` for the other three fields | Backward compatibility: the two existing production call sites (`core/console.py:389`, `agent/tools.py:359`) do not yet have a way to surface vendor URL / API version / response hash because module `hunt()` signatures don't return them. Rather than gating this slice on a module-author API rewrite (out-of-scope, larger surface), we accept null provenance as a documented degraded state. `x_ap_fetched_at` is always populated because the workspace knows storage time unambiguously — it's the only field that doesn't require module cooperation. Surfacing the other three through `hunt()` is a deliberate follow-up. |
| DEC-59-STIX-PROVENANCE-005 | `export_stix_bundle()` rebuilds via `stix2.v21.Bundle` + `stix2.parse()` round-trip, not by hand-rolled dict construction | Hand-rolled construction is what produced the spec-non-compliant bundle in the first place. Going through python-stix2 makes spec compliance automatic and lets the library catch any future regression at export time (it raises if a required field is missing). The plain-dict return shape (DEC-GRAPH-004) is preserved by `json.loads(bundle.serialize())`. The performance cost (one round-trip per export) is negligible for AP's typical bundle size (tens to hundreds of objects, DEC-GRAPH-001). |
| DEC-59-STIX-PROVENANCE-006 | No DB schema migration; `stix_objects.json_blob` accepts the augmented blob as-is | The column is already `JSON`-typed (`models/database.py:73`). Pre-existing rows remain valid (older SCOs lack `x_ap_*` fields, which the round-trip test handles via a documented legacy-state assertion). Adding columns for provenance would create dual authority (column AND blob), the exact anti-pattern §12 forbids. |
| DEC-59-STIX-PROVENANCE-007 | The `file` SCO type produced by `cti/virustotal.py` remains a silently-dropped path in this slice; documented as a known gap | `dict_to_stix()` returns the original dict for unrecognized types (DEC-STIX-002), and `store_stix_objects()` skips plain dicts (workspace.py line 281). `cti/virustotal` produces `file` SCOs when the target type is `"hash"` — those are currently dropped. Fixing this requires adding a `file` SCO creator to `_SCO_CREATORS` in `models/stix.py`, which expands scope to vendor-specific defining-properties decisions (hash algorithm choice, `hashes` dict shape). Out of scope for this slice; filed as a follow-up. The Evaluation Contract DOES require that the new round-trip test exercises only the SCO types that today's `_SCO_CREATORS` recognizes (`ipv4-addr`, `ipv6-addr`, `domain-name`, `url`, `email-addr`). |

### Work item

| ID | Title | Type | Worktree | Status |
|---|---|---|---|---|
| W-59-STIX-PROVENANCE | STIX 2.1 spec compliance + per-SCO provenance — workspace as single authority for `x_ap_*` fields; `export_stix_bundle` rebuilt via stix2 round-trip | source + tests | `.worktrees/feature-59-stix-provenance` | in progress (planner complete; implementer next) |

**Implementer sub-task order** (one worktree, sequential — explicitly serial to keep authority changes atomic):

1. WI-59-1.1 — `core/workspace.py::store_stix_objects()`: extend signature with `source_url=None, api_version=None, response_sha256=None, fetched_at=None` kwargs; add provenance-augmentation step that mutates the parsed `json_dict` before `StixObject(json_blob=json_dict)`. Default `fetched_at` to current UTC RFC3339 (`Z`-suffixed). `_store_sco` and `_store_relationship` receive the augmented dict.
2. WI-59-1.2 — `core/graph.py::export_stix_bundle()`: replace the hand-rolled construction with `stix2.parse()` round-trip per SCO/relationship + `stix2.v21.Bundle(objects=[...])`. Return `json.loads(bundle.serialize())`. Remove the inline `import uuid` and the synthetic `relationship--<uuid4>` / `bundle--<uuid4>` generation (the library handles bundle id and relationship ids carry through from `json_blob`).
3. WI-59-1.3 — `tests/test_stix_roundtrip.py` (NEW): build a workspace with mixed SCOs (`ipv4-addr`, `ipv6-addr`, `domain-name`, `url`, `email-addr`), some with full provenance kwargs and some without; call `export_stix_bundle()`; assert `stix2.parse(bundle, allow_custom=True)` returns a `stix2.v21.Bundle`; assert every SCO has `id`, `spec_version == "2.1"`, and non-null `x_ap_fetched_at`; assert pass-through provenance matches what was supplied; assert deterministic-id idempotency (same SCO stored twice → same id); assert content-hash pass-through (same `response_sha256` → same stored value).
4. WI-59-1.4 — Extend `tests/test_workspace.py` with: (a) provenance kwargs persist into `json_blob`, (b) `x_ap_fetched_at` always populated, (c) legacy call sites (no provenance kwargs) still work and produce `x_ap_fetched_at` only, (d) modules MUST NOT emit `x_ap_*` invariant (assert that direct-emission is detected — design: workspace logs or raises on caller-supplied dict that already contains `x_ap_*` keys; choose one in implementer stage and document as a follow-up `@decision`).
5. WI-59-1.5 — Extend `tests/test_graph.py`: `export_stix_bundle()` returns a parse-able dict; existing tree-rendering and GEXF tests must continue to pass (no regression).
6. WI-59-1.6 — Update production call sites in `core/console.py:389` and `agent/tools.py:359` to pass `None` for the four provenance kwargs explicitly (documents the legacy degraded state at the call site; future module-API change will populate them). No behavior change today; just makes the gap visible to future implementers.
7. WI-59-1.7 — Live evidence captures in `tmp/evidence-59-stix-provenance/`: (a) a workspace export saved as `bundle.json` and verified via `python -c "import stix2, json; print(type(stix2.parse(json.load(open('bundle.json')), allow_custom=True)))"` printing `<class 'stix2.v21.bundle.Bundle'>`; (b) a JSONL of three stored SCOs proving `x_ap_fetched_at` non-null and pass-through provenance present; (c) a transcript of `pytest tests/test_stix_roundtrip.py -v` green.
8. WI-59-1.8 — Close issue #59 with a comment linking the merge SHA and amend this MASTER_PLAN.md section with the closeout SHA + evidence summary.

**Critical path:** strictly sequential 1.1 → 1.8 (1.2 depends on 1.1's blob shape; 1.3-1.5 depend on 1.1+1.2 landing; 1.6 is a thin pass-through; 1.7-1.8 are closeout).

### Evaluation Contract

To be persisted in runtime via `cc-policy workflow work-item-set ... --evaluation-json` (9 legal keys per DEC-CLAUDEX-EVAL-CONTRACT-SCHEMA-PARITY-001). Authoritative copy summary:

- **Required tests (8 scenarios):**
  1. `tests/test_stix_roundtrip.py::test_bundle_parses_through_stix2_parse` — `stix2.parse(bundle, allow_custom=True)` returns `stix2.v21.Bundle`; `.objects` length matches stored SCO + relationship count.
  2. `tests/test_stix_roundtrip.py::test_every_sco_has_required_spec_fields` — every SCO in the parsed bundle has `id` matching `<type>--<uuid>`, `spec_version == "2.1"`, and non-null `x_ap_fetched_at`.
  3. `tests/test_stix_roundtrip.py::test_provenance_passthrough` — supplied `source_url`, `api_version`, `response_sha256` survive verbatim into the parsed bundle SCOs.
  4. `tests/test_stix_roundtrip.py::test_deterministic_id_independent_of_provenance` — same SCO content stored twice at different times → same id; provenance differs but `id`, `spec_version` unchanged (DEC-59-STIX-PROVENANCE-002 invariant).
  5. `tests/test_stix_roundtrip.py::test_legacy_call_no_provenance_kwargs` — store with no provenance kwargs, bundle still parses; `x_ap_fetched_at` populated by workspace default; other three fields absent from `json_blob` (or present as `null` — implementer chooses, must be consistent across the four).
  6. `tests/test_workspace.py::test_workspace_rejects_caller_supplied_x_ap_fields` — when caller-supplied SCO dict contains `x_ap_*`, workspace either raises or strips with a logged warning (DEC-59-STIX-PROVENANCE-001 invariant; behavior choice documented in implementer-stage `@decision`).
  7. `tests/test_graph.py::test_export_stix_bundle_is_spec_compliant` — `export_stix_bundle()` return value round-trips through `stix2.parse()`; existing tree/GEXF assertions continue to pass.
  8. `tests/test_workspace.py` + `tests/test_graph.py` baseline — full file passes with no regression in non-stix tests (deduplication, type filtering, GEXF export, tree rendering).
- **Required evidence (3 artifacts in `tmp/evidence-59-stix-provenance/`):**
  - `bundle.json` — a captured workspace export with at least one SCO of each recognized type, proving parse via the one-liner shown in WI-59-1.7.
  - `sco_provenance_sample.jsonl` — three stored SCOs serialized one per line, proving `x_ap_fetched_at` non-null and pass-through provenance present where supplied.
  - `pytest_roundtrip.txt` — `pytest tests/test_stix_roundtrip.py -v` transcript, green.
- **Required real-path checks:**
  - `uv run pytest tests/test_stix_roundtrip.py tests/test_workspace.py tests/test_graph.py -v` — green.
  - `uv run pytest` (full suite) — zero regression vs the ~1497-test post-Phase 10 baseline; expected delta +6 to +10 tests.
  - `uv run ruff check src/adversary_pursuit/core/workspace.py src/adversary_pursuit/core/graph.py src/adversary_pursuit/models/stix.py tests/test_stix_roundtrip.py` — clean.
  - `python -c "import stix2, json; bundle = json.load(open('tmp/evidence-59-stix-provenance/bundle.json')); parsed = stix2.parse(bundle, allow_custom=True); assert isinstance(parsed, stix2.v21.Bundle); print('OK', len(parsed.objects), 'objects')"` — prints `OK <n> objects`.
- **Required authority invariants:**
  - `workspace.store_stix_objects()` is the sole writer of `x_ap_*` fields (DEC-59-STIX-PROVENANCE-001).
  - Provenance fields are NOT part of deterministic-id derivation (DEC-59-STIX-PROVENANCE-002).
  - `export_stix_bundle()` returns a plain dict that parses through `stix2.parse()` (DEC-59-STIX-PROVENANCE-005 + DEC-GRAPH-004 preserved).
  - No DB schema change; `stix_objects.json_blob` shape stays JSON-typed (DEC-59-STIX-PROVENANCE-006).
  - No module under `src/adversary_pursuit/modules/**` is modified.
  - `models/stix.py::dict_to_stix()` and `_SCO_CREATORS` unchanged for `ipv4-addr`, `ipv6-addr`, `domain-name`, `url`, `email-addr` (DEC-STIX-001/002 preserved).
- **Required integration points:**
  - `core/console.py:389` updated to pass `None` for the four provenance kwargs (explicit-legacy marker; no behavior change).
  - `agent/tools.py:359` updated to pass `None` for the four provenance kwargs (explicit-legacy marker; no behavior change).
  - `models/database.py::StixObject` unchanged.
  - `dict_to_stix()` continues to be the path from plain dict → typed stix2 SCO.
- **Forbidden shortcuts:**
  - No edits to any file under `src/adversary_pursuit/modules/**`.
  - No edits to `models/database.py` (no schema change).
  - No parallel provenance authority (e.g., a separate `provenance` table or a separate `x_ap_*` writer outside `workspace.store_stix_objects()`).
  - No silent suppression of `stix2.exceptions.STIXError` during `export_stix_bundle()` — if a stored blob can't be parsed back, the test must surface it; runtime behavior is to raise.
  - No custom namespace UUID for SCO id derivation (let the python-stix2 library own this per DEC-STIX-001).
  - No hand-rolled bundle dict construction left behind in `core/graph.py`.
  - No fabricated provenance values (e.g., don't generate a fake `x_ap_source_url` when the caller passes `None` — leave it null/absent).
  - No edits to `pyproject.toml` or `uv.lock` (stix2 is already a dep).
- **Rollback boundary:** one merge revert restores prior behavior in full; no schema migrations; pre-existing `json_blob` rows remain valid both before and after this slice (the augmentation is additive, not transformative).
- **Ready-for-guardian:** pytest green (8 new tests pass; full suite no regression) + ruff green on scope files + 3 evidence artifacts present in `tmp/evidence-59-stix-provenance/` + MASTER_PLAN.md amended with closeout SHA + reviewer `REVIEW_VERDICT=ready_for_guardian` on current HEAD.

### Scope Manifest

To be persisted in runtime via `cc-policy workflow scope-sync w-59-stix-provenance --work-item-id wi-59-impl --scope-file tmp/scope-w-59-stix-provenance.json` (file already authored, this commit). Summary:

- **Allowed (11 paths):** `core/workspace.py`, `core/graph.py`, `core/console.py`, `agent/tools.py`, `models/stix.py`, three test files (`tests/test_stix_roundtrip.py` NEW, `tests/test_workspace.py`, `tests/test_graph.py`), `tmp/evidence-59-stix-provenance/**`, `tmp/scope-w-59-stix-provenance.json`, `MASTER_PLAN.md`.
- **Required (5 paths):** `core/workspace.py`, `core/graph.py`, `models/stix.py` (touch may be limited to a re-verification — see implementer-stage decision), `tests/test_stix_roundtrip.py`, `MASTER_PLAN.md`.
- **Forbidden (19 paths):** all `modules/**` (this is the issue's #1 invariant), `models/database.py`, all `gamification/**`, `agent/chat.py`, `agent/error_handler.py`, `core/error_interpreter.py`, `core/config.py`, `core/plugin_mgr.py`, `core/event_bus.py`, `core/scoring.py`, all `scripts/**`, `pyproject.toml`, `uv.lock`, `.github/**`, `.claude/**`, `DECISIONS.md`, `README.md`, `CLAUDE.md`, `AGENTS.md`.
- **State domains touched:** `stix_sco_provenance_augmentation` (new), `stix_bundle_export_construction` (extended — now goes through stix2 round-trip), `deterministic_stix_id_namespace` (verified-unchanged — library-owned), `stix_response_content_hash` (new — caller-supplied, workspace-stored).

### Out-of-scope (deliberately deferred)

- **Surfacing per-vendor URL / API version / response hash through the module `hunt()` signature.** This is the larger architectural change that would populate the four kwargs at the production call sites. Filed as a follow-up planner slice. Until then, the four kwargs are populated only by direct callers (tests, future migration helpers).
- **`file` SCO type round-trip.** The `cti/virustotal.py` hash path produces `file` SCOs that today are silently dropped by `dict_to_stix()` (DEC-STIX-002 fall-through). Closing this requires extending `_SCO_CREATORS` and making spec-compliance decisions about the `hashes` dict shape. Filed as a follow-up.
- **Backfilling provenance for SCOs already in production workspace files.** This slice changes write-path behavior only. A future "workspace migrate" command (out-of-scope) would walk existing `json_blob`s and stamp `x_ap_fetched_at = "unknown"` or similar for forensic-chain transparency.
- **Schema migration to dedicated provenance columns.** Per DEC-59-STIX-PROVENANCE-006, the JSON-column path is the v1-correct authority. A future schema-level provenance authority can be considered if cross-workspace provenance querying becomes a real workflow.

---

## Phase 12: Auto-Pivot Policy Engine — IOC filter + confidence gate + per-cascade budget + dry-run (W-60-AUTO-PIVOT-POLICY, post-v1, 2026-05-25)
**Status:** in-progress (planner stage complete, implementer next)
**Workflow id:** `w-60-auto-pivot-policy` · **Goal id:** `g-60-auto-pivot-policy` · **Work item id:** `wi-60-impl-01`
**Branch:** `feature/60-auto-pivot-policy` · **Worktree:** `.worktrees/feature-60-auto-pivot-policy` · **Base:** `main` @ `a797831`
**Closes:** [GitHub issue #60](https://github.com/jarocki/ap/issues/60)

### User directive (verbatim, via Threat Hunter P0 verdict 2026-05-23)

> "URLScan returning 15 CDN domains cascades 15 × (DNS + WHOIS + OTX) queries = quota bomb. Default config is hostile to anyone with a free-tier key. I cannot recommend AP until the cascade is throttled by quota-aware gates."

### Why this is a v1-hardening slice, not a v2 feature

`v0.1.0` shipped EventBus auto-pivot with a single safety gate (`PivotConfig.max_depth=2`, recursion depth only) and a per-module whitelist. Auto-pivot is opt-in (`autopivot on`), but once enabled the cascade is unconditional: every emitted SCO publishes to every subscribed callback. There is no IOC value filter (RFC1918 IPs, RFC6761 special-use names, and top-1k CDN domains all cascade identically to a high-signal IOC), no confidence gate (AbuseIPDB's `x_abuse_confidence_score` is ignored), and no quota budget (a single URLScan SCO with 15 child domain SCOs unconditionally fires 15 × N subscribed-module calls).

The Threat Hunter advisory blocks broader recommendation of AP until cascades are quota-aware. This slice closes that gap in one bounded change without modifying any module, without altering F59 provenance, and without touching the agent tool contract. The policy engine sits between EventBus.publish and the subscribed callback, as the SOLE gate authority. The pre-F60 `max_depth` recursion limit is removed (superseded by the per-cascade and per-session budgets — Sacred Practice 12, no parallel cascade-stopping authority).

### Code-as-truth audit (what already exists vs. what's missing)

| Surface | Today (post-v0.1.0, post-F59) | Gap closed by this slice |
|---|---|---|
| `core/event_bus.py::EventBus.publish` (line 82) | Gates only on `self.config.enabled` and `event.depth >= self.config.max_depth`. After those two checks, every subscribed callback fires unconditionally. | `publish` consults `self._policy.evaluate(event, callback_module)` as the SOLE gate authority before invoking the callback. The depth check is removed (DEC-60-PIVOT-POLICY-006). The disabled-flag short-circuit remains as the on/off switch. |
| `core/event_bus.py::PivotConfig` (line 39) | Dataclass with `enabled`, `max_depth=2`, `module_whitelist`. | `max_depth` field removed. `enabled` retained. `module_whitelist` retained (orthogonal authority — selects which modules can be candidates; pivot_policy is the value/confidence/budget authority). New field `policy: AutoPivotPolicyConfig` carries the policy configuration. |
| `core/pivot_policy.py` | Does not exist. | NEW. Owns the three-gate evaluation pipeline: ioc_value -> confidence -> budget, in that order. Returns a typed `PolicyDecision(verdict: Literal["allow","skip"], gate: str, reason: str)`. Stateless across calls except for the per-session budget counter (held on the EventBus instance and consulted via callback). |
| `core/config.py::GeneralConfig` (line 161) | Has `auto_pivot: bool = False` and `auto_pivot_depth: int = 2` (the latter is the source of `PivotConfig.max_depth`). | `auto_pivot` retained as the on/off switch. `auto_pivot_depth` retained but marked deprecated in the `@decision` annotation — informational only post-F60, no longer consulted. New submodel `AutoPivotPolicyConfig` added with: `confidence_threshold: int = 75`, `max_per_cascade: int = 5`, `max_per_session: int = 50`, `allowlist_path: str \| None = None` (defaults to `~/.ap/pivot-allowlist.txt`), `denylist_path: str \| None = None` (defaults to `~/.ap/pivot-denylist.txt`). |
| `src/adversary_pursuit/data/pivot_allowlist_top1k.txt` | Does not exist. | NEW. Bundled snapshot of Cloudflare Radar top-1k domains (snapshot date documented in the module docstring of `pivot_policy.py`). One domain per line, lowercase, ASCII (IDNA-canonicalized). Loaded once on `PivotPolicy.__init__` and cached. |
| User-supplied lists | None. | Optional `~/.ap/pivot-allowlist.txt` and `~/.ap/pivot-denylist.txt`. Newline-separated entries, blank/comment lines ignored. Missing file is silently treated as empty (no warning — the bundled defaults are the baseline). |
| `agent/tools.py::ToolContext.run_module` (line 376) | Calls `event_bus.process_results(results, source_module=module_path, depth=0)` after a successful hunt. Cascade results are aggregated into the tool payload. | Threads `options.get("dry_run", False)` from the tool invocation through to `process_results`. When dry-run, callbacks are NOT invoked; instead the policy's decision-log is surfaced on the tool payload as `decision_log: list[dict]`. |
| `tests/test_event_bus.py` | 27 tests covering pub/sub, depth limits, whitelist, `process_results`. | The depth-limit tests are rewritten to assert the depth gate is REMOVED. New tests added asserting `publish` consults `PivotPolicy.evaluate` as the sole gate authority. Existing pub/sub and history tests preserved. |

### Architecture

**Single new authority:** `core/pivot_policy.py::PivotPolicy.evaluate(event: PivotEvent, candidate_module: str) -> PolicyDecision` is the SOLE gate authority. `EventBus.publish` MUST call it before invoking any subscribed callback. No inline conditionals in `publish` other than (a) the `enabled` short-circuit, (b) the policy call, and (c) the verdict branch (allow → invoke; skip → log + record + skip).

**Three-gate ordering (strictly enforced):**
1. **`ioc_value` gate** — Evaluates the SCO value against the canonical filter stack:
   - **Static-deny** (RFC1918 `10/8`, `172.16/12`, `192.168/16`; loopback `127/8`; link-local `169.254/16`; IPv6 `::1`, `fe80::/10`; RFC6761 special-use names: `localhost`, `*.localhost`, `*.test`, `*.example`, `*.invalid`, `*.example.com`, `*.example.net`, `*.example.org`) — denied unless overridden by user-allowlist.
   - **User-deny** (`~/.ap/pivot-denylist.txt`) — overrides everything below it.
   - **User-allow** (`~/.ap/pivot-allowlist.txt`) — overrides static-deny and static-allow (top-1k).
   - **Static-allow** (bundled `pivot_allowlist_top1k.txt`) — denied as "very-popular, low-pivot-value" unless overridden by user-allow.
   - **Default** — allow. (Permissive fall-through is correct here: the ioc_value gate is a deny-list with a top-1k filter; routable, non-popular IOCs should reach the confidence gate.)
2. **`confidence` gate** — Evaluates `event.value`'s source SCO for `x_abuse_confidence_score`:
   - If present: `score >= policy.confidence_threshold` → pass; else skip with reason `"confidence_below_threshold"`.
   - If absent: per-SCO-type policy registry. Default `"optimistic"` for non-scoring SCO types (`url`, `domain-name`, `email-addr`, `ipv4-addr` from non-scoring modules, `ipv6-addr`). `"pessimistic"` only for SCO types where the vendor IS the scoring authority and absence means "no signal at all" — currently empty (AbuseIPDB emits zero-score SCOs explicitly, so a literal score of zero in the field triggers the below-threshold branch, NOT the missing-field branch). The registry is keyed on `(source_module, sco_type)` to avoid global decisions.
3. **`budget` gate** — Two counters consulted in order:
   - `per_cascade_count` (initialized at start of each `process_results` invocation, incremented per allow): `count < policy.max_per_cascade` → pass; else skip with reason `"per_cascade_budget_exhausted"`.
   - `per_session_count` (lives on EventBus; reset by `clear_history()`): `count < policy.max_per_session` → pass; else skip with reason `"per_session_budget_exhausted"`.

The first skip short-circuits and the decision carries the gate name verbatim. The `decision_log` records EVERY evaluation (pass or skip), which is what dry-run mode returns.

**Dry-run mode:** `EventBus.process_results(results, source_module, depth=0, dry_run=False)` and `EventBus.publish(event, dry_run=False)` accept a `dry_run` kwarg. When `True`, the policy is consulted and the decision log is built, but allowed callbacks are NOT invoked. The return value of `process_results(..., dry_run=True)` is the decision-log list rather than the aggregated callback results. Threaded through `agent/tools.py::ToolContext.run_module` via `options.get("dry_run", False)`.

**State-authority map:**

| State domain | Canonical authority | Notes |
|---|---|---|
| IOC value filter rules (static) | `core/pivot_policy.py::PivotPolicy._evaluate_ioc_value` | NEW. Sole authority for RFC1918/RFC6761/loopback/link-local detection and top-1k lookup. |
| Bundled top-1k allowlist | `src/adversary_pursuit/data/pivot_allowlist_top1k.txt` (Cloudflare Radar snapshot) | NEW. Sole bundled-data authority. Snapshot source URL and date documented in `pivot_policy.py` module docstring (DEC-60-PIVOT-POLICY-003). |
| User allow/deny lists | `~/.ap/pivot-allowlist.txt` / `~/.ap/pivot-denylist.txt`, parsed by `PivotPolicy._load_user_lists()` | NEW. Sole user-data authority. Missing files = empty (silent fall-through). |
| Confidence threshold | `GeneralConfig.auto_pivot_policy.confidence_threshold` | NEW config field. Default 75. Read once on `PivotPolicy.__init__`. |
| Confidence-missing per-SCO-type policy | `PivotPolicy._missing_confidence_policy` registry | NEW. Keyed on `(source_module, sco_type)`. Defaults to `"optimistic"`. Documented in DEC-60-PIVOT-POLICY-004. |
| Per-cascade budget | `process_results` local counter, incremented per allow within one invocation | NEW. Sole authority. Resets per `process_results` call (one source SCO = one cascade). |
| Per-session budget | `EventBus._policy_session_count` instance attribute, reset by `clear_history()` | NEW. Sole authority. Hunter / agent lifecycle calls `clear_history()` at hunt boundaries. |
| Dry-run mode propagation | `EventBus.publish(dry_run=...)` and `EventBus.process_results(dry_run=...)` | NEW. Sole authority. No global flag; explicit kwarg passed by callers. |
| EventBus cascade-stopping authority | `PivotPolicy.evaluate` (via the budget gate) | EXTENDED. The pre-F60 `max_depth` recursion limit is REMOVED — no parallel cascade-stopping authority remains (DEC-60-PIVOT-POLICY-006). |
| Module subscription whitelist | `PivotConfig.module_whitelist` (unchanged) | UNCHANGED. Orthogonal to pivot_policy — it controls which modules CAN be candidates; pivot_policy decides whether a candidate fires for a given event. |
| Auto-pivot on/off switch | `GeneralConfig.auto_pivot` + `PivotConfig.enabled` (kept in sync by `ToolContext.set_autopivot`) | UNCHANGED. The on/off short-circuit in `publish` runs BEFORE the policy. |

**Removal targets (addition without subtraction is debt):**

- `core/event_bus.py::PivotConfig.max_depth` field — removed entirely. No deprecation shim; the field has no other consumers (verified via grep).
- `core/event_bus.py::PivotEvent.depth` field — RETAINED. It is still useful as a diagnostic carried in the decision log ("this candidate was at depth N when the budget gate denied it"). But it is NO LONGER consulted by `publish` as a gating criterion.
- `core/event_bus.py::publish` lines 91-93 (the `event.depth >= self.config.max_depth` check) — removed.
- `core/config.py::GeneralConfig.auto_pivot_depth` field — retained for backward compatibility with v0.1.0 config.toml files in the wild, but marked deprecated in an `@decision` annotation and NOT consulted by any new code. Future `v2` work item filed to remove it after a documented migration window.

### Decisions (planner stage)

| Decision ID | Title | Rationale |
|---|---|---|
| DEC-60-PIVOT-POLICY-001 | `core/pivot_policy.py::PivotPolicy.evaluate` is the sole gate authority consulted by `EventBus.publish` before invoking any subscribed callback | Single-source-of-truth (CLAUDE.md §12). If gates lived inline in `publish` AND in a policy module, two authorities would silently diverge: a future implementer adding a new gate would have to remember to update both paths. The architecture rule (CLAUDE.md "Encode authority, don't imply it") is satisfied by a single explicit authority. Tests assert that `publish` contains no inline gate conditionals other than the `enabled` short-circuit and the policy call. |
| DEC-60-PIVOT-POLICY-002 | Three-gate ordering is strictly `ioc_value` -> `confidence` -> `budget`; first skip short-circuits and the decision carries the gate name verbatim | Ordering matters: the IOC-value filter is cheap and deterministic (no SCO fields needed beyond `type` and `value`), so it should run first to short-circuit obvious cases (RFC1918, RFC6761) without inspecting confidence or burning budget. The confidence gate is next because it depends only on the source SCO's fields, not on cascade state. The budget gate runs last because it has cross-event side effects (counters mutate) — running it earlier would charge budget for IOCs the IOC-value filter would have denied anyway. The fixed order is the contract; tests assert the ordering and verify each gate's name is recorded in the decision. |
| DEC-60-PIVOT-POLICY-003 | Bundled top-1k allowlist ships as `src/adversary_pursuit/data/pivot_allowlist_top1k.txt`; source is Cloudflare Radar top-1k (snapshot date documented in `pivot_policy.py` docstring); top-1k chosen over top-10k for bundle-size tradeoff | Bundled data over network fetch: determinism (offline-correct), no first-run network dependency, no rate-limit risk against Alexa/Cloudflare during testing, version-controlled (the snapshot is reviewable in git). Source choice: Cloudflare Radar publishes a free, CSV-style top-1k that's redistribution-friendly under their public dataset terms. Alexa's top-1k was retired in May 2022 — using a current and maintained source matters. Size choice: top-1k is ~25 KB packed; top-10k would be ~250 KB and would denylist many medium-popularity sites that DO have legitimate pivot value (e.g., niche threat-actor hosting on lesser-known CDNs). The snapshot is refreshed once per minor release via a separate maintenance slice (out-of-scope for F60). |
| DEC-60-PIVOT-POLICY-004 | Confidence-field-missing policy is per-SCO-type and defaults to optimistic (allow) for non-scoring SCO types; pessimistic only when the vendor IS the scoring authority and absence means "no signal" — currently NO SCO type meets that criterion, so the registry is empty in F60 | Pessimistic-default would break the URLScan -> DNS -> WHOIS chain entirely: URLScan emits `url` and `domain-name` SCOs that legitimately don't carry `x_abuse_confidence_score`, but those are exactly the SCOs we want to pivot from. The decision is to default to optimistic and document the empty pessimistic-registry as a deliberate F60 state — when a future module emits SCOs whose semantics require pessimistic treatment, the registry receives a (`module`, `sco_type`) entry in that slice. AbuseIPDB explicitly emits zero-score SCOs (a literal `x_abuse_confidence_score: 0`), so its low-confidence IPs hit the `confidence_below_threshold` branch via the present-but-low path, NOT the missing-field branch. Tests cover both paths. |
| DEC-60-PIVOT-POLICY-005 | Dry-run mode is a kwarg on `EventBus.publish` and `EventBus.process_results`, threaded through `agent/tools.py::ToolContext.run_module` via `options.get("dry_run", False)`; the returned decision log is a list of typed dicts with `source_sco_id`, `source_sco_value`, `candidate_module`, `gate`, `verdict`, `reason`, `depth` keys | Explicit-kwarg threading over global flag: tests can run dry and non-dry side-by-side; agents that want to "preview" don't have to mutate global state. The decision-log shape is the contract — six required keys, no implementer freedom — so downstream consumers (the agent surfacing dry-run results to the LLM, future Rich-table renderers, future audit logs) have a stable structure. Recorded via a small TypedDict in `pivot_policy.py` so that future schema changes are detectable. |
| DEC-60-PIVOT-POLICY-006 | The pre-F60 `PivotConfig.max_depth=2` recursion limit is REMOVED — superseded by per-cascade and per-session budgets; no parallel cascade-stopping authority remains | Sacred Practice 12 (CLAUDE.md): "I'll add the new way but keep the old way as a fallback" creates dual-authority bugs. The per-cascade and per-session budgets subsume max-depth: a deep recursion will run out of session budget long before it becomes pathological. Keeping max-depth as a fallback would mean a future cascade could be stopped by max-depth without the decision log recording a budget-gate skip — invisible to users debugging "why didn't this pivot?". Removing the field is the unified-implementation answer (CLAUDE.md §12, addition-without-subtraction). `GeneralConfig.auto_pivot_depth` is retained on the config schema for backward TOML compatibility but is no longer consulted; flagged for removal in a future slice. |
| DEC-60-PIVOT-POLICY-007 | User allow/deny list precedence is `user_deny > user_allow > static_deny > static_allow_top1k > default_allow`; missing user files are silent fall-through (no warning) | The user's explicit deny must always win — if an analyst puts `cloudflare.com` in their personal denylist, they want that respected even though it's in the bundled top-1k. The user's explicit allow must override the bundled static-deny — so an analyst investigating an internal subdomain that happens to be top-1k OR a deliberate test of RFC1918 traffic can put the host in their allowlist and pivot. The static-deny (RFC1918/RFC6761) sits above static-allow because RFC-reserved space is by definition non-routable and shouldn't be pivoted on accidentally, but a user can still override via allowlist. Silent fall-through on missing files matches the design intent that the bundled defaults are the baseline; a missing user file is the normal case, not an error. |

### Work item

| ID | Title | Type | Worktree | Status |
|---|---|---|---|---|
| W-60-AUTO-PIVOT-POLICY | Auto-pivot policy engine — `pivot_policy.py` as sole gate authority; three-gate ordering; remove `max_depth`; dry-run mode; F59 provenance preserved | source + tests | `.worktrees/feature-60-auto-pivot-policy` | in progress (planner complete; implementer next) |

**Implementer sub-task order** (one worktree, sequential — explicit serial to keep authority changes atomic):

1. WI-60-1.1 — `core/config.py`: add `AutoPivotPolicyConfig` Pydantic submodel with five fields (`confidence_threshold=75`, `max_per_cascade=5`, `max_per_session=50`, `allowlist_path=None`, `denylist_path=None`); add `GeneralConfig.auto_pivot_policy: AutoPivotPolicyConfig = Field(default_factory=AutoPivotPolicyConfig)`. Mark `auto_pivot_depth` as deprecated via `@decision` annotation. Extend `tests/test_config.py` for round-trip and default-value coverage.
2. WI-60-1.2 — `src/adversary_pursuit/data/pivot_allowlist_top1k.txt` (NEW): bundled Cloudflare Radar top-1k snapshot; one lowercase ASCII domain per line; module docstring of `pivot_policy.py` records source URL, snapshot date, and SHA-256 of the file. Add `src/adversary_pursuit/data/__init__.py` if needed for packaging.
3. WI-60-1.3 — `src/adversary_pursuit/core/pivot_policy.py` (NEW): `PolicyDecision` dataclass (`verdict`, `gate`, `reason`, optional `depth`); `PivotPolicy` class with `__init__(policy_config: AutoPivotPolicyConfig)`, `_load_static_rules`, `_load_user_lists`, `_evaluate_ioc_value`, `_evaluate_confidence`, `evaluate(event, candidate_module, *, sco_attrs, per_cascade_count, per_session_count) -> PolicyDecision`. Confidence-missing registry exposed as `_missing_confidence_policy: dict[tuple[str, str], Literal["optimistic","pessimistic"]]`, initialized empty.
4. WI-60-1.4 — `src/adversary_pursuit/core/event_bus.py`: remove `PivotConfig.max_depth` field and the depth check in `publish`; add `PivotConfig.policy: AutoPivotPolicyConfig | None = None`; add `EventBus._policy: PivotPolicy` (constructed from policy_config on init); add `_policy_session_count: int = 0` instance attribute reset by `clear_history`; extend `publish(event, *, dry_run=False, _per_cascade_count_ref=None)` and `process_results(..., *, dry_run=False)` signatures; on each callback iteration consult `self._policy.evaluate(...)` and dispatch accordingly. Update `register_module_subscriptions` only to the extent the dataclass change requires.
5. WI-60-1.5 — `src/adversary_pursuit/agent/tools.py`: thread `options.get("dry_run", False)` from `run_module` into `process_results`; surface the returned `decision_log` on the tool payload as a new top-level `decision_log` key when dry-run; ensure `cascade_results`/`cascade_count` are `[]`/`0` in dry-run. Update `ToolContext.__init__` to pass `GeneralConfig.auto_pivot_policy` from `config_mgr.load().general` into `PivotConfig(enabled=False, policy=...)`.
6. WI-60-1.6 — `tests/test_pivot_policy.py` (NEW): 28 unit tests per the Evaluation Contract — RFC1918, RFC6761, loopback, link-local, user lists, confidence thresholds, missing-field optimistic, missing-field pessimistic registry empty-state, budget exhaustion, budget reset, dry-run, decision-log shape, gate ordering, allowlist-file-missing fall-through.
7. WI-60-1.7 — `tests/test_pivot_policy_integration.py` (NEW): 5 integration tests that reconstruct the URLScan-fronted quota-bomb scenario end-to-end with mocked module callbacks. Asserts: (a) default config caps to ≤ `max_per_cascade` callbacks per source SCO; (b) total cascade ≤ `max_per_session`; (c) chain URLScan -> DNS -> WHOIS respects per-session budget across depth; (d) dry-run produces the full decision log with zero callback invocations; (e) pre-F60 baseline (simulated by disabling all gates) would have fired 45 callbacks — the post-F60 default fires ≤ 50 across the entire hunt.
8. WI-60-1.8 — `tests/test_event_bus.py`: rewrite the depth-limit tests to assert `max_depth` is gone (PivotConfig has no such field; `publish` no longer gates on depth); add tests that `publish` consults `PivotPolicy.evaluate`; keep pub/sub, history, and whitelist tests green. Extend `tests/test_agent_tools.py` to verify the dry-run path threads through and `decision_log` surfaces on the tool payload.
9. WI-60-1.9 — Live evidence captures in `tmp/evidence-60-auto-pivot-policy/`: (a) `pytest_pivot_policy.txt` from `pytest tests/test_pivot_policy.py tests/test_pivot_policy_integration.py tests/test_event_bus.py -v`; (b) `decision_log_15_cdn_domains.json` captured from the integration test showing each of the 15 candidate pivots with its gate verdict and reason; (c) `quota_bomb_before_after.txt` counting callback invocations pre-F60 vs post-F60; (d) `ruff_clean.txt`; (e) `full_suite.txt`.
10. WI-60-1.10 — Close issue #60 with a comment linking the merge SHA, and amend this MASTER_PLAN.md section with the closeout SHA + evidence summary.

**Critical path:** strictly sequential 1.1 → 1.10. 1.4 depends on 1.1 (config submodel) and 1.3 (policy class). 1.5 depends on 1.4 (process_results signature). 1.6 depends on 1.3. 1.7 depends on 1.4+1.5. 1.8 depends on 1.4. 1.9 depends on 1.6-1.8 landing. 1.10 is closeout.

### Evaluation Contract

Persisted in runtime via `cc-policy workflow work-item-set w-60-auto-pivot-policy g-60-auto-pivot-policy wi-60-impl-01 --evaluation-json "$(cat tmp/f60-evaluation.json)"` (9 legal keys per DEC-CLAUDEX-EVAL-CONTRACT-SCHEMA-PARITY-001). Authoritative summary:

- **Required tests (39 scenarios):** see `tmp/f60-evaluation.json` for the full list. Spans `tests/test_pivot_policy.py` (28 unit tests covering each gate, each rule, ordering, dry-run, decision-log shape), `tests/test_pivot_policy_integration.py` (5 quota-bomb scenarios), `tests/test_event_bus.py` (4 tests asserting depth gate removed and policy is sole authority), `tests/test_config.py` (2 tests for the new submodel).
- **Required evidence (5 artifacts in `tmp/evidence-60-auto-pivot-policy/`):** `pytest_pivot_policy.txt`, `decision_log_15_cdn_domains.json`, `quota_bomb_before_after.txt`, `ruff_clean.txt`, `full_suite.txt`.
- **Required real-path checks:** scoped pytest green, full suite green, ruff clean on scope files, two `python -c` one-liners proving RFC1918 and top-1k denial paths return the expected `PolicyDecision`.
- **Required authority invariants:** `PivotPolicy.evaluate` is the sole gate (DEC-60-001); three-gate ordering strict (DEC-60-002); `max_depth` removed (DEC-60-006); bundled allowlist is the sole top-1k authority (DEC-60-003); per-SCO-type missing-confidence policy registry (DEC-60-004); per-session budget reset semantics owned by `clear_history`; `AutoPivotPolicyConfig` submodel is the runtime read source; F59 provenance preserved (no edits to workspace.py); dry-run thread-through unchanged for module.hunt path.
- **Required integration points:** `publish` calls `_policy.evaluate` per callback; `process_results` forwards `dry_run`; `ToolContext.run_module` threads `options.get("dry_run")` and surfaces `decision_log`; `_make_cascade_callback` unchanged; F59 `workspace.store_stix_objects` unchanged.
- **Forbidden shortcuts:** no env-var bypass; no silent fall-back on skip (every skip logged); no inline gates in `publish`; no module-side self-throttling; no swallowing of gate decisions in scoring/badges; no edits to `modules/**`, `workspace.py`, `models/`, `pyproject.toml`, `uv.lock`; no network fetch at import; no DateTime-based snapshot read every call; no retention of `max_depth` as a fallback; no allow/deny path leakage into log messages.
- **Rollback boundary:** single revertable merge commit on `feature/60-auto-pivot-policy`. Restores `max_depth=2` behavior and removes `pivot_policy.py` + bundled data file. `auto_pivot` boolean (pre-F60) retained. Post-F60 config.toml files with `[general.auto_pivot_policy]` section round-trip cleanly through a reverted parser because Pydantic ignores unknown top-level fields on the GeneralConfig submodel boundary.
- **Acceptance notes:** F59 provenance preserved; F4 atomic token consumption and F2 CAN_COMMIT_FEATURE_BRANCH unchanged. The integration test concretely demonstrates the URLScan quota-bomb scenario is solved: 15 CDN domains yield ≤ `max_per_cascade` (5) callback invocations per source SCO and ≤ `max_per_session` (50) total. The decision-log artifact records, for each of the 15 candidates, which gate denied it.
- **Ready-for-guardian:** all 39 pytest tests green, full suite green with zero regressions vs the post-F59 baseline, ruff clean on scope files, all 5 evidence artifacts present, MASTER_PLAN.md amended with closeout SHA, reviewer `REVIEW_VERDICT=ready_for_guardian` on current HEAD, scope compliance verified (no files outside Allowed in the diff), single-authority confirmed by grep (PivotPolicy.evaluate is the only place that returns a gate verdict).

### Scope Manifest

Persisted in runtime via `cc-policy workflow scope-sync w-60-auto-pivot-policy --work-item-id wi-60-impl-01 --scope-file tmp/f60-scope.json` (file authored in this commit). Summary:

- **Allowed (15 paths):** `core/event_bus.py`, `core/pivot_policy.py` (NEW), `core/config.py`, `data/pivot_allowlist_top1k.txt` (NEW), `data/__init__.py`, `agent/tools.py`, `agent/chat.py`, three new+extended test files (`tests/test_pivot_policy.py` NEW, `tests/test_pivot_policy_integration.py` NEW, `tests/test_event_bus.py` extended), `tests/test_config.py` extended, `tests/test_agent_tools.py` extended, `tmp/evidence-60-auto-pivot-policy/**`, `tmp/f60-scope.json`, `tmp/f60-evaluation.json`, `MASTER_PLAN.md`.
- **Required (7 paths):** `core/event_bus.py`, `core/pivot_policy.py`, `core/config.py`, `data/pivot_allowlist_top1k.txt`, `tests/test_pivot_policy.py`, `tests/test_pivot_policy_integration.py`, `MASTER_PLAN.md`.
- **Forbidden (19 paths):** all `modules/**` (preserves no-module-edit invariant), `models/database.py`, `models/stix.py`, all `gamification/**`, `core/workspace.py` (preserves F59), `core/console.py`, `core/graph.py`, `core/report.py`, `core/error_interpreter.py`, `core/plugin_mgr.py`, `agent/error_handler.py`, `pyproject.toml`, `uv.lock`, `.github/**`, `.claude/**`, `README.md`, `CLAUDE.md`, `AGENTS.md`, `DECISIONS.md`.
- **State domains touched:** `auto_pivot_policy_gate` (new), `auto_pivot_ioc_value_filter` (new), `auto_pivot_confidence_threshold` (new), `auto_pivot_per_cascade_budget` (new), `auto_pivot_per_session_budget` (new), `auto_pivot_dry_run_decision_log` (new), `auto_pivot_bundled_allowlist` (new), `auto_pivot_user_allow_deny_lists` (new).

### Out-of-scope (deliberately deferred)

- **Removing the deprecated `GeneralConfig.auto_pivot_depth` field.** Retained in F60 for backward TOML compatibility with v0.1.0 config files; marked deprecated via `@decision`. A future slice (after one minor-release migration window) removes it.
- **Allowlist/denylist snapshot refresh tooling.** The bundled top-1k is a static snapshot; a `scripts/refresh_pivot_allowlist.py` maintenance script that fetches the current Cloudflare Radar dump is filed as a follow-up. F60 ships with whatever snapshot is committed at merge time.
- **Rich-table dry-run renderer in the CLI / agent chat.** F60 surfaces the structured `decision_log` on the tool payload; presentation is a follow-up UX slice.
- **Per-module confidence threshold overrides.** F60 uses a single global `confidence_threshold` (default 75). Allowing per-module thresholds (e.g., "OTX = 50, AbuseIPDB = 75, GreyNoise = 80") is a downstream config-schema enrichment. Filed as a follow-up.
- **Allowlist source pluralization.** Today the static-allow source is Cloudflare Radar top-1k. Supporting multiple sources (Tranco list, Majestic Million, etc.) is a downstream enrichment. Filed as a follow-up.
- **Cross-session persistent quota counters.** The per-session budget resets per `Hunter.hunt()` call. Persistent daily/weekly quota across sessions (tracked in workspace SQLite) is a v2-grade feature filed as a follow-up.

---

## Runtime Hygiene Backlog

Cross-cutting runtime issues surfaced during recent dispatch chains. Tracked as GitHub issues (not v1 plan slices) — they affect orchestrator/Guardian quality of life but not the AP product surface:

- **#49** — `cc-policy test-state` should reconcile worktree↔main-repo paths on Guardian preflight (currently a path-shape mismatch can wedge readiness).
- **#50** — lease op vocabulary classifies straightforward FF push as `high_risk` (should be `routine` post-evaluation).
- **#51** — worktree `.venv` lacks the `[agent]` extra; full `pytest` collection fails on agent-dependent test modules.

Fix order is opportunistic — whoever hits one first files the slice. Not blocking on v1.

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

**All v1 boundary work items have landed (closed 2026-05-18).** The table below preserves the traceability ledger; no rows remain open.

| ID | Title | Type | Merge SHA | Status |
|----|-------|------|-----------|--------|
| W-V1-RELEASE-VERIFY | Verify the GitHub-Releases distribution path for #24 — cut `v0.1.0rc1`, run `release.yml`, install wheel in fresh venv with `[agent]` extras, confirm 11 entry-points + `ap chat` work, finalize README install block | release / docs / ops | `cd3709a` (closeout 2026-05-18; tag `v0.1.0rc1` SHA `d392deb`) | completed |
| W-OTX-TIMEOUT | cti/otx `httpx.ReadTimeout` on high-cardinality IPs — add `TIMEOUT` option + timeout-stub SCO mirroring URLScan pattern | source + tests | `b877574` (merge) / `72fd3eb` (impl) | completed |
| W-GREYNOISE | Add `osint/greynoise` (Community API IP reputation) as the 11th catalog module — per 2026-05-16 user directive, pre-v1 catalog top-off | source + tests + docs | `6884317` | completed |
| W-V1-FINAL-SHIP | Promote `v0.1.0rc1` to stable `v0.1.0`: update pyproject.toml + uv.lock + README, force-replace the stale v0.1.0 GitHub Release (2026-05-02, pre-rc1 commit `1debf76`) with the rc1-verified stable release, amend MASTER_PLAN.md closeout | release / docs / ops | `e8e9b13` (prep commit, 2026-05-19; tag object SHA `e669b5d`) | completed |

### Post-v1 user-driven work items

| ID | Title | Type | Merge SHA | Status |
|----|-------|------|-----------|--------|
| W-FRIENDLY-ERRORS | Universal `core/error_interpreter.py` — catches all errors at the cmd2 + ap chat + smoke_test surfaces, renders friendly Rich panels with fix-suggestions + 8-char diagnostic IDs, offers `[y/n]` auto-fix prompts on mechanically safe fixes (rerun `ap config setup`, restore `~/.ap/config.toml.bak`, sleep-and-retry on rate-limit), preserves full tracebacks in `~/.ap/debug.log` (JSONL, fcntl-locked, 1000-line rotated). Per 2026-05-14 user directive. See "Phase 10" section above. | source + tests + evidence | `1ccf13b` (impl) | completed |
| W-59-STIX-PROVENANCE | STIX 2.1 spec compliance + per-SCO provenance — workspace single authority for `x_ap_*` fields (`x_ap_fetched_at`, `x_ap_source_url`, `x_ap_api_version`, `x_ap_response_sha256`); `export_stix_bundle()` rebuilt via `stix2.v21.Bundle` round-trip. Closes issue #59. Per 2026-05-22 Threat Hunter expert assessment. See "Phase 11" section above. | source + tests + evidence | _pending implementer_ | in-progress |

> **Recommended next work item:** `W-59-STIX-PROVENANCE` — planner stage complete (this commit). Scope manifest authored at `tmp/scope-w-59-stix-provenance.json` (implementer will `cc-policy workflow scope-sync` it), evaluation contract written (9 keys, 8 required tests, 3 required evidence artifacts, 7 architecture decisions DEC-59-STIX-PROVENANCE-001..007). Implementer next; canonical chain continues `planner → guardian (provision) → implementer → reviewer → guardian (land)`.
>
> _Historical note (2026-05-19):_ v1 ship gate fully closed — `v0.1.0` (stable, no rc suffix) published at https://github.com/jarocki/ap/releases/tag/v0.1.0 with `isPrerelease: false`. All four v1 boundary work items landed (`W-V1-RELEASE-VERIFY`, `W-OTX-TIMEOUT`, `W-GREYNOISE`, `W-V1-FINAL-SHIP`).
>
> Non-blocking ops/hygiene work remains as an opportunistic backlog under "Runtime Hygiene Backlog" above (GitHub issues #35, #37, #40, #42, #49, #50, #51, #52, #53, #54, #55). Those affect orchestrator/Guardian quality of life, not the AP product surface; they will be filed and landed through the canonical planner chain as discrete slices when prioritized.
>
> The previously listed `W-SCOPE-25` is retired by ADR-010. The previously listed `W-COVERAGE-METRIC` (cosmetic `@decision` ratio) is deferred — it is not a v1 release blocker and was always optional. `W-V1-PYPI-VERIFY` is retired by the 2026-05-03 GitHub-Releases pivot (`02fed4d`).

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
Phase 5 (Polish):        #21 -> #22 -> #23 -> #24                   [done — W-V1-RELEASE-VERIFY landed cd3709a (v0.1.0rc1, 2026-05-18); W-V1-FINAL-SHIP stable v0.1.0 published 2026-05-19 at e8e9b13]
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
- *MLP Status (Phase 6 closeout, 2026-05-01):* MLP threshold crossed. `ap chat` provides 10 modules, full gamification (scoring + celebrations + badges + modes + hints), auto-pivot, challenges, graph/export, and reports — exceeds the revised MLP.
- *Post-MLP Status (reconciled 2026-05-19, v1 stable shipped):* Phase 7 (post-Phase-6 CTI pipeline + TUI polish, ~12 commits) landed organically. Phase 8 closed with `W-OTX-TIMEOUT` landing (`b877574`). Phase 9 closed with `W-GREYNOISE` landing (`6884317` — 11th module). Phase 5 closed with `W-V1-RELEASE-VERIFY` landing (`cd3709a` — `v0.1.0rc1` published, install path verified end-to-end) and `W-V1-FINAL-SHIP` landing (`e8e9b13` — stable `v0.1.0` published 2026-05-19, `isPrerelease: false`). The v1 ship gate is fully closed: `v0.1.0` is the stable public release. All four v1 boundary work items have landed. Future work is user-determined post-v1.

The previous "Start with #1 (scaffolding) immediately" instruction is retired — Phase 1-9 are landed. There are no open v1 plan slices. Next direction is user-determined (cut final `v0.1.0` tag, begin v2 planning, address the runtime-hygiene backlog opportunistically).

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
