# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.7.0] — 2026-08-01

This early-availability release consolidates the unreleased 0.6 development
checkpoints into one verified minor release.

### Added

- Added a concise Quick Start, a task-oriented User Guide, a documentation
  index, and an accessible transcript for the guided demonstration.
- Added the finished two-minute guided video and current screenshots covering
  startup, masked credential setup, model selection, the Investigation
  Constellation, relationship graph, and reporting.
- Added one shared model and API configuration authority for the terminal
  cyberdeck and Pivotglass. `model show`, `model list`, `model check`,
  `model select`, enable/disable, repair, and advisor controls now execute
  locally instead of falling through to model synthesis.
- Added a viewport-centered Pivotglass Configuration center with masked
  credential state, explicit credential tests, per-service enable/disable,
  safe credential removal, live provider model catalogs, and model selection.
- Added account-visible model profiles whose strengths and limitations are
  derived from provider availability and optional local LiteLLM capability
  metadata, with explicit caveats where quota, latency, quality, or capability
  are not proven.
- Added throttled, asynchronous configuration suggestions in every public
  character voice. Suggestions are local deterministic narration, never
  evidence; they spend no tokens, make no background provider requests, do not
  steal focus, and can be disabled.
- Added the persistent Investigation Constellation: stored indicators form
  rows, the nine canonical Dossier dimensions form columns, and every cell
  shows its deterministic empty, partial, filled, or deferred state from the
  indicator and evidence in its direct graph neighborhood.

### Changed

- Intelligence-service disable controls now prevent the disabled module from
  resolving credentials or running while preserving the stored credential.
- Model disable now blocks every synthesis call while deterministic commands
  and investigation tools remain available.
- Expanded shared command completion and operator documentation for the new
  model and configuration command families.
- Hardened command-completion stacking with an explicit top-level interaction
  layer and opaque surface, keeping every row above Systems, Intelligence, and
  maximized panes; dialogs remain above the completion layer.
- Made Constellation newest-last-seen first by default, with reversible search,
  IoC-type, mapped-completeness, first/last-seen, direct-relatedness, and sort
  controls. Enrichment lifecycle remains a separate secondary matrix.

### Security

- Ordinary configuration payloads expose credential source and health only.
  A newly entered secret exists transiently in the masked field and explicit
  local save/test request; stored secrets are not returned by routine polling,
  repopulated into fields, logged, exported, or sent to a model.

### Visualization, graph, and atmosphere

#### Added

- Added the Pivotglass 0.6.0 semantic visualization foundation: a bounded
  Python-owned intent schema, deterministic question-to-view policy, and an
  allow-listed TypeScript adapter that compiles supported charts through Flint.
- Added question-first visual analysis for stored evidence composition,
  dossier completeness, UTC activity concentration, indicator-by-enrichment job
  state, and stored relationships. Every view includes source scope,
  missing-data treatment, an accessible exact-data table, empty/error states,
  caveats, and CSV or JSON export.

#### Changed

- Replaced the ad hoc Artifact Field chart with a unified Visual Analysis
  workspace and removed the decorative hand-drawn geography from the
  analytical surface.
- Made relationship overviews bounded and filterable, show actual indicator
  values, distinguish explicit relationships from property pivots, and state
  plainly when stored indicators have no relationship edges.
- Replaced the static relationship overview with a deterministic force-directed
  investigation graph. Analysts can drag, pan, zoom, center, filter, select,
  and open evidence for actual IoC nodes and provenance-backed directional
  edges without changing stored evidence.
- Added an in-pane restore control and corrected stacking so maximized cockpit
  panes remain readable and escapable.
- Replaced the hairline screen sweep with a broad, soft-edged fog band that
  remains behind evidence and focus indicators and respects reduced motion.
- Raised command completion above every ordinary and maximized cockpit pane,
  bounded it to the viewport, and added a one-time preference migration that
  reveals Visual Analysis for existing installations.
- Expanded the character arcade with larger shuffled question banks and
  seeded, replayable scenarios. Neuromancer now has eight increasingly
  difficult 5×5–7×7 Jack In runs with trace pressure, black ICE, data caches,
  scoring, same-map retries, and fresh generated identities.
- Added deterministic arcade-engine tests covering content variation and 800
  generated Neuromancer maps, each verified to retain a route to the exit.
- Made the editable-checkout web launcher reject stale static exports and
  disabled browser caching for exported assets so `ap` cannot silently serve
  an older cockpit after source changes.

#### Security

- Updated Next.js from 16.2.10 to 16.2.12, rebuilt the packaged Pivotglass
  static assets, and restored a zero-vulnerability `npm audit` result.

## [0.5.2] — 2026-07-28

### Added

