# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.4.5] — 2026-07-21

### Added

- Complete interactive TUI session history with no hidden 5,000-line render
  boundary.
- Local `find <text>`, `open <ev-id>`, and `back` transcript navigation with
  stable evidence anchors and exact return positioning.
- Startup loading of the canonical persisted dossier snapshot and production
  lifecycle wiring for slot-transition events.
- Viewport-derived PageUp/PageDown behavior and regression coverage for complete
  history, transcript search, dossier initialization, mouse dragging, and
  laptop-safe navigation.

### Changed

- Page navigation moves one rendered viewport minus a context row and clamps to
  real transcript bounds.
- Returning to live output clears unread telemetry without deleting history.
- TUI help and README now document evidence drill-down and transcript search.

## [0.4.4] — 2026-07-21

### Added

- Persistent attention records for discoveries, corroboration, contradictions,
  dossier transitions, source faults, and operator actions.
- Master Caution queue with unread count, highest severity, origin navigation,
  evidence detail actions, and non-destructive acknowledgement.
- TUI unread-attention telemetry while an analyst reviews older history.

### Changed

- Source faults and contradictions now receive theme-independent semantic
  styling rather than relying on character color alone.
- Returning the terminal feed to live position clears its unread indicator
  without removing any historical event.

## [0.4.3] — 2026-07-21

### Added

- Stable compact evidence references and a credential-safe detail projection
  with normalized fields, provenance, explicit unavailable values, and safe raw
  records.
- History-aware Pivotglass evidence drawers and selectable artifact cards.
- TUI `open ev-…` drill-down rendered entirely from stored workspace evidence.
- Tests for reference stability, redaction, missing provenance, web projection,
  and terminal detail rendering.

### Changed

- Web state now exposes compact evidence cards rather than raw workspace
  records.
- New terminal evidence cards show actionable detail references when tools
  store artifacts.

## [0.4.2] — 2026-07-21

### Added

- A shared, UI-neutral investigation lifecycle with stable IDs, timestamps,
  resumable cursors, per-probe states, cancellation acknowledgement, and
  incremental event delivery.
- Live elapsed-time feedback and incremental probe/evidence cards in
  Pivotglass.
- Focused lifecycle, cursor, cancellation, and truthful-instrumentation tests.
- The approved v0.4.2 through v0.5.0 QA/UX release plan.

### Changed

- Pivotglass now starts investigations asynchronously and polls an authoritative
  event stream rather than waiting on one opaque synchronous request.
- Approximate reactor, probe, token, and hull meters now report measured state
  or explicitly say that a measurement is unavailable or not engaged.

## [0.4.1] — 2026-07-21

### Changed
- **Character-driven Pivotglass cockpit and true TUI scrolling**: the local web
  cockpit now consumes the canonical 14-mode theme and cockpit authorities,
  adds mode-aware voice, navigation, help, operational meters, dossier cells,
  alerts, animation, and active system telemetry. The terminal intelligence
  feed now uses a real prompt-toolkit viewport with a visible draggable
  scrollbar, pointer wheel support, and PageUp/PageDown navigation.
- **Deterministic TUI mode controls**: `mode` and `mode list` now show the same
  local character catalogue every time, selected modes are acknowledged by
  their exact name, unknown modes receive one stable error with valid choices,
  and local state-changing commands are serialized to prevent rapid-input
  races. Mode catalogue completion and the in-deck help expose the command.
- **Pivotglass web cockpit is now primary**: bare `ap` serves a static
  React/Next.js cockpit on loopback; `ap web` is explicit, `ap chat` / `ap tui`
  retain the terminal cyberdeck, and `ap basic` / `ap repl` retain direct
  control. Microsoft Flint compiles the first evidence-distribution
  visualization. The browser layer calls existing Python authorities rather
  than duplicating investigation logic.
- **Verifiable web supply chain**: exact npm versions and SHA-512 lockfile
  integrity are committed; registry signature/provenance verification and a
  zero-moderate-vulnerability audit are release gates. Runtime assets are local
  and the server binds to `127.0.0.1` with a restrictive CSP and no telemetry.
