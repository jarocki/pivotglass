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

## Plan Status (Reconciled 2026-04-28, Reframed 2026-04-29, v1 Closed 2026-05-18, Stable Shipped 2026-05-19, v2 Scoping Closed 2026-05-27, v0.2.0 Wave Landing 2026-05-28..2026-05-29)

| Phase | Status | Notes |
|-------|--------|-------|
| Phase 0 — Foundation Modules (was Phase 1) (#1-#5) | completed | All 5 issues landed; cmd2 console wires Config + Plugin + Workspace + Modes. Now reframed as supporting infrastructure for the agent. |
| Phase 1 — OSINT/CTI Modules (was Phase 2) (#6-#13) | completed | All 8 priority modules landed; plus stretch `whois_lookup`, `dns_resolve`. Modules are the uniform tool surface both interfaces share. |
| Phase 2 — Gamification (was Phase 3) (#14-#18) | completed | Scoring, Challenges, Modes, Badges, Hints all landed. Fully wired into both the cmd2 console and the agent path (all 9 W-AGENT-* slices complete). |
| Phase 3 — Auto-Pivot & Graph (was Phase 4) (#19-#20) | completed | Event bus opt-in (DEC-EVENTBUS-002); graph + GEXF + STIX bundle export. Wired into both cmd2 console and agent path (W-AGENT-AUTOPIVOT `8e48256`, W-AGENT-GRAPH-EXPORT `0b83eb2`). |
| Phase 4 — Agentic Chat Interface (#25 + W-AGENT-*) | completed | All 9 W-AGENT-* slices landed. 21 LLM tools covering all 10 modules + celebrations + badges + hints + modes + autopivot + challenges + graph/export + reports. Full gamification parity with cmd2 console achieved. |
| Phase 5 — Polish & Release (#21-#24) | completed (2026-05-18) | #21, #22, #23 done; #24 CI/CD landed. **Distribution strategy pivoted PyPI → GitHub Releases (`02fed4d`, 2026-05-03).** `W-V1-PYPI-VERIFY` retired; replaced by `W-V1-RELEASE-VERIFY` which landed at merge `cd3709a` (2026-05-18) — `v0.1.0rc1` pre-release published at https://github.com/jarocki/ap/releases/tag/v0.1.0rc1 (tag SHA `d392deb`), wheel+sdist attached, fresh-venv install with `[agent]` extras verified end-to-end. See "Phase 5 closeout" section below. |
| Phase 6 — Agent Docs (W-AGENT-DOCS) | completed | README rewritten for agent-first v1: `ap chat` primary interface documented, all 21 LLM tools, 8 meta-commands, 10 modes, and persona-prompt protocol. MASTER_PLAN Phase 4 status and W-AGENT-* table updated with all merge SHAs. |
| Phase 7 — Post-Phase-6 CTI Pipeline & TUI Polish (unscheduled, landed organically 2026-05-03..2026-05-15) | completed | ~12 user-driven commits hardening CTI reliability, setup UX, and TUI polish: setup wizard `b44968c` (#45), 3-layer key resolution `a4cc341`, Censys Platform API v3 `fef6bfd` (#43), CTI pipeline repairs `9e6daa0`, URLScan submit/poll fixes `26c5b54` + `5cc2be6`, smoke SKIP classification `137fb45` (#48), smoke ConfigManager fix `823d54e`, TUI polish `db576b9`, provider/model wizard `4e11dde`, help meta-commands `70ede27`, `AP_MODEL` env override `9129c1b`, wizard dotfile export `4b9d030`. |
| Phase 8 — Smoke Test Reliability | completed (W-OTX-TIMEOUT landed `b877574`, impl `72fd3eb`) | `W-OTX-TIMEOUT` added `TIMEOUT` option to `cti/otx` + classified `httpx.ReadTimeout` as a timeout-stub SCO, mirroring the URLScan transient-failure pattern (`5cc2be6`). No other smoke regressions open at v1 ship; future live-smoke regressions will be filed as discrete slices through the canonical planner chain. |
| Phase 9 — Pre-v1 Module Catalog Top-Off (W-GREYNOISE) | completed (2026-05-16, merge `6884317`) | Per 2026-05-16 user directive ("Is GreyNoise one of the API lookup sources? If not, please add it before we ship v1.0."), added `osint/greynoise` as the 11th catalog module using the free-tier GreyNoise Community API (`/v3/community/{ip}`). Closes the noise/RIOT classification gap in the v1 IP-reputation surface. See "Phase 9 closeout" section below. |
| Phase 10 — Friendly Errors (W-FRIENDLY-ERRORS) | completed (2026-05-14, impl `1ccf13b`) | Universal `core/error_interpreter.py` — catches all errors at cmd2 + ap chat + smoke_test surfaces, renders friendly Rich panels with fix-suggestions + 8-char diagnostic IDs, optional `[y/n]` auto-apply for mechanically safe fixes. Per 2026-05-14 user directive. See "Phase 10" section. |
| Phase 11 — STIX 2.1 Spec Compliance + Per-SCO Provenance (W-59-STIX-PROVENANCE) | completed (2026-05-22, merge `a797831`, impl `f4a71a3`) | Workspace single authority for `x_ap_*` fields (`x_ap_fetched_at`, `x_ap_source_url`, `x_ap_api_version`, `x_ap_response_sha256`); `export_stix_bundle()` rebuilt via `stix2.v21.Bundle` round-trip. Closes #59. Per Threat Hunter expert assessment. See "Phase 11" section. |
| Phase 12 — Auto-Pivot Policy Engine (W-60-AUTO-PIVOT-POLICY) | completed (2026-05-25, merge `8035add`, impl `60eab19`) | IOC filter + confidence gate + per-cascade budget + dry-run, 3-gate rate limiting. Closes #60. Per Threat Hunter P0 verdict. See "Phase 12" section. |
| Phase 12B — Streak Mechanic + Honest Modes (W-62-STREAK-AND-HONEST-MODES) | completed (2026-05-26, merge `e3cf5ca`, impl `1d424ae` + `8b0faa2`) | StreakManager single-authority + first_blood wiring + run_fail authority + `random.choice` honest fix. Per Atwood [P1] gamification assessment. See "Phase 12B" section. |
| Phase 12C — Milestone Catch-Up + streak_continued Score Event (W-63-MILESTONE-CATCHUP) | completed (2026-05-26, merge `8778af3`, impl `a21eaba`) | Per Atwood [P2] gamification assessment. F63 milestone catch-up + streak_continued ScoreEvent subtype. See "Phase 12C" section. |
| Phase 13 — De-duplicate LLM Narration vs Rich Panel (W-64-DEDUP-LLM-NARRATION) | completed (2026-05-26, merge `3b92032`, impl `e460b41`) | Strip gamification text from LLM-facing summary; sidecar pattern preserves Rich-panel celebrations. F64 panel-separation single-authority established. See "Phase 13" section. |
| Phase 14 — Keyless Hunter Modules (W-61-KEYLESS-HUNTERS) | completed (2026-05-26, merge `556f873`, impl `bce981f` + `5a5b8e1`) | 4 keyless CTI/OSINT hunters (URLhaus, ThreatFox, MalwareBazaar, crt.sh) + smoke_test wiring + per-module `x_ap_*` exclusion tests. Closes #61. See "Phase 14" section. |
| Phase 16 — Threat Actor Dossier Reframe — Strategic Scoping (W-68-DOSSIER-REFRAME-SCOPING) | **Status:** completed (2026-05-27, merge `b2b846a`, impl `36b7f30`) | Per 2026-05-26 Project Reckoning (the most important unmade decision in the project) and issue #68. Ratifies the dossier-puzzle metaphor as v2's product center (DEC-68-DOSSIER-REFRAME-001), establishes scoring authority resolution (DEC-002), defines slot schema v1.0 (9 slots), decomposes the reframe into M-1..M-9 slices, dispositions issues #29/#30/#31/#32 (sequence-within / independent / **retire** / augment), schedules the Original Intent crowdsourcing axis as M-9. **No source code touched.** See Phase 16 section + `.claude/plans/dossier-reframe-v2-roadmap.md`. |
| Phase 17 — Character System v2 — LLM Personas — Strategic Scoping (W-30-CHARACTER-V2-SCOPING) | **Status:** completed (2026-05-27, merge `fe4c0b1`, impl `5726819`) | Per issue #30. Ratifies "Borderlands/Fallout RPG-style" as voice-quality recommendation (not catalog replacement); per-mode disposition (8 UPGRADE / 2 KEEP_STATIC / 0 RETIRE — disposition for `ninja` flipped to UPGRADE by C-2, see Phase 17E); `LLMPersonaProfile` schema v1.0 (8 fields, ≤ 165 tokens/mode, via `AgentRunner.set_character`); C-1..C-4 decomposition; F62/F64 invariant preservation; XP-grind retired (DEC-68-DOSSIER-REFRAME-005); narrow `mastery_level` hook deferred to C-4. **No source code touched.** See Phase 17 + `.claude/plans/character-v2-roadmap.md`. |
| Phase 17B — Dossier Visualization Panel — M-1 MVP (W-68-M1-DOSSIER-PANEL) | **Status:** completed (2026-05-28, merge `486a5ad`, impl `11aaf83`) | First implementer slice flowing out of Phase 16. New `src/adversary_pursuit/dossier/` package — read-only slot inference + Rich panel + `dossier` meta-command in `ap chat`. 3/9 slots infer real status (Identity / TTPs / Infrastructure); other 6 render `deferred` per DEC-M1-DOSSIER-002 (vocabulary unchanged; status enum widened). DEC-M1-DOSSIER-001..004 binding. `get_dossier_state` LLM tool deferred to M-2 per DEC-M1-DOSSIER-004. Landed in parallel with C-1 (Phase 17C) per DEC-30-CHARACTER-V2-007. |
| Phase 17C — Character v2 — C-1 MVP — `full_troll` LLMPersonaProfile (W-30-C1-FULL-TROLL-PROFILE) | **Status:** completed (2026-05-28, merge `e49e70b`, impl `5417cec`) | First implementer slice flowing out of Phase 17 (originally numbered 17B by C-1 planner; renumbered to 17C per chronological merge order — C-1 landed ~5 min after M-1). `LLMPersonaProfile` frozen dataclass + `CharacterMode.llm_profile: \| None = None` + extended `AgentRunner.set_character` composer + `full_troll` profile authored verbatim per DEC-C1-FULLTROLL-001. F62/F64 invariant test suite incl. `test_persona_swap_preserves_tool_call_identity` hard gate (DEC-C1-FULLTROLL-004). Other 9 modes ship at `llm_profile=None` (= F62 behavior). DEC-C1-FULLTROLL-001..005 binding. Landed in parallel with M-1 (Phase 17B). |
| Phase 17D — Per-Module Dossier Slot Extractors + `get_dossier_state` LLM Tool (W-68-M2-SLOT-EXTRACTORS) | **Status:** completed (2026-05-29, merge `11b3fd3`, impl `83a98d9`) | Second implementer slice flowing out of Phase 16. Extends M-1 with 4 real extractors (Timing / Targeting / Capability / Motivation) + 2 scaffold-only (Predictions / Denial) + `infer_dossier_state_full(scos, module_runs, notes)` entrypoint + `get_dossier_state` LLM tool (DEC-M1-DOSSIER-004 deferred surface now landed). `PredictionRecord` + `DenialStrategyRecord` typed scaffold dataclasses (auto-infer deferred to M-4 per DEC-M2-DOSSIER-004). DEC-M2-DOSSIER-001..005 binding. Bug fix surfaced during compound integration test: `_parse_utc_hour` handles both `str` and `datetime.datetime` (WorkspaceManager.get_module_runs returns native datetime). M-1 panel renders correctly with extended schema (no panel.py edits — byte-identical). F59/F60/F62/F63/F64 invariants preserved. |
| Phase 17E — Character v2 — C-2 — `ninja` LLMPersonaProfile (W-30-C2-NINJA-PROFILE) | **Status:** completed (2026-05-29, merge `f8bded8`, impl `699dbc8`) | Second implementer slice flowing out of Phase 17. Ninja's disposition flipped from KEEP_STATIC to UPGRADE per DEC-C2-NINJA-001 (quiet-operator voice extends ninja's static terseness rather than re-inventing it). Two-file slice: `gamification/modes.py` (add `llm_profile` to ninja entry) + `tests/test_character_v2.py` (update C-1 tests per DEC-C2-NINJA-003 + add ninja mirror suites). `runner.py` byte-identical (C-1 injection branch fires for any non-None profile). DEC-C2-NINJA-001..003 binding. 45/45 test_character_v2.py + 1984/1985 full suite pass. Closes #30 C-2 slice. |
| Phase 17F — Dossier Scoring + Score Event Re-Tune — M-3 (W-68-M3-DOSSIER-SCORING) | **Status:** completed (2026-06-01, merge `2809b13`, impl `974fa1a`) | Third implementer slice flowing out of Phase 16. New `dossier/scoring.py` pure-function event emitter (DEC-M3-DOSSIER-001); per-IOC `DEFAULT_RULES` re-tune to `initial=minimum=1` for all 9 SCO-mapped action keys (DEC-M3-DOSSIER-004); hunt-site snapshot+emit wiring at `run_module` + `_execute_hunt` (DEC-M3-DOSSIER-002); `dossier_prediction_validated` event subtype scaffolded but NOT emitted (DEC-M3-DOSSIER-005 — M-4 plugs it in). F59/F60/F62/F63/F64 invariants preserved; `ScoringEngine` behavior unchanged (DEC-M3-DOSSIER-003). DEC-M3-DOSSIER-001..005 binding. Closes M-3 of the dossier roadmap. |
| Phase 17G — Persistent Dossier State + Predictions Log Auto-Validation — M-4 (W-68-M4-PERSISTENT-DOSSIER) | **Status:** completed (2026-06-02, merge `f928149`, impl `1b1a2b0`) | Fourth implementer slice flowing out of Phase 16. NEW `dossier/state.py` (DossierState persistence via F63 sentinel-row pattern in `score_events`) + NEW `dossier/predictions.py` (PredictionRecord lifecycle + typed `ExpectedEvidence` validation engine); hunt-site rewire so `pre_state` comes from persistent snapshot (one fewer `infer_dossier_state_full` call per hunt); NEW `create_dossier_prediction` LLM tool; M-3 scaffolded `emit_dossier_prediction_validated_event` wired to fire on confirmation at weight 4. Narrow `core/workspace.py` change (`_RESERVED_ACTIONS` frozenset + `get_recent_scores` filter widening per DEC-M4-PERSIST-002); no schema change, no new SQLAlchemy model. Active falsification deferred to M-5 (DEC-M4-PRED-005). DEC-68-DOSSIER-REFRAME-007 falsified-prediction deduction committed: confirmation=+4 / falsification=0 (DEC-M4-PRED-006). F59/F60/F62/F63/F64 invariants preserved. DEC-M4-PERSIST-001..003 + DEC-M4-PRED-001..006 binding. See Phase 17G section + `.claude/plans/dossier-m4-persistent-state.md`. |
| Phase 17H — Denial / Deception Strategies (slot 9) + User-Note Authoring Surface + Active Falsification Engine — M-5 (W-68-M5-DENIAL-STRATEGIES) | **Status:** in-progress (planner-staged 2026-06-07; implementer slice `wi-68-m5-impl-01` to follow) | Fifth implementer slice flowing out of Phase 16. EXTEND `dossier/slot_inference.py` with a real slot 9 extractor (DGA shape + fast-flux TTL hint + denial-keyword notes — DEC-M5-DENIAL-001..003); EXTEND `dossier/predictions.py` with `FalsificationEvidence` dataclass + `falsify_predictions` engine + `PersistedPrediction` schema v2 (DEC-M5-FALSIFY-001..008); EXTEND `dossier/scoring.py` with `emit_dossier_prediction_falsified_event` helper; NEW chat meta-command `note <text>` + NEW `create_dossier_note` LLM tool (rides on the existing `WorkspaceManager.add_note()` + `AnalystNote` table — DEC-M5-NOTE-001..003 reject the dispatch context's sentinel-row suggestion because `AnalystNote` is the canonical authority); NEW `falsify_dossier_prediction` manual-override LLM tool; widen `_DOSSIER_ACTIONS` F64 filter to 3-tuple. `core/workspace.py` BYTEWISE UNCHANGED in M-5 (stronger than M-4's narrow-edit clause). `models/database.py` UNCHANGED (DEC-DB-002 preserved). DEC-M4-PRED-006 falsification=+0 stays canon. F59/F60/F62/F63/F64 + Sacred Practice 12 invariants preserved. DEC-M5-DENIAL-001..003 + DEC-M5-NOTE-001..003 + DEC-M5-FALSIFY-001..008 binding. See Phase 17H section + `.claude/plans/dossier-m5-denial-strategies.md`. |

**Aggregate (reconciled 2026-06-07, v0.2.x continuation):** Phases 0–14 complete (v1 through stable `v0.1.0` shipped 2026-05-19; v1-hardening F59/F60/F62/F62B/F63/F64/F61 all landed by 2026-05-26). Phases 16 + 17 closed the v2 strategic scoping (2026-05-27). Phases 17B + 17C closed the v0.2.0 MVP parallel wave (2026-05-28). Phases 17D + 17E closed the v0.2.x continuation wave (2026-05-29). Phase 17F closed M-3 dossier scoping (2026-06-01, merge `2809b13`). Phase 17G closed M-4 persistent dossier + predictions log (2026-06-02, merge `f928149`, impl `1b1a2b0`). Phase 17H (M-5 Denial / Deception slot 9 + User-Note Authoring Surface + Active Falsification Engine) is in flight as of 2026-06-07. 23 phases landed; 24th in progress. Next work after M-5 lands: **M-6 — Dossier-Aware Auto-Pivot Policy** (extends F60's 3-gate policy with a "would this pivot fill an empty high-value slot?" input, per `.claude/plans/dossier-reframe-v2-roadmap.md` §M-6). M-7 (Reports / Celebrations / Badges Dossier-Aware Upgrade — absorbs issue #32) is independent of M-6 once M-5 lands; both can schedule in any order before M-8 closes the v0.3.x cleanup.

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
**Status:** completed (landed 2026-05-15, merge `1ccf13b feat(errors): universal ErrorInterpreter — catch all, suggest fix, optional auto-apply`)
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

### Decision Log (Phase 10)

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
**Status:** completed (landed 2026-05-25, merge `a797831 Merge feature/59-stix-provenance (#59)`, work commit `f4a71a3 feat(stix): STIX 2.1 spec compliance + per-SCO provenance (#59)`)
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

### Decision Log (Phase 11)

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
**Status:** completed (landed 2026-05-25, merge `8035add Merge feature/60-auto-pivot-policy (#60)`, work commit `60eab19 feat(pivot-policy): auto-pivot policy engine with 3-gate rate limiting (closes #60)`)
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

### Decision Log (Phase 12)

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

## Phase 12B: Streak Mechanic + Honest Modes (W-62-STREAK-AND-HONEST-MODES, post-v1, 2026-05-26)

**Status:** completed (landed 2026-05-26, merge `e3cf5ca Merge feature/62-streak-and-honest-modes (#62)`, work commit `1d424ae feat(F62): kill dead-code lies + ship streak mechanic + mode-flavored failures` + reviewer-fixup `8b0faa2 fix(F62): wire run_fail + first_blood_message in agent surface (reviewer findings)`)
**Workflow id:** `w-62-streak-and-honest-modes` · **Goal id:** `g-62-streak-and-honest-modes` · **Work item id:** `wi-62-impl-01`
**Branch:** `feature/62-streak-and-honest-modes` · **Worktree:** `.worktrees/feature-62-streak-and-honest-modes` · **Base:** `main` @ `8035add`
**Closes:** [GitHub issue #62](https://github.com/jarocki/ap/issues/62)
**Numbering note:** This phase landed chronologically between Phase 12 (F60, 2026-05-25) and Phase 13 (F64, 2026-05-26). Both F62 and F64 planners independently numbered themselves "Phase 13" in their plan amendments; F62's MASTER_PLAN edit was never committed by its implementer, leaving F64 in the Phase 13 slot. This section is appended retroactively as Phase 12B per the 2026-05-26 Project Reckoning closeout.

### User directive (verbatim, via Gamification expert assessment, Jeff Atwood lens, 2026-05-22)

> "If I can't tell ninja and full_troll apart from a Shodan lookup's output, the modes are skins, not personas." — Atwood on documentation lies

> "they built the museum, not the slot machine." — Atwood on the missing streak mechanic

### Problem (Atwood [P1])

**Part A — documentation lies in gamification:**
- `gamification/modes.py` defined per-mode fields (`hint_style`, `personality` strings promising "speed bonuses", "combo multipliers", "chaos mode") that no consumer in `src/` read.
- `mode.run_fail` was defined on every mode but `console.py:325` always showed a generic red Rich Panel on exceptions.
- `first_blood_message()` and `_first_blood_used` — tested API surface that NO code in `src/` invoked.
- `celebrations.py:114` claimed ASCII art was randomized but always picked `CELEBRATION_ART[level][0]` — the `[0]` index defeated `random.choice`.

**Part B — the streak that isn't:**
- `HintProvider._revealed` was in-memory only (DEC-HINT-002 deferred persistence to v2).
- Score and badges were per-workspace only.
- Nothing pulled a returning user back tomorrow morning.

### Resolution

- DELETED `hint_style`; REWROTE aspirational `personality` substrings (kept the field, removed the lies).
- WIRED `mode.run_fail` on both surfaces: `console.py` exception path AND `agent/tools.py` exception path (the latter via reviewer-fixup `8b0faa2` after Round-0 surfaced the agent-side gap).
- DELETED parallel `_MODE_TITLE_FLAVORS` dict in `core/error_interpreter.py` (F61-drift; single authority restored).
- WIRED `CelebrationEngine._first_blood_used` + `first_blood_message()` on both surfaces.
- FIXED `celebrations.py:114` `[0]` bug (now `random.choice(CELEBRATION_ART[level])` actually picks randomly).
- NEW `core/streak.py::StreakManager` is the sole authority for `~/.ap/streak.json`. Schema: `{current_streak, longest_streak, last_hunt_date, freezes_used_this_week, last_iso_week}`. Atomic write via `tempfile + os.replace`. Corruption → log WARNING, rename to `.corrupt-<ts>`, fresh state. Clock-skew backward → clamp without mutation. ISO-week freeze: 1 per week (Duolingo pattern).
- Update fires from `APConsole._execute_hunt` AND `ToolContext.run_module` (NOT from modules — single authority).
- `StreakManager.format_banner_line()` shared by `agent/banner.render_boot_banner` AND `core/console.APConsole.preloop`. `AP_NO_BANNER=1` suppresses both.

### Decision Log (Phase 12B)

| DEC | File | Rationale |
|-----|------|-----------|
| DEC-62-KILL-DOC-LIES-001 | `gamification/modes.py` | DELETE `hint_style` (zero consumers, undefined semantics); REWRITE personality strings to remove unimplemented mechanic names ("speed bonuses", "combo multipliers", "chaos mode"). |
| DEC-62-KILL-DOC-LIES-002 | `agent/tools.py`, `core/error_interpreter.py` | Rich-strip helper `_strip_rich_markup` shared between `execute_tool` exception path and `_panel_title`. Inline regex `re.sub(r"\[/?[^\]]+\]", "", text)` (broader than `repl_input.py`'s whitelist pattern); single-authority refactor deferred per cc-todos follow-up. |
| DEC-62-CELEBRATIONS-001 | `gamification/celebrations.py:114` | Remove `[0]` index from `random.choice(CELEBRATION_ART[level])[0]`; the `[0]` defeated randomness. Fixed. |
| DEC-62-STREAK-001 | `core/streak.py` | NEW `StreakManager` is sole authority for `~/.ap/streak.json`. |
| DEC-62-STREAK-002 | `core/streak.py` | ISO-week anchored freeze (not Monday-UTC); handles year-boundary cleanly. |
| DEC-62-STREAK-003 | `core/streak.py` | Atomic write via `tempfile + os.replace`; corruption → rename to `.corrupt-<ts>` + fresh state + WARNING log. |
| DEC-62-STREAK-004 | `core/streak.py` | Clock-skew backward → clamp without mutation (no negative streaks). |
| DEC-62-STREAK-005 | `agent/tools.py`, `core/console.py` | Streak update fires from `_execute_hunt` AND `run_module` (NOT from modules — keeps no-touch-modules invariant). `first_blood_message()` wired at both call sites. |
| DEC-62-STREAK-006 | `agent/banner.py`, `core/console.py` | `format_banner_line()` shared by `render_boot_banner` AND `APConsole.preloop`. `AP_NO_BANNER=1` suppresses both. |
| DEC-62-STREAK-007 | `core/streak.py` | First-ever run: file doesn't exist → create with `current_streak=1`, `last_hunt_date=today`. |

### Implementer evidence

- 11 files changed, +1068/-110 (initial commit `1d424ae`)
- 4 files, +267/-4 (reviewer-fixup commit `8b0faa2`)
- 41 tests in `tests/test_streak.py` covering all StreakManager invariants
- Full pytest: 1678/1679 pass at the merged SHA (1 pre-existing skip)
- F59/F60/F4 invariants preserved (workspace.py, pivot_policy.py, leases token-consumption all bytewise untouched)
- F2 in action: implementer-authored commits on feature branch (not Guardian-commits-on-behalf)

---

## Phase 12C: Milestone Catch-Up + streak_continued Score Event (W-63-MILESTONE-CATCHUP, post-v1, planned 2026-05-26)

**Status:** planned (not yet implemented)
**Workflow id:** `w-63-milestone-catchup` · **Goal id:** `g-63-milestone-catchup` · **Planner work item:** `wi-63-planner-01` (in_progress) · **Implementer work item:** `wi-63-impl-01` (pending)
**Branch:** `feature/63-milestone-catchup` · **Worktree:** `.worktrees/feature-63-milestone-catchup` · **Base:** `main` @ `ba110a5`
**Closes:** [GitHub issue #63](https://github.com/jarocki/ap/issues/63)
**Numbering note:** This phase is appended as `12C` to keep the gamification-feedback-loop neighborhood (12B = F62 streak mechanic, 12C = F63 milestone catch-up + streak score event) contiguous, parallel to how Phase 12 / 12B were positioned in the 2026-05-26 closeout. Existing Phases 13 (F64) and 14 (F61) retain their chronological slots.

### User directive (verbatim, via Gamification expert assessment, Jeff Atwood lens, 2026-05-22)

> "If your milestones only fire on exact-hit, jumping 99→105 silently skips First Century forever. As built, the most aspirational moments are silently swallowed by arithmetic. Track `last_milestone_announced` in the workspace instead." — Atwood, on the milestone exact-hit dead end

> "F62 built the slot machine. Now wire the payout. The streak counts up but the score economy never reacts to it — give the score a reason to fire that isn't 'you found another IP.'" — Atwood, on the missing streak-retention reward signal

### Problem (Atwood [P2])

**Part A — milestone exact-hit dead end (DEC-CELEBRATION-002):**

`gamification/celebrations.py::milestone_message(total_score)` returns `MILESTONES.get(total_score)`. The thresholds are `{100, 500, 1000, 5000, 10000}`. Any hunt that crosses a threshold by more than zero — the common case once scoring rules ever award batches larger than 1 — silently skips the milestone. With current scoring rules a single `new_ip` (initial=100) lands you at exactly 100 only when your prior total is exactly 0. Every other path through the score curve dodges every milestone forever. The 5 highest-feedback moments in the game are documented as "fires when score lands exactly on the threshold" — i.e. almost never. DEC-CELEBRATION-002 codified this as accepted; F63 reverses it as a documented bug-class.

**Part B — streak retention has no score-economy signal:**

F62 (Phase 12B) shipped `StreakManager` and `~/.ap/streak.json`. The streak appears in `format_banner_line()` at REPL boot, and `update()` fires from `_execute_hunt` and `run_module`. But the `score_events` table — the heart of the score economy — never gets a row for streak retention. A user who pushes through to a 7-day streak gets a banner line and nothing in their score history. The score does not react to the mechanic that's designed to pull them back tomorrow morning.

The compound symptom: AP has the slot machine (F62) and the museum of badges (F14-F18), but the two highest-arousal feedback paths (cross-a-milestone, retain-your-streak) both either fail to fire or fail to leave a trace in the score economy.

### Goal

After F63 lands:

- Crossing 100 points for the first time in a workspace — whether the run that crosses lands at 100, 105, 207, or 1247 — fires the First Century milestone exactly once for that workspace, ever. Same for 500, 1000, 5000, 10000.
- A workspace that already has a score above any threshold at the moment F63 ships does NOT retroactively announce milestones it never saw — first hunt after upgrade is quiet ("seed baseline" migration).
- `StreakManager.update()` returns a typed `StreakUpdate` snapshot indicating `incremented / frozen_used / reset / current_streak`. The two existing call sites consume it; modules still cannot reach the streak machinery directly.
- Every day a user extends their streak through `_execute_hunt` or `run_module`, a `score_events` row with `action="streak_continued"` is inserted with step-decay points: 10/day for streak days 1–7, 5/day for days 8–30, 2/day for day 31 and beyond. Floor never reaches zero so the streak always carries some score signal; bands prevent infinite-farming growth.
- The score-display surfaces (`do_score` cmd2 table, agent `result['score_events']`) show the streak_continued rows in the recent-events feed.
- F62 remains the sole authority for `~/.ap/streak.json`. F63 only consumes the typed return value.

### State-Authority Map

| Domain | Pre-F63 owner | Post-F63 owner | Notes |
|--------|---------------|----------------|-------|
| `~/.ap/streak.json` (streak state) | `core/streak.py::StreakManager` (DEC-62-STREAK-001) | UNCHANGED | Only the return shape of `update()` changes — F62 still owns the file. |
| `StreakUpdate` return value | (did not exist) | `core/streak.py::StreakManager.update()` | Read-only typed snapshot; not a second mutable authority. |
| `score_events` table (point-bearing events) | `core/workspace.py::WorkspaceManager.store_score_events` | UNCHANGED | New action keys `streak_continued` and `milestone_announced` plug into the existing table; no schema change. |
| `last_milestone_announced` per workspace | (did not exist; DEC-CELEBRATION-002 silently swallowed) | `score_events` rows with `action="milestone_announced", points=0, indicator=str(threshold)` | Sentinel-row authority. Read via new `WorkspaceManager.get_announced_milestone_thresholds()`. Idempotency is the `SELECT WHERE action='milestone_announced' AND indicator=…` query. |
| Milestone trigger logic | `CelebrationEngine.milestone_message(total_score)` (exact-hit, DEC-CELEBRATION-002) | `CelebrationEngine.crossed_milestones(previous_total, current_total) -> list[int]` + `milestone_message(threshold)` (formatter) | Pure functions over the MILESTONES table; do not touch workspace state. Console + agent orchestrate. |
| `streak_continued` point computation | (did not exist) | `gamification/scoring.py::streak_continued_points(current_streak)` | Pure step-decay function; documented bands. |
| Streak update wiring | `APConsole._execute_hunt`, `ToolContext.run_module` (DEC-62-STREAK-007) | SAME two call sites | F63 inherits F62's no-touch-modules invariant; new streak_continued ScoreEvent fires from the same two sites only. |
| Milestone announcement wiring | (none — was broken) | `APConsole._execute_hunt`, `ToolContext.run_module` | Same two surfaces. cmd2 prints `MILESTONES[threshold]` to Rich panel; agent path appends to the existing `celebration` sidecar (DEC-64-LLM-PANEL-SEPARATION-001 preserved). |

### Architecture Decisions

**DEC-63-MILESTONE-CATCHUP-001 — `score_events` sentinel rows are the sole authority for `last_milestone_announced` per workspace.**

Three options were considered:

- **Option (a) — workspace metadata JSON field.** Would require a new SQLAlchemy column on a new `WorkspaceMeta` model. Touches `models/database.py` which is a forbidden_path for this slice (single-slice scope discipline) AND violates DEC-DB-002 (no migrations in v1).
- **Option (b) — separate `~/.ap/milestones.json` file.** Creates a parallel state file alongside `~/.ap/streak.json`, multiplying the surface area that has to be atomically-written, corruption-recovered, and clock-skew-defended. Adds a second authority for per-workspace milestone state living *outside* the workspace database — directly violates DEC-WS-001 (one SQLite file per workspace, no shared state).
- **Option (c) — `score_events` sentinel rows** (CHOSEN). Reuse the existing `ScoreEvent` table that already houses non-discovery events (`hint_purchase` rows carry negative points; F63 adds zero-point milestone-announcement sentinels). The query authority is `SELECT WHERE action='milestone_announced' AND indicator='<threshold>'`. Idempotency is the existence check. `points=0` keeps `get_total_score()` unaffected. No schema change. Workspaces are still portable / deletable / inspectable as single SQLite files (DEC-WS-001 preserved). Mirrors the established AP idiom (`hint_purchase` already piggybacks on ScoreEvent for non-discovery point-bearing events).

The catch-up logic itself: `CelebrationEngine.crossed_milestones(previous_total, current_total)` returns the integer thresholds strictly crossed during this hunt in ascending order. Orchestrator (console or agent) intersects that list with `WorkspaceManager.get_announced_milestone_thresholds()` and announces only the new ones, then `record_milestone_announcement(threshold)` writes the sentinel iff missing (and returns True). The return-True gate is the only thing that prints — guarantees a milestone is never announced twice for the same workspace, even if two parallel calls race (SQLAlchemy session.commit serializes; the second call sees the first's row).

Migration (DEC-63-MIGRATION-001): on first orchestration call in a workspace that has zero `milestone_announced` sentinel rows AND `get_total_score() > 0`, `seed_milestone_baseline_if_unset()` inserts sentinel rows for every threshold ≤ current total. Quiet-start: an upgraded workspace at score 1200 does NOT fire First Century / Half a Grand / Grand Master on the first hunt after upgrade — those announcements would be archaeological, not aspirational.

**DEC-63-STREAK-SCORE-001 — `streak_continued` is a ScoreEvent row, step-decay 10/5/2 over bands [1–7, 8–30, 31+], fires only when `StreakUpdate.incremented` is True.**

Event shape: `{"action": "streak_continued", "points": <decayed>, "indicator": "day-<N>", "rule_description": "Streak day N"}`. Plugs into the existing `WorkspaceManager.store_score_events` path with no schema change (parallel to how `hint_purchase` events ride the same table).

Decay choice: step function `{1-7: 10, 8-30: 5, 31+: 2}`. Considered alternatives:

- **Linear `10 - day` capping at 0** rejected — hits zero by day 11, removes all signal exactly when long-streak retention is hardest to earn (the most valuable users get the smallest reward).
- **Exponential `10 * 0.9^(day-1)`** rejected — non-integer points, opaque rationale, hard to test pin (every test would have to compute a float).
- **Step `{1-7: 10, 8-30: 5, 31+: 2}`** (CHOSEN) — integer points, readable for users (`do_score` table shows clean numbers), three pin-able bands (7-test coverage), floor never reaches zero so streak always carries some score signal. Anti-farming: total weekly cap is bounded (max 70 pts/week early, then 35, then 14). The decreasing-but-non-zero floor matches Duolingo's "you still get something" philosophy that mapped well in F62.

Hook point: identical to F62 — `APConsole._execute_hunt` (cmd2) and `ToolContext.run_module` (agent), AFTER the existing `streak_mgr.update(date.today())` call, gated on `update.incremented`. The same DEC-62-STREAK-007 invariant (modules do not touch streak) holds for F63's score-event side-effect.

Per-day idempotency: comes for free from F62. Same-day `update()` returns `incremented=False` (already-recorded), so no second streak_continued row fires the same day.

**DEC-63-MIGRATION-001 — Quiet-start: seed milestone sentinel rows on first orchestration after upgrade so retroactive announcements are suppressed.**

Loud option: an upgraded workspace at total=1200 would fire 3 announcements on the first hunt after upgrade. Considered briefly; rejected as user-hostile (the announcements would be lying about *when* the milestones were earned).

Quiet option (CHOSEN): `seed_milestone_baseline_if_unset()` runs at the orchestrator's call site BEFORE the cross-threshold check on every hunt. On first invocation in a workspace with no sentinel rows AND `get_total_score() > 0`, it inserts sentinel rows for every threshold ≤ current_total. The same hunt's cross-threshold check then only fires for thresholds strictly greater than the seeded baseline — typically zero new announcements on the first hunt post-upgrade.

For brand-new workspaces (zero score, zero sentinel rows), the seed is a no-op — first cross fires normally.

### Wave Decomposition

Single wave; one implementer slice. Test-first internal ordering (write the unit tests for celebrations/scoring/workspace pure functions, then implement; then write streak return-type tests, then implement; then write the console + agent integration tests, then wire the orchestration).

| W-ID | Title | Weight | Gate | Deps | Integration |
|------|-------|--------|------|------|-------------|
| `wi-63-impl-01` | Cross-threshold milestone catch-up + streak_continued score event (one feature commit) | L | review | none | `gamification/celebrations.py`, `gamification/scoring.py`, `core/workspace.py`, `core/streak.py`, `core/console.py`, `agent/tools.py`, `tests/test_celebrations.py`, `tests/test_streak.py`, `tests/test_workspace.py`, `tests/test_scoring.py`, `tests/test_console.py`, `tests/test_agent_tools.py` |

Critical path: one slice; max width 1. Reviewer-fixup commits are permitted on the same branch as a separate commit (precedent: F62 `8b0faa2`, F61 `5a5b8e1`).

### Scope Manifest (wi-63-impl-01)

Runtime authority: `cc-policy workflow scope-get w-63-milestone-catchup` (synced via `scope-sync` from `tmp/f63-scope.json`).

- **Allowed paths:** `src/adversary_pursuit/gamification/celebrations.py`, `src/adversary_pursuit/gamification/scoring.py`, `src/adversary_pursuit/core/workspace.py`, `src/adversary_pursuit/core/streak.py`, `src/adversary_pursuit/core/console.py`, `src/adversary_pursuit/agent/tools.py`, `tests/test_celebrations.py`, `tests/test_scoring.py`, `tests/test_workspace.py`, `tests/test_streak.py`, `tests/test_console.py`, `tests/test_agent_tools.py`, `MASTER_PLAN.md`.
- **Required paths:** `src/adversary_pursuit/gamification/celebrations.py`, `src/adversary_pursuit/core/streak.py`, `src/adversary_pursuit/core/console.py`, `src/adversary_pursuit/agent/tools.py`, `tests/test_celebrations.py`, `tests/test_streak.py`, `MASTER_PLAN.md`.
- **Forbidden paths:** `src/adversary_pursuit/models/**` (no schema change — DEC-DB-002), `src/adversary_pursuit/modules/**` (no-touch-modules invariant), `src/adversary_pursuit/gamification/badges.py`, `src/adversary_pursuit/gamification/challenges.py`, `src/adversary_pursuit/gamification/hints.py`, `src/adversary_pursuit/gamification/modes.py`, `src/adversary_pursuit/core/pivot_policy.py` (F60), `src/adversary_pursuit/core/event_bus.py`, `src/adversary_pursuit/core/error_interpreter.py`, `src/adversary_pursuit/core/graph.py`, `src/adversary_pursuit/core/report.py`, `src/adversary_pursuit/core/config.py`, `src/adversary_pursuit/core/plugin_mgr.py`, `src/adversary_pursuit/agent/runner.py`, `src/adversary_pursuit/agent/chat.py` (F64 surface unchanged), `src/adversary_pursuit/agent/banner.py`, `src/adversary_pursuit/agent/error_handler.py`, `src/adversary_pursuit/agent/provider_setup.py`, `src/adversary_pursuit/agent/repl_input.py`, `pyproject.toml`, `CLAUDE.md`, `AGENTS.md`, `agents/**`, `hooks/**`, `.claude/**`, `.github/**`, `settings*.json`.
- **State-authority domains touched:** `score_events_table`, `milestone_announcement_sentinel`, `streak_score_event`, `streak_update_return_shape`, `celebration_cross_threshold_api`.

### Evaluation Contract (9-key, wi-63-impl-01)

Runtime authority: stored on `wi-63-impl-01.evaluation_json` (loaded from `tmp/f63-evaluation.json` via `work-item-set --evaluation-json`).

- **required_tests:** 36 tests across 6 files (full list in runtime; summarised below):
  - `tests/test_celebrations.py::TestMilestoneCrossThreshold` (7 tests) — exact-hit preserved, 99→105 fires First Century, 99→1001 fires two milestones in ascending order, already-announced does not refire, below-first returns empty, legacy `milestone_message(threshold)` formatter still works.
  - `tests/test_workspace.py::TestMilestoneAnnouncementSentinel` (5 tests) — record persists sentinel row, read-back returns the announced set, sentinels carry `points=0` and do not affect `get_total_score()`, record is idempotent on repeat call, baseline-seed on first hunt in high-score workspace produces no spurious announcement.
  - `tests/test_streak.py::TestStreakUpdateReturn` (8 tests) — consecutive day → `incremented=True`, same-day → `incremented=False`, freeze-bridge → `incremented=True` AND `frozen_used=True`, break → `reset=True`, first-ever → `incremented=True`, backward clock skew → `incremented=False` AND `reset=False`, `current_streak` matches `state.current_streak`.
  - `tests/test_scoring.py::TestStreakContinuedDecay` (7 tests) — pin every band boundary: day 1/7=10, day 8/30=5, day 31/365=2, floor never zero.
  - `tests/test_console.py` (4 tests) — `_execute_hunt` fires streak_continued on consecutive day, NOT on same day, announces First Century on cross-threshold jump, does NOT double-announce on subsequent run.
  - `tests/test_agent_tools.py` (5 tests) — `run_module` fires streak_continued, no same-day duplicate, celebration sidecar contains First Century on cross, does NOT repeat after announced, records milestone sentinel row.

- **required_evidence:** `tmp/evidence-63-milestone-catchup/` containing `pytest_targeted.txt` (36-test slice), `pytest_full_celebrations.txt`, `pytest_full_streak.txt`, `pytest_full_workspace.txt`, `pytest_full_scoring.txt`, `pytest_full_console.txt`, `pytest_full_agent_tools.txt`, `pytest_full_suite.txt`, `ruff_clean.txt`, `diff_summary.txt`, `manual_cross_threshold_demo.txt`.

- **required_real_path_checks (6):**
  1. Cross-threshold catch-up via cmd2 surface — seed workspace to 99 pts, hunt scores +20, assert one sentinel `indicator='100'` row inserted AND Rich console shows First Century text.
  2. Idempotency via cmd2 surface — second hunt immediately after path A inserts no second `indicator='100'` sentinel and prints no milestone text.
  3. Multi-threshold jump via agent surface — seed at 99, score +905 (post-total 1004), assert TWO sentinel rows (`100`, `500`) and `result['celebration']` contains BOTH milestone substrings in ascending order.
  4. `streak_continued` via cmd2 surface — inject StreakManager with `tmp_path/streak.json`; two consecutive dates each produce a `streak_continued` row with `points=10`; same-day repeat produces no extra rows.
  5. `streak_continued` decay band via agent surface — 9 consecutive simulated dates; rows show `points=10` days 1–7 and `points=5` days 8–9.
  6. Migration quiet-start — new workspace seeded directly with score 1200; first hunt seeds sentinel rows for `100/500/1000` AND emits no milestone celebration text.

- **required_authority_invariants (8):**
  - `score_events` remains sole authority for per-workspace point-bearing AND milestone-announcement state; NO new SQLAlchemy model; NO separate JSON file.
  - `StreakManager` remains sole authority for `~/.ap/streak.json` (DEC-62-STREAK-001 preserved); `StreakUpdate` is a read-only typed snapshot, NOT a second mutable authority.
  - `CelebrationEngine` remains pure formatting layer; `crossed_milestones` is a pure function and does NOT touch workspace state.
  - `modules/**` MUST NOT call milestone or streak machinery directly (DEC-62-STREAK-007 invariant extended).
  - `ScoreEvent.points` contract: `streak_continued` rows carry positive points equal to decay band; `milestone_announced` sentinel rows carry `points=0` so `get_total_score()` is unaffected by sentinel insertion.
  - F59 STIX provenance, F60 pivot policy, F61 keyless hunters, F62 streak mechanic, F64 LLM-summary separation invariants preserved bytewise on owned files.
  - DEC-CELEBRATION-002 is SUPERSEDED by DEC-63-MILESTONE-CATCHUP-001 and explicitly marked superseded in `celebrations.py`; no parallel exact-hit path remains.
  - DEC-64-LLM-PANEL-SEPARATION-001 contract preserved: streak_continued rows appear in `score_events` list and per-event lines, but no streak-narration prose is added to the LLM-facing summary string.

- **required_integration_points (10):** see runtime evaluation JSON for the canonical list. High-level: `celebrations.py` adds `crossed_milestones` and renames the legacy formatter arg to `threshold`; `workspace.py` adds `record_milestone_announcement`, `get_announced_milestone_thresholds`, `seed_milestone_baseline_if_unset`; `streak.py` changes `update()` to return `StreakUpdate`; `scoring.py` adds `streak_continued_points`; `console.py::_execute_hunt` and `agent/tools.py::run_module` get the parallel orchestration refactor (capture `prev_total`, seed baseline, compute crossed, record + announce, fire streak_continued event). All 6 new test files/classes ship in the same commit.

- **forbidden_shortcuts (9):**
  - NO new SQLAlchemy model (would touch `models/database.py` — forbidden_path; creates parallel authority).
  - NO env-var or feature-flag bypass — this is bug-fix, not opt-in behavior change.
  - NO snapshot-and-diff streak detection (read `current_streak` before/after `update()`) — the StreakManager must own the typed return.
  - NO `last_milestone_announced` in workspace JSON, `~/.ap/milestones.json`, or any new file.
  - NO double-printing milestone text (the `record_milestone_announcement` return-bool MUST be the only print gate).
  - NO firing streak_continued when `StreakUpdate.incremented` is False.
  - NO leak of streak_continued narration into LLM-facing summary string (DEC-64-LLM-PANEL-SEPARATION-001 invariant).
  - NO module-level call into `StreakManager` or `CelebrationEngine.crossed_milestones` (DEC-62-STREAK-007 invariant).
  - NO touching `gamification/badges.py`, `gamification/challenges.py`, `gamification/hints.py`, `gamification/modes.py` — slice is milestones + streak-as-score-event ONLY.

- **rollback_boundary:** single revertable feature commit on `feature/63-milestone-catchup` (reviewer-fixup commits acceptable as separate commits, ala F62 `8b0faa2`, F61 `5a5b8e1`). Revert restores DEC-CELEBRATION-002 exact-hit behavior; `streak_continued` and `milestone_announced` rows in workspace databases remain as inert zero-effect history on revert (the `score` cmd2 table simply displays them as unknown actions; `get_total_score()` is unaffected for milestones and accurate for streaks).

- **acceptance_notes:** live demo against a fresh `ap chat` session: (1) seed default workspace to 99 points via a real hunt; (2) run a second hunt that crosses 100 — observe First Century milestone text in the Rich panel surface; (3) run a third hunt that scores more but stays below 500 — observe NO repeat First Century text; (4) run a hunt on a second date (via injected `date.today` for the demo) — observe a `+10 streak_continued` line in the Recent Scoring Events table when `score` is invoked. Compound Atwood acceptance: the 99→105 catch-up demo PRODUCES the celebration the original assessment said was being swallowed by arithmetic, and the streak day-7 demo PRODUCES the feedback signal the score economy was missing.

- **ready_for_guardian_definition:** all 36 required tests PASS at HEAD; full pytest suite PASS at HEAD (no regressions vs base `ba110a5` — the 1 pre-existing skip is allowed); `ruff` clean on changed files; all 6 required_real_path_checks evidenced in `tmp/evidence-63-milestone-catchup/`; git diff touches only allowed_paths (no `models/**`, no `modules/**`, no `runner.py`/`chat.py`); DEC-63-MILESTONE-CATCHUP-001, DEC-63-STREAK-SCORE-001, DEC-63-MIGRATION-001 recorded in this Phase 12C decision-log block AND as `@decision` annotations at the canonical source sites; DEC-CELEBRATION-002 explicitly marked superseded with backpointer to DEC-63-MILESTONE-CATCHUP-001; reviewer issues `REVIEW_VERDICT=ready_for_guardian`.

### Decision Log (Phase 12C)

| DEC ID | File / Surface | Rationale |
|--------|----------------|-----------|
| DEC-63-MILESTONE-CATCHUP-001 | `gamification/celebrations.py`, `core/workspace.py`, `core/console.py`, `agent/tools.py` | Replace exact-hit milestone gating (DEC-CELEBRATION-002, SUPERSEDED) with cross-threshold detection. Authority for `last_milestone_announced` is `score_events` sentinel rows (`action='milestone_announced'`, `points=0`, `indicator=<threshold>`) — reuses the existing per-workspace state authority (DEC-WS-001), avoids `models/**` edits, and idempotency is the existence query. `CelebrationEngine.crossed_milestones(prev, curr) -> list[int]` is a pure function; the orchestrator (console + agent) records and announces. Rejected: workspace metadata column (touches forbidden `models/**` and violates DEC-DB-002 no-migrations); separate `~/.ap/milestones.json` (parallel authority — violates DEC-WS-001 and CLAUDE.md Sacred Practice 12). |
| DEC-63-STREAK-SCORE-001 | `gamification/scoring.py`, `core/streak.py`, `core/console.py`, `agent/tools.py` | Add `score_events` action `streak_continued` with step decay 10/5/2 over bands [1–7, 8–30, 31+]. Decay is non-zero at all bands so retention always carries score signal; bands are pin-able with finite tests; bounded weekly maximum prevents farming. `StreakManager.update()` is extended to return a typed `StreakUpdate(incremented, frozen_used, reset, current_streak)`; orchestrator fires the new ScoreEvent iff `update.incremented` is True. Rejected: linear `10-day` decay (hits zero by day 11, removes signal exactly when long-streak users need it most); exponential `0.9^d` (non-integer points, opaque rationale); snapshot-and-diff streak detection (racy, inverts authority direction). |
| DEC-63-MIGRATION-001 | `core/workspace.py`, `core/console.py`, `agent/tools.py` | Quiet-start migration: on first orchestration call in a workspace with zero `milestone_announced` sentinel rows AND `get_total_score() > 0`, `seed_milestone_baseline_if_unset()` inserts sentinel rows for every threshold ≤ current total. Suppresses retroactive announcements that would lie about *when* the milestone was earned. For brand-new workspaces (zero score), seed is a no-op so the first cross still fires normally. |
| DEC-CELEBRATION-002 (SUPERSEDED) | `gamification/celebrations.py` (annotation block) | Mark superseded with backpointer to DEC-63-MILESTONE-CATCHUP-001. The exact-hit behaviour was an architectural bug, not an accepted constraint; F63 reverses the decision. |

### What is NOT in scope

- **Schema changes.** `models/database.py` is forbidden. No new model, no new column, no migration tooling. The score_events sentinel pattern fits the existing schema.
- **Module-level changes.** All 11 modules under `modules/**` are untouched — F63 inherits and preserves DEC-62-STREAK-007 (modules don't touch streak/milestone authorities).
- **Gamification surfaces beyond celebrations + scoring.** `badges.py`, `challenges.py`, `hints.py`, `modes.py` are untouched.
- **Agent presentation surface.** `runner.py`, `chat.py`, `banner.py` are untouched — F64 invariants preserved. The milestone text rides on the existing `celebration` sidecar that F64 already wired through to the Rich Panel.
- **Streak banner display.** Streak panel as a Rich Panel surface remains a follow-up (filed in F64's "Streak panel surface" follow-ups section).
- **Pivot policy / event bus / STIX provenance.** F59 / F60 invariants preserved by forbidden_paths.

### Follow-ups (not in F63)

- **Streak panel surface.** Once F63 lands the streak_continued ScoreEvent rows, a future slice may add a Rich Panel that surfaces streak retention with mode-flavored persona text (this is the F64 "Streak panel surface" follow-up, now with score-event data to render).
- **Configurable milestone thresholds.** `MILESTONES` is hardcoded; a future slice may allow per-workspace or per-mode milestone overrides. Out of scope here.
- **Streak score-event display formatting.** Today the `do_score` table shows raw `streak_continued` rows — a future slice may add an icon column or band-label column (e.g. "🔥 streak day 7"). Out of scope here; the goal of F63 is the signal existing, not the formatting polish.
- **Atwood [P2] item 3** (any third Atwood [P2] note from the same gamification assessment that isn't milestones or streak-economy): track via new GitHub issue once the assessment's third bullet is itemised. Out of scope for F63.

---

## Phase 13: De-duplicate LLM narration vs Rich Panel for gamification events (W-64-DEDUP-LLM-NARRATION, post-v1, 2026-05-26)

> **Status:** completed (landed 2026-05-26, merge `3b92032 Merge feature/64-dedup-llm-narration (#64)`, work commit `e460b41`) · **Workflow:** `w-64-dedup-llm-narration` · **Branch:** `feature/64-dedup-llm-narration` · **Worktree:** `.worktrees/feature-64-dedup-llm-narration` · **GitHub issue:** #64

### Problem

The agent path narrates every gamification event twice. When the LLM completes a tool call that earns a badge or completes a challenge, two things happen:

1. **`tools.py::ToolContext.run_module()`** appends gamification text directly into the LLM-facing `summary` field (lines 540–566): `Badge(s) earned: [LEGENDARY] Supreme Hunter: …` and `Challenge(s) completed: …`. The LLM reads this tool result as a `tool`-role conversation message and dutifully narrates the award in its next assistant response.
2. **`chat.py:632–666`** then renders a separate Rich Panel for the same celebration (lines 638–646) and for each newly-earned badge (lines 657–666) immediately after the LLM response prints.

The user sees the same badge named twice: once in the LLM's prose, once in the panel. Atwood (user) called the discipline boundary explicitly: "Pick one: either the LLM gets to be the announcer, or the panel does. Not both." The panel is the gamification surface; the LLM should react to the **discovery** (IOCs, +points, pivot opportunities) without naming the badge.

A parallel gap exists for challenges: `result['challenges']` is populated in `run_module` but the agent runner has **no `last_challenges` accumulator** and `chat.py` has **no challenge-panel render loop** — so challenges currently leak only into the LLM summary string. The cleanup must also build the missing challenge-panel surface, otherwise removing challenge text from `summary` silently deletes user-visible challenge announcements.

### Goal

After F64:

- The LLM-facing tool summary contains ONLY findings: `Found N indicators:`, the type/value lines (up to 10), the `+{total} points!` line and per-event scoring breakdown, and the `Auto-pivoted: K additional discoveries from M cascaded module subscriptions.` line when cascades fire.
- The LLM-facing summary contains NO badge name/rarity/description, NO celebration ASCII art, NO `first_blood_message`, NO challenge name, and NO streak phrasing.
- `result['badges']`, `result['celebration']`, and `result['challenges']` continue to carry the full typed payload — these sidecar fields are the single source of truth for the Rich Panel surfaces.
- `chat.py` renders the same user-visible badge + celebration panels as pre-F64, **plus** a new challenge panel loop driven by `runner.last_challenges`.
- `runner.last_challenges` is populated by `AgentRunner.chat()` from `result['challenges']`, parallel to `last_badges` and `last_celebrations`.

### State-Authority Map

| Domain | Pre-F64 owner | Post-F64 owner | Notes |
|--------|---------------|----------------|-------|
| LLM-visible tool result text | `ToolContext.run_module` summary composition (`summary_lines`) | `ToolContext.run_module` summary composition (`summary_lines`) | Same authority, narrower content scope. |
| Panel payload (typed) | `result['badges']` + `result['celebration']` + `result['challenges']` in `run_module` | Same — UNCHANGED authority and shape | Sidecar fields ARE the panel surface; their typed structure is preserved. |
| Agent-side panel accumulator | `runner.last_badges`, `runner.last_celebrations` | **Add** `runner.last_challenges` | Closes a pre-existing gap: challenges had no panel surface. |
| Rich panel rendering | `chat.py:632–666` (celebration + badge loops) | `chat.py:632–666` plus new challenge loop | Renders typed objects only; never parses `summary`. |
| Badge/Celebration/Challenge/Streak emission | `gamification/badges.py`, `gamification/celebrations.py`, `gamification/challenges.py`, `core/streak.py` | **UNCHANGED** | F64 is at the agent-presentation boundary, NOT the gamification-emission boundary. |

### Architecture Decision

DEC-64-LLM-PANEL-SEPARATION-001 — Adopt the **sidecar-payload (option-c) design** with a single source of truth in `run_module`. The composer in `run_module` emits two parallel surfaces from one place: the LLM-facing `summary` string (findings only) and the typed panel-payload sidecars (`badges`, `celebration`, `challenges`). `chat.py` never parses the summary string; it reads `runner.last_*` typed accumulators only.

Alternatives considered and rejected:

- **Option (a) — two separate compose calls** (`llm_summary` and `panel_payload` as independent producers): rejected. Would duplicate the findings-extraction logic in two functions, increasing the chance of divergence (CLAUDE.md Sacred Practice 12 — single source of truth).
- **Option (b) — build one summary then regex-filter at the LLM boundary**: rejected by Atwood directly: "no string-filtering fragility." Build-then-filter is brittle; the gamification emission text format can change without the filter noticing, silently re-leaking the legacy text into the LLM context.
- **Option (c) — sidecar payload, one composer** (CHOSEN): the summary composer in `run_module` simply omits gamification lines; the panel-payload sidecars are already returned in the result dict; chat.py and runner are extended to consume the challenge sidecar (the only missing accumulator). This is the unified-implementation answer that respects Sacred Practice 12 and the existing badge-channel architecture.

### Wave Decomposition

Single wave; one implementer slice.

| W-ID | Title | Weight | Gate | Deps | Integration |
|------|-------|--------|------|------|-------------|
| `wi-64-impl-01` | Strip gamification text from LLM summary; add challenge-panel surface | M | review | none | `agent/tools.py`, `agent/chat.py`, `agent/runner.py`, `tests/test_agent_tools.py` |

Critical path: one slice; max width 1.

### Scope Manifest (wi-64-impl-01)

Runtime authority: `cc-policy workflow scope-get w-64-dedup-llm-narration` (synced via `scope-sync` from `tmp/f64-scope.json`).

- **Allowed paths:** `src/adversary_pursuit/agent/tools.py`, `src/adversary_pursuit/agent/chat.py`, `src/adversary_pursuit/agent/runner.py`, `tests/test_agent_tools.py`, `MASTER_PLAN.md`.
- **Required paths:** `src/adversary_pursuit/agent/tools.py`, `src/adversary_pursuit/agent/chat.py`, `src/adversary_pursuit/agent/runner.py`, `tests/test_agent_tools.py`.
- **Forbidden paths:** `src/adversary_pursuit/gamification/**`, `src/adversary_pursuit/core/streak.py`, `src/adversary_pursuit/core/pivot_policy.py`, `src/adversary_pursuit/core/workspace.py`, `src/adversary_pursuit/core/event_bus.py`, `src/adversary_pursuit/modules/**`, `src/adversary_pursuit/console/**`, `pyproject.toml`, `.claude/**`, `settings*.json`, `agents/**`, `hooks/**`, `CLAUDE.md`, `AGENTS.md`.
- **Authority/state domains touched:** `llm_tool_summary`, `panel_payload`, `agent_runner_panel_state`.

### Evaluation Contract (9-key, wi-64-impl-01)

Runtime authority: stored on `wi-64-impl-01.evaluation_json` (loaded from `tmp/f64-evaluation.json` via `work-item-set --evaluation-json`).

- **required_tests** (16 named tests in `tests/test_agent_tools.py`):
  1. `test_llm_summary_excludes_badge_text` — summary contains no "Badge(s) earned" or earned badge name/rarity/description.
  2. `test_llm_summary_excludes_challenge_text` — summary contains no "Challenge(s) completed" or completed challenge name.
  3. `test_llm_summary_excludes_celebration_art` — summary contains no CelebrationEngine ASCII art tokens or active mode's score_celebration template.
  4. `test_llm_summary_excludes_first_blood_text` — when badge-first-blood is awarded, summary contains no `first_blood_message()` output (it remains on `result['celebration']`).
  5. `test_llm_summary_excludes_streak_text` — summary mentions no streak state across consecutive-date `run_module` calls.
  6. `test_llm_summary_keeps_findings_and_points` — summary still contains `Found {N} indicators`, type/value lines (≤10), `+{total} points!`, and per-event scoring breakdown.
  7. `test_llm_summary_keeps_autopivot_count` — summary still contains `Auto-pivoted: K additional discoveries from M cascaded module subscriptions.` when cascades fire.
  8. `test_panel_payload_carries_badges` — `result['badges']` still returns the full `list[Badge]`.
  9. `test_panel_payload_carries_challenges` — `result['challenges']` still returns the full `list[Challenge]`.
  10. `test_panel_payload_carries_celebration` — `result['celebration']` still returns the ASCII art + mode score line + optional milestone + optional first_blood prefix.
  11. `test_runner_last_challenges_populated` — `AgentRunner.chat()` accumulates `result['challenges']` into `runner.last_challenges`.
  12. `test_chat_renders_badge_panel_unchanged` — existing badge-panel render still matches pre-F64 user-visible bytes.
  13. `test_chat_renders_challenge_panel` — `chat.py` renders a new Rich Panel per item in `runner.last_challenges`.
  14. `test_chat_renders_celebration_panel_unchanged` — existing celebration-panel render still matches pre-F64 user-visible bytes.
  15. `test_compound_hunt_badge_only_panel_user_visible` — compound integration: LLM tool-role message has no badge name; mocked console shows exactly one badge panel + one celebration panel + one challenge panel.
  16. `test_existing_badge_in_summary_test_inverted` — the legacy `test_badge_info_appended_to_llm_summary` and `test_run_module_challenge_in_summary` are intentionally inverted/replaced; both replacement tests cite DEC-64-LLM-PANEL-SEPARATION-001 in their docstrings.

- **required_evidence:** `tmp/evidence-64-dedup-llm-narration/` containing `pytest_targeted.txt` (16-test slice), `pytest_full_agent_tools.txt` (full file), `pytest_full_suite.txt` (full repo), `ruff_clean.txt`, `diff_summary.txt`.

- **required_real_path_checks:** (a) high-score `ToolContext` → `execute_tool('check_ip_reputation', ...)` → `AgentRunner.chat()` → mocked console; assert LLM tool-role message contains no badge name and exactly one of each panel renders; (b) two-date streak update across two `run_module` calls produces no streak text in either summary.

- **required_authority_invariants:** `gamification/**`, `modules/**`, `core/streak.py`, `core/pivot_policy.py`, `core/event_bus.py`, `core/workspace.py` unchanged; F59/F60/F62 invariants preserved; DEC-AGENT-BADGES-001 / DEC-AGENT-CHALLENGES-001 surface contracts preserved; `run_module` is the sole composer of (summary, badges, challenges, celebration); chat.py never parses the summary string.

- **required_integration_points:**
  1. `agent/tools.py:540–578` — remove the Badge and Challenge text blocks from `summary_lines`; keep findings/+points/auto-pivot blocks; return dict shape unchanged.
  2. `agent/runner.py:165–206` — add `self.last_challenges: list[Challenge] = []` and thread `result['challenges']` through `execute_tool`.
  3. `agent/tools.py:1344–1452` — `execute_tool` return contract: extend to a 4-tuple `(summary, celebration, badges, challenges)` (recommended), updating all 14 return sites. Workspace meta-tools / hints / report tools return `[]` for challenges (parallel to badges).
  4. `agent/chat.py:632–666` — add a third Rich-Panel loop after badges, iterating `runner.last_challenges` with consistent styling.

- **forbidden_shortcuts:** no env-var bypass; no build-then-regex-filter; no silent dropping of all summary content; no chat.py parsing of `summary`; no edits to `gamification/**`, `modules/**`, `core/streak.py`, `core/pivot_policy.py`, `core/workspace.py`, `core/event_bus.py`; no new state authority for gamification text; no removal of typed sidecar payload fields.

- **rollback_boundary:** single revertable feature commit on `feature/64-dedup-llm-narration`. All four file changes ship in one commit so there is no partial migration.

- **acceptance_notes:** live `ap chat` against a real LLM with workspace seeded to ~99 points and a hunt that crosses 100 → LLM narrates IOCs + `+points` + pivot opportunity without naming the Century badge; exactly one Achievement Unlocked panel + one Badge Earned! panel + (if applicable) one Challenge panel render below.

- **ready_for_guardian_definition:** all 16 required tests PASS; full pytest suite PASS; ruff clean on changed files; `result['summary']` text-free of gamification names/art/messages across all scenarios; sidecar payloads unchanged in shape and content; `runner.last_challenges` populated; chat.py renders all three panel surfaces; evidence files exist; git diff touches only allowed-scope files; DEC-64-LLM-PANEL-SEPARATION-001 recorded here.

### Decision Log (Phase 13)

| DEC ID | Decision | Rationale |
|--------|----------|-----------|
| DEC-64-LLM-PANEL-SEPARATION-001 | Sidecar-payload, single-composer split (option c). `run_module` emits the LLM-facing summary (findings only) AND the typed panel-payload sidecars (`badges`, `celebration`, `challenges`) from one place. `chat.py` reads typed `runner.last_*` accumulators only; never parses the summary string. Add the missing `runner.last_challenges` accumulator + `chat.py` challenge-panel loop in the same commit. | Atwood's discipline boundary: "Pick one — either the LLM gets to be the announcer, or the panel does. Not both." Build-then-filter (option b) was explicitly rejected as fragile. Two-composer (option a) would duplicate findings-extraction logic (Sacred Practice 12 violation). Option c keeps the single source of truth in `run_module`, preserves the typed sidecar contract that's already wired through for badges/celebration, and closes the pre-existing challenge-panel gap in the same change so we don't leave addition-without-subtraction behind. The split is unconditional (no env-var bypass) because dual-authority "transition aid" creates exactly the drift this slice exists to eliminate. |

### What is NOT in scope

- **Changing gamification emission.** `BadgeManager`, `CelebrationEngine`, `ChallengeManager`, `StreakManager` are NOT touched. Their outputs are unchanged; only their presentation at the agent boundary is reorganized.
- **The cmd2 REPL surface.** `console.py` renders its own gamification panels via the Rich console directly; that path was never double-narrating because there is no LLM in the loop. No `console/**` changes.
- **Streak surface design.** F62 deliberately kept streak as a side-effect-only update (no surfacing). F64 codifies that "no streak text in LLM summary" is now an invariant (test 5). A future slice may add a streak panel; that is out of scope here.
- **Module-level changes.** All 11 modules under `modules/**` are untouched.
- **STIX/provenance / autopivot policy / event bus.** F59 / F60 invariants are preserved by forbidden-paths.

### Follow-ups (not in F64)

- **Streak panel surface.** Today streak state has no user-visible Rich Panel either; once the LLM-summary leak is closed, a future slice may add a streak Rich Panel parallel to badge/challenge surfaces.
- **Persona-aware panel styling.** Modes (`ModeManager`) already influence the celebration string; panels could pick up mode color palettes. Filed as a follow-up.

---

## Phase 14: Keyless Hunter Modules — abuse.ch family + Certificate Transparency (W-61-KEYLESS-HUNTERS, post-v1, 2026-05-26)

> **Status:** completed (landed 2026-05-26, merge `556f873 Merge feature/61-keyless-hunters (#61)`, two work commits `bce981f` + `5a5b8e1` reviewer fixup) · **Workflow:** `w-61-keyless-hunters` · **Goal:** `g-61-keyless-hunters` · **Branch:** `feature/61-keyless-hunters` · **Worktree:** `.worktrees/feature-61-keyless-hunters` · **GitHub issue:** #61

### Problem

Threat-Hunter advisory (2026-05): the v0.1.0 module catalog covers 11 sources but is heavily key-gated. New users hitting `ap chat` for the first time face a SKIP wall — every CTI/OSINT module except `dns_resolve` and `whois_lookup` requires a configured API key before it returns evidence. The "first five minutes" experience is degraded: the agent demos beautifully on a key-fed dev box and silently gates on a fresh user's machine. Two missing capability axes are also material:

1. **No abuse.ch coverage.** abuse.ch operates three of the most-cited free OSINT/CTI services in modern hunting workflows (URLhaus, ThreatFox, MalwareBazaar). All three are keyless and serve JSON over HTTPS. Their absence means AP cannot answer "is this URL on the URLhaus blocklist?", "is this IOC in ThreatFox?", or "what's the metadata on this sample hash?" — three of the highest-value first-pass questions in a threat-hunting flow.
2. **No Certificate Transparency search.** crt.sh is the canonical free interface for CT log discovery (subdomain enumeration, certificate-pivoting against a target apex). Without it the agent cannot answer "what subdomains has this domain registered TLS certs for?" — a foundational pivot for any infrastructure-mapping investigation.

The slice fills both gaps with strictly-keyless modules so the fresh-install experience demonstrates real evidence return on the first query.

### Goal

After F61:

- AP ships **15 catalog modules** (up from 11): existing 11 + `cti/urlhaus` + `cti/threatfox` + `cti/malwarebazaar` + `osint/crtsh`.
- All 4 new modules are **strictly keyless** — no `ApiKeysConfig` field, no `AP_*_API_KEY` env var, no wizard `CTI_SERVICES` row. A fresh-install user runs `ap chat`, asks about a URL or domain, and sees real evidence in the first response.
- All 4 modules satisfy the canonical `PursuitModule` Protocol (DEC-MODULE-002) via `BaseModule` subclassing — no parallel module contract.
- `core/event_bus.py::DEFAULT_SUBSCRIPTIONS` is extended so the 4 new modules participate in F60 auto-pivot cascades (no new gate authority created — `PivotPolicy.evaluate` remains the sole gate per DEC-60-PIVOT-POLICY-001).
- `scripts/smoke_test.py` shows `[PASS]` for each new module against live keyless endpoints (no SKIP-on-no-key paths — these modules have no keys).
- `pyproject.toml [project.entry-points."adversary_pursuit.modules"]` and `core/plugin_mgr.py::_BUILTIN_MODULES` are both extended with 4 new entries, preserving the dual-registration invariant established by W-GREYNOISE.
- F59 provenance authority preserved: modules emit zero `x_ap_*` fields in `hunt()` output. `workspace.store_stix_objects()` remains the sole writer of the `x_ap_*` namespace.

### Scoping Decision (DEC-61-SCOPING-001)

**Ship 4 modules in one slice; defer `circl_pdns` to F61b.**

The goal contract names 5 candidates (urlhaus, threatfox, malwarebazaar, crtsh, circl_pdns). The planner ships the first 4 in one bounded slice and explicitly defers `circl_pdns`.

Rationale:

- The 3 abuse.ch modules share HTTP shape (POST/GET against `https://*.abuse.ch/api/v1/`) and benefit from a small shared `_abuse_ch.py` helper (single auth-less `AsyncClient` post + typed error mapping). Splitting them into separate waves would triplicate boilerplate review cycles for no risk reduction.
- `osint/crtsh` is independent but architecturally identical complexity to the abuse.ch trio. Slicing it separately doubles dispatch/review overhead with no shared state contention.
- **`circl_pdns` is not strictly keyless.** It requires a CIRCL free-registration API key. Including it here would force ApiKeysConfig + `_AP_ENV_VAR_MAP` + `_VENDOR_ENV_VAR_MAP` + `provider_setup.CTI_SERVICES` + smoke-runner SKIP-on-no-key extensions that the other 4 modules don't need — diluting the "no key needed" smoke invariant that distinguishes this slice. F61b will pick up `circl_pdns` cleanly with its own ApiKeysConfig + wizard rows.
- The full 9-surface integration playbook is already proven (Phase 9 W-GREYNOISE closeout). One slice with 4 modules each repeating that playbook is reviewable as a single mechanical pattern — not 4 independent patterns.

### State-Authority Map

| Domain | Pre-F61 owner | Post-F61 owner | Notes |
|--------|---------------|----------------|-------|
| Module catalog (entry-point side) | `pyproject.toml [project.entry-points."adversary_pursuit.modules"]` (11 rows) | Same authority + 4 new rows | Single-purpose pyproject.toml expansion (DEC-61-PYPROJECT-SCOPE-001). No dependency, build-system, or version-bump edits. |
| Module catalog (builtin side) | `core/plugin_mgr.py::_BUILTIN_MODULES` (11 rows) | Same authority + 4 new rows | Dual-registration invariant preserved (W-GREYNOISE precedent — 11/11 modules in both surfaces). |
| Auto-pivot default subscriptions | `core/event_bus.py::DEFAULT_SUBSCRIPTIONS` (8 rows) | Same authority + 4 new rows | Per DEC-61-EVENT-BUS-SUBSCRIPTIONS-001. |
| Agent tool catalog | `agent/tools.py` — schemas list + `_SERVICE_NAMES` + `_MODULE_MAP` | Same authority + 4 new entries per surface | `_SERVICE_NAMES` value is `None` for keyless modules (no `get_api_key()` call). |
| REPL module autocomplete | `agent/repl_input.py::_MODULE_NAMES` | Same authority + 4 tail-name entries | |
| Smoke test runner | `scripts/smoke_test.py` — `_run_*` functions + `module_runs` rows | Same authority + 4 new functions + 4 rows | The 4 functions OMIT the SKIP-on-no-key gate that keyed-module runners use — they go directly to live call. |
| Per-SCO provenance (`x_ap_*`) | `core/workspace.py::store_stix_objects()` (DEC-59-001) | **UNCHANGED — out of scope** | New modules MUST NOT emit `x_ap_*` fields. Tests enforce this per module. |
| Auto-pivot gate authority | `core/pivot_policy.py::PivotPolicy.evaluate` (DEC-60-001) | **UNCHANGED — out of scope** | New subscriptions flow through the existing F60 gate; no new gate logic. |
| API key configuration surface | `core/config.py::ApiKeysConfig` + `_AP_ENV_VAR_MAP` + `_VENDOR_ENV_VAR_MAP` | **UNCHANGED — out of scope** | Keyless modules don't extend this surface. F61b will (for circl_pdns). |

### Module Specifics

| Module | Endpoint | Method | Target type(s) | SCO output |
|--------|----------|--------|----------------|------------|
| `cti/urlhaus` | `https://urlhaus-api.abuse.ch/v1/url/` and `https://urlhaus-api.abuse.ch/v1/host/` | POST form-encoded `url=<target>` or `host=<target>` | URL or domain/IP | One `url` SCO (when querying `/v1/url/`) with `x_urlhaus_threat`, `x_urlhaus_tags` (list), `x_urlhaus_url_status`, `x_urlhaus_date_added`, `x_urlhaus_reporter`, `x_urlhaus_reference`; OR one `domain-name`/`ipv4-addr` SCO (when querying `/v1/host/`) plus child `url` SCOs (capped at 15) for each `urls[]` entry on the host. |
| `cti/threatfox` | `https://threatfox-api.abuse.ch/api/v1/` | POST JSON `{"query":"search_ioc","search_term":"<target>"}` | IP, domain, URL, hash | One SCO per match (capped at 15). SCO type inferred from `ioc_type`: `ip:port` → `ipv4-addr` (value pre-colon); `domain` → `domain-name`; `url` → `url`; `md5_hash`/`sha1_hash`/`sha256_hash` → `file` (with `hashes` dict). Custom fields: `x_threatfox_threat_type`, `x_threatfox_malware`, `x_threatfox_confidence_level`, `x_threatfox_first_seen`, `x_threatfox_reference`. |
| `cti/malwarebazaar` | `https://mb-api.abuse.ch/api/v1/` | POST form-encoded `query=get_info&hash=<sha256_or_sha1_or_md5>` | Sample hash | One `file` SCO with `hashes` dict (`SHA-256`, `SHA-1`, `MD5`) + `name` (from `file_name`) + `size` (from `file_size`) + `x_mb_signature`, `x_mb_file_type`, `x_mb_first_seen`, `x_mb_reference`, `x_mb_tags` (list). |
| `osint/crtsh` | `https://crt.sh/?q=%25.<domain>&output=json` | GET (URL-encoded `q` parameter, `output=json`) | Domain | One `domain-name` SCO per unique `common_name`/`name_value` (split on `\n`, wildcard `*.` prefix stripped, dedup against a `seen` set seeded with the query target, capped at 50). Custom fields: `x_crtsh_issuer_ca_id`, `x_crtsh_issuer_name`, `x_crtsh_not_before`, `x_crtsh_not_after` (taken from the first CT-log entry that surfaced the name). |

**Common module shape (all 4):**

- Class subclasses `BaseModule`; `name`, `description`, `author = "Adversary Pursuit"`, `module_type` set at class scope.
- `options` defines a single `TARGET` entry.
- `initialize()` is a no-op for keyless modules (the `_config` dict from `BaseModule.__init__` stays empty).
- `hunt()` uses `httpx.AsyncClient` with a 30s default timeout (`TIMEOUT` option optional).
- Error mapping: HTTP 429 → `RateLimitError` (with `Retry-After` honored when present); `httpx.TimeoutException` → `ModuleError("<module> request timed out")`; malformed JSON → `ModuleError("<module> returned non-JSON response")`; other 4xx/5xx → `response.raise_for_status()` (propagates `httpx.HTTPStatusError`).
- NEVER raises `AuthenticationError` — keyless modules have no auth surface. (Helper file `tests/test_*` includes `test_no_api_key_required_no_auth_error` to enforce this.)
- NEVER emits `x_ap_*` fields. Per-module test `test_module_emits_no_x_ap_provenance_fields` asserts this.

**Optional shared helper:** `src/adversary_pursuit/modules/cti/_abuse_ch.py` may extract the abuse.ch POST pattern (`async def post_json(url, payload, timeout=30.0) -> dict`) plus the typed error mapping. Leading underscore signals private — it is NOT added to `pyproject.toml` entry_points or `plugin_mgr._BUILTIN_MODULES`. If the implementer judges the helper too small to extract (3 thin sites), they may inline it; the helper file then becomes an unused-allowed-path and is dropped from the diff (acceptable). DEC-61-ABUSE-CH-HELPER-001 documents the recommendation but does not force extraction.

### Decision Log (Phase 14)

| DEC ID | Decision | Rationale |
|--------|----------|-----------|
| DEC-61-SCOPING-001 | Ship 4 strictly-keyless modules in F61 (urlhaus, threatfox, malwarebazaar, crtsh); defer `circl_pdns` to F61b | The goal contract names 5 candidates but `circl_pdns` requires a CIRCL free-registration API key — it is not keyless. Mixing it into this slice would force ApiKeysConfig + AP_*_API_KEY env + wizard + SKIP-on-no-key smoke logic that the other 4 modules don't need, diluting the "no key needed" Evaluation Contract invariant. Single-purpose slice scope is preferred over a mixed slice that needs a partial roll-back if circl_pdns hits an authentication wall. The 4 chosen modules also share a tight integration shape (9 surfaces, exactly the W-GREYNOISE precedent) — one slice, one mechanical pattern, four parallel applications. |
| DEC-61-EVENT-BUS-SUBSCRIPTIONS-001 | `DEFAULT_SUBSCRIPTIONS` extended with: `cti/urlhaus`: `["domain-name", "ipv4-addr", "url"]`; `cti/threatfox`: `["ipv4-addr", "domain-name", "url", "file"]`; `cti/malwarebazaar`: `["file"]`; `osint/crtsh`: `["domain-name"]` | These subscriptions match each module's TARGET capability. URLhaus accepts URL/host targets (both ipv4 and domain forms). ThreatFox searches by any IOC. MalwareBazaar is hash-only (`file` SCO with `hashes`). crtsh is domain-only (CT logs are domain-keyed). The subscriptions flow through `PivotPolicy.evaluate` unchanged — no new gate logic — so the F60 quota-bomb protection (per-cascade and per-session budgets) applies automatically. The `file` SCO type subscription for malwarebazaar/threatfox is currently a no-op against today's stix2-recognized SCO_CREATORS set (DEC-59-PROVENANCE-007 documents `file` as silently-dropped at workspace.store time); the subscription is still declared so when a future `file` SCO creator lands, malwarebazaar/threatfox cascades activate automatically without an event_bus.py edit. |
| DEC-61-PYPROJECT-SCOPE-001 | `pyproject.toml` is touched ONLY to extend `[project.entry-points."adversary_pursuit.modules"]` with 4 new lines. No dependency changes, no version bump, no build-system edits, no other table modifications | `pyproject.toml` is normally a forbidden file for planner-strict-scope. AP's plugin discovery requires both `pyproject.toml` entry_points AND `plugin_mgr._BUILTIN_MODULES` to be updated for a new module to be discoverable post-install (the dual-registration invariant). Forbidding `pyproject.toml` would either: (a) break module discovery for installed wheels, or (b) force a parallel mechanism. The single-purpose scope amendment — entry_points additions ONLY — preserves the architectural rule (one authority for module entry points) while permitting the necessary surface extension. Reviewer enforces the surgical-edit invariant: the `pyproject.toml` diff MUST be 4 added lines under `[project.entry-points."adversary_pursuit.modules"]` and zero other changes. |
| DEC-61-ABUSE-CH-HELPER-001 | Optional shared `modules/cti/_abuse_ch.py` helper recommended for the POST + typed-error-mapping shape; leading underscore + no entry_point registration to mark it private | Reuse is a Sacred Practice 12 reflex when 3 modules share a wire pattern. The helper centralizes the POST shape, the 429 / timeout / malformed-JSON branching, and the `httpx.AsyncClient` invocation. Extraction is RECOMMENDED but not REQUIRED — if the implementer judges the helper too thin (3 sites, ~15 LOC each), they may inline. In that case the unused-allowed-path is dropped from the diff and the DEC's "as-implemented" footnote documents the decision. The helper MUST NOT be added to `pyproject.toml` entry_points or `plugin_mgr._BUILTIN_MODULES` — the underscore prefix and absence from those registries is what marks it private. |
| DEC-61-CRTSH-001 | crt.sh `?output=json` is the canonical JSON interface; an HTML response signals rate-limit/error and MUST raise `ModuleError`, not return a synthesized SCO list | crt.sh occasionally serves HTML (a status page or rate-limit error) when the JSON endpoint is degraded. Parsing HTML to extract names would create a parallel, fragile data path that drifts the moment crt.sh changes its template. The canonical contract is JSON — anything else is an error. The test `test_html_response_raises_module_error_not_returns_html` asserts this invariant. Dedup uses a `seen` set seeded with the query target plus an empty string (mirroring URLScan's DEC-MODULE-URLSCAN-003 pattern); wildcard `*.` prefix is stripped before dedup. Cap at 50 unique domain-name SCOs per call — large apex domains routinely have hundreds of certificates and unbounded output overwhelms downstream consumers (mirrors URLScan's 15-cap, scaled up because subdomain enumeration legitimately surfaces more entities than a single page-load IP/domain list). |
| DEC-61-MODULES-EMIT-NO-PROVENANCE-001 | New modules emit zero `x_ap_*` provenance fields in `hunt()` output; `workspace.store_stix_objects()` remains the sole writer of the `x_ap_*` namespace | Direct re-affirmation of DEC-59-STIX-PROVENANCE-001 against the new module surface. Without this explicit assertion (and the matching per-module test), a well-meaning implementer might add `x_ap_source_url` to the SCO output thinking "more provenance is better" — creating exactly the dual-authority bug F59 was built to prevent. The per-module test is therefore part of the Evaluation Contract, not an after-the-fact lint. |

### Wave Decomposition

Single wave; one implementer slice (no parallelism — all 4 modules touch the same 9 integration surfaces and must land atomically to preserve the dual-registration invariant).

| W-ID | Title | Weight | Gate | Deps | Integration |
|------|-------|--------|------|------|-------------|
| `wi-61-impl-01` | Add 4 keyless modules (urlhaus, threatfox, malwarebazaar, crtsh) + optional `_abuse_ch.py` helper + 9-surface integration + smoke test + per-module tests | L | review | none | `modules/cti/{urlhaus,threatfox,malwarebazaar,_abuse_ch}.py` (NEW), `modules/osint/crtsh.py` (NEW), `core/plugin_mgr.py`, `core/event_bus.py`, `agent/tools.py`, `agent/repl_input.py`, `scripts/smoke_test.py`, `pyproject.toml`, `tests/test_{urlhaus,threatfox,malwarebazaar,crtsh,abuse_ch_helper}.py` (NEW), `MASTER_PLAN.md` |

Critical path: one slice; max width 1.

### Scope Manifest (wi-61-impl-01)

Runtime authority: `cc-policy workflow scope-get w-61-keyless-hunters` (synced from `tmp/f61-scope.json` via `scope-sync --work-item-id wi-61-impl-01`). The Scope Manifest is also persisted on `work_items.scope_json` for `wi-61-impl-01` (2843 bytes).

- **Allowed paths (18):** `src/adversary_pursuit/modules/cti/_abuse_ch.py`, `src/adversary_pursuit/modules/cti/urlhaus.py`, `src/adversary_pursuit/modules/cti/threatfox.py`, `src/adversary_pursuit/modules/cti/malwarebazaar.py`, `src/adversary_pursuit/modules/osint/crtsh.py`, `src/adversary_pursuit/core/plugin_mgr.py`, `src/adversary_pursuit/core/event_bus.py`, `src/adversary_pursuit/agent/tools.py`, `src/adversary_pursuit/agent/repl_input.py`, `src/adversary_pursuit/gamification/hints.py`, `scripts/smoke_test.py`, `pyproject.toml`, `tests/test_urlhaus.py`, `tests/test_threatfox.py`, `tests/test_malwarebazaar.py`, `tests/test_crtsh.py`, `tests/test_abuse_ch_helper.py`, `MASTER_PLAN.md`.
- **Required paths (15):** `modules/cti/{urlhaus,threatfox,malwarebazaar}.py`, `modules/osint/crtsh.py`, `core/plugin_mgr.py`, `core/event_bus.py`, `agent/tools.py`, `agent/repl_input.py`, `scripts/smoke_test.py`, `pyproject.toml`, `tests/test_{urlhaus,threatfox,malwarebazaar,crtsh}.py`, `MASTER_PLAN.md`. (The `_abuse_ch.py` helper, its tests, and the `gamification/hints.py` entries are allowed-but-not-required — see DEC-61-ABUSE-CH-HELPER-001.)
- **Forbidden paths (29):** `modules/base.py` (Protocol authority), `core/workspace.py` (F59), `core/pivot_policy.py` (F60), `core/streak.py` (F62), `core/console.py`, `core/config.py` (would imply keyed-module scope), `core/graph.py`, `core/report.py`, `core/error_interpreter.py`, `agent/chat.py`, `agent/runner.py`, `agent/provider_setup.py` (would imply wizard CTI_SERVICES row), `agent/error_handler.py`, all `gamification/{badges,celebrations,challenges,scoring}.py`, `models/stix.py`, `models/database.py`, `uv.lock`, `CLAUDE.md`, `AGENTS.md`, `DECISIONS.md`, `README.md`, `.github/**`, `.claude/**`, `settings.json`, `hooks/**`, `agents/**`.
- **State/authority domains touched:** `osint_module_catalog`, `event_bus_default_subscriptions`, `agent_tool_catalog`, `smoke_test_classification`, `module_entry_point_registration`.

### Evaluation Contract (9-key, wi-61-impl-01)

Runtime authority: stored on `wi-61-impl-01.evaluation_json` (11247 bytes; loaded from `tmp/f61-evaluation.json`). Summary below; the runtime contract is the binding artifact.

- **required_tests (38):** ~9 per module (happy path, no-results, 429, timeout, malformed JSON, SCO shape, no `x_ap_*`, plus module-specific edge cases: urlhaus URL-vs-host routing, threatfox SCO-type inference, malwarebazaar required-hashes-dict, crtsh dedup + wildcard-strip + HTML-not-allowed + 50-cap), plus 1 helper test (`test_post_json_*`), plus 1 each in `test_event_bus.py` and `test_smoke_test.py` for catalog parity.
- **required_evidence:** `tmp/evidence-61-keyless-hunters/{pytest_targeted.txt, pytest_full_suite.txt, ruff_clean.txt, smoke_test_keyless_pass.txt, diff_summary.txt, pyproject_entry_points.txt, plugin_mgr_discovery.txt}`.
- **required_real_path_checks (4):** (a) `python scripts/smoke_test.py` shows `[PASS]` for `cti/urlhaus`, `cti/threatfox`, `cti/malwarebazaar`, `osint/crtsh` against default targets WITHOUT any API key configured; (b) `importlib.metadata.entry_points(group="adversary_pursuit.modules")` lists 15 modules after `pip install -e .` in the worktree venv; (c) `PluginManager().list_modules()` returns all 15 module paths; (d) `core.event_bus.DEFAULT_SUBSCRIPTIONS` contains the 4 new entries per DEC-61-EVENT-BUS-SUBSCRIPTIONS-001.
- **required_authority_invariants (10):** Protocol satisfaction, httpx.AsyncClient + 30s timeout + typed errors, zero `x_ap_*` in module output, workspace.py untouched, pivot_policy.py untouched, event_bus.py touched only in `DEFAULT_SUBSCRIPTIONS`, dual-registration parity, smoke-PASS-on-keyless (no SKIP-for-auth path), private `_abuse_ch.py` helper not entry_point-registered, pyproject.toml surgical-edit invariant (4 added lines under `[project.entry-points."adversary_pursuit.modules"]` only).
- **required_integration_points (7):** plugin_mgr `_BUILTIN_MODULES`+4 rows, event_bus `DEFAULT_SUBSCRIPTIONS`+4 rows, tools.py schemas+`_SERVICE_NAMES`+`_MODULE_MAP`+4 each, repl_input `_MODULE_NAMES`+4 rows, gamification/hints.py optional, smoke_test.py 4 new `_run_*` functions + 4 `module_runs` rows (omitting SKIP-for-auth), pyproject.toml 4 entry_point lines.
- **forbidden_shortcuts (12):** no live HTTP in unit tests (respx/MockTransport only); no HTML parsing for crtsh; no API-key gating; no swallowing of typed errors; no in-module retry loop; no edits to base.py / workspace.py / pivot_policy.py / config.py; no partial shipments without smoke+real-path-check; no `x_ap_*` suppression-test bypass; no circl_pdns scaffolding; no synthesized "no result" SCOs to hide upstream failures.
- **rollback_boundary:** single revertable feature commit on `feature/61-keyless-hunters`. Revert restores 11-module catalog; no DB schema or state migration involved.
- **acceptance_notes:** `python scripts/smoke_test.py` exits 0 with `[PASS]` on the 4 new keyless modules; each returns ≥1 STIX SCO; `ap chat` tool catalog discovery shows 4 new tools; auto-pivot cascades over crtsh-emitted `domain-name` SCOs respect the F60 PivotPolicy gate; full pytest suite green; ruff clean across changed files.
- **ready_for_guardian_definition:** all 38 required tests PASS; full pytest suite green with zero regressions; ruff clean; smoke shows `[PASS]` on the 4 new keyless modules against live endpoints (no SKIP-for-auth path); `importlib.metadata` discovers 15 modules; `PluginManager.list_modules()` returns 15; `DEFAULT_SUBSCRIPTIONS` contains the 4 new entries; git diff touches ONLY Scope Manifest allowed paths; reviewer issues `REVIEW_VERDICT=ready_for_guardian` on current HEAD; all 7 evidence files exist in `tmp/evidence-61-keyless-hunters/`.

### What is NOT in scope (out-of-scope, deferred, or follow-up)

- **`osint/circl_pdns`** — deferred to F61b per DEC-61-SCOPING-001. Requires CIRCL free-registration API key; needs `ApiKeysConfig.circl_pdns`, `_AP_ENV_VAR_MAP["circl_pdns"]`, `_VENDOR_ENV_VAR_MAP["circl_pdns"]`, `agent/provider_setup.CTI_SERVICES` row, and SKIP-on-no-key smoke handling — none of which the 4 keyless modules need.
- **F62 stretch modules** named in the goal context (misp_import, yara_match, GreyNoise riot-only) — out of scope. `misp_import` requires a workspace authority extension (importing third-party STIX bundles); `yara_match` is a local-execution module (not an HTTP-fetched OSINT/CTI source) with different testing semantics; "GreyNoise riot-only" is already covered by the existing `osint/greynoise` module (the `riot` field is in its output). None belong in F61.
- **`file` SCO creator support in `models/stix.py`** — DEC-59-STIX-PROVENANCE-007 documented `file` SCOs as silently-dropped at `workspace.store_stix_objects` time because `_SCO_CREATORS` does not include `file`. F61 inherits this gap: ThreatFox and MalwareBazaar both produce `file` SCOs that are accepted by `dict_to_stix()` (passthrough on unknown types per DEC-STIX-002) but **dropped on store** (workspace.py line ~281). A separate slice will add `file` to `_SCO_CREATORS` with a chosen `hashes`-dict shape and defining-properties policy. F61's `DEFAULT_SUBSCRIPTIONS` declares `file` subscriptions for malwarebazaar/threatfox anyway, so when the future slice lands, cascades activate automatically without an event_bus.py edit.
- **Wizard CTI_SERVICES rows for keyless modules** — keyless modules don't have keys to configure, so `agent/provider_setup.CTI_SERVICES` and `_CTI_ENV_VAR` are forbidden. Wizard discovery of keyless modules happens via the standard catalog (after plugin_mgr loads).
- **API key configuration** in `core/config.py` — explicitly forbidden. Adding ApiKeysConfig fields for keyless modules would imply key-required and would expand the rollback surface beyond a single revertable commit.

### Follow-ups (filed, not in F61)

- **F61b: `osint/circl_pdns`** — CIRCL Passive DNS module with single free-registration key. ApiKeysConfig + AP_*_API_KEY env + wizard CTI_SERVICES row + SKIP-on-no-key smoke logic. Independent slice; depends on F61 only insofar as the 4 keyless modules have demonstrated the integration playbook.
- **`file` SCO creator in `models/stix.py`** — adds `file` to `_SCO_CREATORS` with `hashes` dict shape and defining-properties policy. Unblocks malwarebazaar / threatfox / virustotal hash SCOs reaching the workspace store. Separate slice; touches F59 authority surface so it goes through its own planner round.
- **`misp_import` and `yara_match`** — separate planner slices when prioritized. Both touch workspace authority or introduce local-execution semantics, neither belongs in a keyless-HTTP-fetch slice.

---

## Phase 16: Threat Actor Dossier Reframe — Strategic Scoping (W-68-DOSSIER-REFRAME-SCOPING, post-v1, 2026-05-27)

**Status:** completed (strategic scoping landed 2026-05-27, merge `b2b846a`, impl `36b7f30`; binding decisions and M-1..M-9 decomposition closed; no source code touched by this slice). M-1 implementer slice landed at Phase 17B (merge `486a5ad`, 2026-05-28). M-2 implementer slice landed at Phase 17D (merge `11b3fd3`, 2026-05-29). M-3 is the next slice (W-68-M3-DOSSIER-SCORING per `.claude/plans/dossier-reframe-v2-roadmap.md` §M-3).

**Source directive:** Issue [#68](https://github.com/jarocki/ap/issues/68) (filed 2026-05-23) reframes AP from indicator-graph traversal to **Threat Actor Dossier completion**. The 2026-05-26 Project Reckoning (Section VIII, item 3) elevated this to "the most important unmade decision in the project — every day it sits unscoped is a day the project's v2 center of gravity is unset."

**Verbatim user directive (issue #68 body, key passages):**

> "Adversary Pursuit is **not** about pivoting through indicators to find factoids. It is about **piecing together a picture of a Threat Actor** — their habits, their strengths, technology they use or are comfortable with — and the quirky way they use it, their motivations, their 'tells,' anything else that can match activity to their **persona fingerprint** or **predict what they'll do next**, or build a strategy for **confusing / denying / discouraging** further attack progress."
>
> "The right metaphor is a **dossier** — a **puzzle** where the pieces filled in are the actual score drivers. The more important pieces (the ones nobody else has, the ones that pin actor identity, the ones that predict the next move) are worth higher scores."

> _2026-05-26 Reckoning (Section VIII.3):_ "Issue #68 (Dossier reframe) is the most important unmade decision in the project. … It is conceptually closer to the Original Intent than today's trajectory."

**Scoping deliverable:** This Phase 16 section + `.claude/plans/dossier-reframe-v2-roadmap.md` (the full strategic scoping artifact). MASTER_PLAN carries the binding decisions and slice index; the roadmap document carries the full schema, rationale, and disposition tables. **No source code is touched by this workflow.** Implementer slices M-1 through M-9 are separate workflows that flow out of this scoping.

### Binding Decisions (full rationale in `.claude/plans/dossier-reframe-v2-roadmap.md` §8)

| DEC ID | Decision (one-line) | See |
|--------|---------------------|-----|
| **DEC-68-DOSSIER-REFRAME-001** | The dossier-puzzle metaphor is ratified as v2's product center. AP's analytic unit of value shifts from indicator-graph traversal to Threat Actor Dossier completion. | roadmap §2 |
| **DEC-68-DOSSIER-REFRAME-002** | Scoring authority: layer a new `dossier/` aggregator over the existing `ScoringEngine`; emit new `DossierSlotFilled` / `DossierPredictionValidated` `ScoreEvent` subtypes via the same engine; re-tune per-IOC `MODULE_RUN_SCORED` to baseline weight 1.0. No deprecation shim, no fallback flag. Preserves F62/F63/F64 invariants. | roadmap §4 |
| **DEC-68-DOSSIER-REFRAME-003** | Issue #29 (18 SATs as agent capabilities) is sequenced *within* the dossier roadmap as the analyst-step interpretation engine; SAT library lands under `dossier/sats/`. | roadmap §6 |
| **DEC-68-DOSSIER-REFRAME-004** | Issue #30 (character v2 personas) stays independent. Player persona vs target persona; orthogonal. | roadmap §6 |
| **DEC-68-DOSSIER-REFRAME-005** | Issue #31 (RPG gamification v2: XP/levels/skill trees/loot/quests) is **retired** as superseded by #68. Close with supersession comment pointing at M-3 / M-7 / this DEC. | roadmap §6 |
| **DEC-68-DOSSIER-REFRAME-006** | Issue #32 (LLM-enhanced celebrations + reports) augments the dossier roadmap as M-7 sub-issue. Gated on M-3 and M-4. Honors F64 panel-authority invariants. | roadmap §6 |
| **DEC-68-DOSSIER-REFRAME-007** | Predictions Log slot (slot 8): falsified prediction contributes 0 to slot weight. Whether falsified predictions *deduct* score is deferred to M-3 implementer slice. | roadmap §8 |
| **DEC-68-DOSSIER-REFRAME-008** | v1's interview-based investigation report is replaced by the actor-dossier report at M-7. v1 template available via `--style classic` for one release cycle (v0.2.x), removed at M-8 cleanup. | roadmap §5 (M-7/M-8) |
| **DEC-68-DOSSIER-REFRAME-009** | Original Intent crowdsourcing / competition / career-development axis is **scheduled as M-9** (v0.3.0+), NOT retired as a Non-Goal. Dossiers are STIX-bundle-comparable; the dossier reframe makes the axis tractable. | roadmap §7 |
| **DEC-68-DOSSIER-REFRAME-010** | The dossier slot schema v1.0 (9 slots) is binding for M-1 with the explicit exception that M-1 may refine by ±2 slots before the first implementer touches code. Further refinement requires a planner re-stage and a successor DEC-ID. | roadmap §3 |

### Dossier Slot Schema v1.0 (binding, refinable per DEC-68-DOSSIER-REFRAME-010)

| # | Slot | Score weight | Confidence: contested \| low \| medium \| high |
|---|------|--------------|-------------|
| 1 | Identity / Attribution | 5.0 | |
| 2 | TTPs and Tradecraft | 3.0 | |
| 3 | Infrastructure Habits | 2.0 | |
| 4 | Timing / Behavioral | 2.0 | |
| 5 | Targeting Profile | 2.5 | |
| 6 | Capability Ceiling | 3.5 | |
| 7 | Motivation Indicators | 3.0 | |
| 8 | Predictions Log | 4.0 | |
| 9 | Denial / Deception Strategies | 2.5 | |

Baseline routine per-IOC lookup with no slot impact = 1.0 (v1 baseline retained for backward compatibility). Full evidence-types per slot, source-attribution requirements, and confidence-level definitions: `.claude/plans/dossier-reframe-v2-roadmap.md` §3.

### Decomposition Index — M-1 through M-9 (each becomes a separate planner workflow)

| Slice | Title | Size | Blocked by | v0.x target |
|-------|-------|------|------------|-------------|
| **M-1 (MVP)** | Dossier Visualization Panel — `ap chat` panel + `get_dossier_state` LLM tool, read-only inference over existing workspace SCOs; no new tables, no new scoring math | S–M | nothing | v0.2.0 |
| M-2 | Module-to-Slot Mapping Layer — `dossier/extractors.py` per existing module (15 modules) | M | M-1 | v0.2.x |
| M-3 | Dossier Scoring + Score Event Re-Tune — new `ScoreEvent` subtypes, slot-weight × confidence × rarity formula; re-tune per-IOC events to baseline 1.0; preserve F62/F63/F64 | M–L | M-2 | v0.2.x |
| M-4 | Persistent Dossier State + Predictions Log (slot 8) — new SQLite tables `dossier_slot`, `dossier_evidence_link`, `dossier_prediction` | L | M-3 | v0.2.x or v0.3.0 |
| M-5 | Denial / Deception Strategies (slot 9) + User-Note Surface | M | M-4 | v0.3.x |
| M-6 | Dossier-Aware Auto-Pivot Policy — extend F60 policy with "would this pivot fill an empty high-value slot?" input; preserve DEC-60-* | M | M-4 | v0.3.x |
| M-7 | Reports / Celebrations / Badges Dossier-Aware Upgrade — absorbs issue #32; honors F64 panel authority | L | M-3, M-4, M-5, M-6 | v0.3.x |
| M-8 | Cleanup, Closeout, and Novel-Method Achievement Mechanism — removes "classic" report shim from M-7; implements #68's "recognizing a novel method" bonus-space ask | M | M-7 | v0.3.x |
| **M-9** | Crowdsourced Dossier Comparison + Public Actor Library — fulfills Original Intent's crowdsourcing axis; STIX-bundle-based dossier export/import; opt-in public-library | L | M-8 | v0.3.0+ |

**Critical path:** M-1 → M-2 → M-3 → M-4 → M-7 → M-8 → M-9. Max parallel width: M-5 + M-6 can land in parallel after M-4 and before M-7.

### Related Issue Disposition Table

| Issue | Title | Disposition | Action | DEC |
|-------|-------|-------------|--------|-----|
| #29 | 18 SATs as agent capabilities | **Sequence-within** (M-2/M-3) | Comment re-aiming #29 to dossier extraction; label `dossier-roadmap` | DEC-68-DOSSIER-REFRAME-003 |
| #30 | Character v2 LLM personas | **Stays independent** | Clarifying comment (player persona ≠ target persona) | DEC-68-DOSSIER-REFRAME-004 |
| #31 | RPG gamification v2 (XP/levels/skill trees/loot/quests) | **Retired** | Close #31 with supersession comment pointing at M-3, M-7, DEC-68-DOSSIER-REFRAME-005 | DEC-68-DOSSIER-REFRAME-005 |
| #32 | LLM-enhanced celebrations + reports | **Augment via M-7** | Re-scope as M-7 sub-issue; gated on M-3 + M-4 | DEC-68-DOSSIER-REFRAME-006 |

### Non-Superseded Prior Decisions (continue to bind)

The dossier reframe **does not** supersede any of these v1 invariants. They continue to apply to M-1 through M-9:

- ADR-005 (STIX 2.1 as internal data model)
- DEC-59-STIX-PROVENANCE-001..007 (workspace as sole `x_ap_*` authority; per-SCO provenance)
- DEC-WS-001..006 (workspace SQLite + dedup + Session semantics)
- DEC-STIX-001..002 (deterministic ids; dict passthrough on unknown types)
- DEC-EVENTBUS-002 (opt-in event bus)
- DEC-60-PIVOT-POLICY-001..007 (3-gate policy engine; preserved by M-6 extension)
- DEC-62-STREAK-* (streak mechanic; preserved by M-3 re-tune)
- DEC-63-MILESTONE-* (milestone catch-up; preserved by M-3 re-tune)
- DEC-64-LLM-PANEL-SEPARATION-001 (sidecar pattern; preserved by M-7 augmentation)
- Sacred Practice 12 (single authority per operational fact)
- Principle 4 (modules are pure data producers; dossier rides on top, never inside modules)

### Out-of-Scope for This Workflow

- **No source code touched.** This is the planning slice. Only `MASTER_PLAN.md` and `.claude/plans/dossier-reframe-v2-roadmap.md` are written.
- **No new modules.** Dossier is an aggregation layer; existing 15-module catalog suffices for M-1 through M-8.
- **No federation, no real-time multi-user, no DALL-E, no web/GUI.** v1 Non-Goals continue to bind through M-9 (file-based dossier export/import via STIX bundle remains permitted under existing STIX 2.1 commitments).
- **No MCP-migration (#65) dependency.** Orthogonal; both reframes can land in either order.

### Subsequent Workflow Cue

After this planning slice lands, the recommended next workflow is `M-1` (Dossier Visualization Panel) — smallest viable shipping unit, validates the slot schema against real workspace data, no persistence commit, no scoring change. The planner that opens M-1 authors its own Evaluation Contract and Scope Manifest under a successor workflow id (e.g., `w-68-m1-dossier-panel`).

### Decision Log (Phase 16)

| DEC ID | Decision | Rationale |
|--------|----------|-----------|
| DEC-68-DOSSIER-REFRAME-001 | Ratify the dossier-puzzle metaphor as v2's product center. AP's analytic unit of value shifts from indicator-graph traversal to Threat Actor Dossier completion. | Five independently sufficient reasons (roadmap §2.1–2.5): closer to Original Intent than v1 trajectory; serves Principle 4 ("modules are pure data producers") more cleanly than v1 scoring; resolves a latent tension in the gamification stack that F60/F62/F63/F64 have been working around; absorbs Threat Hunter expert pressure at the *value* layer (v1 hardened the evidence chain; v2 needs the analytic-value chain); architecturally cheap given ADR-010 + F59/F60/F61 separation discipline. |
| DEC-68-DOSSIER-REFRAME-002 | Scoring authority resolution: **option (c)** — layer a `dossier/` aggregator over `ScoringEngine`; emit new `DossierSlotFilled` / `DossierPredictionValidated` event subtypes via the existing engine; re-tune per-IOC `MODULE_RUN_SCORED` to baseline weight 1.0. Reject option (a) replace (breaks F62/F63/F64 in one landing); reject option (b) parallel augment (creates permanent dual-authority surface). | The `dossier/` package owns "what's the analytic-state-of-the-world?"; `ScoringEngine` continues to own "what's a scoreable event?" Distinct questions, distinct authorities — Sacred Practice 12 honored. F62 streak chain + F63 milestone catch-up + F64 panel de-duplication all observe `ScoreEvent`s (unchanged interface). No fallback flag; no env-var bypass; no parallel emission outside `ScoringEngine`. |
| DEC-68-DOSSIER-REFRAME-003 | Sequence issue #29 (18 SATs as agent capabilities) *within* the dossier roadmap as the analyst-step interpretation engine. SAT library lands under `dossier/sats/`, not as a parallel `agents/capabilities/` surface. | SATs are exactly the analyst-step interpretation that turns raw SCO evidence into slot values (issue #29 body: "into the bones"). Analysis of Competing Hypotheses becomes the M-3 confidence-resolution mechanic; Key Assumptions Check becomes the slot 8 Predictions Log sanity gate. Avoids creating two parallel "analyst capability" surfaces. |
| DEC-68-DOSSIER-REFRAME-004 | Issue #30 (character v2 LLM personas) stays independent of the dossier reframe. Player persona (#30) and target persona (dossier slots 1, 6, 7) answer different questions; the dossier IS the target persona; #30 governs presentation flavor. | Orthogonality test: a Bobby Hill-mode user fills the same dossier slots a Columbo-mode user fills. Persona affects presentation, not analytic state. No dossier-roadmap dependency in either direction; #30 ships independently when prioritized. |
| DEC-68-DOSSIER-REFRAME-005 | **Retire issue #31** (RPG gamification v2: XP, levels, skill trees, loot, quests) as superseded by #68. Close with supersession comment pointing at M-3, M-7, and this DEC-ID. The quest piece survives in spirit as "fill a high-value empty slot for actor X" under M-3/M-7; it does NOT survive as a quest *subsystem*. | RPG level-grinding rewards activity volume — exactly the v1 frame the dossier reframe replaces. Skill trees gate progression by mechanical specialization rather than by what's been learned about actors. Loot is the wrong metaphor (the rare finding *is itself* the reward because it fills a high-value slot). Keeping #31 open would create permanent friction against the dossier scoring model. Most assertive call in this scoping; worth user adjudication if disputed. |
| DEC-68-DOSSIER-REFRAME-006 | Augment issue #32 (LLM-enhanced celebrations + reports) via sequence-within: #32 becomes an M-7 sub-issue. Gated on M-3 (so there's `DossierSlotFilled` content to narrate) and M-4 (so there's persistent slot state for narrative reference). Honors F64 panel-authority invariants — LLM narration is the *content* of panel events, not a parallel surface. | The dossier reframe gives #32 a substrate it didn't have under v1's per-IOC framing. v1 ASCII-art celebrations continue to fire for routine baseline events at weight 1.0; LLM-narrated celebrations fire for high-weight slot-fill events. |
| DEC-68-DOSSIER-REFRAME-007 | Predictions Log (slot 8): a falsified prediction contributes 0 to slot weight (not negative). Whether falsified predictions should *deduct* score is **deferred** to the M-3 implementer slice. | Deferred not because the question is unimportant but because the right answer depends on whether negative-score events break F62 streak invariants or F63 milestone catch-up math. M-3 implementer evaluates against existing DEC-62-* / DEC-63-* and decides; planner re-stages only if M-3 surfaces a violation of an existing DEC. |
| DEC-68-DOSSIER-REFRAME-008 | The v1 interview-based investigation report (DEC-AGENT-REPORT-* under Phase 6) is replaced by the actor-dossier report at M-7. The v1 template remains available via `--style classic` flag for one release cycle (v0.2.x); removed at M-8 cleanup. | One-release-cycle deprecation is the minimum window for a single user to consume the change without surprise; longer windows would create the parallel-authority residue Sacred Practice 12 forbids. M-8 is the named removal point so cleanup is not optional. |
| DEC-68-DOSSIER-REFRAME-009 | **Schedule the Original Intent crowdsourcing / competition / career-development axis as M-9** (Crowdsourced Dossier Comparison + Public Actor Library, v0.3.0+). Do NOT retire as a Non-Goal. | The dossier reframe makes the axis architecturally tractable: dossiers are STIX-bundle-comparable; career = dossier corpus; competition = slot-fill speed / validated-prediction ratio; crowdsourcing = opt-in dossier publication. Retiring it would contradict the 2026-05-26 Reckoning's framing that the dossier reframe is "Original Intent's voice clarifying itself." Scheduling it (rather than leaving it latent or formally retiring it) resolves the 7-week latency the Reckoning called out. |
| DEC-68-DOSSIER-REFRAME-010 | The dossier slot schema v1.0 (§3 of roadmap; 9 slots above) is binding for M-1 with the exception that M-1 may refine the schema by ±2 slots before the first implementer touches code. Further refinement post-M-1 requires a planner re-stage and a successor DEC-ID. | Locking the schema before MVP contact with real data would be premature; locking it forever after MVP would be brittle. The ±2-slot M-1 window lets the MVP validate the metaphor; the successor-DEC-ID gate ensures subsequent refinements remain tracked under the Decision Log discipline. |

---

## Phase 17: Character System v2 — LLM Personas — Strategic Scoping (W-30-CHARACTER-V2-SCOPING, post-v1, 2026-05-27)

**Status:** completed (strategic scoping landed 2026-05-27, merge `fe4c0b1`, impl `5726819`; binding decisions and C-1..C-4 decomposition closed; no source code touched by this slice). C-1 implementer slice landed at Phase 17C (merge `e49e70b`, 2026-05-28). C-2 implementer slice landed at Phase 17E (merge `f8bded8`, 2026-05-29; ninja disposition flipped KEEP_STATIC → UPGRADE per DEC-C2-NINJA-001 supersession). C-3 (Philosophy + Bureaucratese modes — `sun_tzu`, `bruce_lee`, `bureaucrat`) is the next character-v2 slice.

**Source directive:** Issue [#30](https://github.com/jarocki/ap/issues/30) — "Upgrade character modes from static templates to LLM personality profiles." Ratified as **orthogonal** to the dossier reframe by DEC-68-DOSSIER-REFRAME-004 (player persona ≠ target persona).

**Verbatim user directive (issue #30 body, key passages):**

> "Upgrade character modes from static templates to LLM personality profiles."
>
> "Phase 3 system prompts per character (Borderlands/Fallout RPG style); dynamic personality responding to investigation context; character-specific tool preferences; RPG-style level progression."

**Scoping deliverable:** This Phase 17 section + `.claude/plans/character-v2-roadmap.md` (the full strategic scoping artifact). MASTER_PLAN carries the binding decisions and slice index; the roadmap document carries the full schema, per-mode disposition tables, and rationale. **No source code is touched by this workflow.** Implementer slices C-1 through C-4 are separate workflows that flow out of this scoping.

**Companion roadmap:** `.claude/plans/dossier-reframe-v2-roadmap.md` (W-68; landed Phase 16). DEC-68-DOSSIER-REFRAME-004 ratified #30 as orthogonal to #68 — both v2 roadmaps proceed independently, with one sequencing preference (C-4 prefers post-M-4) and one inverse preference (M-7 prefers post-C-1). See Phase 17 §6.5 below.

### Binding Decisions (full rationale in `.claude/plans/character-v2-roadmap.md` §7)

| DEC ID | Decision (one-line) | See |
|--------|---------------------|-----|
| **DEC-30-CHARACTER-V2-001** | The "Borderlands/Fallout RPG style" brief is interpreted as a *voice-quality recommendation* applied non-uniformly across the existing 10 F62-cleaned modes, NOT a literal IP-aesthetic mandate that replaces the catalog. Option (c) over (a) replace-with-genre and (b) replace-with-professional. | roadmap §2 |
| **DEC-30-CHARACTER-V2-002** | Per-mode disposition: 8 of 10 modes UPGRADE with LLM profiles; 2 (default, ninja) KEEP_STATIC; 0 RETIRE. KEEP_STATIC ≠ second-class — those modes serve "no flavor" / "minimal flavor" user-mood anchors. | roadmap §4 |
| **DEC-30-CHARACTER-V2-003** | Personality profile schema v1.0 (8 fields; ≤ 165 tokens per mode) injects via the existing `AgentRunner.set_character` site as a system-prompt fragment. Reject sidecar-agent + post-processor as parallel-authority surfaces. | roadmap §3 |
| **DEC-30-CHARACTER-V2-004** | "RPG-style level progression": XP-grind / skill-tree / loot / quest forms are **retired** (already retired by DEC-68-DOSSIER-REFRAME-005 superseding #31). A narrow `mastery_level` hook is **deferred to C-4** as an optional expressive-depth axis keyed off session count, NOT score-grinding. C-4 may retire the hook entirely. | roadmap §5.1 |
| **DEC-30-CHARACTER-V2-005** | F62 + F64 invariants jointly preserved: `mode.run_fail` remains sole authority for failure voice; StreakManager remains sole streak authority; persona has no streak fields; gamification-event narration stays on Rich-panel surface; `tool_preferences` is voice-affinity only and MUST NOT bias tool selection (C-1 invariant test enforces). F60 auto-pivot architecturally disconnected. | roadmap §5.2–5.4 |
| **DEC-30-CHARACTER-V2-006** | C-1 MVP scope: one upgraded mode (`full_troll` recommended) + the `LLMPersonaProfile` dataclass + extended `set_character` composer + invariant test suite. Other 9 modes ship at `llm_profile=None` (= F62 behavior). ≤ 2 weeks implementer effort; v0.2.x target. | roadmap §6 (C-1) |
| **DEC-30-CHARACTER-V2-007** | Sequencing relative to AP #68: C-1 lands **parallel with M-1** (zero dependency; complementary v0.2.0 product story). C-4 prefers post-M-4. M-7 prefers post-C-1. All four preferences are simultaneously satisfiable. | roadmap §6.5 |

### Personality Profile Schema v1.0 (binding, refinable per DEC-30-CHARACTER-V2-003)

`LLMPersonaProfile` (new frozen dataclass) — 8 fields:

| Field | Type | Token budget |
|-------|------|--------------|
| `voice_summary` | `str` | ≤ 20 |
| `tone_registers` | `tuple[str, ...]` (2–4 register words) | ≤ 10 |
| `signature_phrases` | `tuple[str, ...]` (2–5 catch-phrases) | ≤ 30 |
| `fourth_wall_stance` | `Literal["in_character", "winking", "meta_aware"]` | ≤ 5 |
| `dialect_cadence` | `str` | ≤ 20 |
| `context_hooks` | `tuple[str, ...]` (1–3 context-response pointers) | ≤ 40 |
| `tool_preferences` | `tuple[str, ...]` (0–3 voice-affinity hints — **NOT selection bias**) | ≤ 20 |
| `forbidden_voice` | `tuple[str, ...]` (0–3 negative voice constraints) | ≤ 20 |

Per-mode total budget: **≤ 165 tokens**. C-1 may refine schema by ±2 fields before first implementer touches code (DEC-30-CHARACTER-V2-003). `CharacterMode` extends with `llm_profile: LLMPersonaProfile | None = None` (default None → F62 behavior preserved verbatim). Full schema, evidence, and injection composer at `.claude/plans/character-v2-roadmap.md` §3.

### Per-Mode Disposition (binding)

| Mode | Disposition | Reason (one-line) |
|------|-------------|-------------------|
| `default` | **KEEP_STATIC** | The neutral baseline — purpose is *no persona flavor*. |
| `ninja` | **KEEP_STATIC** | Purpose is *less output*, not more characterful. |
| `full_troll` | **UPGRADE (C-1 MVP)** | Strongest fit for Borderlands/Fallout snark; highest comedic visibility. |
| `drunken_master` | **UPGRADE (C-2)** | Rambling tipsy diction — LLM dynamism wins decisively over static templates. |
| `bobby_hill` | **UPGRADE (C-2)** | Signature phrase + chaotic energy — LLM extends past 4-line catalog. |
| `chuck_norris` | **UPGRADE (C-2)** | Chuck Norris facts are a well-defined corpus; LLM extends naturally. |
| `sun_tzu` | **UPGRADE (C-3)** | LLM pulls context-appropriate Art of War quotes from a wider pool. |
| `bruce_lee` | **UPGRADE (C-3)** | Parallel to sun_tzu — flow-state philosophy extends beyond static templates. |
| `bureaucrat` | **UPGRADE (C-3)** | Heavy idiom load (forms, policy sections) — LLM extends without explicit form-name authoring. |
| `columbo` | **UPGRADE (C-4, post-M-4)** | Most AP-thematically-aligned; bridges persona ↔ dossier ("just one more thing… have we checked the WHOIS?"). |

Full per-mode rationale in `.claude/plans/character-v2-roadmap.md` §4.

### Decomposition Index — C-1 through C-4 (each becomes a separate planner workflow)

| Slice | Title | Size | Blocked by | v0.x target |
|-------|-------|------|------------|-------------|
| **C-1 (MVP)** | First Upgraded Mode (`full_troll` recommended) — `LLMPersonaProfile` dataclass + `CharacterMode.llm_profile` field + extended `AgentRunner.set_character` composer + F62/F64 invariant test suite | S–M | nothing | v0.2.x |
| C-2 | Voice-Driven Modes upgrade (drunken_master, bobby_hill, chuck_norris) — three profiles authored against the C-1 schema; no code change beyond data | M | C-1 | v0.2.x |
| C-3 | Philosophy + Bureaucratese Modes upgrade (sun_tzu, bruce_lee, bureaucrat) — three idiom-heavy profiles | M | C-1 (C-2 not required) | v0.2.x or v0.3.x |
| C-4 | `columbo` upgrade + optional `mastery_level` hook (C-4 planner decides whether to implement or retire the hook) | M–L | C-1; **prefers post-M-4** for dossier-aware `context_hooks` | v0.3.x |

**Critical path:** C-1 → (C-2, C-3, C-4 parallel after C-1). C-4 *prefers* post-M-4 (#68 persistent dossier state) so columbo's `context_hooks` can reference real slot state; not strictly blocked.

**Sequencing relative to AP #68 (DEC-30-CHARACTER-V2-007):**

```
v0.2.0:  C-1 + M-1                  (parallel, independent — zero dependency)
v0.2.x:  C-2 + M-2 + M-3            (parallel, independent)
v0.3.x:  C-3 + M-4 + M-5 + M-6      (parallel, independent)
v0.3.x:  C-4 + M-7                  (C-4 prefers post-M-4 ✓; M-7 prefers post-C-1 ✓)
v0.3.x:  M-8
v0.3.0+: M-9
```

### F62 / F64 / F60 Non-Superseded Invariants (continue to bind)

The character v2 reframe **does not** supersede any of these v1 invariants. They continue to apply to C-1 through C-4:

- **DEC-MODE-001/002** — CharacterMode as frozen dataclass; `score_celebration` uses `str.format(points=N)`. Extension of CharacterMode with `llm_profile` is a compatible field addition.
- **DEC-62-KILL-DOC-LIES-001** — `hint_style` deleted; `run_fail` is the single authority for failure voice. v2 personas MUST NOT re-introduce a `hint_style` field or any parallel failure-voice surface.
- **F62 StreakManager single-authority** (DEC-62-STREAK-*) — persona has no streak fields. Mastery (if C-4 implements it) keys off session count, NOT streak state.
- **DEC-64-LLM-PANEL-SEPARATION-001** — gamification events (celebrations, badges, challenges) ride on the Rich-panel sidecar; persona LLM text MUST NOT smuggle "+N points" strings.
- **F60 pivot policy** (DEC-60-PIVOT-POLICY-001..007) — architecturally disconnected from the persona surface. Persona MUST NOT influence pivot decisions.
- **DEC-AGENT-CHAT-002** — `mode` meta-command routing in `chat.py`. v2 does not alter the meta-command surface; only the `set_character` consumer changes.
- **Sacred Practice 12** (single authority per operational fact) — v2 personas are an *additive* layer over the F62 CharacterMode surface; one integration site (`AgentRunner.set_character`).
- **DEC-68-DOSSIER-REFRAME-004** — #30 stays independent of the dossier reframe. v2 personas drive presentation flavor; the dossier drives analytic state. Orthogonal axes.

### Out-of-Scope for This Workflow

- **No source code touched.** This is the planning slice. Only `MASTER_PLAN.md` and `.claude/plans/character-v2-roadmap.md` are written.
- **No new modes.** The 10 F62-cleaned modes are the v2 catalog. New persona ideas get a fresh issue and a fresh planner pass.
- **No cmd2 console persona-prompt changes.** v2 persona profiles are an `ap chat` (agentic) surface only. The cmd2 path remains the F62 Rich-panel-voice path.
- **No new gamification events.** Persona is pure presentation flavor; never emits `ScoreEvent`s, never earns badges, never triggers challenges.
- **No persona-bound tool restrictions.** `tool_preferences` is voice flavor only. Bureaucrat mode does NOT actually require Form TPS-001 before crt.sh enrichment.
- **No federation, no real-time multi-user, no DALL-E, no web/GUI.** v1 Non-Goals continue to bind.
- **No MCP-migration (#65) dependency.** Orthogonal.

### Subsequent Workflow Cue

After this planning slice lands, the recommended next workflow is **C-1** (First Upgraded Mode — `full_troll`). Smallest viable shipping unit; validates `LLMPersonaProfile` schema + F62/F64 invariant tests against one real persona before 7 others inherit any latent bug. The planner that opens C-1 authors its own Evaluation Contract and Scope Manifest under a successor workflow id (e.g., `w-30-c1-full-troll-profile`).

C-1 may be sequenced in parallel with W-68-M1-DOSSIER-PANEL (DEC-30-CHARACTER-V2-007 — zero dependency; v0.2.0 product story benefits from landing both).

### Decision Log (Phase 17)

| DEC ID | Decision | Rationale |
|--------|----------|-----------|
| DEC-30-CHARACTER-V2-001 | The "Borderlands/Fallout RPG style" brief is interpreted as a *voice-quality recommendation* applied non-uniformly across the existing 10 F62-cleaned modes, NOT a literal IP-aesthetic mandate that replaces the catalog. Option (c) selected over (a) replace-with-genre and (b) replace-with-professional. | F62 (W-62-STREAK-AND-HONEST-MODES) just landed 10 honest modes one day prior to this scoping; throwing them out one day later wastes the cleanup and violates Sacred Practice 12's "addition without subtraction" warning. The 10-mode catalog serves user-mood states (irreverent vs strategic vs investigative vs bureaucratic) that a single-genre catalog cannot. The brief's "Borderlands/Fallout" words fit best as the voice quality of the snarky-irreverent modes (`full_troll` especially), not as a catalog-wide aesthetic. |
| DEC-30-CHARACTER-V2-002 | Per-mode disposition: 8 UPGRADE (full_troll, drunken_master, bobby_hill, chuck_norris, sun_tzu, bruce_lee, bureaucrat, columbo); 2 KEEP_STATIC (default, ninja); 0 RETIRE. KEEP_STATIC ≠ second-class — those modes serve "no flavor" / "minimal flavor" user-mood anchors that LLM-upgraded modes cannot serve without contradicting themselves. | Each disposition justified in `.claude/plans/character-v2-roadmap.md` §4 table. KEEP_STATIC modes earn their slots by purpose, not by adoption of the v2 mechanism. |
| DEC-30-CHARACTER-V2-003 | Personality profile schema v1.0 (8 fields; per-mode token budget ≤ 165 tokens) injects via the existing `AgentRunner.set_character` site (`runner.py:278-295`) as a system-prompt fragment. Reject (b) sidecar agent and (c) response post-processor as parallel-authority surfaces that violate F60 token-budget discipline. CharacterMode is extended with `llm_profile: LLMPersonaProfile | None = None` (compatible — frozen-dataclass field addition, DEC-MODE-001 discipline preserved). | Single integration site honors Sacred Practice 12. No additional LLM round-trips per turn. Token budget bounded and test-enforced. Refinement window: C-1 may refine the schema by ±2 fields before first implementer touches code; further refinement requires planner re-stage and successor DEC-ID. |
| DEC-30-CHARACTER-V2-004 | "RPG-style level progression" from the issue body is partially adopted: the XP-grind / skill-tree / loot / quest forms are **retired** (already retired by DEC-68-DOSSIER-REFRAME-005 superseding #31). A narrow `mastery_level: int` hook on `LLMPersonaProfile` is **deferred to C-4** as an optional future expressive-depth axis keyed off session count or per-mode dossier-completion count, NOT off score-grinding. The C-4 planner may retire the mastery hook entirely if the prior slices' usage patterns don't justify it. | Re-introducing XP grind would directly contradict the dossier reframe (#68) and Sacred Practice 12's parallel-authority warning. Per-persona expressive depth is unambiguously a UX-flavor axis, not a scoring axis, and is bounded enough that it cannot drift into score-grinding. Deferring to C-4 lets the prior slices' usage patterns inform whether the mastery axis is worth implementing at all. |
| DEC-30-CHARACTER-V2-005 | F62 + F64 invariants are jointly preserved: `mode.run_fail` remains the sole authority for failure voice (`tools.py:1622-1628` wiring untouched); StreakManager remains the sole streak authority (persona has no streak fields); `hint_style` is not re-introduced; gamification-event narration stays on the Rich-panel surface (LLM persona text MUST NOT smuggle "+N points" / "+N pts" strings); `tool_preferences` is voice-affinity only and MUST NOT bias tool selection. C-1's Evaluation Contract includes a persona-swap-tool-call-identity test as a hard gate. F60 auto-pivot policy is architecturally disconnected from the persona surface. | v2 personas are **strictly additive** to the F62 CharacterMode surface — the existing Rich-panel-voice fields (`prompt_prefix`, `greeting`, `run_success`, `run_fail`, `score_celebration`) and the existing single-authority wirings stay exactly as they are. The most important *forbidden shortcut* is the `tool_preferences` field becoming a tool-selection bias; the persona-swap test is the gate that catches it. |
| DEC-30-CHARACTER-V2-006 | C-1 is the MVP: one upgraded mode (`full_troll` recommended) + the `LLMPersonaProfile` dataclass + the extended `set_character` composer + the invariant test suite (F62 single-authority for `run_fail`; F64 panel-separation; tool-call-identity under persona swap; per-mode token budget). v0.2.x target. ≤ 2 weeks implementer effort. The other 9 modes ship at `llm_profile=None` (default) and continue to behave exactly as F62 until C-2/C-3/C-4. | MVP validates the schema and the invariant test suite against one real persona before 7 others inherit any latent bug. Smallest unit of demonstrable user-visible v2 value; reversible at the per-mode boundary; user can A/B compare voice by `mode full_troll` then `mode default`. |
| DEC-30-CHARACTER-V2-007 | Sequencing relative to AP #68: C-1 lands **parallel with M-1** (zero dependency between them; the two slices share `agent/chat.py` only as a file-level coincidence — M-1 adds a meta-command branch; C-1 does not edit `chat.py` at all). C-2/C-3 may land any time after C-1 (additive). **C-4 prefers post-M-4** (dossier persistent state) so columbo's `context_hooks` can reference real slot state. **M-7 prefers post-C-1** so LLM-narrated celebrations can lean on `LLMPersonaProfile` for voice consistency. All four preferences are simultaneously satisfiable per the §6.5 schedule. | No critical-path conflict. Parallel C-1/M-1 makes v0.2.0 a stronger product story (visible dossier panel + recognizable Borderlands-snark voice) than either alone. Orchestrator may schedule C-1 and M-1 to the same wave or stagger them — both are consistent with this scoping. |

---

## Phase 17B: Dossier Visualization Panel — M-1 MVP Implementation (W-68-M1-DOSSIER-PANEL, post-v1, 2026-05-28)

**Status:** completed
**Merge SHA:** `486a5ad` (Merge #68: feat(dossier): M-1 Dossier Visualization Panel MVP)
**Implementer commit:** `11aaf83` (feat(dossier): M-1 Dossier Visualization Panel MVP — read-only slot inference + Rich panel)
**Worktree (now disposable):** `/Users/jarocki/src/ap/.worktrees/feature-68-m1-dossier-panel` (branch `feature/68-m1-dossier-panel`, base AP main `fe4c0b1`).
**Closeout note (2026-05-29):** This section is recovered from the M-1 worktree where it was planner-authored but never reached main because the implementer did not pick up the planner's staged MASTER_PLAN.md edit. AP #74 documents the bookkeeping gap; this closeout slice (`w-plan-drift-fix-2026-05-29`) harvests the content verbatim.

**Source:** Phase 16 (W-68-DOSSIER-REFRAME-SCOPING) ratified the dossier-puzzle metaphor as v2's product center and decomposed the reframe into M-1..M-9 follow-on workflows. M-1 is the smallest valuable shipping unit per `.claude/plans/dossier-reframe-v2-roadmap.md` §5 / §7. M-1 shared the v0.2.0 wave with C-1 (Phase 17C / W-30-C1-FULL-TROLL-PROFILE) per DEC-30-CHARACTER-V2-007 — zero dependency between them.

### M-1 Desired End State (verbatim from goal contract)

> Ship the v0.2.0 MVP slice of #68 dossier-puzzle reframe: a read-only Dossier panel surfaced in `ap chat` that visualizes filled slots from the user's CURRENT workspace state — no new scoring math yet, no extractors yet, no persistence yet beyond what STIX SCOs already give us. The panel renders the 9 slots (Identity/TTPs/Infrastructure/Timing/Targeting/Capability/Motivation/Predictions/Denial) with fill status (empty/partial/filled) inferred from SCO type + provenance fields already in workspace. User can invoke via meta-command (e.g., `dossier` or `show dossier`).

### Decision Log (Phase 17B / M-1)

| DEC ID | Decision | Rationale |
|--------|----------|-----------|
| **DEC-M1-DOSSIER-001** | The new `src/adversary_pursuit/dossier/` package is the sole read-only authority for slot inference. It CONSUMES `WorkspaceManager.get_stix_objects()` and emits a `DossierState` value object; it MUST NOT call any workspace mutator and MUST NOT set any `x_ap_*` provenance field (DEC-59-STIX-PROVENANCE-001 preserved). | Sacred Practice 12: the question "what is the dossier state of this workspace?" gets exactly one owner. Putting inference helpers in `core/` or `gamification/` would split the authority across two packages on day one. Placing it in `dossier/` matches the Phase 16 layering (DEC-68-DOSSIER-REFRAME-002: `dossier/` is the new analytic-value layer that rides over the existing scoring authority). |
| **DEC-M1-DOSSIER-002** | M-1 exercises the DEC-68-DOSSIER-REFRAME-010 ±2-slot refinement window conservatively: **the 9-slot vocabulary is unchanged**. Instead, the presentational status enum is widened from {`empty`, `partial`, `filled`} to {`empty`, `partial`, `filled`, `deferred`}. Slots 4 (Timing), 5 (Targeting), 6 (Capability), 7 (Motivation), 8 (Predictions), 9 (Denial) render as `deferred` in M-1 because their inference paths land in M-2 / M-4 / M-5. Slots 1 (Identity), 2 (TTPs), 3 (Infrastructure) infer real status from SCO types listed in roadmap §3. | Mutating the schema before MVP contact with real data would burn the ±2-slot window for cosmetic reasons. A `deferred` status is honest about the M-1 surface: the slot is part of the v2 vocabulary, but its inference is scheduled for a later slice. This is presentational, not a schema change, and is reversible at the per-slot level when M-2 lands. |
| **DEC-M1-DOSSIER-003** | Panel rendering authority is `dossier.panel.render(state: DossierState) -> rich.panel.Panel` — a pure function returning a `rich.panel.Panel` for the chat REPL to print via the existing `console.print(panel)` site. No new helper is added to `core/console.py`; chat.py composes the rich.console.Console (already constructed) with `dossier.panel.render(...)`. | Pure-function rendering matches the existing `RelationshipGraph.render_tree()` and `RelationshipGraph.export_gexf()` patterns used by the `graph` and `export gexf` meta-commands (chat.py:368–416). Avoids growing `core/console.py` into a second dossier-aware surface. Reuses the rich.console.Console singleton already present in chat.py. F64 LLM/Panel separation honored — the panel is Rich-only, never enters the LLM prompt path. |
| **DEC-M1-DOSSIER-004** | The meta-command surface is `dossier` (with alias `show dossier`). It is a deterministic local handler in `chat.py` — no LLM dispatch, no agent-tool invocation, no `get_dossier_state` LLM tool in M-1. The roadmap §7 mentions `get_dossier_state` as part of M-1 acceptance; this DEC narrows the M-1 surface to the panel only, deferring the LLM tool to M-2 where the module→slot mapping is the natural input for an LLM-readable structured dict. The help_table in `chat.py` gains a `dossier` row. | M-1 is the visualization MVP; adding a parallel LLM tool surface in the same slice expands blast radius unnecessarily (agent/tools.py is forbidden territory for M-1). The user demo "open ap chat, run a hunt, type dossier" is delivered fully by the meta-command. The LLM tool lands cleanly in M-2 when extractors give it real per-module input vocabulary. Roadmap §7 acceptance is honored at the panel level; M-2 picks up the LLM tool with its own evaluation contract. |

### M-1 Work Item Index

| ID | Title | Type | Status |
|----|-------|------|--------|
| **wi-68-m1-planner** | M-1 planner: dossier panel MVP Evaluation Contract + Scope Manifest | docs only | landed (Phase 17B section authored in M-1 worktree; harvested to main via plan-drift closeout 2026-05-29) |
| **wi-68-m1-impl-01** | M-1 implementer: Dossier Visualization Panel MVP (read-only inference + Rich panel + chat meta-command) | source + tests | landed @ `11aaf83`; merged @ `486a5ad` |

### M-1 Scope Manifest (summary)

**Allowed (10):** the new `src/adversary_pursuit/dossier/` package (`__init__.py`, `slots.py`, `slot_inference.py`, `panel.py`), `src/adversary_pursuit/agent/chat.py` (meta-command surface only), four new test files (`test_dossier_slots.py`, `test_dossier_slot_inference.py`, `test_dossier_panel.py`, `test_chat_dossier_metacommand.py`), and `MASTER_PLAN.md`.

**Forbidden (30, partial list):** `core/workspace.py` (F59), `core/pivot_policy.py` (F60), `core/streak.py` + `gamification/scoring.py` (F62), `core/event_bus.py` (DEC-EVENTBUS-002 opt-in discipline), `core/console.py` (DEC-M1-DOSSIER-003), `agent/tools.py` (F64 LLM/Panel separation), `agent/runner.py` (no persona/LLM coupling), `modules/**` (Principle 4), `models/**` (no schema mutation), `gamification/**` (no scoring/celebration changes — that is M-3 / M-7), `pyproject.toml` / `uv.lock` (no dependency adds), `hooks/**`, `settings.json`, `CLAUDE.md`, `agents/**`, `.claude/**`.

**State domains touched:** `dossier_slot_inference`, `dossier_panel_rendering`, `chat_metacommand_dispatch`.

### M-1 Evaluation Contract (summary, as evaluated by reviewer pre-landing)

| Key | Count | Notes |
|-----|-------|-------|
| `required_tests` | 35 | 3 schema tests; 18 inference tests; 6 panel tests; 5 meta-command tests; 3 deferred-status assertions. |
| `required_evidence` | 3 | Full pytest output; ruff exit 0; pasted Rich panel renderings for the three acceptance scenarios. |
| `required_real_path_checks` | 3 | End-to-end `dossier` meta-command against fixture-populated and empty WorkspaceManager; assertion that LLM dispatch is NOT invoked on the `dossier` input. |
| `required_authority_invariants` | 7 | DEC-59-STIX-PROVENANCE-001; DEC-60-PIVOT-POLICY-001..007; DEC-62-STREAK-* + scoring; DEC-64-LLM-PANEL-SEPARATION-001; Sacred Practice 12 (dossier/ sole authority); Principle 4 (modules untouched); DEC-68-DOSSIER-REFRAME-010 (vocabulary unchanged; status enum widened only). |
| `required_integration_points` | 3 | `chat.py` (meta-command branch + help_table row, mirror `graph` / `export gexf` local-handler pattern); `core/workspace.py` (CONSUME `get_stix_objects()` read-only); `core/console.py` (REUSE existing rich.console.Console). |
| `forbidden_shortcuts` | 9 | No SCO mutation; no LLM-summary emission; no scoring math; no persistence; no pivot-policy changes; no env-var bypass; no SCO-type auto-discovery; no silent fallback on malformed SCOs; no event-bus emit. |
| `rollback_boundary` | — | Single feature branch revertable as one merge commit; no schema migrations, no settings changes. |
| `ready_for_guardian_definition` | — | All 35 required_tests pass; full suite green; ruff exit 0 over scope; scope-check finds no diff outside allowed + no diff inside forbidden; real-path renderings pasted; 7 authority invariants verified. |

### M-1 Out-of-Scope (deferred to later slices — see Phase 17D for what M-2 picked up)

- **`get_dossier_state` LLM tool** — deferred to M-2 (Phase 17D landed it). Roadmap §7 §M-1 mention narrowed to "panel only" by DEC-M1-DOSSIER-004.
- **No `DossierSlotFilled` ScoreEvent** — deferred to M-3.
- **No SQLite tables** — deferred to M-4. M-1 computes `DossierState` on demand from current workspace SCO list each invocation.
- **No user-note `dossier note` command** — deferred to M-5.
- **No pivot-policy slot input** — deferred to M-6.
- **No celebration / report / badge upgrades** — deferred to M-7.
- **No CharacterMode coupling** — orthogonal per DEC-30-CHARACTER-V2-007.

### Decision Log (Phase 17B summary; verbatim from M-1 worktree)

| DEC ID | Decision | Rationale |
|--------|----------|-----------|
| DEC-M1-DOSSIER-001 | New `src/adversary_pursuit/dossier/` package is the sole read-only authority for slot inference; CONSUMES `WorkspaceManager.get_stix_objects()`; never mutates workspace; never sets `x_ap_*`. | Sacred Practice 12. Phase 16 DEC-68-DOSSIER-REFRAME-002 placed the analytic-value layer in a new `dossier/` namespace; M-1 instantiates that namespace with the smallest possible read-only surface so subsequent slices extend rather than refactor. |
| DEC-M1-DOSSIER-002 | M-1 exercises the DEC-68-DOSSIER-REFRAME-010 ±2-slot window conservatively: vocabulary unchanged; presentational status enum widened to {empty, partial, filled, deferred}. 6 slots render `deferred` in M-1; 3 slots (Identity / TTPs / Infrastructure) infer real status. | A `deferred` status keeps the v2 vocabulary visible without burning the ±2 window on cosmetic changes. Reversible at per-slot level when M-2 / M-4 / M-5 supply inference paths. |
| DEC-M1-DOSSIER-003 | Panel rendering authority is `dossier.panel.render(state) -> rich.panel.Panel`, a pure function. No new helper in `core/console.py`. chat.py calls the existing `console.print(panel)` site. | Matches the existing `RelationshipGraph.render_tree()` / `export_gexf()` pure-function pattern used by `graph` and `export gexf` meta-commands (chat.py:368–416). Avoids growing `core/console.py` into a second dossier-aware surface. F64 honored — panel is Rich-only. |
| DEC-M1-DOSSIER-004 | Meta-command surface: `dossier` and alias `show dossier`. Deterministic local handler; no LLM dispatch; no `get_dossier_state` LLM tool in M-1 (deferred to M-2; landed in Phase 17D). `chat.py` help_table gains a `dossier` row. | Adding the LLM tool in M-1 expands blast radius into `agent/tools.py` (forbidden territory for M-1). The user-visible demo is fully delivered by the meta-command. The LLM tool lands cleanly in M-2 alongside the extractor vocabulary it consumes. |

---

## Phase 17C: Character v2 — C-1 MVP — `full_troll` LLMPersonaProfile (W-30-C1-FULL-TROLL-PROFILE, post-v1, 2026-05-28)

**Status:** completed
**Merge SHA:** `e49e70b` (Merge branch 'feature/30-c1-full-troll-profile' — C-1 full_troll persona MVP)
**Implementer commit:** `5417cec` (feat(character-v2): C-1 MVP — full_troll LLMPersonaProfile + set_character injection)
**Worktree (now disposable):** `/Users/jarocki/src/ap/.worktrees/feature-30-c1-full-troll-profile` (branch `feature/30-c1-full-troll-profile`, base AP main `fe4c0b1`).

**Closeout / Renumber note (2026-05-29):** This section is recovered from the C-1 worktree where the C-1 planner originally numbered it `Phase 17B` (independently from M-1's planner who picked the same number). C-1 landed approximately 5 minutes after M-1 (M-1 merge `486a5ad` 2026-05-28 ~22:54 UTC; C-1 merge `e49e70b` 2026-05-28 ~22:59 UTC), so this closeout (`w-plan-drift-fix-2026-05-29`) renumbers the C-1 section to **17C** per chronological merge order; all other content is harvested verbatim. AP #74 documents the bookkeeping gap that produced two independent `Phase 17B` titles in parallel worktrees.

**Workflow:** `w-30-c1-full-troll-profile` / goal `g-30-c1-full-troll-profile` / planner work item `wi-30-c1-planner` / implementer work item `wi-30-c1-impl-01`.
**Parallel with:** `w-68-m1-dossier-panel` (DEC-30-CHARACTER-V2-007 zero-dependency invariant; dossier package and `agent/chat.py` were in C-1's `forbidden_paths`).

**Bound by upstream:** DEC-30-CHARACTER-V2-001..007 (Phase 17). C-1 executes DEC-30-CHARACTER-V2-006 (C-1 MVP scope) without re-litigating it.

### What shipped

1. `LLMPersonaProfile` frozen dataclass in `gamification/modes.py` per roadmap §3.2 (8 fields; per-mode token budget ≤ 165).
2. `CharacterMode.llm_profile: LLMPersonaProfile | None = None` (compatible field addition under DEC-MODE-001).
3. `full_troll`'s `LLMPersonaProfile` instance (voice = snarky/irreverent/meta-aware, Borderlands/Fallout style per DEC-30-CHARACTER-V2-001). The other 9 modes ship at `llm_profile=None` (= F62 behavior preserved verbatim).
4. Extended `AgentRunner.set_character` composer in `agent/runner.py:278-295` per roadmap §3.3: when `mode.llm_profile is not None`, compose the profile fragment into `self.system_prompt`; when `None`, preserve the v1 composition byte-identical.
5. Test surface — extension of `tests/test_modes.py` + two new files (`tests/test_character_v2_full_troll.py`, `tests/test_agent_runner_persona.py`) covering 20 named tests including F62/F64 invariant gates and the persona-swap-tool-call-identity hard gate.

### Per-slice decisions (binding for C-1; further slices re-decide per their own planner pass)

| DEC ID | Decision | Rationale |
|--------|----------|-----------|
| **DEC-C1-FULLTROLL-001** | `full_troll`'s `LLMPersonaProfile` content is authored as: **voice_summary** "Chaotic-good shitposter who narrates threat intel like Claptrap commentating a CTF speedrun"; **tone_registers** ("snarky", "irreverent", "loud", "meme-aware"); **signature_phrases** ("LEEEROOY JENKINSSS", "GET REKT ADVERSARY", "bruh", "absolute unit of an IOC", "git rekt scrub"); **fourth_wall_stance** "meta_aware" (full_troll knows it's an LLM and revels in it); **dialect_cadence** "ALL-CAPS bursts punctuated by lowercase asides; one-line zingers; emoji used as punctuation"; **context_hooks** `()` (deferred — see DEC-C1-FULLTROLL-005); **tool_preferences** ("crt.sh feels like searching a haunted Wikipedia at 3am", "VirusTotal hits are the loot drop of the OSINT world") — phrased as voice-affinity only, NEVER as preference instruction; **forbidden_voice** ("never narrate point totals — the Rich panel owns scoring", "never use bureaucratese", "never apologize for being snarky"). Implementer copies this content verbatim. | Brief asked for Borderlands/Fallout snarky-irreverent voice; full_troll's existing static surfaces (`run_success="GET REKT ADVERSARY!"`, `run_fail="BRUH. Even my grandma..."`) already establish the register, so the LLM profile *extends* the same voice into chat responses instead of inventing a new persona. `forbidden_voice` mechanically blocks the F64 panel-separation shortcut (no "+N points" smuggling) at the prompt level. `tool_preferences` framing is deliberately *affinity language* ("feels like") not *instruction language* ("prefer") so the LLM cannot reasonably interpret it as selection bias — and the persona-swap-tool-call-identity test gates it anyway. |
| **DEC-C1-FULLTROLL-002** | Schema realized as `CharacterMode.llm_profile: LLMPersonaProfile \| None` (default `None`). Other 9 modes inherit the default and need zero code change to their existing fields. `LLMPersonaProfile` is a `@dataclass(frozen=True)` mirroring `CharacterMode`'s DEC-MODE-001 discipline. | Compatible extension; preserves DEC-MODE-001 frozen-dataclass invariant; the `None`-default path is the F62-behavior path verbatim (test gate: `test_set_character_default_uses_v1_composition_verbatim`). |
| **DEC-C1-FULLTROLL-003** | Injection mechanism: in-place concatenation inside `AgentRunner.set_character` at the existing call site (`runner.py:278-295`). The v2 composition replaces the v1 `f"Character mode: {mode.name}\n{mode.personality}\n\n"` prefix with the §3.3 multi-line profile fragment, then concatenates `_default_system_prompt()` as before. **NO** post-processor pass over LLM responses; **NO** sidecar agent; **NO** new tool that re-narrates. | DEC-30-CHARACTER-V2-003 (a) selected; (b) and (c) rejected as parallel-authority surfaces. Single integration site honors Sacred Practice 12. Reverting C-1 restores byte-identical v1 behavior because the only changed code path is `set_character` and the `None`-default branch keeps the v1 string verbatim. |
| **DEC-C1-FULLTROLL-004** | Tool-selection-bias forbidden-shortcut test pattern: `test_persona_swap_preserves_tool_call_identity` constructs a deterministic mock LLM that records `(tool_name, tool_args_json)` for each turn, drives the AgentRunner through a fixed synthetic query under `full_troll`, then drives it through the *same fixed query* under `default`, and asserts the two recorded tool-call sequences are byte-identical. The mock returns a canned response so the test does not depend on real LLM behavior; the gate is that *the persona profile does not change what the agent system surface emits as tool selections*. If the implementer cannot produce a deterministic harness, the planner re-stages — this test is non-negotiable per DEC-30-CHARACTER-V2-005. | Without a mechanical gate, `tool_preferences` can drift into a selection-biasing field over time (the worst forbidden shortcut in the v2 design). A deterministic mock-LLM harness gives us a regression test that survives across all 4 C-slices. Equivalent in pattern to F60's mocked policy-engine tests. |
| **DEC-C1-FULLTROLL-005** | `context_hooks` for `full_troll` ships as **empty tuple `()`** in C-1. Reason: meaningful context hooks depend on real dossier slot state, which lands in #68 M-4 (parallel/independent of C-1 but not yet shipped). Authoring placeholder hooks now would either be generic (low value) or speculative (couples C-1 to an unbuilt surface). Empty tuple is the v1.0-schema-conformant minimum. C-2 and later slices may use `context_hooks` for their persona if those personas don't have a dossier dependency; the columbo C-4 slice is the one explicitly waiting on M-4. **Refinement window applied:** uses 1 of the ±2 fields C-1 was authorized to refine under DEC-30-CHARACTER-V2-003 — *not* by deleting `context_hooks` from the schema, but by deliberately authoring it empty for full_troll. The schema field stays. | Sacred Practice 7: code is truth, and the truth for C-1 is that there is no dossier state for `context_hooks` to bind to yet. Better to ship empty (honest) than to ship placeholder text (a doc lie). When M-4 lands, a small follow-up slice can populate `full_troll.llm_profile.context_hooks` without re-litigating the schema. |

### C-1 Scope Manifest (summary; runtime-authoritative via `cc-policy workflow scope-sync`)

- **allowed_paths (6):** `src/adversary_pursuit/gamification/modes.py`, `src/adversary_pursuit/agent/runner.py`, `tests/test_modes.py`, `tests/test_character_v2_full_troll.py`, `tests/test_agent_runner_persona.py`, `MASTER_PLAN.md`.
- **required_paths (3):** `src/adversary_pursuit/gamification/modes.py`, `src/adversary_pursuit/agent/runner.py`, `tests/test_character_v2_full_troll.py`.
- **forbidden_paths (22):** notably `agent/tools.py` (F62 `run_fail` wiring — bytewise unchanged required), `agent/chat.py` (DEC-AGENT-CHAT-002 + parallel-workflow boundary for W-68-M1-DOSSIER-PANEL), `core/streak.py` (F62 StreakManager), `core/pivot_policy.py` (F60), `core/workspace.py` (F59), `gamification/celebrations.py` + `gamification/scoring.py` + `gamification/badges.py` (F62/F63/F64), `models/**`, `modules/**`, **`dossier/**`** (parallel M-1 territory), `pyproject.toml`, `CLAUDE.md`, `AGENTS.md`, `settings.json`, `hooks/**`, `agents/**`, `.claude/**`, `runtime/**`.
- **state_domains (2):** `character_persona_profile`, `agent_system_prompt_assembly`.

### C-1 Evaluation Contract (summary, as evaluated by reviewer pre-landing)

- **required_tests (20):** dataclass invariants on `LLMPersonaProfile` and `CharacterMode.llm_profile`; full_troll profile content and budget tests; set_character integration tests for full_troll-on and default-off; F62/F64 invariant gates including: `test_persona_swap_preserves_tool_call_identity` (hard gate — DEC-C1-FULLTROLL-004), `test_persona_text_not_present_in_tool_result_summary` (F64 hard gate), `test_full_troll_response_does_not_smuggle_point_totals` (F64), `test_run_fail_wiring_in_tools_remains_byte_identical_to_baseline` (F62), `test_run_fail_field_still_consumed_at_tools_py_1622_1628` (F62), `test_streak_manager_module_not_imported_by_modes_module` (F62).
- **required_evidence (6):** full pytest output (≥1901 baseline + new), `git diff main` of `tools.py` and `streak.py` showing zero changes, runtime verification that `full_troll.llm_profile is not None` and `default.llm_profile is None`, and proof that `set_character` toggles the profile fragment in/out of `system_prompt` correctly.
- **required_real_path_checks (4):** production-path AgentRunner construction with set_character toggles, exception-path verification at `tools.py:1622-1628` showing no persona text in LLM-facing error string, idempotency check across repeated set_character calls.
- **required_authority_invariants (9):** all DEC-MODE-*, DEC-62-*, DEC-64-*, DEC-30-CHARACTER-V2-005, DEC-AGENT-CHAT-002, F60 architectural-disconnection, and Sacred Practice 12 single-integration-site invariants.
- **required_integration_points (5):** modes.py LLMPersonaProfile + field; runner.py:278-295 set_character extension as SOLE injection site; three test files.
- **forbidden_shortcuts (14):** tool-selection-bias prohibition, F64 panel-leak prohibition, `tools.py`/`streak.py`/`chat.py`/`dossier/**` no-touch rules, no sidecar/post-processor, no `hint_style` re-introduction, no `mastery_level` field (deferred to C-4), no `context_hooks` content for full_troll (deferred per DEC-C1-FULLTROLL-005).
- **rollback_boundary:** single feature branch, revertible as one merge commit (no DB schema / persistence / config changes).
- **ready_for_guardian_definition:** all 20 required_tests pass; full pytest green; required_real_path_checks evidence pasted; git-diff-against-main empty for `tools.py`, `streak.py`, `chat.py`, `pivot_policy.py`, `dossier/**`; persona-swap-tool-call-identity hard gate passes; persona absent from LLM-facing tool summary and error string; token budget ≤ 165 for full_troll; scope compliance verified.

### Decision Log (Phase 17C summary; verbatim from C-1 worktree)

| DEC ID | Decision | Rationale |
|--------|----------|-----------|
| DEC-C1-FULLTROLL-001 | `full_troll`'s LLMPersonaProfile content authored per the field table above (voice_summary, tone_registers, signature_phrases, fourth_wall_stance, dialect_cadence, tool_preferences, forbidden_voice). Implementer copied verbatim. | Extends full_troll's existing F62 Rich-panel snark into the LLM chat surface without inventing a new persona; `forbidden_voice` mechanically blocks F64 "+N points" smuggling at the prompt level; `tool_preferences` framing is deliberately affinity-language not instruction-language to satisfy DEC-30-CHARACTER-V2-005 alongside the persona-swap test. |
| DEC-C1-FULLTROLL-002 | Schema realized as `CharacterMode.llm_profile: LLMPersonaProfile \| None = None`. `LLMPersonaProfile` is a frozen dataclass mirroring CharacterMode's DEC-MODE-001 discipline. | Compatible field addition; default None path is byte-identical to F62; reverting C-1 restores v1 behavior verbatim. |
| DEC-C1-FULLTROLL-003 | Injection via in-place concatenation inside the existing `AgentRunner.set_character` site (`runner.py:278-295`). No post-processor, no sidecar, no new tool. | DEC-30-CHARACTER-V2-003 (a) executed; single integration site honors Sacred Practice 12. |
| DEC-C1-FULLTROLL-004 | Tool-selection-bias gate: `test_persona_swap_preserves_tool_call_identity` uses a deterministic mock LLM that records `(tool_name, tool_args_json)` per turn, drives the runner under `full_troll` then `default` over a fixed query, and asserts byte-identical tool-call sequences. Non-negotiable hard gate. | The most important forbidden shortcut in v2 needs a mechanical gate, not a doc warning; deterministic mock harness is the pattern that makes the gate stable across C-2/C-3/C-4 as more personas land. |
| DEC-C1-FULLTROLL-005 | `full_troll.llm_profile.context_hooks` ships as `()` in C-1. The schema field stays; only the *content* is deferred until #68 M-4 lands real dossier slot state. Uses 1 of the ±2 field-refinement budget DEC-30-CHARACTER-V2-003 granted to C-1. | Sacred Practice 7: code is truth. With no dossier state to bind to, empty is honest; placeholder hook strings would be doc-lies. Follow-up slice (post-M-4) can populate without schema re-litigation. |

---

## Phase 17D: Per-Module Dossier Slot Extractors + `get_dossier_state` LLM Tool — M-2 (W-68-M2-SLOT-EXTRACTORS, post-v1, 2026-05-29)

**Status:** completed
**Merge SHA:** `11b3fd3` (Merge #68 M-2: per-module dossier slot extractors + get_dossier_state LLM tool)
**Implementer commit:** `83a98d9` (feat(dossier): M-2 per-module slot extractors + get_dossier_state LLM tool (#68))
**Per-slice plan (authoritative for content rationale):** `.claude/plans/dossier-m2-slot-extractors.md` (landed alongside source).

**Closeout note (2026-05-29):** M-2 landed code-only — the per-slice plan was authored to `.claude/plans/dossier-m2-slot-extractors.md` and the source files were annotated with `DEC-M2-DOSSIER-001..005` and `DEC-M2-MOTIVATION-001` references, but no Phase 17D section was added to `MASTER_PLAN.md` (deferred to AP #74 doc closeout to avoid stacking more orphaned-planner-content carry-forward). This closeout slice harvests the binding decisions and Evaluation Contract summary from the per-slice plan and the source annotations.

**Source:** Phase 16 (W-68-DOSSIER-REFRAME-SCOPING) decomposed the reframe into M-1..M-9. M-1 (Phase 17B) shipped a 9-slot panel with real inference for 3 slots and `DEFERRED` placeholders for the other 6. M-1 also deferred the `get_dossier_state` LLM tool per DEC-M1-DOSSIER-004. M-2 closes both gaps: real extractors for 4 more slots (Timing / Targeting / Capability / Motivation), typed scaffolding for the remaining 2 (Predictions / Denial), and the LLM tool.

### M-2 Goal (verbatim from per-slice plan §1)

> After M-2:
> - The dossier panel renders **real status** for at least 4 of the 6 currently-deferred slots (Timing, Targeting, Capability, Motivation). Predictions and Denial remain deferred as *scaffold-only* — but their deferral marker names a clearer milestone (M-4 / M-5) rather than re-using the generic M-2 placeholder.
> - The agent has a `get_dossier_state` LLM tool that returns a structured dict the LLM can reason about ("which slot to push next?").
> - All Phase 16 / Phase 17 invariants preserved (F59 / F60 / F62 / F63 / F64).
> - M-1 panel + meta-command rendering continues to work unchanged (regression test).

### Decision Log (Phase 17D / M-2; verbatim from per-slice plan §2 and source annotations)

| DEC ID | Decision | Rationale |
|--------|----------|-----------|
| **DEC-M2-DOSSIER-001** | Per-slot extractor architecture: each of the 6 new slots has its own pure-function `_infer_<slot>_slot(...)` extractor. A single dispatcher `infer_dossier_state_full(scos, module_runs, notes)` fans out to each extractor and assembles the `DossierState`. Per-slot extractors over a single-pass aggregator. The legacy `infer_dossier_state(scos)` is preserved as a thin wrapper (M-1 chat meta-command site is byte-identical). | Per-slot extractors map 1:1 to per-slot unit tests, which is exactly the Evaluation Contract shape M-2 needs. Single-pass aggregator would force same-shape inputs or duplicate per-slot branching; per-slot extractors are clearer, more testable, and let each slot evolve independently in future milestones. |
| **DEC-M2-DOSSIER-002** | Timing extractor uses `x_ap_fetched_at` (DEC-59-STIX-PROVENANCE-001 surface — read-only) + `module_runs.timestamp` and clusters by hour-of-day UTC; "FILLED" threshold is ≥10 total events AND ≥25% concentrated in one of 24 hour buckets. Weekday clustering deferred to M-3 (documented as a TODO marker in code with explicit DEC-M2-DOSSIER-002 reference). | Matches roadmap §3 confidence ladder (Low <5 / Medium 5-10 / High ≥10 + cluster). 25% in 1 of 24 buckets is ~6× uniform — a strong working-hours signal — without pulling in scipy or full statistical clustering. M-3 may refine. |
| **DEC-M2-DOSSIER-003** | Capability extractor: "expected modules" is `set(DEFAULT_SUBSCRIPTIONS.keys())` from `core/event_bus.py`, evaluated at call time (not hardcoded). "Not observed" = expected − observed (from `module_runs`). FILLED requires ≥3 observed AND ≥3 unobserved. | `DEFAULT_SUBSCRIPTIONS` is the canonical module-arsenal authority the auto-pivot engine already uses; reusing it avoids creating a parallel "module list" surface (Sacred Practice 12). The 3+3 thresholds give a meaningful breadth + ceiling-inference signal without false-positives on tiny investigations. Forbidden shortcut: the extractor MUST NOT hardcode "[12]" anywhere — it must compute `len(DEFAULT_SUBSCRIPTIONS)` at call time. |
| **DEC-M2-DOSSIER-004** | Predictions (slot 8) and Denial (slot 9) ship as scaffold-only in M-2: extractors always return `SlotStatus.DEFERRED`; M-2 adds typed `PredictionRecord` / `DenialStrategyRecord` dataclasses (in `dossier/slots.py`) so M-4 / M-5 have stable shapes to target. No auto-inference, no in-memory state, no persistence. | Predictions need persisted cross-session state (M-4 owns); Denial needs a user-note authoring surface (M-5 owns). Doing either in M-2 would build the wrong shape (in-memory predictions are lost; UX trap) or pull M-4/M-5 scope into M-2. Scaffolding ships now so successor slices have a stable contract. |
| **DEC-M2-DOSSIER-005** | `get_dossier_state` LLM tool returns a typed JSON dict (`{slots: {name: {status, evidence_count, fill_percentage, weight}}, total_sco_count, summary}`) as its `summary` string. No Rich markup, no `_SLOT_DISPLAY_NAME` text, no `dossier.panel.render()` invocation in the tool path. The tool delegates to `dossier.slot_inference` — it does NOT re-infer in `agent/tools.py`. | F64 (DEC-64-LLM-PANEL-SEPARATION-001) applied to the dossier package: the LLM-facing representation is structured data the LLM reasons about; the user-facing representation is the Rich panel. Same `DossierState` source-of-truth, two separate presentations, no double-narration risk. Sacred Practice 12 honored — `dossier/` remains the sole inference authority. |
| **DEC-M2-MOTIVATION-001** | Motivation extractor reads `AnalystNote` rows via the same direct-engine query pattern `core/report.py` already uses (lines 348-369); no new `workspace.py` accessor is added. The Motivation extractor receives `notes: list[dict]` as a parameter (pre-fetched by the caller), parallel to how it receives `scos: list[dict]` today. | The dispatch spec said "derive from analyst-note tagging (workspace notes already exist)" but the workspace has no `get_analyst_notes()` reader and the spec forbids touching `workspace.py` (F59 / DEC-59-STIX-PROVENANCE-001 authority). The direct-engine pattern is already in use in `core/report.py`; reusing it preserves single-authority discipline. |

### M-2 Work Item Index

| ID | Title | Type | Status |
|----|-------|------|--------|
| **wi-68-m2-planner** | M-2 planner: per-slice plan + Evaluation Contract + Scope Manifest authoring | docs only | landed (per-slice plan at `.claude/plans/dossier-m2-slot-extractors.md`; Phase 17D MASTER_PLAN section harvested via plan-drift closeout 2026-05-29) |
| **wi-68-m2-impl-01** | M-2 implementer: per-module slot extractors + `infer_dossier_state_full` + `get_dossier_state` LLM tool + scaffold dataclasses | source + tests | landed @ `83a98d9`; merged @ `11b3fd3` |

### M-2 Scope Manifest (summary; full at `.claude/plans/dossier-m2-slot-extractors.md` §3.b)

**Allowed / Required (touched):** `src/adversary_pursuit/dossier/slot_inference.py` (extended), `src/adversary_pursuit/dossier/slots.py` (extended with `PredictionRecord`, `DenialStrategyRecord`, `MOTIVATION_TAG_VOCABULARY`, `M2_ACTIVE_SLOTS`; `M1_ACTIVE_SLOTS` preserved as historical marker), `src/adversary_pursuit/agent/tools.py` (added `get_dossier_state` tool per DEC-M2-DOSSIER-005), `tests/test_dossier_slot_inference.py` (extended with M-2 cases), `tests/test_dossier_get_state_tool.py` (NEW), `tests/test_agent_tools.py` (extended with `get_dossier_state` registration + dispatch).

**Forbidden (preserved authorities):** `core/workspace.py` (F59 / DEC-59-STIX-PROVENANCE-001 — Motivation extractor reads `AnalystNote` via the same direct-engine pattern `core/report.py` uses; no new `workspace.py` accessor added). `core/pivot_policy.py`, `core/event_bus.py` (F60). `core/streak.py`, `gamification/scoring.py`, `gamification/celebrations.py` (F62 / F63 / F64). `gamification/modes.py`, `agent/runner.py` (C-1 / C-2 territory). `models/**`, `modules/**` (modules emit no provenance per DEC-61-MODULES-EMIT-NO-PROVENANCE-001; M-2 reads only). `MASTER_PLAN.md` was deferred to this closeout. `dossier/panel.py` byte-identical (panel already renders all 9 slots from M-1; extractor wiring change must let existing panel render new real statuses with zero panel-code edits).

### M-2 Evaluation Contract (summary; full at `.claude/plans/dossier-m2-slot-extractors.md` §5)

- **required_tests:** 34+ tests across `test_dossier_slot_inference.py` (extended), `test_dossier_get_state_tool.py` (new), `test_agent_tools.py` (extended). Notable hard gates: `test_get_dossier_state_no_rich_markup_in_summary` (F64 invariant — DEC-M2-DOSSIER-005); `test_get_dossier_state_delegates_to_slot_inference` (Sacred Practice 12); per-slot extractor unit tests for Timing / Targeting / Capability / Motivation across empty / partial / FILLED thresholds; Predictions / Denial DEFERRED-only assertions.
- **required_authority_invariants:** F59 (workspace.py byte-identical), F60 (pivot_policy / event_bus untouched), F62/F63 (streak / scoring / celebrations untouched), F64 (LLM/Rich-panel separation preserved at dossier package boundary), Sacred Practice 12 (`dossier/` is sole inference authority — `get_dossier_state` delegates to `dossier.slot_inference`, does NOT re-infer in `agent/tools.py`).
- **required_integration_points:** `dossier/slot_inference.py` (6 new extractors + dispatcher); `dossier/slots.py` (scaffold dataclasses + vocabulary constants); `agent/tools.py` (`get_dossier_state` registration + dispatch).
- **forbidden_shortcuts:** no `workspace.py` mutator add; no `panel.py` edit; no `runner.py` / `modes.py` touch (C-territory); no hardcoded module count; no Rich markup in LLM tool summary; no `dossier.panel.render()` invocation in tool path; no new ScoreEvent emission (M-3 territory); no SQLite tables (M-4 territory).
- **rollback_boundary:** single feature branch revertible as one merge commit; legacy `infer_dossier_state(scos)` preserved so M-1 panel works under revert; no schema migrations, no settings changes.
- **ready_for_guardian_definition:** all required_tests pass; full suite green; `panel.py` byte-identical against main; `workspace.py` / `pivot_policy.py` / `event_bus.py` / `streak.py` / `scoring.py` / `celebrations.py` / `modes.py` / `runner.py` byte-identical against main; M-1 chat meta-command renders correctly with M-2 extractors.

### M-2 Bug Fix Surfaced During Compound Integration Test

During end-to-end testing of `infer_dossier_state_full` against a real `WorkspaceManager.get_module_runs()` return value, `_parse_utc_hour` (the helper that buckets timestamps for DEC-M2-DOSSIER-002 clustering) was discovered to assume input strings; `WorkspaceManager.get_module_runs()` actually returns native `datetime.datetime` objects per the F60 implementation. The fix landed in the same M-2 commit (`83a98d9`): `_parse_utc_hour` now branches on `isinstance(value, datetime.datetime)` and returns `value.hour` directly when given a datetime, falling back to `dateutil.parser.parse(value).hour` otherwise. Sub-decision recorded inline in `dossier/slot_inference.py` adjacent to DEC-M2-DOSSIER-002.

### M-2 Out-of-Scope (deferred to later slices)

- **No scoring changes** — M-3 owns. M-2 does not emit new `ScoreEvent`s, does not change weights, does not register new event subtypes.
- **No new workspace tables** — M-4 owns persistence. M-2 reads existing `stix_objects`, `module_runs`, `notes`.
- **No panel CSS / display order changes** — Panel is byte-identical.
- **No removal of `M1_ACTIVE_SLOTS`** — it stays as a historical marker so future readers can see the M-1 / M-2 expansion progression. Replaced as the inference driver by a new `M2_ACTIVE_SLOTS` constant.
- **No auto-inference for Predictions / Denial in M-2** — scaffold-only per DEC-M2-DOSSIER-004.

### Subsequent Workflow Cue

After M-2 lands, the recommended next workflow is **M-3 — Dossier Scoring + Score Event Re-tune** (W-68-M3-DOSSIER-SCORING per `.claude/plans/dossier-reframe-v2-roadmap.md` §M-3). M-3 introduces `DossierSlotFilled` and `DossierEvidenceConfidenceUpgraded` `ScoreEvent` subtypes and re-tunes per-IOC `MODULE_RUN_SCORED` to baseline 1.0 while preserving F62 streak chain + F63 milestone catch-up. M-3 is the load-bearing v2 product-center change that must land before M-4 persistence (predictions are themselves scored).

---

## Phase 17E: Character v2 — C-2 — `ninja` LLMPersonaProfile (W-30-C2-NINJA-PROFILE, post-v1, 2026-05-29)

**Status:** completed
**Merge SHA:** `f8bded8` (Merge #30: feat(character-v2) C-2 ninja LLMPersonaProfile)
**Implementer commit:** `699dbc8` (feat(character-v2): C-2 ninja LLMPersonaProfile)
**Per-slice plan (authoritative for content rationale):** `.claude/plans/c2-ninja-profile-plan.md` (authored in the C-2 worktree; orphaned at landing per the same gap AP #74 tracks — recovered to `.worktrees/feature-30-c2-ninja-profile/.claude/plans/` and harvested into this section).

**Closeout note (2026-05-29):** C-2 landed code-only — the per-slice plan was authored to `.claude/plans/c2-ninja-profile-plan.md` in the C-2 worktree and never reached main (parallel to the M-2 gap), and the source files were annotated with `DEC-C2-NINJA-001..003` references. This closeout slice harvests the binding decisions from the per-slice plan and the source annotations.

**Workflow:** `w-30-c2-ninja-profile` / goal `g-30-c2-ninja-profile`.
**Worktree (now disposable):** `/Users/jarocki/src/ap/.worktrees/feature-30-c2-ninja-profile` (branch `feature/30-c2-ninja-profile`, base AP main `e49e70b` — post C-1 merge).

**Bound by upstream:** DEC-30-CHARACTER-V2-001..007 (Phase 17) + DEC-C1-FULLTROLL-001..005 (Phase 17C; schema, runner injection, full_troll profile already live). C-2 is a single additive `LLMPersonaProfile` data entry plus mirrored hard-gate tests — schema, injection wiring, and authority decisions are all settled by C-1; the C-2 implementer copies the C-1 pattern for a different voice.

### What shipped

1. `ninja`'s `LLMPersonaProfile` instance added to `DEFAULT_MODES["ninja"]` in `gamification/modes.py` (quiet operator voice — terse, precise, deadpan, opaque fourth-wall stance).
2. `tests/test_character_v2.py` updates per DEC-C2-NINJA-003:
   - `test_llm_profile_default_is_none_for_all_modes` exclusion set expanded to `{"full_troll", "ninja"}` (the remaining 8 modes stay `llm_profile=None`).
   - `test_llm_profile_is_none_on_legacy_static_modes` split into `test_default_mode_keeps_static` (default-only assertion; ninja assertion removed).
   - `test_set_character_ninja_uses_v1_composition_verbatim` repointed to `drunken_master` (still `llm_profile=None` post-C-2 per DEC-30-CHARACTER-V2-006).
   - Positive test `test_set_character_ninja_injects_profile` added (C-1-style mirror).
   - New classes: `TestNinjaProfileContent` (10 tests), `TestNinjaPersonaSwapHardGates` (tool-call identity gate mirroring C-1 DEC-C1-FULLTROLL-004), `TestNinjaF64PanelSeparation` (F64 mirrors).
   - Inline `git diff main` hard gate added to `TestF62AuthorityInvariants` proving `tools.py` / `runner.py` / `chat.py` byte-identical to main.
3. Test results: 45/45 `test_character_v2.py` pass; 1984/1985 full suite pass (1 skip is the pre-existing optional smoke-test skip).

### Per-slice decisions (binding for C-2; verbatim from `c2-ninja-profile-plan.md` §3 and source annotations)

| DEC ID | Decision | Rationale |
|--------|----------|-----------|
| **DEC-C2-NINJA-001** | `ninja`'s `LLMPersonaProfile` content is authored as: **voice_summary** `"Quiet operator: terse, precise, factual; no flourish, no narration; one short sentence is the default."`; **tone_registers** `("cold-deadpan", "technical-precise", "clipped", "calm")`; **signature_phrases** `("noted.", "tracked.", "indeed.", "negative.", "advance.")`; **fourth_wall_stance** `"opaque"` (ninja is the role — no LLM/tool acknowledgement); **dialect_cadence** `"Clipped sentences; one short line by default; widely-known acronyms only (IOC, C2, IP); no filler, no hedging."`; **context_hooks** `()` (deferred to M-4 per DEC-C1-FULLTROLL-005 pattern); **tool_preferences** `("crt.sh: a quiet ledger of names", "VirusTotal: a public verdict to weigh, not to trust")` — voice-affinity language ONLY; **forbidden_voice** `("never narrate point totals — the Rich panel owns scoring", "never exclaim — no exclamation marks, no hyperbole", "never use sarcasm or trolling — that is full_troll's lane")`. Implementer copies verbatim. | Ninja's established static voice (`personality="Minimal output, silent and concise messaging"`, `run_success="Target acquired. Moving on."`) sets the register: short, dim, deadpan. The LLM extension preserves that discipline rather than amplifying any new flourish. The `forbidden_voice` entry on point totals is the F64 hard requirement; the no-exclamation and no-sarcasm entries protect the voice register itself from drifting toward `full_troll` or any future loud mode. Per-mode token budget: ≤ 165 (verified by C-1 budget test extended to ninja). **Supersession of Phase 17 DEC-30-CHARACTER-V2-002:** ninja's disposition flips from KEEP_STATIC to UPGRADE; the C-2 voice is so well-defined by the existing static surfaces that authoring the LLM profile is a pure extension, not a re-invention. The Phase 17 KEEP_STATIC reasoning ("ninja's purpose is *less output*, not more characterful") is preserved — the LLM profile *enforces* less output via `dialect_cadence` + `forbidden_voice` rather than abandoning the principle. |
| **DEC-C2-NINJA-002** | C-2 modifies exactly two source/test files: `src/adversary_pursuit/gamification/modes.py` (add `llm_profile=LLMPersonaProfile(...)` to the existing `"ninja"` entry in `DEFAULT_MODES`); `tests/test_character_v2.py` (extend with ninja-mirror tests plus C-1 test updates per DEC-C2-NINJA-003). NO other source changes. | `runner.py` already routes any non-None `llm_profile` through the C-1 injection branch; no edit there is required or permitted under this slice. This preserves the single-authority discipline established by C-1 (Sacred Practice 12). |
| **DEC-C2-NINJA-003** | Existing C-1 tests that reference ninja MUST be updated, not worked around: `test_llm_profile_default_is_none_for_all_modes` (expand exclusion set to `{"full_troll", "ninja"}`); `test_llm_profile_is_none_on_legacy_static_modes` (split into `test_default_mode_keeps_static` + remove ninja assertion); `test_set_character_ninja_uses_v1_composition_verbatim` (REWRITE to use `drunken_master` as the v1-path KEEP_STATIC carrier). The new C-2 ninja test class then includes the C-1-style positive test `test_set_character_ninja_injects_profile`. | The C-1 tests encoded the C-1-era invariant (only full_troll has a profile). Once C-2 changes the disposition for ninja, the invariant moves; the tests must move with it. Skipping or weakening the C-1 tests would leave a silent gap in coverage. Updating them keeps every prior C-1 hard gate in force while extending the suite to ninja. |

### C-2 Work Item Index

| ID | Title | Type | Status |
|----|-------|------|--------|
| **wi-30-c2-planner** | C-2 planner: per-slice plan + binding DECs + test-refactor disposition | docs only | landed (per-slice plan at `.claude/plans/c2-ninja-profile-plan.md`; Phase 17E MASTER_PLAN section harvested via plan-drift closeout 2026-05-29) |
| **wi-30-c2-impl-01** | C-2 implementer: ninja LLMPersonaProfile + test_character_v2.py refactor | source + tests | landed @ `699dbc8`; merged @ `f8bded8` |

### C-2 Scope Manifest (summary; full at `.claude/plans/c2-ninja-profile-plan.md` §4)

- **allowed_paths (2):** `src/adversary_pursuit/gamification/modes.py`, `tests/test_character_v2.py`.
- **required_paths (2):** same two files.
- **forbidden_paths:** `src/adversary_pursuit/agent/tools.py` (F62/F64 bytewise identical), `src/adversary_pursuit/agent/runner.py` (injection already routes any profile — zero edits required or permitted), `src/adversary_pursuit/agent/chat.py` (mode meta-command preserved), `src/adversary_pursuit/core/streak.py`, `core/pivot_policy.py`, `core/workspace.py`, `gamification/celebrations.py`, `scoring.py`, `badges.py`, `models/**`, `modules/**`, `dossier/**` (parallel M-2 territory; M-2 was active in parallel until M-2 landed first at `11b3fd3`), `pyproject.toml`, `CLAUDE.md`, `AGENTS.md`, `settings.json`, `hooks/**`, `agents/**`, `.claude/**`, `runtime/**`.
- **state_domains (1):** `character_persona_profile` (only — `agent_system_prompt_assembly` is preserved unchanged because runner.py is byte-identical).

### C-2 Evaluation Contract (summary; full at `.claude/plans/c2-ninja-profile-plan.md` §4)

- **required_tests:** 10 `TestNinjaProfileContent` field-content assertions + `TestNinjaPersonaSwapHardGates` (tool-call identity gate — mirrors DEC-C1-FULLTROLL-004) + `TestNinjaF64PanelSeparation` (mirrors C-1 F64 gates) + updated `TestCharacterModeLlmProfileField` (exclusion set expansion) + positive `test_set_character_ninja_injects_profile` + rewritten `test_set_character_drunken_master_uses_v1_composition_verbatim`. 45/45 `test_character_v2.py` total. Full suite: 1984 passed / 1 skipped.
- **required_evidence:** `git diff main` showing zero changes to `tools.py`, `runner.py`, `chat.py`, `streak.py` (verified inline by `TestF62AuthorityInvariants`); runtime assertion that `ninja.llm_profile is not None` and that 8 other modes (excluding `full_troll` + `ninja`) remain `llm_profile=None`; `set_character` toggles the profile fragment in/out of `system_prompt` correctly for the ninja path.
- **required_authority_invariants:** all DEC-MODE-*, DEC-62-* (streak / scoring untouched), DEC-64-* (panel separation preserved), DEC-30-CHARACTER-V2-005 (tool-call identity hard gate enforced), DEC-AGENT-CHAT-002 (mode meta-command surface preserved), Sacred Practice 12 (single integration site honored — runner.py untouched).
- **required_integration_points:** `gamification/modes.py` `DEFAULT_MODES["ninja"].llm_profile`; `tests/test_character_v2.py` (test refactor per DEC-C2-NINJA-003).
- **forbidden_shortcuts:** no `runner.py` edit (injection already routes); no `tools.py` / `chat.py` touch (F62/F64); no new mode added; no schema field added (uses C-1's 8-field `LLMPersonaProfile` verbatim); no test deletion (C-1 tests updated, not removed); no instruction-language in `tool_preferences` ("prefer", "always", "use", "must use" are forbidden by DEC-C2-NINJA-001).
- **rollback_boundary:** single feature branch revertible as one merge commit; reverting restores ninja to `llm_profile=None` (= C-1-era behavior); no schema / persistence / config changes.
- **ready_for_guardian_definition:** 45/45 `test_character_v2.py` pass; full suite green (1984 passed / 1 skipped); `tools.py` / `runner.py` / `chat.py` / `streak.py` byte-identical against main (verified by inline `TestF62AuthorityInvariants` diff gate); ninja profile content matches DEC-C2-NINJA-001 verbatim; token budget ≤ 165 for ninja; scope compliance verified.

### Decision Log (Phase 17E summary)

| DEC ID | Decision | Rationale |
|--------|----------|-----------|
| DEC-C2-NINJA-001 | `ninja`'s LLMPersonaProfile content authored per the field table above. Implementer copied verbatim. Supersedes Phase 17 DEC-30-CHARACTER-V2-002 ninja=KEEP_STATIC disposition (now UPGRADE). | The LLM profile *enforces* ninja's terseness via `dialect_cadence` + `forbidden_voice` rather than abandoning the "less output" principle. Lowest authoring risk after `full_troll` (C-1) because the static voice is already well-defined. |
| DEC-C2-NINJA-002 | Two-file slice (`gamification/modes.py` + `tests/test_character_v2.py`). `runner.py` byte-identical (C-1 injection already routes). | Sacred Practice 12: single integration site preserved. Smallest possible slice that adds the second upgraded mode. |
| DEC-C2-NINJA-003 | Existing C-1 ninja-referencing tests are updated, not bypassed: `test_llm_profile_default_is_none_for_all_modes` exclusion expanded; `test_llm_profile_is_none_on_legacy_static_modes` split (default-only assertion remains; ninja replaced by positive injection test); `test_set_character_ninja_uses_v1_composition_verbatim` repointed to `drunken_master`. | C-1 tests encoded the C-1-era invariant (only full_troll has a profile). C-2 moves the invariant; the tests must move with it. Skipping or weakening would leave a silent gap. |

### Subsequent Workflow Cue

After C-2 lands, C-3 (Philosophy + Bureaucratese Modes — `sun_tzu`, `bruce_lee`, `bureaucrat`) is the next character-v2 slice. C-3 may land any time (independent of all M-* slices and of C-4). Per the v0.x sequencing in Phase 17 §6.5: C-3 fits the v0.2.x or v0.3.x wave. The recommended dossier next slice is M-3 (see Phase 17D Subsequent Workflow Cue) — the orchestrator may schedule C-3 and M-3 to the same wave or stagger them; both are consistent with Phase 17 DEC-30-CHARACTER-V2-007.

---

## Phase 17F: Dossier Scoring + Score Event Re-Tune — M-3 (W-68-M3-DOSSIER-SCORING, post-v1, 2026-06-01)

**Status:** completed (2026-06-01, merge `2809b13`, impl `974fa1a`). Phase Active pointer at landing was not flipped in the M-3 commit; the M-4 closeout (Phase 17G) re-points to W-68-M4-PERSISTENT-DOSSIER and corrects this status line in the same commit.
**Workflow:** `w-68-m3-dossier-scoring` / goal `g-68-m3-dossier-scoring`.
**Worktree:** `/Users/jarocki/src/ap/.worktrees/feature-68-m3-dossier-scoring` (branch `feature/68-m3-dossier-scoring`, base AP main `de08b4b`).
**Per-slice plan (authoritative for content rationale):** `.claude/plans/dossier-m3-scoring.md` (landed in this worktree; implementer commits it together with source).

**Source:** Phase 16 (W-68-DOSSIER-REFRAME-SCOPING) decomposed the reframe into M-1..M-9. M-1 (Phase 17B) shipped the dossier panel + 3-slot inference; M-2 (Phase 17D) added the per-module slot extractors + `get_dossier_state` LLM tool + scaffold dataclasses for the deferred slots. M-3 is the load-bearing v2 product-center change: it wires dossier slot transitions into the score economy per DEC-68-DOSSIER-REFRAME-002 (option c — layer `dossier/` aggregator over existing `ScoringEngine`).

### M-3 Goal (verbatim from per-slice plan §1)

> Wire dossier slot completion into the score economy per DEC-68-DOSSIER-REFRAME-002 (option c). When a hunt fills a dossier slot (Identity / TTPs / Infrastructure / Timing / Capability / Motivation status moves `empty → partial` or `partial → filled`, per the 9-slot weights from Phase 16 §3 — Identity=5.0, Predictions=4.0, Capability=3.5, TTPs=3.0, Motivation=3.0, Targeting=2.5, Denial=2.5, Infrastructure=2.0, Timing=2.0, baseline IOC=1.0), a `dossier_slot_filled` `ScoreEvent` fires with the weighted point value. The user sees `Identity slot filled +5 points!` (or similar) instead of just `IP found +1`. After M-3, the dossier IS the score economy's center of gravity: per-IOC events drop to baseline 1.0 and slot weights dominate.

### Decision Log (Phase 17F / M-3; verbatim from per-slice plan §9)

| DEC ID | Decision | Rationale |
|--------|----------|-----------|
| **DEC-M3-DOSSIER-001** | New file `src/adversary_pursuit/dossier/scoring.py` containing `emit_dossier_slot_filled_events(pre: DossierState, post: DossierState) -> list[dict]` as a pure function. No I/O, no subscriber, no workspace mutation. Caller wires the pre/post snapshots and persists the returned events via the existing `workspace_mgr.store_score_events(...)` API. | DEC-68-DOSSIER-REFRAME-002 chose option (c) "layer over scoring." Pure function honors that layering: the new file is *the* dossier-event-emission authority, callers integrate without changing scoring-engine semantics or workspace persistence semantics. Rejects two architecturally simpler alternatives (event-bus subscriber; ScoringEngine-internal computation) — see per-slice plan §2.2. |
| **DEC-M3-DOSSIER-002** | Caller wiring lives in `agent/tools.py::run_module` AND `core/console.py::_execute_hunt`. Both capture `pre_dossier` BEFORE `store_stix_objects`, capture `post_dossier` AFTER, compute the diff via `dossier/scoring.py::emit_dossier_slot_filled_events`, persist the events via the existing `store_score_events` API, and include the events in the existing `events` list returned to the LLM as `score_events`. | These are the two existing per-hunt site authorities — both already own the "after hunt" boundary (per-IOC `score_results`, badge/challenge checks, streak update). Adding the dossier snapshot at the same site preserves the single-site-per-hunt pattern (Sacred Practice 12). No new orchestration layer, no new dispatcher. |
| **DEC-M3-DOSSIER-003** | `ScoringEngine` (in `gamification/scoring.py`) is unchanged in *behavior*; only the per-IOC `DEFAULT_RULES` constants are re-tuned. `dossier/scoring.py` is an EVENT EMITTER consumed by the existing scoring path — NOT a parallel scorer. The `score_events` table is the single persistence authority. | Sacred Practice 12: the question "what is a scoreable event in AP?" still has one owner (the score_events table, via the store_score_events API). The question "given a slot state diff, what dossier events does it imply?" gets a new explicit owner (`dossier/scoring.py`). Two distinct questions, one authority each. |
| **DEC-M3-DOSSIER-004** | Per-IOC `DEFAULT_RULES` are re-tuned to `initial == minimum == 1` for all 9 SCO-mapped action keys (`new_ip`, `new_domain`, `new_url`, `new_email`, `adversary_mistake`, `deception_uncovered`, `adversary_linked`, `new_tool`, `campaign_described`). `decay` constants preserved (mathematically inert under `initial == minimum`, but kept so the re-tune diff is minimal and reversible). `streak_continued` (F62/F63) is UNCHANGED. | DEC-68-DOSSIER-REFRAME-002 mandates baseline 1.0 for per-IOC events so slot weights (2–5) dominate. AP scoring stores integers; the closest honest mapping of "weight 1.0 baseline" is `initial == minimum == 1`, which collapses the parabolic decay to a constant 1 regardless of solve_count. Preserving `decay` keeps the diff small and the rollback clean. |
| **DEC-M3-DOSSIER-005** | `dossier_prediction_validated` event subtype is **scaffolded** in M-3 (event shape defined, helper function `emit_dossier_prediction_validated_event(prediction)` ships and is tested for shape contract) but **NOT emitted** during any M-3 hunt. M-4 (persistent dossier state) plugs in the auto-validation logic when real prediction records exist. | Per DEC-M2-DOSSIER-004, the Predictions slot remains DEFERRED until M-4. Without persistent prediction records, no validation transitions occur in M-3. Scaffolding the shape + helper now (a) gives M-4 a stable contract to target, (b) prevents future implementers from inventing incompatible event keys, (c) is testable without M-4 persistence. The DEC-68-DOSSIER-REFRAME-007 falsified-prediction-score-deduction question remains explicitly deferred to M-4 (M-3 ships zero negative-score logic). |

### M-3 Per-IOC Score Event Re-Tune Table (binding for DEC-M3-DOSSIER-004; verbatim from per-slice plan §4)

| action | v1 initial | v1 minimum | v1 decay | M-3 initial | M-3 minimum | M-3 decay |
|--------|-----------|-----------|---------|-------------|-------------|-----------|
| `new_ip` | 100 | 10 | 10 | **1** | **1** | 10 |
| `new_domain` | 100 | 10 | 10 | **1** | **1** | 10 |
| `new_url` | 50 | 5 | 10 | **1** | **1** | 10 |
| `new_email` | 50 | 5 | 10 | **1** | **1** | 10 |
| `adversary_mistake` | 10 | 5 | 5 | **1** | **1** | 5 |
| `deception_uncovered` | 200 | 50 | 5 | **1** | **1** | 5 |
| `adversary_linked` | 500 | 100 | 3 | **1** | **1** | 3 |
| `new_tool` | 500 | 100 | 3 | **1** | **1** | 3 |
| `campaign_described` | 1000 | 200 | 2 | **1** | **1** | 2 |
| `streak_continued` | n/a (helper) | n/a | n/a | **UNCHANGED** | **UNCHANGED** | **UNCHANGED** |

### M-3 Work Item Index

| ID | Title | Type | Status |
|----|-------|------|--------|
| **wi-68-m3-planner** | M-3 planner: per-slice plan + Evaluation Contract + Scope Manifest + Phase 17F authoring | docs only | landed (per-slice plan at `.claude/plans/dossier-m3-scoring.md`; Phase 17F section authored in M-3 worktree 2026-06-01) |
| **wi-68-m3-impl-01** | M-3 implementer: `dossier/scoring.py` + per-IOC re-tune + `run_module` / `_execute_hunt` snapshot wiring + tests | source + tests | dispatched (planner staged 2026-06-01) |

### M-3 Scope Manifest (summary; full at `.claude/plans/dossier-m3-scoring.md` §8)

**Allowed / Required (the implementer MUST touch these):**
- `src/adversary_pursuit/dossier/scoring.py` **(NEW)**
- `src/adversary_pursuit/dossier/__init__.py` (export new symbols)
- `src/adversary_pursuit/gamification/scoring.py` (per-IOC re-tune ONLY — `DEFAULT_RULES` constants)
- `src/adversary_pursuit/agent/tools.py` (`run_module` snapshot + emit wiring per per-slice plan §5.1; private `_read_analyst_notes` helper)
- `src/adversary_pursuit/core/console.py` (`_execute_hunt` same pattern; private `_read_analyst_notes` helper)
- `tests/test_dossier_scoring.py` **(NEW)**
- `tests/test_dossier_slot_inference.py` (extend — transition-readiness tests only)
- `tests/test_scoring.py` (extend — re-tune assertions)
- `tests/test_streak.py` (extend — F62 invariants under M-3)
- `tests/test_agent_tools.py` (extend — compound integration)
- `MASTER_PLAN.md` — this Phase 17F section. **The implementer MUST `git add MASTER_PLAN.md` in the same commit as the source changes** (AP #74 orphan-prevention; the M-1/M-2/C-1/C-2 closeout drift MUST NOT repeat).

**Forbidden (preserved authorities):**
- `core/workspace.py` (F59 + DEC-68 invariant)
- `core/streak.py` (F62 invariant)
- `core/pivot_policy.py`, `core/event_bus.py` (F60 invariants)
- `dossier/slot_inference.py` (M-2 byte-identical — M-3 only READS)
- `dossier/slots.py` (M-1/M-2 byte-identical — `SLOT_WEIGHTS` authority preserved)
- `dossier/panel.py` (M-1 byte-identical)
- `gamification/celebrations.py` (F63 milestone announce)
- `gamification/modes.py`, `agent/runner.py` (C-1/C-2 territory)
- `agent/chat.py` (F64 invariant)
- `models/**`, `modules/**`, `pyproject.toml`, hooks, settings, CLAUDE.md, agents/, runtime/

### M-3 Evaluation Contract (summary; full at `.claude/plans/dossier-m3-scoring.md` §7)

- **required_tests:** ~28–32 tests across `test_dossier_scoring.py` (NEW, ~16 tests covering all 9 slot transition paths, idempotency, skip-step, deferred-target handling, event-dict shape, prediction-validated scaffold), `test_dossier_slot_inference.py` (extend, ~2 transition-readiness tests), `test_scoring.py` (extend, ~5 re-tune assertions), `test_streak.py` (extend, ~2 F62-invariant regression tests), `test_agent_tools.py` and/or new `test_dossier_scoring_integration.py` (~5 compound tests), F63 milestone gate (~1 test). Full suite green: ≥1984 passed (matching C-2 baseline) + the new M-3 tests.
- **required_evidence:** full pytest output green; `git diff main` is empty for every forbidden file; demo trace showing a single mock identity-module hunt produces exactly one `new_email` event (points=1) AND one `dossier_slot_filled` event (indicator=identity, points=5) in `result["score_events"]`, with `result["total_points"] == 6`, and slot-fill text ABSENT from `result["summary"]` (F64 gate).
- **required_authority_invariants:** F59 (workspace byte-identical), F60 (pivot_policy / event_bus byte-identical; no new bus subscriber), F62 (streak.json byte-identical when no streak transition; `streak_continued` semantics unchanged), F63 (milestone seed-from-`pre_total` quiet-start migration honored; dossier events can trigger milestones via `post_total`), F64 (dossier event text absent from LLM `summary`; present in `score_events` sidecar), Sacred Practice 12 (dossier/scoring.py is sole `dossier_slot_filled` emitter authority; ScoringEngine is sole per-IOC emitter authority; workspace is sole persistence authority), DEC-M1-SLOTS-WEIGHT-AUTHORITY-001 (`SLOT_WEIGHTS` constants in `dossier/slots.py` UNCHANGED).
- **required_integration_points:** `dossier/scoring.py` (NEW pure-function module), `dossier/__init__.py` (export new symbols), `gamification/scoring.py::DEFAULT_RULES` (re-tune), `agent/tools.py::run_module` + `core/console.py::_execute_hunt` (snapshot + emit wiring).
- **forbidden_shortcuts:** no env-var bypass; no "old scoring fallback" flag; no new event-bus subscriber; no mutation of `dossier/slot_inference.py` / `dossier/slots.py` / `dossier/panel.py`; no modification of `core/workspace.py` / `core/streak.py` / `gamification/celebrations.py` / `gamification/modes.py` / `agent/runner.py`; no new SQLite tables (M-4 owns); no auto-validation logic for `dossier_prediction_validated` (M-4 owns); no Rich markup in dossier event text (F64); no double-persist of dossier events; no refactor of `tools.py` or `console.py` beyond snapshot + emit wiring.
- **rollback_boundary:** single feature branch revertible as one merge commit; reverting restores v1 `DEFAULT_RULES` constants, removes `dossier/scoring.py` + `dossier/__init__.py` re-exports, restores `tools.py` / `console.py` to M-2 byte state; historical `dossier_slot_filled` rows in `score_events` table remain (action string only — no schema change, no corrupt state); no schema migrations, no settings changes, streak.json untouched.
- **ready_for_guardian_definition:** all required_tests green; full suite green; forbidden-file `git diff main` empty; **Phase 17F appended to `MASTER_PLAN.md` AND committed in the same commit as source** (AP #74 lesson); `dossier/__init__.py` exports `emit_dossier_slot_filled_events` and `emit_dossier_prediction_validated_event` (no surprise additions); implementer commit message follows `feat(dossier):` Phase 17 prefix and references `#68` + `DEC-M3-DOSSIER-001..005`.

### M-3 Out-of-Scope (deferred to later slices)

- **No persistent dossier state / no new SQLite tables** — M-4 owns (`dossier_slot`, `dossier_evidence_link`, `dossier_prediction`).
- **No falsified-prediction score deduction** (DEC-68-DOSSIER-REFRAME-007 open question) — M-4 owns. M-3 ships zero negative-score logic.
- **No `DossierEvidenceConfidenceUpgraded` event** — gated on per-slot confidence inference depth that M-2 didn't ship; M-4/M-7 revisit.
- **No Denial / Deception slot fill events** — M-5 owns the authoring surface.
- **No dossier-aware auto-pivot policy budget** — M-6 owns.
- **No reports / celebrations / badges narrative upgrades** — M-7 owns.
- **No confidence multiplier in `dossier/scoring.py`** — M-3 uses `int(SLOT_WEIGHTS[slot])` flat. M-4/M-7 may add a multiplier when real per-slot confidence values exist.

### Subsequent Workflow Cue

After M-3 lands, the recommended next workflow is **M-4 — Persistent Dossier State + Predictions Log** per `.claude/plans/dossier-reframe-v2-roadmap.md` §M-4. M-4 introduces SQLite tables (`dossier_slot`, `dossier_evidence_link`, `dossier_prediction`), migrates the M-1/M-2/M-3 in-memory inference to persistent state, plugs the `dossier_prediction_validated` emitter (scaffolded by M-3 per DEC-M3-DOSSIER-005) into real validation/falsification rules, and resolves DEC-68-DOSSIER-REFRAME-007 (whether falsified predictions deduct score). C-3 (Philosophy + Bureaucratese modes) remains independent (DEC-30-CHARACTER-V2-007) and may land in the same wave or independently.

**M-4 follow-up note (2026-06-02):** M-4 (Phase 17G below) revised the roadmap §M-4 storage approach. Per DEC-M4-PERSIST-001 the persistence authority is the F63 sentinel-row pattern in the existing `score_events` table — NOT three new SQLite tables (`dossier_slot`, `dossier_evidence_link`, `dossier_prediction`). The simpler authority preserves DEC-DB-002 (no migrations) and keeps `models/database.py` UNCHANGED. The roadmap §M-4 paragraph above remains as historical strategic-scoping prose; Phase 17G is the binding M-4 contract.

---

## Phase 17G: Persistent Dossier State + Predictions Log Auto-Validation — M-4 (W-68-M4-PERSISTENT-DOSSIER, post-v1, 2026-06-02)

**Status:** completed (2026-06-02, merge TBD-guardian-land, impl HEAD feature/68-m4-persistent-dossier).
**Workflow:** `w-68-m4-persistent-dossier` / goal `g-68-m4-persistent-dossier`.
**Worktree:** `/Users/jarocki/src/ap/.worktrees/feature-68-m4-persistent-dossier` (branch `feature/68-m4-persistent-dossier`, base AP main `2809b13`).
**Per-slice plan (authoritative for content rationale):** `.claude/plans/dossier-m4-persistent-state.md` (landed in this worktree; implementer commits it together with source).

**Source:** Phase 16 (W-68-DOSSIER-REFRAME-SCOPING) decomposed the reframe into M-1..M-9. M-1 (Phase 17B) shipped the panel + 3-slot inference; M-2 (Phase 17D) added the per-module slot extractors + `get_dossier_state` LLM tool + scaffold dataclasses (PredictionRecord, DenialStrategyRecord); M-3 (Phase 17F) wired slot-fill events into the score economy + scaffolded `dossier_prediction_validated`. M-4 is the persistence + predictions slice: state survives `ap chat` restart and predictions become a first-class scored slot.

### M-4 Goal (verbatim from per-slice plan §1)

> Make the dossier **stateful across hunts** and turn the Predictions Log into a real, scored slot. Two interlocking surfaces ship: (1) Persistent DossierState — a single per-workspace snapshot of the most-recent inferred dossier state, written at the end of every hunt and read at the start of the next; M-3's "pre = infer_dossier_state_full(...)" becomes "pre = load_dossier_state() or default_deferred_state(); compare against fresh post-inference"; state survives `ap chat` restart. (2) Predictions Log lifecycle — NEW `create_dossier_prediction` LLM tool lets the analyst (via the agent) author predictions tied to slots; predictions are persisted as `PersistedPrediction` entries; subsequent hunts auto-validate them by matching new evidence against typed `expected_evidence` patterns; on confirmation, M-3's scaffolded `emit_dossier_prediction_validated_event` fires with weight=4.0. After M-4, the dossier has memory, predictions are first-class scored events, and the Predictions slot transitions from `deferred` to real `empty`/`partial`/`filled`.

### Decision Log (Phase 17G / M-4; verbatim from per-slice plan §9)

| DEC ID | Decision | Rationale |
|--------|----------|-----------|
| **DEC-M4-PERSIST-001** | Persistent DossierState + Predictions Log storage authority is the F63 sentinel-row pattern in the existing `score_events` table. Two new reserved actions (`_dossier_state_snapshot`, `_predictions_log`) carry JSON payloads in the `indicator` column. No schema change, no new SQLAlchemy model, no `models/database.py` edits. | Mirrors the landed F63 precedent (DEC-63-MILESTONE-CATCHUP-001, merge `8778af3`). Zero migration risk. Persists in workspace SQLite so it survives `ap chat` restart and travels with workspace export. Rejects: NEW `workspace_metadata` table (cleaner but violates DEC-DB-002 + forbidden `models/database.py` edits); flat `~/.ap/dossiers/<id>.json` files (parallel authority — violates Sacred Practice 12). Roadmap §M-4 original three-tables design is superseded by this DEC; the simpler authority preserves the no-migrations v1 discipline. |
| **DEC-M4-PERSIST-002** | `core/workspace.py` gains exactly two narrow changes: (a) module-level `_RESERVED_ACTIONS` frozenset enumerating `_milestone_sentinel` + the two new M-4 reserved actions; (b) `get_recent_scores()` `.where(...)` clause widened from `ScoreEvent.action != _MILESTONE_SENTINEL_ACTION` to `ScoreEvent.action.notin_(_RESERVED_ACTIONS)`. No public-method signature change, no new column, no schema migration. F59 invariant claim becomes: workspace public surface preserves existing caller semantics; M-4 widens an existing display filter from one action to three. | DEC-M4-PERSIST-001 mechanically requires hiding the new sentinel rows from `get_recent_scores()` the same way F63 hides `_milestone_sentinel`. Widening F63's existing filter is the smallest honest workspace.py change that preserves caller semantics. Implementer MUST keep the diff minimal; reviewer enforces. |
| **DEC-M4-PERSIST-003** | JSON envelope for both reserved actions carries `"schema_version": 1`. Serializers live in the owning module (`dossier/state.py` for DossierState, `dossier/predictions.py` for PredictionRecord lists). Mismatched versions raise loud `RuntimeError` (Sacred Practice 5 — no silent fallback). Stable sorting: keys sorted alphabetically; compact form. | Future M-4+ schema evolution needs an explicit handshake; loud failure tells the user "you upgraded AP and your workspace pre-dates the change" rather than silently reading garbage. Per-module serializers honor Sacred Practice 12. |
| **DEC-M4-PRED-001** | Predictions Log persists `PersistedPrediction` (NEW in `dossier/predictions.py`) — a richer typed dataclass with `prediction_id`, `slot`, `expected_evidence`, `created_at`, `validated_at`, `validated_by_sco_id`. M-2's `PredictionRecord` scaffold dataclass in `dossier/slots.py` stays BYTEWISE UNCHANGED. `dossier/predictions.py` provides a one-way adapter `_to_m2_record(persisted) -> PredictionRecord` that lets the M-3 scaffolded helper accept the M-2 shape without signature change. | DEC-M2-DOSSIER-004 ratified the M-2 scaffold as long-lived contract; modifying `dossier/slots.py` would break it. Keeping the richer M-4 shape in `dossier/predictions.py` honors Sacred Practice 12 (the persistence-layer module owns the persistence-layer schema). The adapter preserves the M-3 helper signature so M-3's scaffold is truly the contract M-4 targets. |
| **DEC-M4-PRED-002** | `expected_evidence` validation vocabulary v1.0 is `ExpectedEvidence(sco_type, value_regex, asn_in, note_keyword_any)`. All non-None fields are ANDed. Empty `expected_evidence` is rejected by `create_dossier_prediction` with loud `ValueError`. Richer matching (multi-SCO patterns, relationship-hop queries, numeric thresholds) deferred to M-5+. | Smallest vocabulary that covers the M-4 user story (actor pivot to .ru, ASN reuse, keyword in note) without becoming a query DSL. Typed dataclass over freeform dict keeps the LLM-tool schema honest and validation predictable. |
| **DEC-M4-PRED-003** | Validation scope is **current-hunt evidence only**: `validate_predictions(predictions, new_scos, new_notes)` matches against the SCOs / notes surfaced in the current hunt, not the full workspace history. Predictions already `validated` or `falsified` are skipped (idempotency). | Matches M-3's per-hunt diff pattern; avoids accidental re-validation against unchanged history. Cross-hunt re-validation, if needed later, is a separate M-5+ tool. |
| **DEC-M4-PRED-004** | When validation returns `confirmed=True`, the caller fires `dossier/scoring.py::emit_dossier_prediction_validated_event(_to_m2_record(persisted))` with weight 4 (SLOT_WEIGHTS[PREDICTIONS]). `gamification/scoring.py::DEFAULT_RULES` is UNCHANGED — prediction-validated events are emitted directly with `points=4`, mirroring M-3's `dossier_slot_filled` pattern. | Honors DEC-M3-DOSSIER-003 (ScoringEngine unchanged in behavior). Honors DEC-M1-SLOTS-WEIGHT-AUTHORITY-001 (SLOT_WEIGHTS is the single weight authority). Emission pattern is symmetric with slot-fill events. |
| **DEC-M4-PRED-005** | Active falsification is **out of scope for M-4**. Predictions transition from `pending` to `validated` only; M-4 ships no auto-falsify rules, no per-prediction "must validate within N hunts" window, no manual-override LLM tool. M-5 owns the falsification slice. | Falsification semantics require either a typed `falsification_evidence` shape or a temporal window; both are non-trivial design surfaces that would inflate M-4. Deferring lets M-5 design the falsification engine alongside the Denial / Deception slot work it already owns. Workspaces written by M-4 record predictions as `pending`; M-5 can falsify them retroactively without a schema change. |
| **DEC-M4-PRED-006** | DEC-68-DOSSIER-REFRAME-007 + DEC-M3-DOSSIER-005 deferred question is **committed**: confirmation = +4 points; falsification = 0 points (no deduction). M-4 ships zero negative-event logic. | Negative `points` events would have to flow through `store_score_events` and through `streak_continued` math; both currently assume non-negative event values. The "reckless guessing should cost score" intuition is real but the right surface is M-7 narrative feedback, not silent score deduction. A future re-stage may revisit if M-5's falsification engine surfaces evidence requiring score-level enforcement. |

### M-4 Work Item Index

| ID | Title | Type | Status |
|----|-------|------|--------|
| **wi-68-m4-planner** | M-4 planner: per-slice plan + Evaluation Contract + Scope Manifest + Phase 17G authoring | docs only | landed (per-slice plan at `.claude/plans/dossier-m4-persistent-state.md`; Phase 17G section authored in M-4 worktree 2026-06-02) |
| **wi-68-m4-impl-01** | M-4 implementer: `dossier/state.py` + `dossier/predictions.py` + hunt-site rewire + `create_dossier_prediction` LLM tool + narrow `workspace.py` filter + tests | source + tests | dispatched (planner staged 2026-06-02) |

### M-4 Scope Manifest (summary; full at `.claude/plans/dossier-m4-persistent-state.md` §8)

**Allowed / Required (the implementer MUST touch these):**
- `src/adversary_pursuit/dossier/state.py` **(NEW)** — DossierState persistence + overlay
- `src/adversary_pursuit/dossier/predictions.py` **(NEW)** — PredictionRecord lifecycle + validation engine
- `src/adversary_pursuit/dossier/__init__.py` (export new symbols)
- `src/adversary_pursuit/agent/tools.py` (hunt-site wiring + new `create_dossier_prediction` LLM tool + bounded extension of `_execute_get_dossier_state`)
- `src/adversary_pursuit/core/console.py` (hunt-site wiring mirror)
- `src/adversary_pursuit/core/workspace.py` **(NARROW per DEC-M4-PERSIST-002 only — `_RESERVED_ACTIONS` constant + `get_recent_scores` filter widening; reviewer enforces minimal diff)**
- `tests/test_dossier_state.py` **(NEW)**
- `tests/test_dossier_predictions.py` **(NEW)**
- `tests/test_dossier_persistence_integration.py` **(NEW)**
- `tests/test_dossier_scoring.py` (extend — prediction event emission)
- `tests/test_agent_tools.py` (extend — new tool + persistent-pre wiring + F64 gate)
- `tests/test_workspace.py` (extend — `_RESERVED_ACTIONS` filter regression)
- `tests/test_scoring.py` (extend — F62/F63 regression under prediction events)
- `tests/test_dossier_get_state_tool.py` (extend — persistent-state read)
- `MASTER_PLAN.md` — this Phase 17G section + Phase 17F status flip + Plan Status table row + Active Phase Pointer tail-line update. **The implementer MUST `git add MASTER_PLAN.md` in the same commit as source (AP #74 orphan-prevention; M-3 demonstrated the pattern works at `974fa1a`).**

**Forbidden (preserved authorities):**
- `src/adversary_pursuit/dossier/scoring.py` (M-3 byte-identical)
- `src/adversary_pursuit/dossier/slot_inference.py` (M-2 byte-identical)
- `src/adversary_pursuit/dossier/slots.py` (M-1/M-2 byte-identical — `SLOT_WEIGHTS` + `PredictionRecord` scaffold preserved)
- `src/adversary_pursuit/dossier/panel.py` (M-1 byte-identical)
- `src/adversary_pursuit/gamification/scoring.py` (M-3 byte-identical — no new `DEFAULT_RULES` row for prediction events)
- `src/adversary_pursuit/gamification/celebrations.py` (F63 invariant)
- `src/adversary_pursuit/core/streak.py` (F62 invariant)
- `src/adversary_pursuit/core/pivot_policy.py` (F60 invariant)
- `src/adversary_pursuit/core/event_bus.py` (F60 invariant — no new subscriber)
- `src/adversary_pursuit/models/database.py` (no schema change; DEC-DB-002)
- `src/adversary_pursuit/gamification/modes.py`, `src/adversary_pursuit/agent/runner.py`, `src/adversary_pursuit/agent/chat.py` (C-1/C-2 territory; F64 panel separation)
- `src/adversary_pursuit/modules/**`, `pyproject.toml`, hooks, settings, `CLAUDE.md`, `agents/`, `runtime/`

### M-4 Evaluation Contract (summary; full at `.claude/plans/dossier-m4-persistent-state.md` §7)

- **required_tests:** ~35–45 tests across `test_dossier_state.py` (NEW, ~12), `test_dossier_predictions.py` (NEW, ~14), `test_dossier_scoring.py` (extend, ~3), `test_workspace.py` (extend, ~3), `test_agent_tools.py` (extend, ~5), `test_scoring.py` (extend, ~2), `test_dossier_get_state_tool.py` (extend, ~1), `test_dossier_persistence_integration.py` (NEW, ~3). Full suite green ≥ M-3 baseline + new M-4 tests.
- **required_evidence:** full pytest output green; `git diff main` empty for every forbidden file (paste each); `core/workspace.py` diff limited to DEC-M4-PERSIST-002 narrow change (paste diff); demo trace showing the `ap chat` restart-survival scenario from per-slice plan §5 — two distinct `ap chat` invocations against the same workspace, second invocation loads persisted state + prediction, validates a `.ru` SCO discovered in the second hunt, fires `dossier_prediction_validated` event at points=4 with F64 gate (event text absent from LLM summary).
- **required_authority_invariants:** F59 (workspace public surface preserves caller semantics; only DEC-M4-PERSIST-002 widening); F60 (`pivot_policy.py` + `event_bus.py` BYTEWISE UNCHANGED; no new bus subscriber); F62 (`streak.py` UNCHANGED; prediction events do not reset streaks); F63 (`celebrations.py` UNCHANGED; milestone catch-up sees prediction-validated points); F64 (`_DOSSIER_ACTIONS` filter at `agent/tools.py:665` already covers both action keys; integration test asserts both slot-fill and prediction event text absent from LLM summary); Sacred Practice 12 (one authority per fact — `dossier/state.py` for persistent state, `dossier/predictions.py` for predictions lifecycle, `dossier/scoring.py` for `dossier_*` event shape, `core/workspace.py` for persistence); DEC-M1-SLOTS-WEIGHT-AUTHORITY-001 (`SLOT_WEIGHTS` UNCHANGED); DEC-M2-DOSSIER-004 (M-2's `PredictionRecord` scaffold UNCHANGED); DEC-M3-DOSSIER-001..005 (`dossier/scoring.py` UNCHANGED — M-4 only wires the prediction-validated scaffold).
- **required_integration_points:** `dossier/state.py` (NEW pure-data + sentinel-row persistence + Predictions overlay); `dossier/predictions.py` (NEW pure-data + persistence + validation engine); `dossier/__init__.py` (exports `load_dossier_state`, `save_dossier_state`, `default_deferred_state`, `apply_predictions_overlay`, `load_predictions_log`, `save_predictions_log`, `validate_predictions`, `PersistedPrediction`, `ExpectedEvidence`, `ValidationResult`); `agent/tools.py::run_module` (rewire `pre_state` source + emit prediction events + register `create_dossier_prediction` LLM tool + bounded `_execute_get_dossier_state` extension); `core/console.py::_execute_hunt` (mirror); `core/workspace.py` (NARROW: `_RESERVED_ACTIONS` constant + `get_recent_scores` filter).
- **forbidden_shortcuts:** no env-var bypass; no "always-re-infer" fallback flag; no new event-bus subscriber; no schema migration; no `models/database.py` edits; no new public method on `WorkspaceManager`; no modification of M-3 byte-identical files; no Rich markup in dossier event text or `create_dossier_prediction` output (F64); no active falsification logic (M-5 owns; DEC-M4-PRED-005); no negative-points ScoreEvent emission (DEC-M4-PRED-006); no double-persist; no extension of `infer_dossier_state_full(...)` signature; no refactor of `tools.py` / `console.py` beyond documented wiring + LLM tool registration.
- **rollback_boundary:** single feature branch revertible as one merge commit. Revert restores M-3 byte state; removes `dossier/state.py` + `dossier/predictions.py` + their re-exports; restores `tools.py` / `console.py` / `workspace.py` to M-3 byte state. Historical `_dossier_state_snapshot` and `_predictions_log` sentinel rows in `score_events` remain (valid rows, `points=0`, no effect on `get_total_score()`); a one-line SQL cleanup is the documented manual mitigation. No schema migrations, no settings changes, `streak.json` untouched.
- **ready_for_guardian_definition:** all required_tests green; full suite green; forbidden-file `git diff main` outputs empty; `core/workspace.py` diff limited to DEC-M4-PERSIST-002 narrow change; **Phase 17G appended to `MASTER_PLAN.md` AND committed in the same commit as source** (AP #74 lesson; M-3 demonstrated the pattern works); Phase 17F status line flipped from in-progress to completed in the same commit (M-3 closeout drift fix); Active Phase Pointer tail-line re-pointed from `W-68-M3-DOSSIER-SCORING` to `W-68-M4-PERSISTENT-DOSSIER`; `dossier/__init__.py` exports the M-4 public symbols; implementer commit message follows `feat(dossier):` Phase 17 prefix and references `#68` + `DEC-M4-PERSIST-001..003` + `DEC-M4-PRED-001..006`.

### M-4 Out-of-Scope (deferred to later slices)

- **No new SQLite tables** — DEC-M4-PERSIST-001 binds to F63 sentinel-row pattern; roadmap §M-4 original `dossier_slot` / `dossier_evidence_link` / `dossier_prediction` table sketch is explicitly superseded.
- **No active falsification rules** — M-5 owns (DEC-M4-PRED-005). Predictions stay `pending` until they confirm; never auto-transition to `falsified` in M-4.
- **No manual-override LLM tool (`falsify_dossier_prediction`)** — M-5 owns.
- **No negative-points ScoreEvents** — DEC-M4-PRED-006 commits the open DEC-68-DOSSIER-REFRAME-007 question: confirmation = +4, falsification = 0, no deduction.
- **No Denial / Deception slot fill events** — M-5 owns.
- **No dossier-aware auto-pivot policy budget** — M-6 owns.
- **No reports / celebrations / badges narrative upgrades** — M-7 owns.
- **No richer `expected_evidence` vocabulary** — M-4 ships `sco_type` + `value_regex` + `asn_in` + `note_keyword_any` only; multi-SCO patterns, relationship-hop queries, numeric thresholds deferred to M-5+.
- **No cross-hunt revalidation** — M-4 validates against current-hunt evidence only; a `revalidate_all_predictions(workspace)` repair tool is an M-5+ candidate.
- **No `infer_dossier_state_full` signature extension** — persistent state lives strictly above inference; the overlay-merge pattern is the only legal way to surface persistent-Predictions-slot status (DEC-M4-PRED-001 protects M-2 scaffold contract).

### Subsequent Workflow Cue

After M-4 lands, the recommended next workflow is **M-5 — Denial / Deception Strategies (slot 9) + User-Note Surface** per `.claude/plans/dossier-reframe-v2-roadmap.md` §M-5. M-5 introduces `dossier note` meta-command + `add_dossier_strategy` LLM tool + cross-evidence linkage, and is the natural place to revisit DEC-M4-PRED-005 (active falsification) — the user-note surface it introduces can carry analyst-authored "this prediction was wrong because X" notes that feed an extended falsification engine. M-6 (dossier-aware auto-pivot) is independent of M-5 once M-4 persistence lands and may be scheduled in parallel. C-3 (Philosophy + Bureaucratese modes — `sun_tzu`, `bruce_lee`, `bureaucrat`) remains independent of the dossier roadmap (DEC-30-CHARACTER-V2-007) and may land in the same wave or independently.

---

## Phase 17H: Denial / Deception Strategies (slot 9) + User-Note Authoring Surface + Active Falsification Engine — M-5 (W-68-M5-DENIAL-STRATEGIES, post-v1, 2026-06-07)

**Status:** in-progress (planner-staged 2026-06-07; implementer slice `wi-68-m5-impl-01` to follow).
**Workflow:** `w-68-m5-denial-strategies` / goal `g-68-m5-denial`.
**Worktree:** `/Users/jarocki/src/ap/.worktrees/feature-68-m5-denial-strategies` (branch `feature/68-m5-denial-strategies`, base AP main `cfafd6a` — M-4 landed at merge `f928149`, impl `1b1a2b0`).
**Per-slice plan (authoritative for content rationale):** `.claude/plans/dossier-m5-denial-strategies.md` (landed in this worktree; implementer commits it together with source).

**Source:** Phase 16 (W-68-DOSSIER-REFRAME-SCOPING) decomposed the reframe into M-1..M-9. M-1 (Phase 17B) shipped the panel + 3-slot inference; M-2 (Phase 17D) added the per-module slot extractors + `get_dossier_state` LLM tool + scaffold dataclasses; M-3 (Phase 17F) wired slot-fill events into the score economy + scaffolded `dossier_prediction_validated`; M-4 (Phase 17G) shipped persistent DossierState + Predictions Log auto-validation (confirmation path). M-5 is the slice that (a) fills slot 9 with a real extractor, (b) introduces the user-note authoring surface as first-class dossier evidence, and (c) closes the predictions lifecycle with an active falsification engine (DEC-M4-PRED-005's deferred responsibility).

### M-5 Goal (verbatim from per-slice plan §1)

> Three interlocking surfaces ship in this slice: (1) **Denial / Deception slot 9 inference** — replace the DEFERRED stub with a real extractor that pattern-matches SCOs + analyst notes for denial / deception indicators (DGA-shaped domains, fast-flux DNS hints, decoy / sandbox-evasion keywords in notes); slot 9 transitions `deferred → empty / partial / filled` and emits at +2 points through the M-3 emitter with zero scoring.py changes. (2) **User-note authoring surface** — chat meta-command `note <text>` + `create_dossier_note(text)` LLM tool, both riding on the existing `WorkspaceManager.add_note()` public method and the existing `AnalystNote` SQLAlchemy table (DEC-M5-NOTE-001 rejects the dispatch context's sentinel-row suggestion because the table already exists and is the canonical authority — adding a parallel sentinel would silently break every existing `_read_analyst_notes` caller). Notes immediately become evidence for motivation extraction, M-4 `note_keyword_any` prediction validation, the new M-5 denial extractor, and the new M-5 falsification engine. (3) **Active falsification engine** — typed `FalsificationEvidence` dataclass mirroring `ExpectedEvidence` plus a `falsify_predictions(...)` function that transitions `pending → falsified` when (a) typed contradiction evidence appears in current-hunt SCOs / notes or (b) the prediction has been pending for N or more hunts (`stale_after_n_hunts` temporal window). A `falsify_dossier_prediction(prediction_id, reason)` manual-override LLM tool lets the analyst mark a prediction wrong without waiting for auto-falsify evidence. Falsification events fire at +0 points per DEC-M4-PRED-006 (canon inherited; M-5 explicitly does not relitigate the negative-points question).

### Decision Log (Phase 17H / M-5; verbatim from per-slice plan §9)

| DEC ID | Decision | Rationale |
|--------|----------|-----------|
| **DEC-M5-DENIAL-001** | Slot 9 (Denial / Deception) v1.0 extractor vocabulary is three evidence categories: (a) DGA-shaped domain names (consonant-to-vowel ratio ≥ 3 AND label length ≥ 12); (b) fast-flux infrastructure hints (`x_ap_dns_ttl ≤ 60` extension on ipv4/ipv6 SCOs — forward-compatible reserve, no current AP module surfaces it); (c) denial / evasion keywords in analyst notes via a closed `_DENIAL_KEYWORDS` frozenset. Implemented as a pure function `_extract_denial(scos, notes)` in `dossier/slot_inference.py`. `DossierSlotName.DENIAL` leaves the always-DEFERRED set. | Smallest vocabulary covering the issue #68 user story ("confusing / denying / discouraging further attack progress") without becoming a TTP-classification engine. Mirrors the M-2 motivation extractor's shape. Richer detection (sandbox-detection IOCs from SCO extensions, multi-stage TTP cross-reference, registrar-rotation behavior) deferred to M-7 or later. |
| **DEC-M5-DENIAL-002** | Slot 9 status thresholds: EMPTY = 0 evidence items; PARTIAL = ≥ 1 evidence item in any single category; FILLED = ≥ 1 item across ≥ 2 distinct categories (cross-category corroboration). | Single-category evidence is suggestive but not analytically sufficient for "this actor uses denial tactics." Threshold mirrors DEC-M1-DOSSIER-INFERENCE-STATUS-001 and the M-2 motivation extractor's "≥ 2 categories → FILLED" rule. |
| **DEC-M5-DENIAL-003** | DGA shape detector is a deterministic pure-function helper `_is_dga_shaped(label) -> bool` with the rule `len(label) >= 12 AND consonant_count / max(vowel_count, 1) >= 3`. Misses dictionary-word DGAs by design; catches some legitimate-but-cryptic domains by design. | Pure-function detector keeps the extractor side-effect-free. Avoids new dependencies (n-gram entropy / frequency analysis). Conservative MVP behavior is fine because the cross-category corroboration rule (DEC-M5-DENIAL-002) prevents false-positive FILLED status from DGA-only noise. |
| **DEC-M5-NOTE-001** | User-note authoring persistence authority is the existing `AnalystNote` SQLAlchemy table (`models/database.py:218`) + the existing `WorkspaceManager.add_note(content, stix_object_id=None)` public method (workspace.py:647). Both the chat `note <text>` meta-command and the `create_dossier_note(text)` LLM tool call `add_note()` directly. NO new SQLAlchemy table, NO new `_RESERVED_ACTIONS` entry, NO `core/workspace.py` change. **The dispatch context's instruction to piggyback on the F63 sentinel-row pattern for user notes is explicitly overridden by this DEC** — the dispatch context did not catch that `AnalystNote` already exists and is the canonical authority for notes. | Sacred Practice 12 violation rejected: the F63 sentinel-row pattern is correct when no table exists for the data type; `AnalystNote` already exists and is already the canonical authority (used by motivation extractor, M-4 prediction validation `note_keyword_any`, report.py analyst-notes section, workspace stats, badge counts). Adding a parallel `_dossier_user_note` sentinel would silently break every existing `_read_analyst_notes` caller. The dispatch context's "no schema change" intent is honored trivially because the table already exists. |
| **DEC-M5-NOTE-002** | User-note authoring surface in M-5 is the chat meta-command `note <text>` (in `agent/chat.py`) + the `create_dossier_note(text)` LLM tool (in `agent/tools.py`). NO cmd2 `do_note` command is added to `core/console.py`. | cmd2 REPL is a power-user surface per ADR-010; v1's user-facing front door is `ap chat`. cmd2 parity is a future slice if requested. M-5 already touches 8+ files; adding `do_note` is negligible product value relative to the integration surface. |
| **DEC-M5-NOTE-003** | LLM tool `create_dossier_note(text)` v1.0 schema accepts only the `text` field; omits the `stix_object_id` parameter that the underlying `add_note()` method supports. | Minimal surface for v1.0. Most analyst notes are about the actor as a whole, not a specific SCO. Future slice may extend the tool to accept the optional argument if specific-SCO linkage proves useful. |
| **DEC-M5-FALSIFY-001** | Active falsification engine ships as a new `falsify_predictions(predictions, new_scos, new_notes, hunt_count) -> list[FalsificationResult]` function in `dossier/predictions.py`, parallel to M-4's `validate_predictions`. Falsified-prediction state rides on the existing `_predictions_log` sentinel row (M-4 storage authority) — no new `_RESERVED_ACTIONS` entry, no second sentinel action. | Mirrors the M-4 validation engine shape so implementer + reviewers can navigate by analogy. Reusing the existing sentinel row avoids parallel-authority residue — falsification state is part of the prediction's lifecycle, so it belongs in the same persisted record. |
| **DEC-M5-FALSIFY-002** | `FalsificationEvidence` vocabulary v1.0 mirrors `ExpectedEvidence` in the negative sense plus a temporal-window field: `negative_sco_type, negative_value_regex, negative_asn_in, contradiction_keyword_any, stale_after_n_hunts`. All non-None evidence fields ANDed. Empty FalsificationEvidence rejected with loud `ValueError`. Sentinel exception: `stale_after_n_hunts` alone is a valid configuration. | Smallest vocabulary covering the M-5 user story without becoming a query DSL. Typed dataclass keeps the LLM tool schema honest. Strict mirror of ExpectedEvidence makes the implementer's job mechanical. The stale-rule sentinel exception lets predictions carry "give up after N hunts" without forcing a contradiction-evidence shape. |
| **DEC-M5-FALSIFY-003** | The `stale_after_n_hunts` temporal rule is computed against the workspace's `get_module_runs()` row count, not wall-clock time. `PersistedPrediction.created_at_hunt_count` (NEW M-5 field) captures the run count at creation. Falsifier transitions on `(current_hunt_count - created_at_hunt_count) >= stale_after_n_hunts`. Legacy M-4 entries with `created_at_hunt_count=0` are skipped by the stale-rule path. | Workspace-relative counters are robust to clock skew, time-zones, and `ap chat` idle. The skip-on-0 path lets M-5 deploy against M-4-authored workspaces without retroactively falsifying old predictions on first M-5 hunt. |
| **DEC-M5-FALSIFY-004** | Falsification evidence scope = **current-hunt evidence only** (mirrors DEC-M4-PRED-003). The contradiction-evidence categories match against current-hunt SCOs and notes. The temporal `stale_after_n_hunts` rule is the ONLY cross-hunt signal — it counts run-rows, not a workspace-wide rescan. | Honors DEC-M4-PRED-003. A workspace-wide rescan would be expensive and create surprising behavior. A `revalidate_all_predictions(workspace)` repair tool can land as a separate slice if needed. |
| **DEC-M5-FALSIFY-005** | Falsification ScoreEvent: `action="dossier_prediction_falsified"`, `points=0` (DEC-M4-PRED-006 canon inherited), `indicator=prediction_id`, `rule_description` plain ASCII. F62 sees a no-op zero-points event. F63 milestone math unchanged. The new action joins the F64 `_DOSSIER_ACTIONS` filter (widened to 3-tuple) so its text is stripped from LLM summary. | Inheriting DEC-M4-PRED-006 keeps M-5 in scope (negative-points changes would require streak/milestone math changes — large blast radius). The "reckless guessing should cost score" intuition is documented M-7 narrative-feedback territory. The event still flows through `store_score_events` so audit trails reflect the falsification without affecting totals. |
| **DEC-M5-FALSIFY-006** | Manual override LLM tool `falsify_dossier_prediction(prediction_id, reason)` accepts a prediction id + plain-text reason. Idempotent: already-concluded predictions return a no-op JSON message. Persists via the same `save_predictions_log` path used by auto-falsification. | Analysts need a way to mark predictions wrong without authoring contradiction evidence in advance. Idempotency is non-negotiable for LLM-driven tool calls. The reason field flows into both the score event `rule_description` and the persisted PersistedPrediction's `validated_at` (reused as the conclusion timestamp). |
| **DEC-M5-FALSIFY-007** | `PersistedPrediction` gains two optional fields: `falsification_evidence: FalsificationEvidence | None = None` and `created_at_hunt_count: int = 0`. Both non-breaking. | Additive extension preserves M-4's persistence contract. Default values cover legacy M-4 entries without an upgrade migration. |
| **DEC-M5-FALSIFY-008** | The `_predictions_log` JSON envelope schema version bumps `1 → 2`. Deserializer accepts both v1 and v2 (v1 deserializes with M-5 fields at defaults). Serializer always emits v2. v3+ raises loud `RuntimeError`. The `_dossier_state_snapshot` envelope stays at v1. | DEC-M4-PERSIST-003 loud-failure handshake preserved (one version bump). Single envelope advances so only one (de)serializer pair updates. v1-read capability is the regression that protects M-4-authored workspaces. |

### M-5 Work Item Index

| ID | Title | Type | Status |
|----|-------|------|--------|
| **wi-68-m5-planner** | M-5 planner: per-slice plan + Evaluation Contract + Scope Manifest + Phase 17H authoring | docs only | landed (per-slice plan at `.claude/plans/dossier-m5-denial-strategies.md`; Phase 17H section authored in M-5 worktree 2026-06-07) |
| **wi-68-m5-impl-01** | M-5 implementer: slot 9 extractor + FalsificationEvidence + falsify_predictions + PersistedPrediction schema v2 + emit_dossier_prediction_falsified_event + create_dossier_note + falsify_dossier_prediction LLM tools + `note` chat meta-command + hunt-site rewire + tests | source + tests | dispatched (planner staged 2026-06-07) |

### M-5 Scope Manifest (summary; full at `.claude/plans/dossier-m5-denial-strategies.md` §8)

**Allowed / Required (the implementer MUST touch these):**
- `src/adversary_pursuit/dossier/slot_inference.py` (EXTEND: slot 9 extractor + DGA helper; slot 9 leaves the deferred set)
- `src/adversary_pursuit/dossier/predictions.py` (EXTEND: FalsificationEvidence + FalsificationResult + falsify_predictions + mark_confirmed_or_falsified + PersistedPrediction schema bump + v2 serializer)
- `src/adversary_pursuit/dossier/scoring.py` (EXTEND: emit_dossier_prediction_falsified_event helper; M-3 emitters byte-identical)
- `src/adversary_pursuit/dossier/__init__.py` (export new symbols)
- `src/adversary_pursuit/agent/tools.py` (hunt-site falsification wiring; new `create_dossier_note` + `falsify_dossier_prediction` LLM tools; extend `create_dossier_prediction` schema with optional `falsification_evidence`; widen `_DOSSIER_ACTIONS` filter; capture `created_at_hunt_count` in `_execute_create_dossier_prediction`)
- `src/adversary_pursuit/core/console.py` (hunt-site wiring mirror)
- `src/adversary_pursuit/agent/chat.py` (NEW `note <text>` meta-command branch + help-table row)
- `tests/test_dossier_slot_inference.py` (extend)
- `tests/test_dossier_predictions.py` (extend)
- `tests/test_dossier_predictions_serialization.py` (NEW or extension) — JSON envelope v1/v2 + schema_version=3 raises
- `tests/test_dossier_scoring.py` (extend)
- `tests/test_dossier_state.py` (extend — `apply_predictions_overlay` with falsified entries)
- `tests/test_agent_tools.py` (extend — new tools + hunt-site falsification + F64 gate)
- `tests/test_chat_dossier_metacommand.py` (extend — `note <text>` coverage)
- `tests/test_dossier_persistence_integration.py` (extend — Stages B + C of acceptance test)
- `tests/test_dossier_get_state_tool.py` (extend — slot 9 now real)
- `MASTER_PLAN.md` — this Phase 17H section + Phase 17G status flip + Plan Status table row + Active Phase Pointer tail-line update. **Implementer MUST `git add MASTER_PLAN.md` in the same commit as source (AP #74 orphan-prevention).**

**Forbidden (preserved authorities):**
- `src/adversary_pursuit/core/workspace.py` (F59 — BYTEWISE UNCHANGED in M-5; stronger than M-4's narrow-edit clause)
- `src/adversary_pursuit/models/database.py` (DEC-DB-002 + DEC-M5-NOTE-001 — no schema change; no new model)
- `src/adversary_pursuit/dossier/slots.py` (M-1/M-2/M-4 byte-identical — `SLOT_WEIGHTS` + `PredictionRecord` + `DenialStrategyRecord` scaffolds preserved)
- `src/adversary_pursuit/dossier/panel.py` (M-1 byte-identical)
- `src/adversary_pursuit/dossier/state.py` (M-4 byte-identical OR doc-only edits — no API change)
- `src/adversary_pursuit/gamification/scoring.py` (M-3 byte-identical — no new `DEFAULT_RULES` row)
- `src/adversary_pursuit/gamification/celebrations.py` (F63 invariant)
- `src/adversary_pursuit/core/streak.py` (F62 invariant)
- `src/adversary_pursuit/core/pivot_policy.py` + `src/adversary_pursuit/core/event_bus.py` (F60 invariant)
- `src/adversary_pursuit/gamification/modes.py`, `src/adversary_pursuit/agent/runner.py` (C-1/C-2 territory)
- `src/adversary_pursuit/modules/**`, `pyproject.toml`, hooks, settings, `CLAUDE.md`, `agents/`, `runtime/`

### M-5 Evaluation Contract (summary; full at `.claude/plans/dossier-m5-denial-strategies.md` §7)

- **required_tests:** ~45 new + extended tests across `test_dossier_slot_inference.py` (extend, ~8), `test_dossier_predictions.py` (extend, ~12), `test_dossier_predictions_serialization.py` (NEW/extension, ~4), `test_dossier_scoring.py` (extend, ~3), `test_dossier_state.py` (extend, ~3), `test_agent_tools.py` (extend, ~9 across new-tools + hunt-site groups), `test_chat_dossier_metacommand.py` (extend, ~3), `test_dossier_persistence_integration.py` (extend, ~3), `test_dossier_get_state_tool.py` (extend, ~1). Full suite green ≥ M-4 baseline (2178) + new M-5 tests.
- **required_evidence:** full pytest output green; `git diff main -- src/adversary_pursuit/core/workspace.py` empty (BYTEWISE invariant — stronger than M-4); `git diff main -- src/adversary_pursuit/models/database.py` empty; `git diff main -- src/adversary_pursuit/dossier/slots.py` empty; all other forbidden files diff-empty (paste each); demo trace (or test transcript) showing the §5 three-stage acceptance scenario — slot 9 transitions EMPTY → FILLED via DGA + denial-keyword note; auto-falsification via contradiction keyword; manual override; stale-rule auto-falsify after N hunts; persistence across `ap chat` restart.
- **required_authority_invariants:** F59 (`core/workspace.py` BYTEWISE UNCHANGED; `_RESERVED_ACTIONS` stays at M-4 three entries; M-5 reuses existing `AnalystNote` table + `add_note()` API per DEC-M5-NOTE-001); F60 (`pivot_policy.py` + `event_bus.py` BYTEWISE UNCHANGED); F62 (`streak.py` BYTEWISE UNCHANGED; falsification events at +0 neither reset nor extend the streak); F63 (`celebrations.py` UNCHANGED; +0-point events don't move milestone math); F64 (`_DOSSIER_ACTIONS` filter widens to 3-tuple; integration test asserts falsified event text absent from LLM summary); Sacred Practice 12 (per §6 matrix — critical: M-5 reuses `AnalystNote` rather than creating a parallel sentinel authority); DEC-M1-SLOTS-WEIGHT-AUTHORITY-001 (slot 9 weight stays 2.5); DEC-M2-DOSSIER-004 (`slots.py` BYTEWISE UNCHANGED — `DenialStrategyRecord` scaffold preserved; M-5 does NOT add per-strategy persistence); DEC-M3-DOSSIER-001..005 (`scoring.py` extended additively); DEC-M4-PERSIST-001..003 (storage authority preserved; `_predictions_log` envelope v1 → v2 with v1-read preserved); DEC-M4-PRED-002 (`ExpectedEvidence` v1.0 FROZEN; `FalsificationEvidence` is the new vocabulary); DEC-M4-PRED-003 (current-hunt scope preserved); DEC-M4-PRED-006 (no negative-points events — canon inherited by DEC-M5-FALSIFY-005).
- **required_integration_points:** `dossier/slot_inference.py` (slot 9 extractor + DGA helper); `dossier/predictions.py` (FalsificationEvidence + falsify_predictions + PersistedPrediction v2); `dossier/scoring.py` (emit_dossier_prediction_falsified_event); `dossier/__init__.py` (new exports); `agent/tools.py` (hunt-site wiring + new tools + filter widen + created_at_hunt_count capture); `core/console.py` (hunt-site mirror); `agent/chat.py` (NEW `note` meta-command).
- **forbidden_shortcuts:** no new SQLAlchemy table/model; no new `_RESERVED_ACTIONS` entry; no `core/workspace.py` modification; no `models/database.py` modification; no `dossier/slots.py` modification; no `dossier/panel.py` modification; no gamification/scoring.py or celebrations.py modification; no streak.py/pivot_policy.py/event_bus.py modification; no Rich markup in dossier event text or new LLM tool output (F64); no negative-points ScoreEvent emission (DEC-M4-PRED-006); no extension of `infer_dossier_state_full(...)` signature; no extension of `ExpectedEvidence` vocabulary (DEC-M4-PRED-002 frozen); no cmd2 `do_note` (DEC-M5-NOTE-002); no cross-hunt rescan for falsification evidence (DEC-M5-FALSIFY-004); no double-persist; no refactor of tools.py/console.py/chat.py beyond documented wiring.
- **rollback_boundary:** single feature branch revertible as one merge commit. Revert restores M-4 byte state; removes M-5 extensions to predictions.py/slot_inference.py/scoring.py/tools.py/console.py/chat.py/dossier-init; restores M-4 `_predictions_log` envelope schema_version=1 serializer. Workspaces written by M-5 will carry `_predictions_log` rows at schema_version=2; after revert the M-4 deserializer raises the documented `RuntimeError` (DEC-M4-PERSIST-003 loud-failure behavior). Documented manual mitigation: `DELETE FROM score_events WHERE action = '_predictions_log';` after revert. `AnalystNote` rows persist (table unchanged — no impact). No schema migrations; no settings changes; `streak.json` untouched.
- **ready_for_guardian_definition:** all required_tests green; full suite green ≥ M-4 baseline; forbidden-file `git diff main` outputs empty (paste each); `core/workspace.py` diff empty (stronger M-5 invariant); `models/database.py` diff empty; `dossier/slots.py` diff empty; **Phase 17H appended to MASTER_PLAN.md AND committed in the same commit as source** (AP #74 orphan-prevention); Phase 17G status flipped in-progress → completed in the same commit (M-4 closeout drift fix); Active Phase Pointer tail-line re-pointed from `W-68-M4-PERSISTENT-DOSSIER` to `W-68-M5-DENIAL-STRATEGIES`; `dossier/__init__.py` exports the M-5 public symbols; implementer commit message follows `feat(dossier):` Phase 17 prefix and references `#68` + `DEC-M5-DENIAL-001..003` + `DEC-M5-NOTE-001..003` + `DEC-M5-FALSIFY-001..008`.

### M-5 Out-of-Scope (deferred to later slices)

- **Targeting slot 5 inference** — remains DEFERRED after M-5. Future slice (likely M-7 or M-8) introduces either a user-supplied victim-industry profile or a victim-industry extractor from SCO data AP modules surface in a future update.
- **Per-`DenialStrategyRecord` persistence layer** — M-5 derives slot 9 status from SCO + note evidence directly, not from a typed strategy table. The M-2 `DenialStrategyRecord` scaffold dataclass stays as import contract for a future per-strategy slice if needed.
- **cmd2 `do_note` command** — DEC-M5-NOTE-002 keeps M-5 scope to chat-meta + LLM tool. cmd2 parity is a small future slice if requested.
- **Richer denial extractor vocabulary** — sandbox-detection IOCs from SCO extensions, multi-stage TTP cross-reference, registrar-rotation behavior, n-gram-entropy DGA detection — deferred to M-7 or later if v1.0 vocabulary proves too narrow.
- **Cross-hunt prediction revalidation** — `revalidate_all_predictions(workspace)` repair tool deferred (DEC-M5-FALSIFY-004 keeps validation + falsification current-hunt-only).
- **Negative-points ScoreEvent emission** — DEC-M4-PRED-006 canon inherited; M-5 explicitly does not relitigate.
- **Richer `ExpectedEvidence` vocabulary** — DEC-M4-PRED-002 v1.0 vocabulary FROZEN; `FalsificationEvidence` is the new vocabulary surface.
- **LLM `create_dossier_note` `stix_object_id` parameter** — DEC-M5-NOTE-003 keeps v1.0 surface minimal.

### Subsequent Workflow Cue

After M-5 lands, the recommended next workflow is **M-6 — Dossier-Aware Auto-Pivot Policy** per `.claude/plans/dossier-reframe-v2-roadmap.md` §M-6. M-6 extends F60's 3-gate pivot policy with a fourth "would this pivot fill an empty high-value slot?" input; the dossier state authority (M-4) and the now-real slot 9 (M-5) give M-6 the data it needs. M-6 and M-7 (Reports / Celebrations / Badges Dossier-Aware Upgrade — absorbs issue #32) are mutually independent once M-5 lands and may schedule in either order before M-8 closes v0.3.x cleanup. C-3 (Philosophy + Bureaucratese modes) remains independent of the dossier roadmap and may land in any wave.

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
| W-59-STIX-PROVENANCE | STIX 2.1 spec compliance + per-SCO provenance — workspace single authority for `x_ap_*` fields (`x_ap_fetched_at`, `x_ap_source_url`, `x_ap_api_version`, `x_ap_response_sha256`); `export_stix_bundle()` rebuilt via `stix2.v21.Bundle` round-trip. Closes issue #59. Per 2026-05-22 Threat Hunter expert assessment. See "Phase 11" section above. | source + tests + evidence | `a797831` (merge) / `f4a71a3` (impl) | completed |
| W-60-AUTO-PIVOT-POLICY | Auto-pivot policy engine — IOC filter + confidence gate + per-cascade budget + dry-run, 3-gate rate limiting. Closes #60. Per Threat Hunter P0 verdict 2026-05-23. See "Phase 12" section above. | source + tests + evidence | `8035add` (merge) / `60eab19` (impl) | completed |
| W-62-STREAK-AND-HONEST-MODES | F62 streak mechanic + honest modes — StreakManager single-authority, first_blood wiring, run_fail authority, `random.choice` honest fix. Per Atwood [P1] gamification assessment. See "Phase 12B" section above. | source + tests | `e3cf5ca` (merge) / `1d424ae`+`8b0faa2` (impl) | completed |
| W-63-MILESTONE-CATCHUP | F63 milestone catch-up + `streak_continued` ScoreEvent subtype. Per Atwood [P2] gamification assessment. See "Phase 12C" section above. | source + tests | `8778af3` (merge) / `a21eaba` (impl) | completed |
| W-64-DEDUP-LLM-NARRATION | F64 de-duplicate LLM narration vs Rich panel — strip gamification text from LLM-facing summary; sidecar pattern. See "Phase 13" section above. | source + tests | `3b92032` (merge) / `e460b41` (impl) | completed |
| W-61-KEYLESS-HUNTERS | F61 keyless hunter modules — 4 hunters (URLhaus, ThreatFox, MalwareBazaar, crt.sh) + smoke_test wiring + per-module `x_ap_*` exclusion tests. Closes #61. See "Phase 14" section above. | source + tests | `556f873` (merge) / `bce981f`+`5a5b8e1` (impl) | completed |
| W-68-DOSSIER-REFRAME-SCOPING | Threat Actor Dossier reframe strategic scoping — ratifies dossier-puzzle metaphor as v2 product center; slot schema v1.0; M-1..M-9 decomposition; #29/#30/#31/#32 disposition; Original Intent crowdsourcing scheduled as M-9. **Planning slice only**, no source code. See Phase 16 + `.claude/plans/dossier-reframe-v2-roadmap.md`. | docs only | `b2b846a` (merge) / `36b7f30` (impl) | completed |
| W-68-M1-DOSSIER-PANEL | Dossier Visualization Panel MVP (v0.2.0). `ap chat` `dossier` meta-command + read-only inference over existing workspace SCOs. No new tables, no new scoring math. Validates slot schema v1.0 against real workspace data; ±2-slot refinement window exercised conservatively per DEC-M1-DOSSIER-002 (vocabulary unchanged; status enum widened to {empty, partial, filled, deferred}). `get_dossier_state` LLM tool deferred to M-2 per DEC-M1-DOSSIER-004 (landed at Phase 17D). Landed in parallel with W-30-C1-FULL-TROLL-PROFILE per DEC-30-CHARACTER-V2-007. See Phase 17B. | source + tests | `486a5ad` (merge) / `11aaf83` (impl) | completed |
| W-30-CHARACTER-V2-SCOPING | Character System v2 strategic scoping — ratifies "Borderlands/Fallout RPG-style" as voice-quality recommendation (not catalog replacement); per-mode disposition (8 UPGRADE / 2 KEEP_STATIC / 0 RETIRE — ninja disposition flipped to UPGRADE by C-2 per DEC-C2-NINJA-001); `LLMPersonaProfile` schema v1.0 (8 fields, ≤ 165 tokens per mode, via `AgentRunner.set_character`); C-1..C-4 decomposition; F62/F64 invariant preservation; XP-grind retired (DEC-68-DOSSIER-REFRAME-005); narrow `mastery_level` hook deferred to C-4. **Planning slice only**, no source code. See Phase 17 + `.claude/plans/character-v2-roadmap.md`. | docs only | `fe4c0b1` (merge) / `5726819` (impl) | completed |
| W-30-C1-FULL-TROLL-PROFILE | Character v2 MVP (v0.2.0). `LLMPersonaProfile` frozen dataclass + `CharacterMode.llm_profile` field + extended `AgentRunner.set_character` composer + `full_troll` profile (DEC-C1-FULLTROLL-001) + F62/F64 invariant test suite (run_fail single-authority preserved; persona-swap tool-call identity hard gate; per-mode token budget ≤ 165; no "+N points" smuggling in LLM text). Other 9 modes shipped at `llm_profile=None` (F62 behavior). DEC-C1-FULLTROLL-001..005 binding. Landed in parallel with W-68-M1-DOSSIER-PANEL per DEC-30-CHARACTER-V2-007. See Phase 17C. | source + tests | `e49e70b` (merge) / `5417cec` (impl) | completed |
| W-68-M2-SLOT-EXTRACTORS | Dossier M-2: per-module slot extractors + `get_dossier_state` LLM tool. 4 real extractors (Timing / Targeting / Capability / Motivation) + 2 scaffold-only (Predictions / Denial) + `infer_dossier_state_full` entrypoint + LLM tool (DEC-M1-DOSSIER-004 deferred surface). DEC-M2-DOSSIER-001..005 + DEC-M2-MOTIVATION-001 binding. `_parse_utc_hour` datetime-handling bug fix included. F59/F60/F62/F63/F64 invariants preserved. See Phase 17D + `.claude/plans/dossier-m2-slot-extractors.md`. | source + tests | `11b3fd3` (merge) / `83a98d9` (impl) | completed |
| W-30-C2-NINJA-PROFILE | Character v2 C-2: `ninja` LLMPersonaProfile (quiet-operator voice, opaque fourth-wall stance, clipped cadence). Two-file slice (`gamification/modes.py` + `tests/test_character_v2.py`). DEC-C2-NINJA-001..003 binding; supersedes Phase 17 DEC-30-CHARACTER-V2-002 ninja=KEEP_STATIC disposition. 45/45 `test_character_v2.py` + 1984/1985 full suite pass. Closes #30 C-2 slice. See Phase 17E + `.claude/plans/c2-ninja-profile-plan.md`. | source + tests | `f8bded8` (merge) / `699dbc8` (impl) | completed |
| W-PLAN-DRIFT-FIX-2026-05-29 | Plan-drift closeout: harvest M-1's orphaned Phase 17B from feature-68-m1-dossier-panel worktree; harvest C-1's orphaned Phase 17B and rename to Phase 17C (chronological merge order); author Phase 17D from `.claude/plans/dossier-m2-slot-extractors.md` + source DEC annotations (M-2 had no orphan); author Phase 17E from `.claude/plans/c2-ninja-profile-plan.md` + source DEC annotations (C-2 had no orphan); flip Phase 16 + Phase 17 body status from in-progress to completed; rebuild Plan Status table with 21 rows; re-point active-phase tail-grep pointer to current next work (M-3). Closes #74. **Bookkeeping only — no source code touched.** | docs only | this commit | completed |
| W-68-M3-DOSSIER-SCORING | Dossier M-3: Scoring + Score Event Re-tune. New `dossier/scoring.py` pure-function emitter (DEC-M3-DOSSIER-001); per-IOC `DEFAULT_RULES` re-tune to `initial=minimum=1` for 9 SCO-mapped action keys (DEC-M3-DOSSIER-004); hunt-site snapshot+emit wiring (DEC-M3-DOSSIER-002); `dossier_prediction_validated` scaffold not emitted (DEC-M3-DOSSIER-005 — M-4 plugs in). F59/F60/F62/F63/F64 invariants preserved. See Phase 17F + `.claude/plans/dossier-m3-scoring.md`. | source + tests | `2809b13` (merge) / `974fa1a` (impl) | completed |
| W-68-M4-PERSISTENT-DOSSIER | Dossier M-4: Persistent Dossier State + Predictions Log Auto-Validation. NEW `dossier/state.py` + NEW `dossier/predictions.py`; hunt-site rewire so `pre_state` comes from persistent snapshot (one fewer `infer_dossier_state_full` call per hunt); NEW `create_dossier_prediction` LLM tool + typed `ExpectedEvidence` match vocabulary; M-3 scaffolded `emit_dossier_prediction_validated_event` wired to fire on confirmation at weight 4. Storage authority: F63 sentinel-row pattern (DEC-M4-PERSIST-001) — no schema change, no new SQLAlchemy model. Narrow `core/workspace.py` change (DEC-M4-PERSIST-002: `_RESERVED_ACTIONS` constant + `get_recent_scores` filter widening). Active falsification deferred to M-5 (DEC-M4-PRED-005). DEC-68-DOSSIER-REFRAME-007 falsified-prediction deduction committed: confirmation=+4 / falsification=0 (DEC-M4-PRED-006). F59/F60/F62/F63/F64 invariants preserved. DEC-M4-PERSIST-001..003 + DEC-M4-PRED-001..006 binding. See Phase 17G + `.claude/plans/dossier-m4-persistent-state.md`. | source + tests | `f928149` (merge) / `1b1a2b0` (impl) | completed |
| W-68-M5-DENIAL-STRATEGIES | Dossier M-5: Denial / Deception Strategies (slot 9) + User-Note Authoring Surface + Active Falsification Engine. EXTEND `dossier/slot_inference.py` with real slot 9 extractor (DGA shape + fast-flux TTL hint + denial-keyword notes; DEC-M5-DENIAL-001..003); EXTEND `dossier/predictions.py` with `FalsificationEvidence` dataclass + `falsify_predictions` engine + `PersistedPrediction` schema v2 (DEC-M5-FALSIFY-001..008); EXTEND `dossier/scoring.py` with `emit_dossier_prediction_falsified_event`; NEW chat meta-command `note <text>` + NEW `create_dossier_note` LLM tool riding on the existing `WorkspaceManager.add_note()` + `AnalystNote` table (DEC-M5-NOTE-001 rejects the dispatch context's sentinel-row suggestion — the table is the canonical authority); NEW `falsify_dossier_prediction` manual-override LLM tool; widen `_DOSSIER_ACTIONS` F64 filter to 3-tuple. `core/workspace.py` BYTEWISE UNCHANGED in M-5 (stronger than M-4's narrow-edit clause). `models/database.py` UNCHANGED. DEC-M4-PRED-006 falsification=+0 canon inherited. F59/F60/F62/F63/F64 + Sacred Practice 12 invariants preserved. DEC-M5-DENIAL-001..003 + DEC-M5-NOTE-001..003 + DEC-M5-FALSIFY-001..008 binding. See Phase 17H + `.claude/plans/dossier-m5-denial-strategies.md`. | source + tests | TBD-guardian-land (merge) / HEAD feature/68-m5-denial-strategies (impl) | in-progress |

> **Recommended next work item:** `W-68-M5-DENIAL-STRATEGIES` — Dossier M-5 Denial / Deception Strategies (slot 9) + User-Note Authoring Surface + Active Falsification Engine per Phase 16 roadmap §M-5. Implementer territory: EXTEND `dossier/slot_inference.py` with slot 9 extractor (DGA + fast-flux TTL + denial-keyword notes); EXTEND `dossier/predictions.py` with `FalsificationEvidence` + `falsify_predictions` engine + `PersistedPrediction` schema v2; EXTEND `dossier/scoring.py` with falsified-event emitter; NEW chat `note <text>` meta-command + NEW `create_dossier_note` + `falsify_dossier_prediction` LLM tools (riding on the existing `AnalystNote` table per DEC-M5-NOTE-001 — explicit override of the dispatch context's sentinel-row suggestion because the table already exists and is the canonical authority). `core/workspace.py` BYTEWISE UNCHANGED in M-5; `models/database.py` UNCHANGED; `dossier/slots.py` BYTEWISE UNCHANGED (DEC-M2-DOSSIER-004 preserved). Authority preserved: F59 workspace single-authority + F60 pivot/event-bus + F62 streak + F63 milestone + F64 panel separation + Sacred Practice 12. DEC-M4-PRED-006 falsification=+0 canon inherited; no negative-points events in M-5. Canonical chain: planner → guardian (provision) → implementer → reviewer → guardian (land). See `.claude/plans/dossier-m5-denial-strategies.md` for binding scope, slot 9 vocabulary, FalsificationEvidence dataclass, schema v1→v2 envelope handshake, and the load-bearing three-stage acceptance test ("§5: slot 9 EMPTY→FILLED via DGA + denial-keyword note; auto-falsification via contradiction keyword; manual override + stale-rule auto-falsify + `ap chat` restart").

> _Historical note (2026-06-02):_ M-4 persistent dossier + predictions auto-validation shipped (Phase 17G, merge `f928149`, impl `1b1a2b0`). NEW `dossier/state.py` + NEW `dossier/predictions.py` + hunt-site rewire + `create_dossier_prediction` LLM tool. Storage authority bound to F63 sentinel-row pattern in `score_events` (no schema change). Narrow `core/workspace.py` filter widening per DEC-M4-PERSIST-002 (`_RESERVED_ACTIONS` frozenset). Seventh DEC family binding for v2: DEC-M4-PERSIST-* + DEC-M4-PRED-*. Active falsification deferred to M-5 per DEC-M4-PRED-005.
>
> **Plan-drift closeout (2026-05-29):** This commit (`w-plan-drift-fix-2026-05-29`) harvested 4 phases of orphaned planner content + landed-but-untracked DEC annotations into MASTER_PLAN.md per AP #74. Phase 17B (M-1) + Phase 17C (C-1, renumbered from C-1 worktree's Phase 17B per chronological order) recovered from disposable worktrees `.worktrees/feature-68-m1-dossier-panel` + `.worktrees/feature-30-c1-full-troll-profile`. Phase 17D (M-2) + Phase 17E (C-2) authored from `.claude/plans/dossier-m2-slot-extractors.md` + `.claude/plans/c2-ninja-profile-plan.md` + source `DEC-M2-*` / `DEC-C2-*` annotations. Phase 16 + Phase 17 body status flipped in-progress → completed. Header counter and active-phase tail-grep pointer re-aligned with actual landed state (21 phase sections; 21 of 21 completed; active pointer = M-3). Pure bookkeeping; no source touched.
>
> _Historical note (2026-05-19):_ v1 ship gate fully closed — `v0.1.0` (stable, no rc suffix) published at https://github.com/jarocki/ap/releases/tag/v0.1.0 with `isPrerelease: false`. All four v1 boundary work items landed (`W-V1-RELEASE-VERIFY`, `W-OTX-TIMEOUT`, `W-GREYNOISE`, `W-V1-FINAL-SHIP`).
>
> _Historical note (2026-05-28..2026-05-29):_ v0.2.0 wave landed — M-1 dossier panel + C-1 full_troll persona (2026-05-28, parallel) + M-2 slot extractors + C-2 ninja persona (2026-05-29). Five DEC families binding for v2: DEC-68-DOSSIER-REFRAME-*, DEC-30-CHARACTER-V2-*, DEC-M1-DOSSIER-*, DEC-C1-FULLTROLL-*, DEC-M2-DOSSIER-*, DEC-C2-NINJA-*.
>
> _Historical note (2026-06-01):_ M-3 dossier scoring shipped (Phase 17F, merge `2809b13`, impl `974fa1a`). `dossier/scoring.py` pure-function emitter + per-IOC re-tune to 1/1 baseline + hunt-site snapshot+emit wiring. Sixth DEC family binding for v2: DEC-M3-DOSSIER-*. `dossier_prediction_validated` scaffolded but not emitted (M-4 wires it).
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

---

## Active Phase Pointer (2026-06-07)

**Phase Active (2026-06-07 — planner staged; implementer slice to follow):** `W-68-M5-DENIAL-STRATEGIES` (Phase 17H — M-5 Denial / Deception Strategies (slot 9) + User-Note Authoring Surface + Active Falsification Engine). M-4 landed 2026-06-02 (merge `f928149`, impl `1b1a2b0`, 2178 tests green). M-5 planner staged 2026-06-07; implementer slice `wi-68-m5-impl-01` to follow. Canonical chain `planner → guardian (provision) → implementer → reviewer → guardian (land)`. This pointer line is positioned as the last `**Phase ...` boldline in the document so `~/.claude/hooks/context-lib.sh:88` `get_plan_status()` tail-grep on `^#.*phase|^**Phase` resolves to current work instead of the historical `**Phase 6 rationale (new):**` narrative line in the Implementation Order section.