- Added reviewed signature-line banks for every public character. Deterministic
  surfaces rotate local lines, while the existing bounded dossier-narration
  path occasionally asks the configured model for one original line under an
  explicit rule that flavor is never evidence.
- Added workspace create, list, switch, delete, export, and merge services;
  shared TUI/Pivotglass command completion; relationship-aware evidence detail;
  and additive VirusTotal, AbuseIPDB, and URLScan metadata.
- Added release demonstrations of the real TUI and Pivotglass interfaces to the
  README and user guide.

### Changed

- Consolidated the public character deck into seven strongly differentiated
  identities: Default (Analyst), Chuck Norris, HAL9000, Troll, Sherlock Holmes,
  Neuromancer, and The Matrix, while retaining compatibility with stored legacy
  mode identifiers.
- Added themed Day/Night palettes, a reliable high-contrast override, visible
  keyboard focus, reduced-motion initialization, and matching terminal
  accessibility palette controls.
- Added a browser-persistent, operator-controlled investigation queue with
  reordering, Run Next/Run All, retry, removal, and explicit lifecycle states.
- Reworked every public mode's procedural score around an original motif,
  harmonic arc, meter, form, orchestration, phrase-level variation, and smooth
  web transitions so the identities remain cinematic without repeating a
  fixed recording or closely imitating a referenced work.
- Replaced synthetic computer-like voices with modeled piano, strings, winds,
  brass, choir, acoustic percussion, expressive envelopes, and room ambience;
  added character-specific cinematic ensembles shared by web and terminal.
- Expanded Pivotglass from an indicator-only launcher into a local-first analyst
  command surface supporting workspace search, graph, dossier gaps, timeline,
  linked notes, reports, exports, pivots, and grounded model questions.
- Restored deterministic terminal routing for previously advertised workspace,
  search, graph, dossier, report, timeline, note, hint, challenge, export, and
  auto-pivot commands.
- Corrected relationship graph/export construction to include persisted STIX
  relationships, and added browser JSON and CSV export.
- Reworked cockpit interaction density with viewport-centered Help, temporary
  full-screen panes, literal 3×3-pixel task LEDs, source-backed geo/malware
  context, one-click indicator queues, conditional maps, and linked annotations.
- Rebuilt Flow Dojo as a functional 8-bit miniscroller and expanded character
  environments with Unicode rain, visible white-rabbit sightings, animated
  cameos, climbing Ninja, and Computer glitch events.
- Added character-specific diversions: a chess conclusion for Sherlock Holmes,
  a safe shutdown sequence for HAL9000, an ICE-routing jack-in for Neuromancer,
  and a power-grid breaker puzzle for The Matrix; realigned Chuck Norris to
  leather, brass, and gold and Neuromancer to dead-channel blue-grey.
- Rebuilt the terminal soundtrack around declarative character scores,
  phrase-level motif transformation, harmonic direction, counterpoint,
  expressive synthesis, and intentional loop form while preserving local,
  deterministic, opt-in, presentation-only playback.
- Refined M4TR1X with an original sample-informed electronic motor, sub-bass
  foundation, bright machine spectrum, and steady eighth-note pressure without
  bundling or reproducing the reference recording.
- Refined Sensei with an original spacious drone form, slow harmonic breathing,
  bowl-like partials, grounded bass, and isolated swells derived from the
  reference's broad emotional and spectral arc.
- Refined The Sprawl with an original descending spectral grid, irregular
  machine signals, obscured tonal center, and late-form noise bloom derived
  from the reference's broad structural and timbral behavior.
- Refined Ninja with an original 140 BPM stealth-to-impact form, clipped motif
  cells, shadow bass, measured footstep pulse, and steep dynamic reveal derived
  from the Apple Music reference's broad pacing and production behavior.
- Refined The Detective with an original crooked three-beat investigation
  pulse, dry clue cells, uneven knocks, rain atmosphere, and abrupt second-act
  reveal derived from the reference's broad dramatic and rhythmic behavior.
- Refined The Computer with an original dreamy cyberspace current, suspended
  luminous harmony, star-like motif points, steady 128 BPM orbit, and restrained
  dynamic arc derived from the reference's broad atmospheric behavior.
- Refined Strategist with an original four-stage long-range build, measured
  pulse, foundation bass, restrained plan motif, widening horizon harmony, and
  final-act arrival derived from the reference's broad structural behavior.
- Refined Default with an original open field-and-sky form, gentle 64 BPM
  stride, seed-like motif, consonant spacing, and gradual hopeful lift derived
  from the reference's broad emotional and registral behavior.
- Made terminal soundtrack volume linear and peak-normalized with useful
  headroom at maximum, and preserved the enabled/muted choice while switching
  character themes.