- **Enrichment briefings teach while services respond**: every deterministic
  enrichment probe now explains which artifacts its source is gathering, why
  they matter, and what the analyst should watch for. Cards remain explicitly
  prospective until results arrive, preserving the boundary between analytical
  guidance and observed evidence.
- **No direct DNS from the operator host**: removed the `dns_resolve` module,
  plugin entry point, agent tool, auto-pivot subscription, and battery dispatch.
  Domain enrichment now routes through explicit intelligence-service APIs such
  as PassiveTotal, VirusTotal, URLScan, OTX, and Censys. WHOIS no longer falls
  back to `socket.getaddrinfo`. The active catalog is 14 modules / 29 tools.
- **Living, voiced cyberdeck**: mode changes now update the LLM persona as well
  as the palette. Active work has a real spinner, laptop-friendly
  keyboard-independent feed navigation, stronger persona/world identity, and
  visible probe/evidence/provenance
  cards. Hunt synthesis now surfaces a concise character-voiced analyst
  intuition and clearly labels evidence, inference, uncertainty, and next pivot.
- **Mode-specific cockpit HUDs**: all 14 modes now select distinct vehicle/deck
  vocabulary and perspective rails. The six-row tactical HUD reports real
  target lock, classification, active probe, queue depth, dossier progress,
  feed position, and active/standby state. Trackpad/wheel scrolling and
  universal `[`/`]` feed keys replace reliance on Mac-intercepted modifiers.
- **Documentation reset**: replaced the legacy feature inventory with an
  operator-facing README that documents the AI-first launch contract, cyberdeck
  layout, deterministic evidence flow, current commands, 15-module catalog,
  configuration, architecture, personas, and project governance. Historical
  roadmap language is now explicitly subordinate to the current implementation
  checkpoint.
- **AI-first launch + storyboard deck hierarchy**: bare `ap` now opens the
  AI-augmented cyberdeck; the classic Metasploit-like console remains available
  as `ap basic` and `ap repl` (`ap chat` remains compatible). The full-screen
  interface now follows the storyboard hierarchy with explicit intelligence,
  command-deck, and multi-color analyst-instrument regions.

### Fixed
- **Repository hygiene sweep**: reconciled GitHub issues with shipped code and
  retired the obsolete Claude-harness backlog (31 issues closed). Fixed the
  remaining small Slice 4/6L/7Ah2 follow-ups: current-turn-only error fallback,
  literal HTTP 400 regression coverage, escaped `show <field>` Rich markup,
  accurate error-catalog numbering and color docstrings, honest structural-label
  documentation, and restored bold classic-console prompts.
- **Cyber-deck recovery**: the full-screen TUI no longer runs LLM/network work on
  the terminal render thread. The interface remains responsive during hunts and
  `stop` / `focus` / `add` / `skip` can execute while work is active. Restored
  contextual Tab completion, persistent history suggestions, configured vi/emacs
  editing, bounded transcript rendering, PageUp/PageDown navigation, and a themed
  command prompt. Redraws are capped at 2 Hz to prevent long sessions from becoming
  progressively slower.
- **Flow-state interface pass**: tool and runner failures now appear inside the
  intelligence feed as recovery cards with a direct next action and compact
  diagnostic reference; detailed logs remain automatic and out of the normal
  workflow. Added an instant `?` overlay help deck, a framed intelligence viewport,
  and a high-contrast animated command marker so the input locus is unmistakable.
- **Trinity mode**: added a Matrix-operator persona with a White Rabbit (`🐇`)
  prompt identity and matrix-green deck theme. Replaced the generic "Intelligence
  Feed" label with live, mode-specific adversary-hunting and pursuit titles.
- **Persona preservation + world titles**: restored Drunken Master as a selectable,
  visibly deprecated classic; the earlier removal confused deprecation with deletion.
  Mode viewport names now describe each character's world (`THE MATRIX`, `THE SPRAWL`,
  `DEEP SPACE`, `THE ARENA`, and others) rather than repeating “Pursuit.”
