# Adversary Pursuit

> "Taking maximum advantage of every mistake, and celebrating with epic memes."

Gamified framework for hunting, pivoting, and discovery of adversary infrastructure, indicators, and TTPs. Combines the tactical depth of professional CTI tools with the engagement of competitive gaming.

The **v1 primary interface is `ap chat`** — a conversational AI agent powered by litellm that discovers and invokes OSINT/CTI modules as tools, gathers STIX 2.1 evidence, and surfaces gamification events (scores, celebrations, badges, hints) in the conversation. The classic `ap` Metasploit-style REPL ships alongside as a supporting power-user surface (per ADR-010).

## Features

- **11 OSINT/CTI Modules** — Shodan, VirusTotal, AbuseIPDB, HIBP, OTX, URLScan, Censys, PassiveTotal, GreyNoise, DNS, WHOIS
- **21 LLM Tools** — All modules plus gamification, reports, graph, and workspace exposed to the agent
- **Conversational AI Interface** — Chat with an LLM-powered analyst (`ap chat`)
- **Classic CLI** — Metasploit-style REPL (`ap`) as a power-user surface
- **STIX 2.1 Data Model** — Industry-standard threat intel storage with deduplication
- **Gamification** — Parabolic decay scoring, challenges, badges, celebrations
- **10 Character Modes** — Ninja, Full Troll, Drunken Master, Sun Tzu, Chuck Norris, Bureaucrat, Bobby Hill, Bruce Lee, Columbo, Default
- **Workspace Isolation** — Per-investigation SQLite databases
- **Graph Visualization** — STIX relationship trees with GEXF and STIX bundle export
- **Report Generation** — Interview-based investigation reports
- **Auto-Pivoting** — Event bus for cascading OSINT discovery
- **Hint System** — Free and paid hints with balance protection

## Installation

### Install from GitHub Releases (recommended)

```bash
# Latest pre-release (replace <VERSION> with the actual release version, e.g., 0.1.0rc1)
pip install "https://github.com/jarocki/ap/releases/download/v<VERSION>/adversary_pursuit-<VERSION>-py3-none-any.whl[agent]"
```

The `[agent]` extras include `prompt-toolkit`, `litellm`, and other dependencies needed for the conversational `ap chat` interface. Omit `[agent]` if you only need the cmd2 REPL (`ap`).

### Install from source (development)

```bash
git clone https://github.com/jarocki/ap.git
cd ap
uv sync --extra agent
uv run ap --help
```

### Configuration

Create `~/.ap/config.toml` and add your API keys under `[api_keys]`, OR set environment variables like `AP_SHODAN_API_KEY`, `AP_VIRUSTOTAL_API_KEY`, etc. Run `ap config setup` for the interactive wizard.

## Quick Start

```bash
# Primary interface: conversational agent (requires litellm extras)
ap chat

# Classic REPL (power users)
ap
```

### Choose an LLM backend

On first run of `ap chat`, the agent runs an interactive setup wizard that:

1. Prompts you to pick a provider from a curated list (Anthropic, OpenAI, OpenRouter, Google, Ollama)
2. Prompts for an API key (skipped for Ollama since it's local)
3. Calls the provider's list-models endpoint to fetch available models
4. Lets you select one
5. Asks where to save your credentials — three options:
   1. `~/.ap/config.toml` only (default — used by `ap chat`)
   2. `~/.ap/config.toml` + append `export …_API_KEY=...` lines to your shell rc (`~/.zshrc` / `~/.bashrc` / `~/.config/fish/config.fish`, auto-detected via `$SHELL`)
   3. Print export lines to stdout so you can paste them anywhere

Re-running the wizard with option 2 replaces the existing export block rather than duplicating it (idempotent marker comment). Unknown shells fall back to option 3 with a warning.

**CTI service credentials:**

After the LLM provider step, the wizard offers to also configure CTI service credentials:

```
Configure CTI service credentials too? (y/N)
```

If you answer `y`, the wizard walks through all 8 supported services. Each is optional — you can skip any service and configure it later. For each service, the wizard:

1. Shows the documentation URL where you obtain an API key
2. Prompts for credentials (input is masked, not echoed)
3. Makes a single validation call to prove the key works before saving
4. Saves to `~/.ap/config.toml` with the same 0600 permissions

**Supported CTI services:**

| Service | Credential | Env var |
|---------|------------|---------|
| Shodan | API Key | `SHODAN_API_KEY` |
| VirusTotal | API Key | `VIRUSTOTAL_API_KEY` |
| AbuseIPDB | API Key | `ABUSEIPDB_API_KEY` |
| HaveIBeenPwned | API Key | `HIBP_API_KEY` |
| AlienVault OTX | API Key | `OTX_API_KEY` |
| URLScan | API Key | `URLSCAN_API_KEY` |
| Censys (Platform PAT) | Personal Access Token | `CENSYS_PAT` |
| PassiveTotal / RiskIQ | Username + API Key | `PT_USERNAME`, `PT_API_KEY` |

CTI keys also support the same 3-layer precedence chain as LLM keys:
`~/.ap/config.toml` > `AP_<SERVICE>_KEY` env > `<SERVICE>_KEY` env.

Subsequent `ap chat` launches use the saved config — no prompts.

**Reconfigure during a session:**

```
ap> model show       # display current provider, model, and source layer
ap> model select     # re-run the wizard
```

**Precedence (highest → lowest):**

1. Explicit `model=` argument to `AgentRunner` (programmatic use)
2. `AP_MODEL` env var (CI / scripted overrides)
3. `~/.ap/config.toml` (set by the wizard)
4. Built-in default (`ollama/qwen2.5:8b`)

**Skip the wizard via env var (CI/dev override):**

```bash
export AP_MODEL=anthropic/claude-3-5-sonnet-20241022
export ANTHROPIC_API_KEY=sk-ant-...
uv run ap chat   # bypasses wizard, uses env vars
```

See [litellm provider docs](https://docs.litellm.ai/docs/providers) for the full
list of supported model strings.

## API Keys

Configure API keys for any LLM provider or CTI service via three methods (highest precedence first):

1. **`~/.ap/config.toml`** (set by `model select` wizard or hand-edited):
   ```toml
   [api_keys]
   agent_anthropic = "sk-ant-..."
   shodan = "..."
   abuseipdb = "..."
   ```
2. **`AP_<SERVICE>_API_KEY`** env vars (project-namespaced, for per-session override without touching config):
   ```bash
   export AP_SHODAN_API_KEY=...
   ```
3. **`<SERVICE>_API_KEY`** env vars (vendor convention — works out of the box if you already have these set):
   ```bash
   export SHODAN_API_KEY=...
   export ANTHROPIC_API_KEY=...
   ```

| Service | config.toml field | AP env var | Vendor env var |
|---|---|---|---|
| Anthropic | `agent_anthropic` | `AP_ANTHROPIC_API_KEY` | `ANTHROPIC_API_KEY` |
| OpenAI | `agent_openai` | `AP_OPENAI_API_KEY` | `OPENAI_API_KEY` |
| OpenRouter | `agent_openrouter` | `AP_OPENROUTER_API_KEY` | `OPENROUTER_API_KEY` |
| Google | `agent_google` | `AP_GOOGLE_API_KEY` | `GOOGLE_API_KEY` |
| Shodan | `shodan` | `AP_SHODAN_API_KEY` | `SHODAN_API_KEY` |
| VirusTotal | `virustotal` | `AP_VIRUSTOTAL_API_KEY` | `VIRUSTOTAL_API_KEY` |
| AbuseIPDB | `abuseipdb` | `AP_ABUSEIPDB_API_KEY` | `ABUSEIPDB_API_KEY` |
| HIBP | `hibp` | `AP_HIBP_API_KEY` | `HIBP_API_KEY` |
| OTX | `otx` | `AP_OTX_API_KEY` | `OTX_API_KEY` |
| URLScan | `urlscan` | `AP_URLSCAN_API_KEY` | `URLSCAN_API_KEY` |
| Censys (ID) | `censys_id` | `AP_CENSYS_ID` | `CENSYS_API_ID` |
| Censys (Secret) | `censys_secret` | `AP_CENSYS_SECRET` | `CENSYS_API_SECRET` |
| PassiveTotal (user) | `passivetotal_user` | `AP_PASSIVETOTAL_USER` | `PT_USERNAME` |
| PassiveTotal (key) | `passivetotal_key` | `AP_PASSIVETOTAL_KEY` | `PT_API_KEY` |

DNS resolve and WHOIS lookup require no API key.

## Chat Interface (Primary v1 Interface)

`ap chat` is the v1 entry point. The LLM agent selects and invokes modules as tools, narrates findings, and emits gamification events as part of the conversation.

```
$ ap chat
╭─────────────────────────────────────────────╮
│ Adversary Pursuit v2 — Conversational CTI   │
╰─────────────────────────────────────────────╯

ap> What can you tell me about 185.220.101.1?

[Calling: check_ip_reputation, shodan_host_lookup, otx_threat_intel]

This IP is a known Tor exit node (AS24940, Hetzner Online GmbH).
AbuseIPDB gives it a 97% abuse confidence score with 1,247 reports.
Shodan shows ports 22, 80, 443, 9001 open. OTX has it in 14 threat
pulses tagged "tor-exit", "scanning", "brute-force".

+400 points!

╔═══════════════════════════╗
║  EXCELLENT WORK!          ║
╚═══════════════════════════╝
```

### Chat Meta-Commands

These are handled locally (not sent to the LLM) for immediate, deterministic behavior. They share the same session state as LLM tools, so workspace and mode changes are reflected in both paths.

| Command | Description |
|---------|-------------|
| `workspace <name>` | Switch to a named workspace (creates if missing) |
| `mode` or `mode list` | List all available character modes with the active one marked |
| `mode <name>` | Switch character mode; updates LLM system prompt immediately |
| `hint` | Get the next free general hint |
| `hint <module>` | Get the next free hint for a specific module (e.g. `hint abuseipdb`) |
| `hint buy` | Buy the next paid hint (costs score points) |
| `hint buy <module>` | Buy the next paid module-specific hint |
| `autopivot` | Show current auto-pivot state |
| `autopivot on` | Enable EventBus cascading (auto-runs subscribed modules on discoveries) |
| `autopivot off` | Disable EventBus cascading |
| `challenges` | List all active/completed challenges in a Rich table |
| `graph` | Render workspace STIX relationship tree |
| `export gexf` | Print GEXF 1.2 XML to terminal (importable into Gephi) |
| `export stix` | Print STIX 2.1 bundle JSON to terminal |
| `report` | Show interview status (auto-starts interview if not started) |
| `report answer <N> <text>` | Record answer for question index N (0–4) |
| `report generate` | Generate and display the Markdown investigation report |
| `quit` / `exit` | Exit the chat session |

## Agent LLM Tools

The agent exposes 21 tools to the LLM in OpenAI function-calling format. The LLM selects and chains tools automatically based on the analyst's natural-language query.

### Module Tools (10)

These wrap the underlying PursuitModule catalog. All module tools store results in the workspace, apply scoring, check badges, and check challenges automatically.

| Tool | Module | Description | Required Parameters |
|------|--------|-------------|---------------------|
| `dns_resolve` | `osint/dns_resolve` | DNS resolution for A, AAAA, MX, NS, TXT records | `domain` |
| `whois_lookup` | `osint/whois_lookup` | WHOIS registration details for domain or IP | `target` |
| `check_ip_reputation` | `osint/abuseipdb` | AbuseIPDB v2 abuse confidence score, ISP, report count | `ip_address` |
| `shodan_host_lookup` | `osint/shodan_ip` | Open ports, services, CVEs, OS fingerprint via Shodan | `ip_address` |
| `check_breaches` | `osint/hibp` | HaveIBeenPwned breach check for an email address | `email` |
| `otx_threat_intel` | `cti/otx` | AlienVault OTX pulse data, reputation, passive DNS | `target` |
| `scan_url` | `osint/urlscan` | URLScan.io async submit+poll, page details, screenshot URL | `url` |
| `virustotal_lookup` | `cti/virustotal` | VirusTotal v3 multi-scanner verdicts (IP/domain/URL/hash) | `target` |
| `censys_host_lookup` | `osint/censys_host` | Censys services, certificates, OS, geolocation for an IP | `ip_address` |
| `passivetotal_lookup` | `cti/passivetotal` | PassiveTotal passive DNS history and WHOIS for domain/IP | `target` |

Optional parameters: `dns_resolve` accepts `record_type` (default `A`); `check_ip_reputation` accepts `max_age_days` (default 90); `shodan_host_lookup` accepts `minify` (default false); `otx_threat_intel` accepts `include_passive_dns` (default true); `scan_url` accepts `visibility` (default `unlisted`); `virustotal_lookup` accepts `target_type` to override auto-detection; `passivetotal_lookup` accepts `include_whois` (default true).

### Gamification Tools (4)

| Tool | Description | Parameters |
|------|-------------|------------|
| `list_challenges` | List all challenges with status (active/completed/expired) | none |
| `check_challenges` | Check current workspace against active challenge requirements; returns newly-completed challenges | none |
| `get_next_hint` | Get the next free contextual hint; optionally filtered to a module | `module` (optional) |
| `buy_hint` | Buy the next paid hint (deducts score points); optionally filtered to a module | `module` (optional) |

Hint balance protection: `buy_hint` will not deduct points if the resulting score would go negative (returns an error string instead).

### Report Tools (3)

| Tool | Description | Parameters |
|------|-------------|------------|
| `start_report_interview` | Initialize (or reset) the interview; returns all 5 questions | none |
| `answer_report_question` | Record the analyst's answer for one question | `question_index` (0–4), `answer` |
| `generate_report` | Generate the Markdown report from workspace data + interview answers | none |

The LLM can drive the report interview multi-turn: call `start_report_interview`, present each question, call `answer_report_question` per answer, then call `generate_report`.

### Graph / Export Tools (2)

| Tool | Description | Parameters |
|------|-------------|------------|
| `render_graph` | Render STIX relationship tree as plain text | none |
| `export_workspace` | Export workspace as GEXF 1.2 XML or STIX 2.1 bundle JSON | `format` (`gexf` or `stix`) |

### Workspace Tools (2)

| Tool | Description | Parameters |
|------|-------------|------------|
| `get_workspace_summary` | Total indicators, type counts, module runs, score, recent activity | none |
| `search_workspace` | Search STIX objects by type (ipv4-addr, domain-name, url, email-addr) | `type_filter` (optional) |

## Character Modes and Personas

Character modes shape the LLM's voice (via a persona injected into the system prompt) and the score-celebration text displayed after each tool execution. Modes are shared between the chat interface and the cmd2 REPL.

### Persona-Prompt Protocol

`CharacterMode.personality` is a one-line descriptor displayed in mode lists. The full persona is applied when `AgentRunner.set_character(mode)` is called (from the `mode <name>` chat meta-command or `do_mode` in the cmd2 REPL). The mode's `personality` text is prepended to the LLM's default system prompt so the voice shifts immediately without clearing conversation history.

Each mode also carries:
- `prompt_prefix` — emoji prepended to the input prompt
- `greeting` — message displayed when mode is activated
- `score_celebration` — template string using `{points}` placeholder for per-tool score lines

### Available Modes

| Mode | Prompt | Personality |
|------|--------|-------------|
| `default` | (none) | Standard analyst mode |
| `ninja` | 🥷 | Minimal output, speed bonuses, stealth tips |
| `full_troll` | 🤡 | Maximum memes, taunt messages |
| `drunken_master` | 🍺 | Random pivot suggestions, chaos mode |
| `sun_tzu` | 📜 | Strategic quotes, methodical approach rewards |
| `chuck_norris` | 💪 | Overpowered hints, confidence boosters |
| `bureaucrat` | 📋 | Office Space vibes, TPS report formatting |
| `bobby_hill` | 😤 | "That's my purse!" energy |
| `bruce_lee` | 🐉 | Flow state, combo multipliers |
| `columbo` | 🔍 | "Just one more thing..." investigative prompts |

Switch modes in chat with `mode ninja` or list with `mode`.

## Classic CLI (Power-User Surface)

The `ap` cmd2 REPL provides direct, deterministic `use → set → run` access to individual modules. It is the "manual transmission" alternative for power users who want explicit control, scripted workflows, or one-shot module runs.

```
[main] ap> workspace create investigation-1
[main] ap> workspace switch investigation-1
[main] ap> use osint/shodan_ip
[module] ap(osint/shodan_ip)> set TARGET 185.220.101.1
[module] ap(osint/shodan_ip)> run

  ╔══════════════════════════╗
  ║  EXCELLENT WORK!         ║
  ╚══════════════════════════╝

+300 points!

[module] ap(osint/shodan_ip)> score
Total Score: 300 pts

[module] ap(osint/shodan_ip)> back
[main] ap> mode drunken_master
*hiccup* Oh hey... we doing this? Let's goooo...
```

## Modules

Both interfaces share the same module catalog:

| Module | Source | What it does |
|--------|--------|-------------|
| `osint/dns_resolve` | stdlib | DNS resolution (A, AAAA, MX, NS, TXT) |
| `osint/whois_lookup` | stdlib | WHOIS registration details |
| `osint/abuseipdb` | AbuseIPDB v2 | IP abuse reputation scoring |
| `osint/shodan_ip` | Shodan | Open ports, services, CVEs, hostnames |
| `osint/hibp` | HIBP v3 | Email breach checking |
| `osint/urlscan` | URLScan.io | URL analysis with async submit+poll |
| `osint/censys_host` | Censys v2 | Host certificates and services |
| `cti/virustotal` | VirusTotal v3 | Multi-scanner verdicts (IP/domain/URL/hash) |
| `cti/otx` | AlienVault OTX | Threat intel pulses + passive DNS |
| `cti/passivetotal` | PassiveTotal | Passive DNS + WHOIS history |

## Configuration

```bash
# Set API keys via CLI
ap config set api_keys.shodan YOUR_KEY

# Or via environment variables
export AP_SHODAN_API_KEY=YOUR_KEY
export AP_VT_API_KEY=YOUR_KEY
export AP_ABUSEIPDB_API_KEY=YOUR_KEY

# Censys requires both an API ID and secret
ap config set api_keys.censys_id YOUR_ID
ap config set api_keys.censys_secret YOUR_SECRET

# PassiveTotal requires user email and API key
ap config set api_keys.passivetotal_user YOUR_EMAIL
ap config set api_keys.passivetotal_key YOUR_KEY
```

Config is stored in `~/.ap/config.toml`. Workspaces live in `~/.ap/workspaces/`.

## Writing Plugins

Implement the `PursuitModule` protocol:

```python
from adversary_pursuit.modules.base import BaseModule

class MyModule(BaseModule):
    name = "osint/my_module"
    description = "My custom OSINT module"
    author = "Your Name"
    module_type = "osint"

    def __init__(self):
        super().__init__()
        self.options = {
            "TARGET": {"required": True, "description": "Target to query", "default": ""},
        }

    async def hunt(self, target, options):
        # Query your API, return STIX-formatted dicts
        return [{"type": "ipv4-addr", "value": "1.2.3.4", "x_custom_field": "data"}]
```

Register in your `pyproject.toml`:

```toml
[project.entry-points."adversary_pursuit.modules"]
my_module = "my_package.my_module:MyModule"
```

Plugins installed via pip are discovered automatically at startup. The agent will expose them as tools if the module path is added to `_MODULE_MAP` in `agent/tools.py`.

## Development

```bash
git clone https://github.com/jarocki/ap.git
cd ap
uv sync
uv run pytest -v    # 1094+ tests
uv run ap chat      # Launch agent
uv run ap           # Launch classic REPL
```

## Architecture

- **Modules** — PursuitModule Protocol with `async def hunt()` returning STIX 2.1 dicts
- **Storage** — SQLite per-workspace with STIX JSON blobs + deduplication
- **Scoring** — CTFd parabolic decay formula: `value = ((min - init) / decay²) × count² + init`
- **Agent** — litellm + OpenAI function-calling format; 21 tools wrapping all modules and gamification primitives (ADR-010: primary v1 interface)
- **cmd2 REPL** — Metasploit-style REPL; supporting power-user surface (ADR-010)
- **Event Bus** — SpiderFoot-pattern pub/sub for auto-pivoting with depth limits (disabled by default; enable via `autopivot on`)
- **Gamification** — Scoring, celebrations, badges, hints, challenges, and character modes shared across both interfaces

ADR-010: The agentic AI chat (`ap chat`, litellm-driven) is the v1 primary user-facing interface. The cmd2 REPL (`ap`) ships as a supporting power-user surface. Both layers share the same module catalog, workspace authority, scoring engine, and gamification primitives.

## Smoke testing

A "dummy-user" smoke script exercises every CTI module against real APIs and verifies workspace persistence. It reads keys from `~/.ap/config.toml` and environment variables — no secrets are hardcoded or committed to the repo.

```bash
# Run against real APIs (keys read from ~/.ap/config.toml + env)
uv run python scripts/smoke_test.py

# Summary only — suppress per-module output
uv run python scripts/smoke_test.py --quiet

# Override the default IP target (8.8.8.8)
uv run python scripts/smoke_test.py --target 1.1.1.1

# Full tracebacks on failure
uv run python scripts/smoke_test.py --verbose
```

Modules whose API keys are not configured are reported as `SKIP` (not `FAIL`). Exit code is `0` when all tests pass or skip, `1` if any test fails. The script also runs a workspace persistence regression check that reproduces and verifies the fix for the SQLAlchemy `UnboundExecutionError` (DEC-WS-006).

Key sources (in precedence order):
1. `~/.ap/config.toml` under `[api_keys]`
2. `AP_*` environment variables (project-namespaced, e.g. `AP_SHODAN_API_KEY`)
3. Vendor-convention env vars (e.g. `SHODAN_API_KEY`, `OTX_API_KEY`, `PT_USERNAME`)

## What's Next

Phase 1–6 of the v1 plan are complete. Distribution is via GitHub Releases — push a `v*.*.*` tag to trigger the release workflow, which builds wheel + sdist and attaches them as release assets automatically.

## License

MIT