### Fixed

- Kept Pivotglass keyboard focus visible and recoverable, restored command
  completion parity with the TUI, and ensured viewport overlays and artifact
  hover details are not clipped by their source panes.
- Made soundtrack start, stop, and character changes cross-fade without
  disruptive transients while preserving the operator's enabled state.
- Preserved human-readable indicator values throughout the graph, queue, and
  evidence surfaces instead of exposing backend STIX identifiers.

### Verified

- Release verification is recorded in
  [`docs/QA_V0.5.2.md`](docs/QA_V0.5.2.md).

## [0.5.1] — 2026-07-21

### Added

- Accessible 3×3 RGB task constellation with non-color lifecycle marks,
  hover/focus previews, bounded attention twinkles, and complete per-enrichment
  transition and evidence drill-down.
- Persistent collapsible panes, active-pane navigation, interactive dossier
  cells, task-oriented contextual Help, and the optional Sensei Flow Dojo.
- Phrase-based multi-voice web soundtrack and a 32-second layered terminal
  movement with motifs, riffs, lead passages, imitative counterpoint, and
  releases.

### Fixed

- Prevented one enrichment from rendering three or four permanently expanded feed
  cards, while preserving every immutable event behind the task detail.
- Prevented `?` from opening Help while typing, made overlays mutually
  exclusive, restored opener focus, respected reduced motion during scrolling,
  and removed horizontal overflow at 320- and 1024-pixel widths.
- Made interactive affordances explicit and removed title-only dossier hints.

### Verified

- Focused Python lifecycle/music/QA tests, TypeScript checking, optimized web
  build, browser interaction checks for Help and persistent collapse, and
  browser layout checks at 320 and 1024 pixels.

## [0.5.0] — 2026-07-21

### Added

- Quality-assured Pivotglass investigation lifecycle with resumable event
  history, stable evidence drill-down, persistent Master Caution, complete TUI
  transcript navigation, accessible responsive cockpit navigation, canonical
  character contracts, signature environments, and opt-in generative music.

### Changed

- The approved eight-package QA/UX plan now forms one consolidated release:
  v0.4.2 through v0.4.9 remain tagged recovery points; v0.5.0 is the supported
  quality-assured implementation.
- Original archetypes replace direct pop-culture character names while approved
  influences survive in restrained voice, geometry, and atmosphere.

### Security

- Exact local web dependencies are locked, advisory-clean, signature-verified,
  and served without CDN code, remote fonts, analytics, or telemetry.

### Verified

- Full Python test and lint suites, optimized TypeScript/Next.js build, Python
  source and wheel packaging, isolated wheel smoke install, compact and desktop
  browser checks, npm advisories, registry signatures, and attestations.

## [0.4.9] — 2026-07-21

### Security

- Locked patched Sharp 0.35.3 across the Next.js dependency graph, clearing two
  high-severity inherited libvips advisories.
- Verified registry signatures for 31 locked npm packages and attestations for
  17 packages.

### Added

- Cross-interface QA matrix gates for complete character presentation
  contracts, structural first-wave differentiation, local opt-in audio, and
  retired-mode exclusion.
- A durable v0.4.9 QA record covering automation, browser checks, packaging,
  accessibility, supply chain, and graceful degradation.

### Changed

- Cleared the repository-wide Python lint backlog without adding exclusions.

### Verified

- Built the Python source distribution and wheel from the declared backend.
- Production npm advisory audit reports zero vulnerabilities.

## [0.4.8] — 2026-07-21

### Added

- Signature, code-native cockpit environments for M4TR1X, The Sprawl, Sensei,
  Detective, and The Computer, plus quieter geometry treatments for the rest
  of the canonical roster.
- Local procedural atmospheric music with distinct archetype palettes,
  explicit opt-in, volume control, visible mute state, and no network or
  copyrighted recording dependency.
- TUI Alt-M emergency mute and an honest unavailable state when no supported
  local audio player exists.

### Changed

- Character changes now affect geometry, motion, instruments, feedback, and
  voice rather than color alone.
- Reduced and off effects also govern signature ambient layers; all operational
  meaning remains available without motion or sound.

### Verified

- Exercised M4TR1X and The Sprawl signature layers, music enable/mute, effects
  off, menu stacking, and a 320-pixel viewport in the production browser build.

## [0.4.7] — 2026-07-21

### Added

- Canonical presentation contracts for geometry, ambient layers, motion,
  instrumentation, event flourishes, character voice, repetition limits, and
  the procedural-music palette planned for each interface.
- Deterministic one-window migration aliases for historical character names.

### Changed

- Consolidated the selectable roster into original archetypes: Strategist,
  Sensei, Detective, The Computer, The Sprawl, and M4TR1X alongside Default,
  Ninja, Full Troll, and Bureaucrat.
