# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
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
- **Reckoning operationalization** (Phase 17X): `DEC-PAUSE-001` declaring pauses out-of-scope, `.github/workflows/regen-decisions.yml` for auto-regen on push to main, project-local `CLAUDE.md` with `DEC-BACKLOG-DISCIPLINE-001` (schedule-or-close every issue at filing).
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

[Unreleased]: https://github.com/jarocki/ap/compare/v0.4.0...HEAD
[0.4.0]: https://github.com/jarocki/ap/compare/v0.1.0...v0.4.0
[0.1.0]: https://github.com/jarocki/ap/releases/tag/v0.1.0