- **AP #76**: `.gitignore` enhancement + committed 5 reckoning artifacts. Blocked ~5 days by AP #100 eval-race in the Claude Code harness; landed after AP #100 fix shipped 2026-07-01.
- **AP #97/#98/#99**: `hunt <ioc>` config initializer chain — Config dataclass bug in Phase 17R fleet dispatch, resolved by extracting a shared credential resolver (`core/module_credentials.py`).
- **AP #84**: 4 M-9 invariant tests referenced a removed worktree path; replaced with `Path(__file__).resolve().parents[1]` (Phase 17U).

### Added
- **Protected visual design context**: added the three persona cyberdeck studies
  under `storyboard/` and the UX-team assessment under `reckonings/` as durable,
  repository-owned inputs to future interface work.
- **Shared operating philosophy**: added `PHILOSOPHY.md` as AP's durable
  judgment framework for evidence, human–computational collaboration,
  optionality, stewardship, and long-horizon decisions. Project guidance now
  applies it through tool-neutral `AGENTS.md` repository governance where no
  more specific instruction or accepted decision controls.
- **Reckoning operationalization** (Phase 17X): `DEC-PAUSE-001` declaring pauses out-of-scope, `.github/workflows/regen-decisions.yml` for auto-regen on push to main, and repository governance with `DEC-BACKLOG-DISCIPLINE-001` (schedule-or-close every issue at filing). The original Claude-specific file was superseded by tool-neutral `AGENTS.md` on 2026-07-18.
- **Phase 18 "Orchestrator Stability" roadmap** (umbrella issue #102): drain queue for 18 harness/runtime bugs.

### Harness (Claude Code side; not shipped with adversary-pursuit but affects the delivery chain)
- AP #75: Guardian completion auto-transitions in_progress work_items to `landed` — DEC-WORKITEM-AUTO-LAND-001 in `runtime/core/decision_work_registry.py`.
- AP #100 (Phase 18 Slice 1): `git stash`, `status`, `log`, and other non-mutating git subcommands no longer trigger post-bash source-mutation eval invalidation. New helper `git_subcommand_for_classify` in `hooks/context-lib.sh` delegates to canonical Python parser (DEC-CLASSIFY-001).
- 06-29 reckoning Confront #7: Pre-merge integration-test gate in `agents/reviewer.md` (`DEC-REVIEWER-INTEGRATION-GATE-001`).

## [0.4.0] — 2026-06-29

This release jumps from `0.1.0` (initial alpha) to `0.4.0` to reflect ~6 weeks of shipped
work across the M-1..M-9 dossier roadmap, C-1..C-4 character profiles, the chat-agent
hunt fleet, REPL revival, and harness stability work. Version `0.4` aligns with the
fourth major roadmap milestone completed since the initial cut.

### Added

- **Phase 17R: REPL revival** — `hunt <ioc>` fleet-dispatch primitive auto-detects IoC
  type and runs every matching enrichment module in one command. `use <short_name>`
  fuzzy-resolves to canonical module paths via `PluginManager.resolve_path()`. Rich
  tables now actually render (Phase 17R fixed a regression where output was written to a
  buried StringIO). New `core/ioc_types.py` + `detect_ioc_type()`; `accepts` tuples
  added to all 15 modules + `PluginManager.modules_accepting()`.
- **Phase 17Q: Banner redesign** — replaced the v1 radar-dish ASCII art with an ANSI
  Shadow figlet wordmark + reticle motif + dim metadata strip (version, IOC count,
  streak). Adds `pyfiglet>=1.0` dependency. Width fallback (< 60 cols) renders compact
  small-font variant.
- **Phase 17P: Workspace clear + chat workspace parity** — `workspace clear` drops the
  6 SQLite tables for a workspace with loud-fail verification (DEC-WORKSPACE-DB-007);
  `ap chat` now has full workspace command parity (list/create/switch/delete/clear) plus
  enhanced `db_status` showing DB file path, humanised file size, per-table row counts,
  total score, and last-event timestamps. Both surfaces share a single
  `_render_db_status_table` helper (DEC-WORKSPACE-DB-005).
- **Phase 17O: Universal error routing** — agent tool exceptions now flow through
  `ErrorInterpreter` and render as Rich panels instead of stderr stack traces. New
  matchers for `httpx.HTTPStatusError` 401/403 (auth), 429 (rate-limit), 5xx (service),
  and 4xx fallthrough (network). LLM-facing return string prefixed `[USER_SAW_PANEL]`.
- **Phase 17T: Shared module credential resolver** — extracted to
  `core/module_credentials.py` so both chat and REPL paths build per-module init dicts
  the same way (DEC-MODULE-CREDS-SHARED-001 — single rendering authority).
- M-1 through M-9 dossier roadmap items: actor profile generation, pivot chains,
  challenge/badge/prediction framework, crowdsourced dossier merging, and STIX
  provenance. See git history (`git log v0.1.0..v0.4.0`) for individual phase entries.
- C-1 through C-4 character profile additions: `sun_tzu`, `bruce_lee`, `bureaucrat`,
  `columbo` — four new modes with distinct persona prompts and score-celebration strings.

### Fixed

- `hunt <ioc>` initializer regression (AP #97 Phase 17S → AP #98 Phase 17T): the
  fleet-dispatch path in Phase 17R passed the raw Pydantic `Config` dataclass to
  `module.initialize()` instead of the `ConfigManager`. Phase 17S extracted a shared
  `_initialize_module` helper; Phase 17T replaced it with a shared credential resolver
  (`core/module_credentials.py`) that both chat and REPL now call identically.
- Four invariant tests (`TestF59Invariant`, `TestF64Invariants`) referenced a removed
  M-9 worktree path in `cwd=` arguments; replaced with `Path(__file__).resolve()
  .parents[1]` (AP #84, Phase 17U). Full suite: 2735 passed, 0 failed, 1 skipped.
- ThreatFox 401 (and similar API failures) no longer leak stack traces to stderr;
  presented as a one-line summary panel via `ErrorInterpreter` (AP #84 + Phase 17O).

### Internal

- Phase 17U: Test fixture path hardcode fix — four test files use `_REPO_ROOT` derived
  from `Path(__file__).resolve().parents[1]` instead of a hardcoded worktree path.
- Phase 17S: AP #97 follow-up — `_initialize_module` shared helper to prevent
  chat/REPL module-init divergence (superseded by Phase 17T shared resolver).
- `scripts/regen_decisions.py` added: DECISIONS.md regeneration tooling (AP #72).
- 7 closed harness/dispatch bugs (AP #86, #91, #92, #93, #94, #95) shipped on the
  Claude Code harness side; listed for completeness because they affect the dispatch
  chain that builds this project.

## [0.1.0] — 2026-05-19

Initial stable release. Core REPL (`ap`, cmd2-based), conversational AI agent
(`ap chat`, litellm-driven, 21 LLM tools), 10 OSINT/CTI modules (Shodan, VirusTotal,
AbuseIPDB, HIBP, OTX, URLScan, Censys, PassiveTotal, DNS, WHOIS), STIX 2.1 data model,
per-workspace SQLite storage, gamification engine (parabolic decay scoring, challenges,
badges, hints), 6 initial character modes, graph export (GEXF + STIX bundle), and
interview-based report generation.

[Unreleased]: https://github.com/jarocki/ap/compare/v0.4.5...HEAD
[0.4.5]: https://github.com/jarocki/ap/compare/v0.4.4...v0.4.5
[0.4.4]: https://github.com/jarocki/ap/compare/v0.4.3...v0.4.4
[0.4.3]: https://github.com/jarocki/ap/compare/v0.4.2...v0.4.3
[0.4.2]: https://github.com/jarocki/ap/compare/v0.4.1...v0.4.2
[0.4.1]: https://github.com/jarocki/ap/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/jarocki/ap/compare/v0.1.0...v0.4.0
[0.1.0]: https://github.com/jarocki/ap/releases/tag/v0.1.0