- Folded the approved martial-arts, detective, computer, and cyberpunk
  influences into those archetypes while retaining evidence-first voice rules.

### Removed

- Retired Drunken Master and Bobby Hill from selectable TUI and Pivotglass
  catalogues. Explicit commands receive stable local retirement guidance;
  historical display can still resolve through documented successors.

## [0.4.6] — 2026-07-21

### Added

- Persistent responsive pane switcher and searchable Command/Control-K command
  palette.
- URL-restorable pane selection and focus-trapped, focus-restoring dialogs.
- Full, reduced, and off visual-effect controls plus independent full, brief,
  and off narration controls persisted locally.
- Keyboard-accessible Flint data table alongside the visual artifact chart.
- Non-color semantic cues and a reduced-motion media policy.

### Fixed

- Removed a 350-pixel intrinsic panel minimum that caused page-level overflow
  at a 320-pixel viewport while retaining every primary control.
- Kept operator help available on compact screens.

### Verified

- Exercised the production build in a live browser at desktop and 320-pixel
  widths, including command search, dialog focus, chart semantics, control
  visibility, and document bounds.

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
  resumable cursors, per-enrichment states, cancellation acknowledgement, and
  incremental event delivery.
- Live elapsed-time feedback and incremental enrichment/evidence cards in
  Pivotglass.
- Focused lifecycle, cursor, cancellation, and truthful-instrumentation tests.
- The approved v0.4.2 through v0.5.0 QA/UX release plan.

### Changed

- Pivotglass now starts investigations asynchronously and polls an authoritative
  event stream rather than waiting on one opaque synchronous request.
- Approximate reactor, enrichment, token, and hull meters now report measured state
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
  enrichment source now explains which artifacts it is gathering, why
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
  visible enrichment/evidence/provenance
  cards. Hunt synthesis now surfaces a concise character-voiced analyst
  intuition and clearly labels evidence, inference, uncertainty, and next pivot.
- **Mode-specific cockpit HUDs**: all 14 modes now select distinct vehicle/deck
  vocabulary and perspective rails. The six-row tactical HUD reports real
  target lock, classification, active enrichment, queue depth, dossier progress,
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
- **Protected visual design context**: added persona cyberdeck studies and a
  UX-team assessment as durable local inputs to future interface work. Those
  private project artifacts are no longer published with the repository.
- **Shared operating philosophy**: added `PHILOSOPHY.md` as AP's durable
  judgment framework for evidence, human–computational collaboration,
  optionality, stewardship, and long-horizon decisions. Project guidance now
  applies it through tool-neutral `AGENTS.md` repository governance where no
  more specific instruction or accepted decision controls.
- **Reckoning operationalization** (Phase 17X): `DEC-PAUSE-001` declaring
  pauses out-of-scope, private automation for decision-index regeneration, and
  repository governance with `DEC-BACKLOG-DISCIPLINE-001` (schedule-or-close
  every issue at filing). The original Claude-specific file was superseded by
  tool-neutral `AGENTS.md` on 2026-07-18.
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

[Unreleased]: https://github.com/jarocki/pivotglass/compare/v0.7.0...HEAD
[0.7.0]: https://github.com/jarocki/pivotglass/compare/v0.5.2...v0.7.0
[0.5.2]: https://github.com/jarocki/pivotglass/compare/v0.5.1...v0.5.2
[0.5.1]: https://github.com/jarocki/pivotglass/compare/v0.5.0...v0.5.1
[0.5.0]: https://github.com/jarocki/pivotglass/compare/v0.4.9...v0.5.0
[0.4.9]: https://github.com/jarocki/pivotglass/compare/v0.4.8...v0.4.9
[0.4.8]: https://github.com/jarocki/pivotglass/compare/v0.4.7...v0.4.8
[0.4.7]: https://github.com/jarocki/pivotglass/compare/v0.4.6...v0.4.7
[0.4.6]: https://github.com/jarocki/pivotglass/compare/v0.4.5...v0.4.6
[0.4.5]: https://github.com/jarocki/pivotglass/compare/v0.4.4...v0.4.5
[0.4.4]: https://github.com/jarocki/pivotglass/compare/v0.4.3...v0.4.4
[0.4.3]: https://github.com/jarocki/pivotglass/compare/v0.4.2...v0.4.3
[0.4.2]: https://github.com/jarocki/pivotglass/compare/v0.4.1...v0.4.2
[0.4.1]: https://github.com/jarocki/pivotglass/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/jarocki/pivotglass/compare/v0.1.0...v0.4.0
[0.1.0]: https://github.com/jarocki/pivotglass/releases/tag/v0.1.0
