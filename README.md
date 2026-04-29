# Adversary Pursuit

> "Taking maximum advantage of every mistake, and celebrating with epic memes."

Gamified framework for hunting, pivoting, and discovery of adversary infrastructure, indicators, and TTPs. Combines the tactical depth of professional CTI tools with the engagement of competitive gaming.

## Features

- **10 OSINT/CTI Modules** — Shodan, VirusTotal, AbuseIPDB, HIBP, OTX, URLScan, Censys, PassiveTotal, DNS, WHOIS
- **Conversational AI Interface** — Chat with an LLM-powered analyst (`ap chat`)
- **Classic CLI** — Metasploit-style REPL (`ap`)
- **STIX 2.1 Data Model** — Industry-standard threat intel storage with deduplication
- **Gamification** — Parabolic decay scoring, challenges, badges, celebrations
- **10 Character Modes** — Ninja, Full Troll, Drunken Master, Sun Tzu, Chuck Norris, Bureaucrat, Bobby Hill, Bruce Lee, Columbo
- **Workspace Isolation** — Per-investigation SQLite databases
- **Graph Visualization** — STIX relationship trees with GEXF export
- **Report Generation** — Interview-based investigation reports
- **Auto-Pivoting** — Event bus for cascading OSINT discovery
- **Hint System** — Free and paid hints with balance protection

## Quick Start

```bash
pip install adversary-pursuit

# Classic CLI
ap

# Chat interface (requires litellm)
pip install 'adversary-pursuit[agent]'
ap chat
```

## Classic CLI Usage

```
[main] ap> workspace create investigation-1
[main] ap> workspace switch investigation-1
[main] ap> use osint/shodan_ip
[module] ap(osint/shodan_ip)> set TARGET 185.220.101.1
[module] ap(osint/shodan_ip)> run

  ╔══════════════════════════╗
  ║  🔥 EXCELLENT WORK! 🔥  ║
  ╚══════════════════════════╝

+300 points!
  new_ip: +100 (185.220.101.1)
  new_domain: +100 (tor-exit.example.com)
  new_ip: +100 (2001:db8::1)

[module] ap(osint/shodan_ip)> score
Total Score: 300 pts

[module] ap(osint/shodan_ip)> back
[main] ap> mode drunken_master
🍺 *hiccup* Oh hey... we doing this? Let's goooo...
```

## Chat Interface

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
```

## Modules

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
```

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

## Development

```bash
git clone https://github.com/jarocki/ap.git
cd ap
uv sync
uv run pytest -v    # 800+ tests
uv run ap           # Launch CLI
```

## Architecture

- **Modules** → PursuitModule Protocol with `async def hunt()` returning STIX 2.1 dicts
- **Storage** → SQLite per-workspace with STIX JSON blobs + deduplication
- **Scoring** → CTFd parabolic decay formula: `value = ((min - init) / decay²) × count² + init`
- **Agent** → litellm + OpenAI function-calling format, wrapping all modules as tools
- **Event Bus** → SpiderFoot-pattern pub/sub for auto-pivoting with depth limits

## License

MIT
