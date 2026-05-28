"""AP module tools for the agent framework.

Each tool wraps an existing PursuitModule, handling initialization,
execution, result formatting, and workspace storage.

@decision DEC-AGENT-TOOLS-001
@title Thin tool wrappers delegating to existing PursuitModule infrastructure
@status accepted
@rationale The existing modules (whois, dns, abuseipdb, shodan, hibp, otx, urlscan,
           virustotal, censys_host, passivetotal) are already tested and working.
           Tool wrappers are thin adapters that: (1) accept simple string args
           from the LLM, (2) initialize the module with config, (3) call hunt(),
           (4) format + store results. No business logic duplication.

@decision DEC-AGENT-GRAPH-EXPORT-001
@title render_graph and export_workspace as stateless per-call RelationshipGraph builds
@status accepted
@rationale RelationshipGraph is a lightweight in-memory object (DEC-GRAPH-001). Building
           it fresh on each render_graph/export_workspace call avoids any staleness issue
           (graph always reflects current workspace state), eliminates session-lifecycle
           complexity, and mirrors exactly how console.py do_graph and do_export work:
           both construct a new RelationshipGraph(), call build_from_workspace(raw_objects),
           then render/export. Caching would require invalidation logic with no benefit
           given graph builds are O(n) on a small CTI workspace. The two tools are
           registered as LLM tools (OpenAI function-calling format, DEC-AGENT-TOOLS-002)
           and also exposed as chat meta-commands in chat.py (mirroring the cmd2 pattern
           of DEC-AGENT-HINTS-001 and DEC-AGENT-AUTOPIVOT-001).

@decision DEC-AGENT-TOOLS-002
@title OpenAI function-calling format for tool definitions
@status accepted
@rationale The OpenAI function-calling schema (list of {type, function: {name,
           description, parameters}}) is now the de facto standard. litellm
           passes this format to every supported LLM provider, translating as
           needed. By producing tool definitions in this format, the tool layer
           is compatible with any litellm-supported backend (Ollama, OpenAI,
           Anthropic, etc.) without changes.

@decision DEC-AGENT-TOOLS-003
@title Per-module credential builders for multi-key auth modules
@status accepted
@rationale Most modules use a single api_key, but Censys requires censys_id +
           censys_secret and PassiveTotal requires passivetotal_user +
           passivetotal_key. _CREDENTIAL_BUILDERS maps module paths to callables
           that construct the full init_config dict from ConfigManager. Modules
           not in the map fall back to the legacy {"api_key": ...} pattern.
           This keeps run_module() generic while correctly threading multi-key
           credentials to modules that need them.

@decision DEC-AGENT-HINTS-001
@title HintProvider wired into ToolContext; both chat meta-command and LLM tools exposed
@status accepted
@rationale Two integration paths are provided for hints in the agent:
           (1) Chat meta-command ('hint', 'hint <module>', 'hint buy [<module>]') in
           chat.py mirrors cmd2's do_hint — gives the analyst immediate access without
           involving the LLM at all. Handled in the local meta-command dispatch before
           any LLM call so it is fast, deterministic, and not subject to LLM refusal.
           (2) LLM tools 'get_next_hint' and 'buy_hint' let the LLM proactively offer
           hints when it detects the analyst is stuck or requests a suggestion. Both
           paths share the SAME HintProvider instance on ToolContext so the revealed-ID
           set (DEC-HINT-002) is consistent regardless of which path surfaced a hint.
           Balance protection (DEC-HINT-001): buy_hint reads get_total_score() before
           calling HintProvider.buy_hint(). On InsufficientBalanceError the cost is
           NOT deducted and an error string is returned — score never goes negative.
           Score deduction for paid hints uses workspace_mgr.store_score_events() with
           a negative points entry, exactly as documented in DEC-HINT-001 and the
           HintProvider docstring. The HintProvider itself is stateless about the
           workspace — the caller (this module and chat.py) owns deduction.

@decision DEC-AGENT-AUTOPIVOT-001
@title EventBus auto-pivot integrated into ToolContext; opt-in via autopivot_enabled flag
@status accepted
@rationale The cmd2 console (APConsole) has no autopivot integration yet — this is the
           first wiring of EventBus.process_results into an execution path. The agent
           tool path is the right place because:
           (1) Opt-in by default (DEC-EVENTBUS-002): autopivot_enabled=False on
               ToolContext. Analysts enable it explicitly via 'autopivot on' in the
               chat meta-command, mirroring the cmd2 pattern where it is a toggle.
           (2) EventBus.process_results is the canonical cascade workhorse. After
               run_module() produces STIX results, process_results() publishes each
               STIX indicator as a PivotEvent which triggers all subscribed module
               callbacks for that STIX type. Cascaded results are collected and
               merged into the tool response summary so the LLM and user both see
               what fired secondarily.
           (3) Depth limit deferred to PivotConfig.max_depth (default=2, DEC-EVENTBUS-001).
               Module whitelist deferred to PivotConfig.module_whitelist. Both are
               respected transparently by EventBus.publish() — the tool layer does not
               duplicate that logic.
           (4) Async bridge: run_module() uses asyncio.run() for each async call
               sequentially (not nested). After asyncio.run(mod.hunt()) returns, a
               second asyncio.run(event_bus.process_results()) starts a fresh event
               loop — valid in Python 3.12+ when calls are sequential.
           (5) Module subscriptions: DEFAULT_SUBSCRIPTIONS maps module_path → stix_types.
               Each entry is registered via event_bus.register_module_subscriptions()
               with a per-module callback that initialises and runs that module's
               hunt() for the pivoted indicator value.

@decision DEC-AGENT-CHALLENGES-001
@title ChallengeManager wired into ToolContext; list_challenges + check_challenges LLM tools
@status accepted
@rationale ChallengeManager is session-scoped (DEC-CHALLENGE-002: in-memory state).
           Wiring it into ToolContext (parallel to BadgeManager, HintProvider) means
           both the LLM tool path and the chat meta-command path share one instance
           so challenge completion state is consistent regardless of which code path
           checks it.

           Two LLM tools are exposed:
           (1) list_challenges() — returns active/all challenges as serializable dicts
               via ChallengeManager.list_challenges(). No side-effects. The LLM can
               call this at session start to announce what challenges are available.
           (2) check_challenges() — runs ChallengeManager.check_all(workspace_data)
               against the current workspace state and returns newly-completed challenges.
               The workspace_data dict is assembled here using the same keys as
               APConsole._build_workspace_data() (DEC-CHALLENGE-001): stix_type_counts,
               modules_used, total_score, total_indicators, indicators.

           Auto-check after every run_module() call (mirrors APConsole._check_challenges_after_run):
           After badges are checked, build workspace_data from WorkspaceManager and call
           check_all(). Newly-completed challenges are appended to the run_module summary
           and returned under the "challenges" key so execute_tool/chat.py can render
           them as Rich panels. A session-scoped set _announced_challenges prevents the
           same challenge from appearing in the summary more than once (parallel to
           _awarded_badges for badges).

           The chat meta-command 'challenges' lists all challenges in a Rich Table,
           mirroring APConsole.do_challenges() exactly — same column layout.

           Modules_used tracking: WorkspaceManager.get_module_runs() is already called
           for workspace summary; here we reuse it to build modules_used as a list of
           module_name strings from get_module_runs(), matching how APConsole builds
           _build_workspace_data(). This is the identical strategy, not a new mechanism.

@decision DEC-AGENT-REPORT-001
@title ReportGenerator wired into ToolContext; interview-driven report via LLM tools + chat meta-command
@status accepted
@rationale ReportGenerator (DEC-REPORT-001/002/003) holds interview state in-memory for
           the session. Two integration paths are provided, both sharing the same
           ReportGenerator instance on ToolContext:

           (1) LLM tools — three tools let the LLM drive the interview multi-turn:
               - start_report_interview: initialises (or resets) ReportGenerator, returns
                 all 5 interview questions so the LLM can present them one by one.
               - answer_report_question: records the analyst's answer for a given question
                 index (0-4). Returns confirmation with the question text.
               - generate_report: calls ReportGenerator.generate() and returns the full
                 Markdown report as a string.
               These three tools mirror cmd2 do_report semantics: start interview, answer
               each question, generate — without forcing interactive input() in the tool
               layer.

           (2) Chat meta-command 'report' — handled locally in chat.py before LLM:
               - 'report'                     -> show interview status (questions + answers so far)
               - 'report answer <idx> <text>' -> set answer for question index idx
               - 'report generate'            -> generate and print the report
               Shares the same ToolContext.report_generator so answers accumulate
               regardless of which path (LLM tool vs chat meta-command) set them.

           Both paths share a single ReportGenerator instance on ToolContext (lazy-init
           on first start_report_interview call). This mirrors DEC-AGENT-HINTS-001 and
           DEC-AGENT-CHALLENGES-001: one session-scoped object, two access paths.
           Re-calling start_report_interview resets the generator (fresh answers list),
           mirroring cmd2 do_report which always starts from blank answers.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from adversary_pursuit.core.config import ConfigManager
from adversary_pursuit.core.event_bus import (
    DEFAULT_SUBSCRIPTIONS,
    EventBus,
    PivotConfig,
)
from adversary_pursuit.core.graph import RelationshipGraph
from adversary_pursuit.core.plugin_mgr import PluginManager
from adversary_pursuit.core.report import ReportGenerator
from adversary_pursuit.core.streak import StreakManager
from adversary_pursuit.core.workspace import WorkspaceManager
from adversary_pursuit.gamification.badges import BadgeManager
from adversary_pursuit.gamification.celebrations import (
    CelebrationEngine,
    highest_crossed_milestone_id,
)
from adversary_pursuit.gamification.challenges import Challenge, ChallengeManager
from adversary_pursuit.gamification.hints import (
    HintProvider,
    HintResult,
    InsufficientBalanceError,
)
from adversary_pursuit.gamification.modes import ModeManager
from adversary_pursuit.gamification.scoring import ScoringEngine, make_streak_continued_event

logger = logging.getLogger(__name__)


class ToolContext:
    """Shared context for all tools — config, workspace, scoring, plugins.

    A single ToolContext is created per agent session and shared across
    all tool invocations. This ensures workspace state accumulates correctly
    across multiple tool calls in one conversation.

    Parameters
    ----------
    config_dir:
        Path to config directory. Defaults to ~/.ap. Pass tmp_path in tests.
    workspace_dir:
        Path to workspace directory. Defaults to ~/.ap/workspaces.
        Pass tmp_path in tests.
    hints:
        Optional custom hint list passed to HintProvider. Defaults to None
        (uses the built-in catalogue). Pass a custom list in tests.
    """

    def __init__(self, config_dir=None, workspace_dir=None, hints=None, streak_path=None):
        self.config_mgr = ConfigManager(config_dir=config_dir)
        self.config = self.config_mgr.load()
        self.workspace_mgr = WorkspaceManager(workspace_dir=workspace_dir)
        self.plugin_mgr = PluginManager()
        self.plugin_mgr.load_plugins()
        self.scoring = ScoringEngine()
        self.celebration = CelebrationEngine()
        self.badge_mgr = BadgeManager()
        self.mode_mgr = ModeManager()
        # StreakManager: sole authority for streak.json (DEC-62-STREAK-007).
        # streak_path is injectable for tests (DEC-62-STREAK-001).
        self.streak_mgr: StreakManager = StreakManager(path=streak_path)
        # HintProvider is session-scoped: revealed-ID set persists across all hint calls
        # in this session so the same hint is never shown twice (DEC-HINT-002).
        # Shared by both the LLM tool path and the chat meta-command path (DEC-AGENT-HINTS-001).
        self.hint_mgr: HintProvider = HintProvider(hints=hints)
        # Tracks badge IDs awarded in this session (application-layer dedup, DEC-BADGE-002).
        # Populated from workspace on first badge check; updated as badges are earned.
        self._awarded_badges: set[str] = set()

        # ChallengeManager is session-scoped (DEC-CHALLENGE-002, DEC-AGENT-CHALLENGES-001).
        # Shared by both the LLM tool path and the chat meta-command path so that
        # challenge completion state is consistent regardless of which path checks it.
        self.challenge_mgr: ChallengeManager = ChallengeManager()
        # Tracks challenge IDs announced in this session to prevent re-announcement
        # in the run_module summary. Parallel to _awarded_badges for badges.
        self._announced_challenges: set[str] = set()

        # ReportGenerator for interview-driven report generation (DEC-AGENT-REPORT-001).
        # Lazy-initialised on first start_report_interview() call so sessions that never
        # use the report feature pay zero overhead. Re-calling start_report_interview()
        # resets this to a fresh instance (blank answers), mirroring cmd2 do_report.
        # Shared by both the LLM tool path and the chat meta-command path so interview
        # answers accumulate consistently regardless of which path set them.
        self.report_generator: ReportGenerator | None = None

        # EventBus for auto-pivot cascades (DEC-AGENT-AUTOPIVOT-001).
        # Starts disabled (autopivot_enabled=False) per DEC-EVENTBUS-002.
        # PivotConfig receives AutoPivotPolicyConfig so PivotPolicy is constructed
        # with user-configured thresholds and budgets (DEC-60-PIVOT-POLICY-CONFIG-001).
        self.event_bus: EventBus = EventBus(
            config=PivotConfig(
                enabled=False,
                policy=self.config.general.auto_pivot_policy,
            )
        )
        self.autopivot_enabled: bool = False

        # Register module subscriptions from DEFAULT_SUBSCRIPTIONS so the event
        # bus knows which modules to cascade-trigger for each STIX type.
        # Each subscription registers a per-module callback that will initialise
        # and hunt() on the pivoted indicator value (see _make_cascade_callback).
        for module_path, stix_types in DEFAULT_SUBSCRIPTIONS.items():
            callback = self._make_cascade_callback(module_path)
            self.event_bus.register_module_subscriptions(module_path, stix_types, callback)

    def run_module(  # noqa: PLR0912
        self, module_path: str, target: str, options: dict | None = None
    ) -> dict:
        """Run a module and return formatted results with scoring.

        Dispatches to the named PursuitModule, runs hunt(), stores results in
        the workspace, applies scoring, computes the celebration artifact, and
        returns a summary dict.

        The ``dry_run`` key in ``options`` (default ``False``) is threaded to
        ``EventBus.process_results`` so that policy gates are evaluated without
        invoking any cascade callbacks (DEC-60-PIVOT-POLICY-005).  In dry-run
        mode ``cascade_results`` and ``cascade_count`` are ``[]``/``0``;
        ``decision_log`` carries the full gate verdicts.

        @decision DEC-AGENT-CELEBRATIONS-001
        @title CelebrationEngine wired into run_module return value
        @status accepted
        @rationale The cmd2 console renders celebrations in _execute_hunt() after
                   scoring. The agent path must surface the same visual feedback to
                   users. Rather than rendering inside run_module (which has no
                   console reference), the celebration string is computed here and
                   returned under the "celebration" key so the caller (execute_tool,
                   chat.py REPL) can render it at the appropriate display boundary.
                   Keeping computation in run_module means tests can assert the
                   artifact without mocking the Rich console.
                   Silent path: celebration is None when total_points == 0 (no
                   scoring events), matching the cmd2 path which only shows
                   celebration when scoring_events is non-empty.
                   Milestone messages are computed against the post-storage total
                   score and appended to the celebration string when they fire.

        @decision DEC-AGENT-BADGES-001
        @title BadgeManager wired into run_module after scoring, mirroring cmd2 _check_badges_after_run
        @status accepted
        @rationale cmd2 APConsole._check_badges_after_run() calls BadgeManager.check_all()
                   after each module execution, persists newly-earned badge events via
                   workspace_mgr.store_badge_event(), and renders a Rich panel per badge.
                   The agent path mirrors this exactly: (1) build already_awarded from the
                   workspace using get_awarded_badges() on first check then from the session
                   cache _awarded_badges thereafter for dedup; (2) call check_all() against
                   get_workspace_stats(); (3) persist via store_badge_event(); (4) return the
                   newly-earned Badge list under "badges" key so execute_tool can thread it
                   to chat.py for Rich panel rendering.
                   Silent path: badges is [] when no new badges earned, matching cmd2
                   behaviour which only renders panels when newly_earned is non-empty.
                   _awarded_badges set is seeded lazily from the workspace on first call
                   so sessions that resume mid-investigation do not re-award old badges.

        @decision DEC-AGENT-MODES-001
        @title ModeManager wired into ToolContext; mode affects celebration text and LLM persona
        @status accepted
        @rationale Three integration points for character modes in the agent path:
                   (1) ToolContext holds a ModeManager instance (parallel to BadgeManager,
                   CelebrationEngine) so mode state is scoped to the agent session, not
                   imported as a global — matches cmd2 APConsole.mode_mgr pattern.
                   (2) run_module celebration: CelebrationEngine produces the ASCII art;
                   mode_mgr.active.score_celebration.format(points=total) appends the
                   mode-specific points line, mirroring console.py _execute_hunt() which
                   uses the same template call. The field is named 'personality' on
                   CharacterMode (not 'persona_prompt' as the plan draft said).
                   (3) LLM persona: AgentRunner.set_character(mode) prepends mode.personality
                   to the default system prompt. chat.py 'mode <name>' meta-command calls
                   ModeManager.switch(name) then runner.set_character(active_mode) so the
                   LLM voice changes immediately without resetting conversation history beyond
                   the system message slot (conversation[0]).

        Parameters
        ----------
        module_path:
            Canonical module path, e.g. "osint/abuseipdb".
        target:
            The target string (IP, domain, URL, email) to hunt.
        options:
            Optional options dict passed to hunt(). Defaults to {}.
            Special key: ``dry_run`` (bool, default False) — when True,
            evaluate pivot policy gates but do NOT invoke cascade callbacks.

        Returns
        -------
        dict with keys:
            results (list[dict]): raw hunt() output
            score_events (list[dict]): scoring events generated
            total_points (int): total points awarded
            summary (str): human-readable summary for the LLM
            celebration (str | None): ASCII art celebration string, or None
                when no points were awarded (silent path).
            badges (list[Badge]): newly-earned Badge objects this run, or []
                when no new badges earned (silent path).
            decision_log (list[dict]): policy decision log entries; populated on
                dry_run=True, empty list otherwise (DEC-60-PIVOT-POLICY-005).

        Returns {"error": str} if the module is not found.
        """
        mod = self.plugin_mgr.get_module(module_path)
        if mod is None:
            return {"error": f"Module '{module_path}' not found"}

        # Build init_config for this module via the shared credential resolver.
        # See _resolve_module_credentials() for the full precedence logic
        # (DEC-AGENT-SERVICE-NAME-MAP-001, DEC-AGENT-TOOLS-003).
        init_config = _resolve_module_credentials(module_path, self.config_mgr)
        mod.initialize(init_config)

        # Run hunt() via asyncio — modules are async
        results = asyncio.run(mod.hunt(target, options or {}))

        # Store in workspace (auto-creates default if none active)
        # Provenance kwargs: None until hunt() surfaces vendor metadata
        # (DEC-59-STIX-PROVENANCE-004). x_ap_fetched_at is defaulted by
        # workspace; the other three require module-author API changes.
        count = self.workspace_mgr.store_stix_objects(
            results,
            module_path,
            target,
            source_url=None,
            api_version=None,
            response_sha256=None,
            fetched_at=None,
        )

        # Capture pre-run total BEFORE storing events — used for quiet-start
        # migration so we seed based on what was ALREADY in the workspace,
        # not the post-run total (which would suppress new milestones earned
        # by this run). DEC-63-MIGRATION-001.
        pre_total = self.workspace_mgr.get_total_score()

        # Score using current workspace state
        stats = self.workspace_mgr.get_stix_type_counts()
        events = self.scoring.score_results(results, stats)
        total = self.scoring.total_score(events)
        if events:
            self.workspace_mgr.store_score_events(events)

        # Compute celebration artifact (DEC-AGENT-CELEBRATIONS-001, DEC-AGENT-MODES-001).
        # The ASCII art comes from CelebrationEngine. The points line uses the active
        # mode's score_celebration template (str.format(points=N)) so the character
        # voice matches the chosen persona — mirrors console.py _execute_hunt().
        # Silent path: no celebration when no points awarded.
        celebration: str | None = None
        if total > 0:
            art = self.celebration.celebrate(total)
            mode_points_line = self.mode_mgr.active.score_celebration.format(points=total)
            celebration = art + "\n" + mode_points_line
            # Milestone catch-up check (DEC-63-MILESTONE-CATCHUP-001).
            # Quiet-start migration: seed last_id from pre_total (score BEFORE this
            # run) so milestones earned by this run are not suppressed.
            # DEC-63-MIGRATION-001: on first access (last_id is None) with a
            # pre-existing score, initialise last_id to the highest already-crossed
            # milestone so retroactive announcements are suppressed.
            try:
                post_total = self.workspace_mgr.get_total_score()
                last_id = self.workspace_mgr.get_last_milestone_id()
                if last_id is None and pre_total > 0:
                    # Seed from pre_total (not post_total) — this run's points
                    # may push over a new milestone and must not be suppressed.
                    seeded_id = highest_crossed_milestone_id(pre_total)
                    if seeded_id is not None:
                        self.workspace_mgr.set_last_milestone_id(seeded_id)
                        last_id = seeded_id
                new_milestones = self.celebration.check_milestones(post_total, last_id)
                if new_milestones:
                    highest_new_id = max(ms.id for ms in new_milestones)
                    self.workspace_mgr.set_last_milestone_id(highest_new_id)
                    milestone_lines = "\n".join(ms.message for ms in new_milestones)
                    celebration = celebration + "\n\n" + milestone_lines
            except Exception:  # noqa: BLE001
                pass  # milestone check must never block tool result delivery

        # Check badges after scoring (DEC-AGENT-BADGES-001).
        # Mirrors cmd2 APConsole._check_badges_after_run() exactly:
        # build already_awarded, evaluate all badges, persist new ones.
        # Lazy-seed _awarded_badges from workspace on first call so sessions
        # resuming mid-investigation don't re-award previously earned badges.
        newly_earned_badges: list = []
        try:
            if not self._awarded_badges:
                # Seed from workspace: captures any badges earned by prior sessions
                awarded_rows = self.workspace_mgr.get_awarded_badges()
                self._awarded_badges = {row["badge_id"] for row in awarded_rows}
            badge_stats = self.workspace_mgr.get_workspace_stats()
            newly_earned_badges = self.badge_mgr.check_all(
                badge_stats, already_awarded=self._awarded_badges
            )
            for badge in newly_earned_badges:
                self.workspace_mgr.store_badge_event(badge.id, badge.name)
                self._awarded_badges.add(badge.id)
        except Exception:  # noqa: BLE001
            pass  # badge check must never block tool result delivery

        # Fire first_blood_message when badge-first-blood was earned this run
        # (F62-R0-002, DEC-62-CELEBRATIONS-001).
        # Console.py calls first_blood_message() unconditionally after _check_badges_after_run
        # (console.py:467-477) and prints it to the terminal. In the agent path there is no
        # Rich console to print to, so the message is appended to the celebration string for
        # chat.py to surface. We condition on newly_earned_badges containing badge-first-blood
        # rather than calling unconditionally — this preserves the invariant that celebration
        # is None when no indicators were found (existing tests rely on this contract).
        # The CelebrationEngine._first_blood_used guard also prevents double-fire.
        try:
            if newly_earned_badges and any(
                b.id == "badge-first-blood" for b in newly_earned_badges
            ):
                fb_msg = self.celebration.first_blood_message()
                if fb_msg is not None:
                    if celebration:
                        celebration = fb_msg + "\n\n" + celebration
                    else:
                        celebration = fb_msg
        except Exception:  # noqa: BLE001
            pass  # first_blood display must never block tool result delivery

        # Auto-pivot cascade (DEC-AGENT-AUTOPIVOT-001, DEC-60-PIVOT-POLICY-005).
        # When autopivot is enabled (or dry_run is True) and results are non-empty,
        # feed the STIX results into the event bus.  process_results() publishes a
        # PivotEvent for each (type, value) pair and routes through PivotPolicy gates
        # before invoking subscribed module callbacks.
        # In dry_run mode, policy gates fire but no callbacks are invoked — the
        # decision_log records each gate verdict.
        # Cascade errors are non-fatal — hunt flow must not be blocked.
        dry_run: bool = bool((options or {}).get("dry_run", False))
        cascade_results: list[dict] = []
        cascade_module_count: int = 0
        decision_log: list[dict] = []
        if (self.autopivot_enabled or dry_run) and results:
            try:
                cascade_results = asyncio.run(
                    self.event_bus.process_results(
                        results,
                        source_module=module_path,
                        depth=0,
                        dry_run=dry_run,
                    )
                )
                # In dry_run mode cascade_results is always [] — callbacks were
                # not invoked; surface the decision log instead.
                if dry_run:
                    decision_log = list(self.event_bus.get_decision_log())
                    cascade_results = []
                    cascade_module_count = 0
                else:
                    # Count how many distinct subscribed callbacks fired
                    cascade_module_count = self.event_bus.subscriber_count
            except Exception:  # noqa: BLE001
                pass  # cascade errors must never block primary tool result

        # Auto-check challenges after scoring and badges (DEC-AGENT-CHALLENGES-001).
        # Mirrors APConsole._check_challenges_after_run(): build workspace_data from
        # WorkspaceManager using the same dict contract as DEC-CHALLENGE-001, then
        # call check_all(). Only newly-completed challenges (status ACTIVE→COMPLETED
        # in this call) are returned. _announced_challenges deduplicates across
        # multiple run_module() calls so the same challenge never appears twice.
        newly_completed_challenges: list[Challenge] = []
        try:
            stix_counts = self.workspace_mgr.get_stix_type_counts()
            runs = self.workspace_mgr.get_module_runs()
            modules_used = [r["module_name"] for r in runs]
            total_score_now = self.workspace_mgr.get_total_score()
            total_indicators = sum(stix_counts.values())
            indicators = [
                {"type": obj.get("type", ""), "value": obj.get("value", "")}
                for obj in self.workspace_mgr.get_stix_objects()
            ]
            workspace_data = {
                "stix_type_counts": stix_counts,
                "modules_used": modules_used,
                "total_score": total_score_now,
                "total_indicators": total_indicators,
                "indicators": indicators,
            }
            all_newly_completed = self.challenge_mgr.check_all(workspace_data)
            for ch in all_newly_completed:
                if ch.id not in self._announced_challenges:
                    newly_completed_challenges.append(ch)
                    self._announced_challenges.add(ch.id)
        except Exception:  # noqa: BLE001
            pass  # challenge check must never block tool result delivery

        # Update streak after a successful hunt (DEC-62-STREAK-007).
        # Called here — after all badge/challenge checks — so failed hunts
        # (which return {"error": ...} before reaching this point) never advance
        # the streak. run_module only reaches this point when hunt() succeeded.
        # F63: consume StreakUpdate.incremented to emit streak_continued score event
        # (DEC-63-STREAK-SCORE-001). Step-decay points prevent farming.
        try:
            from datetime import date

            streak_update = self.streak_mgr.update(date.today())
            if streak_update.incremented:
                streak_event = make_streak_continued_event(streak_update.current_streak)
                try:
                    self.workspace_mgr.store_score_events([streak_event])
                    # Append to events list so it appears in LLM summary
                    events = list(events) + [streak_event]
                    total += streak_event["points"]
                except Exception:  # noqa: BLE001
                    pass  # streak score storage must never block tool result delivery
        except Exception:  # noqa: BLE001
            pass  # streak errors must never block tool result delivery

        # Build human-readable summary for the LLM response
        summary_lines = [f"Found {count} indicators:"]
        for r in results[:10]:
            summary_lines.append(f"  {r.get('type', '?')}: {r.get('value', '?')}")
        if len(results) > 10:
            summary_lines.append(f"  ... and {len(results) - 10} more")
        if total > 0:
            summary_lines.append(f"\n+{total} points!")
            for e in events:
                summary_lines.append(f"  {e['action']}: +{e['points']} ({e['indicator']})")
        # NOTE: badge and challenge award text is intentionally NOT added to summary_lines.
        # @decision DEC-64-LLM-PANEL-SEPARATION-001
        # @title Strip gamification text from LLM-facing summary; surface via sidecar typed fields
        # @status accepted
        # @rationale The LLM receives summary as a tool result and narrates it to the user.
        #            Badge/challenge award text in summary caused double-narration: the LLM would
        #            announce the award *and* chat.py Rich Panels would show it again. F64 removes
        #            badge/challenge lines from summary. The sidecar fields (result["badges"],
        #            result["challenges"], result["celebration"]) are the sole source of truth for
        #            gamification display in chat.py. The LLM narrates discovery findings only.
        # Surface cascade discoveries so the LLM and user see what fired secondarily.
        if cascade_results:
            summary_lines.append(
                f"\nAuto-pivoted: {len(cascade_results)} additional discoveries "
                f"from {cascade_module_count} cascaded module subscriptions."
            )

        return {
            "results": results,
            "score_events": events,
            "total_points": total,
            "summary": "\n".join(summary_lines),
            "celebration": celebration,
            "badges": newly_earned_badges,
            "challenges": newly_completed_challenges,
            "cascade_results": cascade_results,
            "cascade_count": len(cascade_results),
            "decision_log": decision_log,
        }

    def _make_cascade_callback(self, module_path: str):
        """Return an async callback that runs module_path.hunt() for a pivot event.

        The returned coroutine is registered with EventBus.subscribe() so that when
        a PivotEvent fires for a matching STIX type, the module is initialised and
        its hunt() is called against the event's indicator value.

        The callback is a closure over module_path and self so it captures the
        ToolContext's plugin_mgr and config_mgr without holding stale references.
        Module initialisation re-reads credentials fresh on each cascade call.

        Parameters
        ----------
        module_path:
            Canonical path of the module to run on cascade, e.g. "osint/abuseipdb".

        Returns
        -------
        Callable[[PivotEvent], Coroutine[Any, Any, list[dict]]]
            Async callback suitable for EventBus.subscribe().
        """
        from adversary_pursuit.core.event_bus import (
            PivotEvent,
        )  # local import avoids circularity

        async def _callback(event: PivotEvent) -> list[dict]:
            mod = self.plugin_mgr.get_module(module_path)
            if mod is None:
                return []
            # Build credentials via the shared resolver — identical to run_module().
            # (DEC-AGENT-SERVICE-NAME-MAP-001, DEC-AGENT-TOOLS-003)
            init_config = _resolve_module_credentials(module_path, self.config_mgr)
            mod.initialize(init_config)
            try:
                return await mod.hunt(event.value, {})
            except Exception:  # noqa: BLE001
                return []

        return _callback

    def set_autopivot(self, enabled: bool) -> None:
        """Toggle EventBus auto-pivot and keep PivotConfig.enabled in sync.

        Parameters
        ----------
        enabled:
            True to enable auto-pivot cascades, False to disable.
        """
        self.autopivot_enabled = enabled
        self.event_bus.config.enabled = enabled


def create_tools(ctx: ToolContext) -> list[dict]:
    """Create tool definitions for the agent.

    Returns a list of tool dicts in OpenAI function-calling format:
    [{"type": "function", "function": {"name": ..., "description": ..., "parameters": ...}}]

    The ctx parameter is accepted for interface consistency (future tools may
    need dynamic schema generation based on loaded modules).

    Parameters
    ----------
    ctx:
        The shared ToolContext (used for future dynamic tool generation).

    Returns
    -------
    list[dict]
        12 tool definitions covering all built-in AP modules plus workspace ops.
        7 OSINT/CTI modules + VT + Censys + PassiveTotal + 2 workspace tools.
    """
    return [
        {
            "type": "function",
            "function": {
                "name": "dns_resolve",
                "description": (
                    "Resolve DNS records for a domain. Returns IP addresses and domain information."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "domain": {
                            "type": "string",
                            "description": "Domain name to resolve",
                        },
                        "record_type": {
                            "type": "string",
                            "description": "DNS record type (A, AAAA, MX, NS, TXT)",
                            "default": "A",
                        },
                    },
                    "required": ["domain"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "whois_lookup",
                "description": (
                    "WHOIS lookup for domain or IP. "
                    "Returns registration details, registrant info, creation/expiry dates."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "target": {
                            "type": "string",
                            "description": "Domain or IP to look up",
                        },
                    },
                    "required": ["target"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "check_ip_reputation",
                "description": (
                    "Check IP address reputation via AbuseIPDB. "
                    "Returns abuse confidence score, ISP, usage type, report count."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "ip_address": {
                            "type": "string",
                            "description": "IP address to check",
                        },
                        "max_age_days": {
                            "type": "integer",
                            "description": "Max age of reports in days (1-365)",
                            "default": 90,
                        },
                    },
                    "required": ["ip_address"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "shodan_host_lookup",
                "description": (
                    "Query Shodan for IP host information including open ports, "
                    "services, OS, vulnerabilities (CVEs), and hostnames."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "ip_address": {
                            "type": "string",
                            "description": "IP address to query",
                        },
                        "minify": {
                            "type": "boolean",
                            "description": "Return only basic info",
                            "default": False,
                        },
                    },
                    "required": ["ip_address"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "check_breaches",
                "description": (
                    "Check email address against HaveIBeenPwned breach database. "
                    "Returns breach names, dates, and exposed data types."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "email": {
                            "type": "string",
                            "description": "Email address to check",
                        },
                    },
                    "required": ["email"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "otx_threat_intel",
                "description": (
                    "Query AlienVault OTX for threat intelligence on an IP or domain. "
                    "Returns pulse data, reputation, and passive DNS."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "target": {
                            "type": "string",
                            "description": "IP address or domain to query",
                        },
                        "include_passive_dns": {
                            "type": "boolean",
                            "description": "Include passive DNS results",
                            "default": True,
                        },
                    },
                    "required": ["target"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "scan_url",
                "description": (
                    "Submit a URL to URLScan.io for analysis. "
                    "Returns page details, contacted IPs/domains, and screenshot URL."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "URL to scan",
                        },
                        "visibility": {
                            "type": "string",
                            "description": "Scan visibility: public, unlisted, private",
                            "default": "unlisted",
                        },
                    },
                    "required": ["url"],
                },
            },
        },
        # -----------------------------------------------------------------------
        # Three new tools added in Issue #25 / ADR-010 parity slice:
        # VirusTotal (#7), Censys (#8), PassiveTotal (#13)
        # -----------------------------------------------------------------------
        {
            "type": "function",
            "function": {
                "name": "virustotal_lookup",
                "description": (
                    "Query VirusTotal v3 for threat analysis of an IP, domain, URL, or "
                    "file hash. Returns malicious/suspicious/harmless vendor counts, "
                    "reputation score, and AS/country for IPs and domains. "
                    "Target type is auto-detected from the input."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "target": {
                            "type": "string",
                            "description": (
                                "IP address, domain, URL, or file hash (MD5/SHA-1/SHA-256)"
                            ),
                        },
                        "target_type": {
                            "type": "string",
                            "description": (
                                "Override auto-detection: ip, domain, url, or hash. "
                                "Leave empty for auto-detection."
                            ),
                            "default": "",
                        },
                    },
                    "required": ["target"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "censys_host_lookup",
                "description": (
                    "Query Censys for host intelligence on an IP address. "
                    "Returns open services (port/protocol/service_name), OS fingerprint, "
                    "geolocation country, autonomous system, TLS certificate fingerprints, "
                    "and last-updated timestamp."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "ip_address": {
                            "type": "string",
                            "description": "IPv4 address to query",
                        },
                    },
                    "required": ["ip_address"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "passivetotal_lookup",
                "description": (
                    "Query PassiveTotal/RiskIQ for passive DNS records and WHOIS history "
                    "on a domain or IP. Returns first/last seen, total DNS record count, "
                    "related resolved IPs/domains, and optional WHOIS registrant details."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "target": {
                            "type": "string",
                            "description": "Domain or IP address to query",
                        },
                        "include_whois": {
                            "type": "boolean",
                            "description": "Include WHOIS history (default: true)",
                            "default": True,
                        },
                    },
                    "required": ["target"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "greynoise_lookup",
                "description": (
                    "Query GreyNoise Community API for IP address classification. "
                    "Identifies whether an IP is a known internet scanner (noise=True), "
                    "a benign service like Google DNS (riot=True), or unknown. "
                    "Returns classification (benign/malicious/unknown), noise status, "
                    "RIOT status, and scanner/service name when available."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "ip_address": {
                            "type": "string",
                            "description": "IPv4 address to classify",
                        },
                    },
                    "required": ["ip_address"],
                },
            },
        },
        # F61 keyless hunter tools — DEC-61-SCOPING-001
        {
            "type": "function",
            "function": {
                "name": "urlhaus_lookup",
                "description": (
                    "Check a URL or host (IP/domain) against the abuse.ch URLhaus malicious "
                    "URL blocklist. No API key required. Returns url SCO records with threat "
                    "type, tags, reporter, and date-added for each known malicious URL "
                    "associated with the target. Returns empty list when the target is clean."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "target": {
                            "type": "string",
                            "description": (
                                "Full URL (https://...) or host value (IPv4 address or "
                                "domain name) to check against URLhaus"
                            ),
                        },
                    },
                    "required": ["target"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "threatfox_lookup",
                "description": (
                    "Search the abuse.ch ThreatFox IOC platform for threat intelligence on "
                    "IPs, domains, URLs, and file hashes. No API key required. Returns typed "
                    "STIX SCOs (ipv4-addr, url, domain-name, or file) with malware family, "
                    "confidence score, first/last seen, and reporter metadata."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "target": {
                            "type": "string",
                            "description": (
                                "IOC value to search: IPv4 address, domain name, URL, "
                                "MD5 hash, or SHA-256 hash"
                            ),
                        },
                    },
                    "required": ["target"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "malwarebazaar_lookup",
                "description": (
                    "Query the abuse.ch MalwareBazaar repository for malware sample metadata "
                    "by hash. No API key required. Accepts MD5, SHA1, or SHA256 hashes. "
                    "Returns a file SCO with all three hash values, malware signature/family, "
                    "first-seen timestamp, and file type."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "hash_value": {
                            "type": "string",
                            "description": "MD5, SHA1, or SHA256 hash of the sample to look up",
                        },
                    },
                    "required": ["hash_value"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "crtsh_lookup",
                "description": (
                    "Search Certificate Transparency logs via crt.sh for subdomains and "
                    "SSL/TLS certificates associated with a domain. No API key required. "
                    "Returns domain-name SCOs for each unique SAN/subdomain discovered in "
                    "public CT logs, with issuer CA ID, certificate expiry, and entry timestamp."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "domain": {
                            "type": "string",
                            "description": (
                                "Domain name to search CT logs for (e.g. 'example.com'). "
                                "Subdomains are included automatically."
                            ),
                        },
                    },
                    "required": ["domain"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_workspace_summary",
                "description": (
                    "Get a summary of the current workspace — total indicators, "
                    "types, module runs, score, and recent activity."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_workspace",
                "description": ("Search the current workspace for STIX objects by type or value."),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "type_filter": {
                            "type": "string",
                            "description": (
                                "STIX type to filter by (ipv4-addr, domain-name, url, email-addr)"
                            ),
                        },
                    },
                },
            },
        },
        # -----------------------------------------------------------------------
        # Hint tools — DEC-AGENT-HINTS-001
        # get_next_hint: reveals the next free hint (cost=0) for optional module.
        # buy_hint: reveals the next paid hint, deducting its cost from score.
        # Both share the same HintProvider instance on ToolContext so the
        # revealed-ID set is consistent across all paths (DEC-HINT-002).
        # -----------------------------------------------------------------------
        {
            "type": "function",
            "function": {
                "name": "get_next_hint",
                "description": (
                    "Get the next free contextual hint for the current investigation. "
                    "Free hints (cost=0) are always available without score penalty. "
                    "Optionally filter to a specific module (e.g. 'dns_resolve', "
                    "'abuseipdb'). Returns None when all free hints have been revealed."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "module": {
                            "type": "string",
                            "description": (
                                "Module base name to get module-specific hints "
                                "(e.g. 'dns_resolve', 'abuseipdb'). "
                                "Omit for general hints only."
                            ),
                        },
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "buy_hint",
                "description": (
                    "Buy the next paid hint for the current investigation. "
                    "Paid hints cost 10-20 score points (deducted automatically). "
                    "Returns an error if the analyst cannot afford the next hint. "
                    "Optionally filter to a specific module."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "module": {
                            "type": "string",
                            "description": (
                                "Module base name to get module-specific paid hints "
                                "(e.g. 'dns_resolve', 'abuseipdb'). "
                                "Omit for general paid hints."
                            ),
                        },
                    },
                },
            },
        },
        # -----------------------------------------------------------------------
        # Challenge tools — DEC-AGENT-CHALLENGES-001
        # list_challenges: returns all challenges with current status as dicts.
        # check_challenges: runs check_all against current workspace state and
        # returns newly-completed challenges. Both share the same ChallengeManager
        # instance on ToolContext so completion state is consistent.
        # -----------------------------------------------------------------------
        {
            "type": "function",
            "function": {
                "name": "list_challenges",
                "description": (
                    "List all available challenges with their current status. "
                    "Returns each challenge's id, name, description, type, points, "
                    "and status (active/completed/expired). Call this at session start "
                    "to announce what challenges the analyst can pursue."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "check_challenges",
                "description": (
                    "Check whether any active challenges have been completed based on "
                    "the current workspace state. Returns a list of newly-completed "
                    "challenges with their name and bonus points. Returns an empty list "
                    "when no new challenges were completed."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        },
        # -----------------------------------------------------------------------
        # Graph/export tools — DEC-AGENT-GRAPH-EXPORT-001
        # render_graph: builds RelationshipGraph from workspace, returns render_text().
        # export_workspace: exports workspace as GEXF XML or STIX bundle JSON.
        # Both mirror cmd2 do_graph / do_export semantics.
        # -----------------------------------------------------------------------
        {
            "type": "function",
            "function": {
                "name": "render_graph",
                "description": (
                    "Render the current workspace as a plain-text relationship graph. "
                    "Shows STIX objects as nodes and their relationships as edges in a "
                    "tree layout. Useful for inspecting the structure of discovered "
                    "indicators and understanding how they relate to each other. "
                    "Returns an empty-graph message when no objects are in the workspace."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "export_workspace",
                "description": (
                    "Export the current workspace as GEXF XML (for Gephi visualization) "
                    "or as a STIX 2.1 bundle JSON string. "
                    "Use format='gexf' to get GEXF 1.2 XML importable into Gephi. "
                    "Use format='stix' (default) to get a STIX 2.1 bundle dict as JSON."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "format": {
                            "type": "string",
                            "description": (
                                "Export format: 'gexf' for GEXF 1.2 XML (Gephi), "
                                "'stix' for STIX 2.1 bundle JSON. Default: 'stix'."
                            ),
                            "default": "stix",
                        },
                    },
                    "required": ["format"],
                },
            },
        },
        # -----------------------------------------------------------------------
        # Report interview tools — DEC-AGENT-REPORT-001
        # start_report_interview: initialises/resets ReportGenerator, returns all questions.
        # answer_report_question: records one answer by index (0-4).
        # generate_report: produces final Markdown report from workspace + answers.
        # All three share the same ReportGenerator instance on ToolContext so that
        # answers set via the LLM tool path are visible to the chat meta-command
        # path and vice versa. Mirrors cmd2 do_report interview semantics.
        # -----------------------------------------------------------------------
        {
            "type": "function",
            "function": {
                "name": "start_report_interview",
                "description": (
                    "Start (or restart) the investigation report interview. "
                    "Returns all 5 interview questions so you can present them to the "
                    "analyst one by one. Call answer_report_question to record each answer, "
                    "then call generate_report to produce the final Markdown report. "
                    "Re-calling this resets all previous answers."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "answer_report_question",
                "description": (
                    "Record the analyst's answer for one interview question. "
                    "question_index is 0-4 (matching the order returned by "
                    "start_report_interview). Call start_report_interview first if the "
                    "interview has not been started yet. Returns confirmation with the "
                    "question text. After all 5 answers are set, call generate_report."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "question_index": {
                            "type": "integer",
                            "description": "Question index 0-4 to answer.",
                        },
                        "answer": {
                            "type": "string",
                            "description": "The analyst's answer text.",
                        },
                    },
                    "required": ["question_index", "answer"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "generate_report",
                "description": (
                    "Generate the final investigation report as Markdown. "
                    "Combines workspace STIX objects, module run history, score, and "
                    "the interview answers set via answer_report_question. "
                    "Returns the complete Markdown report as a string. "
                    "Call start_report_interview and answer_report_question first to "
                    "capture analyst context before generating."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        },
    ]


# ---------------------------------------------------------------------------
# Service-name map for single-key modules (DEC-AGENT-SERVICE-NAME-MAP-001)
# ---------------------------------------------------------------------------

# @decision DEC-AGENT-SERVICE-NAME-MAP-001
# @title _SERVICE_NAMES map fixes module_path-tail ≠ ConfigManager service-name mismatch
# @status accepted
# @rationale The legacy path in run_module() derived the service name from the
#   module path tail: "osint/shodan_ip" → "shodan_ip". But ConfigManager.get_api_key()
#   expects "shodan" (the field name in ApiKeysConfig), so Shodan keys were never
#   resolved from config or env vars via the 3-layer chain. The fix is an explicit
#   map from module_path to canonical service name. None signals that the module
#   needs no API key (dns_resolve, whois_lookup). Modules absent from the map fall
#   back to the path tail for forward-compat with future plugins. Multi-key modules
#   (Censys, PassiveTotal) stay in _CREDENTIAL_BUILDERS and are never looked up here.
_SERVICE_NAMES: dict[str, str | None] = {
    "osint/shodan_ip": "shodan",
    "osint/abuseipdb": "abuseipdb",
    "osint/urlscan": "urlscan",
    "osint/hibp": "hibp",
    "cti/virustotal": "virustotal",
    "cti/otx": "otx",
    "osint/greynoise": "greynoise",
    "osint/dns_resolve": None,  # no key needed
    "osint/whois_lookup": None,  # no key needed
    # F61 keyless modules — no API key needed (DEC-61-SCOPING-001)
    "cti/urlhaus": None,
    "cti/threatfox": None,
    "cti/malwarebazaar": None,
    "osint/crtsh": None,
}

# ---------------------------------------------------------------------------
# Credential builders for multi-key auth modules (DEC-AGENT-TOOLS-003)
# ---------------------------------------------------------------------------

# Maps module_path -> callable(ConfigManager) -> init_config dict.
# Only modules that require credentials beyond a single "api_key" field
# are listed here. run_module() falls back to {"api_key": ...} for all others.
_CREDENTIAL_BUILDERS: dict[str, Any] = {
    "osint/censys_host": lambda cfg: {
        "censys_pat": cfg.get_censys_pat() or "",
    },
    "cti/passivetotal": lambda cfg: {
        "passivetotal_user": cfg.get_api_key("passivetotal_user") or "",
        "passivetotal_key": cfg.get_api_key("passivetotal_key") or "",
    },
}


def _resolve_module_credentials(module_path: str, config_mgr: Any) -> dict:
    """Return the init_config dict for *module_path* using the canonical precedence.

    This is the single authority for credential resolution used by both
    run_module() and _make_cascade_callback() (DEC-AGENT-SERVICE-NAME-MAP-001,
    DEC-AGENT-TOOLS-003).  Factoring the logic here prevents the two paths
    from diverging again.

    Precedence:
    1. _CREDENTIAL_BUILDERS: multi-key modules (Censys, PassiveTotal).
    2. _SERVICE_NAMES: maps module_path → canonical service name for get_api_key().
       None means no API key needed (e.g. dns_resolve, whois_lookup).
    3. Fallback: path tail used as service name (forward-compat with future plugins).

    Parameters
    ----------
    module_path:
        Canonical module path (e.g. "osint/shodan_ip", "cti/virustotal").
    config_mgr:
        ConfigManager instance to resolve keys from.

    Returns
    -------
    dict
        init_config dict ready for PursuitModule.initialize().  Empty dict
        for key-free modules; {"api_key": ...} for standard single-key modules;
        multi-field dict for Censys/PassiveTotal.
    """
    credential_builder = _CREDENTIAL_BUILDERS.get(module_path)
    if credential_builder is not None:
        return credential_builder(config_mgr)

    # Resolve canonical service name; fall back to path tail for unknown modules.
    service_name = _SERVICE_NAMES.get(module_path, module_path.split("/")[-1])
    if service_name is None:
        # No key needed (e.g. dns_resolve, whois_lookup)
        return {}

    api_key = config_mgr.get_api_key(service_name) or ""
    return {"api_key": api_key}


# ---------------------------------------------------------------------------
# Module → tool name mapping
# ---------------------------------------------------------------------------

# Maps tool name -> (module_path, arg_extractor)
# arg_extractor is a callable that takes the arguments dict and returns
# (target: str, options: dict) for run_module().
_MODULE_MAP: dict[str, tuple[str, Any]] = {
    "dns_resolve": (
        "osint/dns_resolve",
        lambda a: (a["domain"], {"RECORD_TYPE": a.get("record_type", "A")}),
    ),
    "whois_lookup": (
        "osint/whois_lookup",
        lambda a: (a["target"], {}),
    ),
    "check_ip_reputation": (
        "osint/abuseipdb",
        lambda a: (a["ip_address"], {"MAX_AGE": str(a.get("max_age_days", 90))}),
    ),
    "shodan_host_lookup": (
        "osint/shodan_ip",
        lambda a: (a["ip_address"], {"MINIFY": str(a.get("minify", False)).lower()}),
    ),
    "check_breaches": (
        "osint/hibp",
        lambda a: (a["email"], {}),
    ),
    "otx_threat_intel": (
        "cti/otx",
        lambda a: (
            a["target"],
            {"INCLUDE_PASSIVE_DNS": str(a.get("include_passive_dns", True)).lower()},
        ),
    ),
    "scan_url": (
        "osint/urlscan",
        lambda a: (a["url"], {"VISIBILITY": a.get("visibility", "unlisted")}),
    ),
    # New entries — VT/Censys/PassiveTotal parity with cmd2 console
    "virustotal_lookup": (
        "cti/virustotal",
        lambda a: (a["target"], {"TARGET_TYPE": a.get("target_type", "")}),
    ),
    "censys_host_lookup": (
        "osint/censys_host",
        lambda a: (a["ip_address"], {}),
    ),
    "passivetotal_lookup": (
        "cti/passivetotal",
        lambda a: (
            a["target"],
            {"INCLUDE_WHOIS": str(a.get("include_whois", True)).lower()},
        ),
    ),
    "greynoise_lookup": (
        "osint/greynoise",
        lambda a: (a["ip_address"], {}),
    ),
    # F61 keyless hunters (DEC-61-SCOPING-001)
    "urlhaus_lookup": (
        "cti/urlhaus",
        lambda a: (a["target"], {}),
    ),
    "threatfox_lookup": (
        "cti/threatfox",
        lambda a: (a["target"], {}),
    ),
    "malwarebazaar_lookup": (
        "cti/malwarebazaar",
        lambda a: (a["hash_value"], {}),
    ),
    "crtsh_lookup": (
        "osint/crtsh",
        lambda a: (a["domain"], {}),
    ),
}


def _strip_rich_markup(text: str) -> str:
    """Remove Rich markup tags from a string (e.g. ``[bold red]...[/bold red]``).

    Used to sanitise mode.run_fail before embedding in plain-text error returns
    or in Rich markup contexts where inner tags would nest incorrectly.

    @decision DEC-62-KILL-DOC-LIES-002
    @title Rich-strip helper for mode.run_fail in agent error paths
    @status accepted
    @rationale mode.run_fail strings may contain Rich markup (e.g. ``[bold red]``
               for full_troll mode). When prepended to agent error strings — or
               when embedded inside a ``[bold yellow]`` panel title — the nested
               markup produces incorrect rendering. Stripping with a simple regex
               is the correct, self-contained solution: no Rich import required,
               no external dependency, trivially testable.
    """
    return re.sub(r"\[/?[^\]]+\]", "", text)


def execute_tool(
    ctx: ToolContext, tool_name: str, arguments: dict
) -> tuple[str, str | None, list, list]:
    """Execute a tool call and return (summary, celebration, badges, challenges).

    This is the dispatcher that maps LLM tool call names to module invocations.
    The summary string is suitable for inclusion in the LLM conversation as a
    "tool" role message. The celebration string is ASCII art for the user
    terminal (None when no points were awarded — silent path). The badges list
    contains newly-earned Badge objects for Rich panel rendering in chat.py
    ([] when no new badges earned — silent path). The challenges list contains
    newly-completed Challenge objects for Rich panel rendering in chat.py
    ([] when no challenges completed — silent path).

    Workspace meta-tools (get_workspace_summary, search_workspace) always
    return celebration=None, badges=[], challenges=[] because they do not
    trigger scoring or badge/challenge evaluation.

    @decision DEC-AGENT-BADGES-001
    (see run_module docstring for full rationale)
    Four-tuple return chosen over a unified user_messages list because
    celebration (plain string), badges (Badge objects with rarity metadata for
    styled panels), and challenges (Challenge objects) all have different
    rendering logic at the chat.py boundary. Keeping them as separate typed
    values preserves testability and avoids conflating distinct display
    artifacts into an untyped list.

    @decision DEC-64-LLM-PANEL-SEPARATION-001
    @title Strip gamification text from LLM-facing summary; surface via sidecar typed fields
    @status accepted
    @rationale The LLM receives summary as a tool result and narrates it to the user.
               Badge/challenge award text in summary caused double-narration: the LLM would
               announce the award *and* chat.py Rich Panels would show it again. F64 removes
               badge/challenge lines from summary. challenges is now the fourth element of the
               return tuple so chat.py can render challenge panels independently of the LLM.

    Parameters
    ----------
    ctx:
        The shared ToolContext providing workspace, modules, and scoring.
    tool_name:
        Name of the tool to execute (matches names in create_tools()).
    arguments:
        Dict of arguments from the LLM tool call.

    Returns
    -------
    tuple[str, str | None, list, list]
        (summary, celebration, badges, challenges) where summary is the
        LLM-facing result string (findings only — no badge/challenge text),
        celebration is the ASCII art to display to the user or None, badges is
        a list of newly-earned Badge objects ([] when none), and challenges is
        a list of newly-completed Challenge objects ([] when none).
        Returns (error_string, None, [], []) when the tool fails — errors are
        reported to the LLM as tool results.
    """
    # Workspace meta-tools — no scoring, no celebration, no badge/challenge check
    if tool_name == "get_workspace_summary":
        return _workspace_summary(ctx), None, [], []

    if tool_name == "search_workspace":
        return _search_workspace(ctx, arguments.get("type_filter")), None, [], []

    # Hint tools — free and paid, no scoring/celebration/badge side-effects
    # (DEC-AGENT-HINTS-001: hints are dispatched here to keep execute_tool as
    # the single dispatch point for all LLM-callable tools)
    if tool_name == "get_next_hint":
        return _execute_get_next_hint(ctx, arguments.get("module")), None, [], []

    if tool_name == "buy_hint":
        return _execute_buy_hint(ctx, arguments.get("module")), None, [], []

    # Challenge tools — DEC-AGENT-CHALLENGES-001
    if tool_name == "list_challenges":
        return _execute_list_challenges(ctx), None, [], []

    if tool_name == "check_challenges":
        return _execute_check_challenges(ctx), None, [], []

    # Graph/export tools — DEC-AGENT-GRAPH-EXPORT-001
    if tool_name == "render_graph":
        return _execute_render_graph(ctx), None, [], []

    if tool_name == "export_workspace":
        return _execute_export_workspace(ctx, arguments.get("format", "stix")), None, [], []

    # Report interview tools — DEC-AGENT-REPORT-001
    if tool_name == "start_report_interview":
        return _execute_start_report_interview(ctx), None, [], []

    if tool_name == "answer_report_question":
        return (
            _execute_answer_report_question(
                ctx,
                arguments.get("question_index"),
                arguments.get("answer", ""),
            ),
            None,
            [],
            [],
        )

    if tool_name == "generate_report":
        return _execute_generate_report(ctx), None, [], []

    # Module dispatch
    if tool_name not in _MODULE_MAP:
        return f"Unknown tool: {tool_name}", None, [], []

    module_path, arg_mapper = _MODULE_MAP[tool_name]
    try:
        target, options = arg_mapper(arguments)
        result = ctx.run_module(module_path, target, options)
        if "error" in result:
            return f"Error: {result['error']}", None, [], []
        return (
            result["summary"],
            result.get("celebration"),
            result.get("badges", []),
            result.get("challenges", []),
        )
    except Exception as e:
        logger.exception("Tool execution failed: %s", tool_name)
        # Wire run_fail: mode-flavored failure voice in agent exception path
        # (F62-R0-001, DEC-62-KILL-DOC-LIES-001). Rich markup is stripped so
        # the plain-text error string returned to the LLM contains no markup
        # tags. Mirrors console.py _execute_hunt exception paths which print
        # mode_mgr.active.run_fail to the Rich console.
        run_fail_plain = _strip_rich_markup(ctx.mode_mgr.active.run_fail)
        return f"{run_fail_plain} Error running {tool_name}: {e}", None, [], []


def _workspace_summary(ctx: ToolContext) -> str:
    """Generate a workspace summary string for the LLM.

    Returns a multi-line string with workspace name, indicator count,
    score, module runs, and per-type breakdown.
    """
    try:
        objects = ctx.workspace_mgr.get_stix_objects()
        runs = ctx.workspace_mgr.get_module_runs()
        score = ctx.workspace_mgr.get_total_score()
        counts = ctx.workspace_mgr.get_stix_type_counts()

        lines = [
            f"Workspace: {ctx.workspace_mgr.active}",
            f"Total indicators: {len(objects)}",
            f"Total score: {score}",
            f"Module runs: {len(runs)}",
        ]
        if counts:
            lines.append("By type:")
            for t, c in sorted(counts.items()):
                lines.append(f"  {t}: {c}")
        return "\n".join(lines)
    except Exception as e:
        logger.exception("Failed to get workspace summary")
        return f"Error getting workspace summary: {e}"


def _search_workspace(ctx: ToolContext, type_filter: str | None = None) -> str:
    """Search workspace STIX objects and return a formatted string.

    Parameters
    ----------
    ctx:
        The shared ToolContext.
    type_filter:
        Optional STIX type to filter by (e.g. "ipv4-addr").

    Returns
    -------
    str
        Formatted list of matching objects, or a 'no results' message.
    """
    try:
        objects = ctx.workspace_mgr.get_stix_objects(type_filter=type_filter)
        if not objects:
            label = type_filter or "objects"
            return f"No {label} found in workspace."
        lines = [f"Found {len(objects)} {type_filter or 'objects'}:"]
        for obj in objects[:20]:
            lines.append(f"  {obj.get('type', '?')}: {obj.get('value', '?')}")
        if len(objects) > 20:
            lines.append(f"  ... and {len(objects) - 20} more")
        return "\n".join(lines)
    except Exception as e:
        logger.exception("Failed to search workspace")
        return f"Error searching workspace: {e}"


def _execute_get_next_hint(ctx: ToolContext, module: str | None = None) -> str:
    """Return the next free hint as a string for the LLM.

    Free hints (cost=0) are revealed in cost-ascending order (DEC-HINT-003).
    The HintProvider instance on ToolContext is shared with the chat
    meta-command path so the revealed-ID set is consistent (DEC-AGENT-HINTS-001).

    Parameters
    ----------
    ctx:
        The shared ToolContext holding the session-scoped HintProvider.
    module:
        Module base name to include module-specific hints (e.g. "dns_resolve").
        Pass None for general hints only.

    Returns
    -------
    str
        Hint text, or a "no more hints" message when all free hints are revealed.
    """
    result: HintResult | None = ctx.hint_mgr.get_next_hint(module=module)
    if result is None:
        ctx_label = f" for module '{module}'" if module else ""
        return f"No more free hints available{ctx_label}. Use buy_hint to unlock paid hints."
    return f"Hint: {result.hint.text}"


def _execute_buy_hint(ctx: ToolContext, module: str | None = None) -> str:
    """Reveal the next paid hint and deduct its cost from the workspace score.

    Reads current_score from the workspace, calls HintProvider.buy_hint(), and
    on success stores a negative score event so the deduction persists (DEC-HINT-001).
    On InsufficientBalanceError returns a user-friendly error string — score is
    never modified when the analyst cannot afford the hint (balance protection,
    DEC-AGENT-HINTS-001).

    Parameters
    ----------
    ctx:
        The shared ToolContext holding the session-scoped HintProvider and
        WorkspaceManager for score reads and deduction writes.
    module:
        Module base name to include module-specific paid hints.
        Pass None for general paid hints.

    Returns
    -------
    str
        Hint text with cost note, an insufficient-balance error, or a
        "no more paid hints" message.
    """
    try:
        current_score = ctx.workspace_mgr.get_total_score()
    except Exception as e:
        logger.exception("Failed to read score before buy_hint")
        return f"Error reading score: {e}"

    try:
        result: HintResult | None = ctx.hint_mgr.buy_hint(
            current_score=current_score, module=module
        )
    except InsufficientBalanceError as exc:
        return (
            f"Insufficient score to buy a hint: need {exc.required} pts "
            f"but have {exc.available} pts. Earn more points by running modules."
        )
    except Exception as e:
        logger.exception("buy_hint failed unexpectedly")
        return f"Error buying hint: {e}"

    if result is None:
        ctx_label = f" for module '{module}'" if module else ""
        return f"No more paid hints available{ctx_label}."

    # Deduct the cost from the workspace score (DEC-HINT-001: caller owns deduction).
    try:
        ctx.workspace_mgr.store_score_events(
            [
                {
                    "action": "hint",
                    "points": -result.cost_paid,
                    "indicator": module or "general",
                    "rule_description": f"Paid hint: {result.hint.id}",
                }
            ]
        )
    except Exception as e:
        logger.exception("Failed to store hint score deduction")
        # Hint was already revealed — report it but warn about deduction failure
        return (
            f"Hint: {result.hint.text}\n"
            f"(Warning: score deduction of {result.cost_paid} pts could not be saved: {e})"
        )

    return f"Hint (-{result.cost_paid} pts): {result.hint.text}"


def _execute_list_challenges(ctx: ToolContext) -> str:
    """Return all challenges as a formatted string for the LLM.

    Calls ChallengeManager.list_challenges() which returns serializable dicts.
    The result is formatted as a human-readable summary suitable for the LLM
    to read and relay to the analyst (DEC-AGENT-CHALLENGES-001).

    Parameters
    ----------
    ctx:
        The shared ToolContext holding the session-scoped ChallengeManager.

    Returns
    -------
    str
        Formatted challenge list, or a message when no challenges exist.
    """
    items = ctx.challenge_mgr.list_challenges()
    if not items:
        return "No challenges available."
    lines = [f"Challenges ({len(items)} total):"]
    for item in items:
        status = item["status"]
        pts = item["points"]
        lines.append(
            f"  [{status.upper()}] {item['id']}: {item['name']} "
            f"(+{pts} pts) — {item['description']}"
        )
    return "\n".join(lines)


def _execute_check_challenges(ctx: ToolContext) -> str:
    """Run challenge auto-check against workspace and return newly-completed.

    Assembles workspace_data from WorkspaceManager using the DEC-CHALLENGE-001
    dict contract (same keys as APConsole._build_workspace_data), then calls
    ChallengeManager.check_all(). Returns a formatted summary of newly-completed
    challenges, or a message when none completed. Uses _announced_challenges set
    on ToolContext to deduplicate across multiple calls (DEC-AGENT-CHALLENGES-001).

    Parameters
    ----------
    ctx:
        The shared ToolContext holding ChallengeManager and WorkspaceManager.

    Returns
    -------
    str
        Formatted newly-completed challenge list, or a "none completed" message.
    """
    try:
        stix_counts = ctx.workspace_mgr.get_stix_type_counts()
        runs = ctx.workspace_mgr.get_module_runs()
        modules_used = [r["module_name"] for r in runs]
        total_score = ctx.workspace_mgr.get_total_score()
        total_indicators = sum(stix_counts.values())
        indicators = [
            {"type": obj.get("type", ""), "value": obj.get("value", "")}
            for obj in ctx.workspace_mgr.get_stix_objects()
        ]
        workspace_data = {
            "stix_type_counts": stix_counts,
            "modules_used": modules_used,
            "total_score": total_score,
            "total_indicators": total_indicators,
            "indicators": indicators,
        }
    except Exception as e:
        logger.exception("Failed to build workspace_data for challenge check")
        return f"Error checking challenges: {e}"

    try:
        all_newly_completed = ctx.challenge_mgr.check_all(workspace_data)
    except Exception as e:
        logger.exception("ChallengeManager.check_all failed")
        return f"Error running challenge check: {e}"

    # Dedup against already-announced challenges (DEC-AGENT-CHALLENGES-001).
    newly_announced = []
    for ch in all_newly_completed:
        if ch.id not in ctx._announced_challenges:
            newly_announced.append(ch)
            ctx._announced_challenges.add(ch.id)

    if not newly_announced:
        return "No new challenges completed yet. Keep hunting!"
    lines = [f"{len(newly_announced)} challenge(s) newly completed:"]
    for ch in newly_announced:
        lines.append(f"  {ch.name} (+{ch.points} pts): {ch.description}")
    return "\n".join(lines)


def _execute_render_graph(ctx: ToolContext) -> str:
    """Render the current workspace as a plain-text relationship graph.

    Builds a RelationshipGraph from all STIX objects in the active workspace
    and returns the render_text() output — a multi-line tree string safe for
    LLM consumption (no ANSI escape codes).

    Mirrors cmd2 APConsole.do_graph: build RelationshipGraph, call
    build_from_workspace(raw_objects), render_tree() via render_text().
    See DEC-AGENT-GRAPH-EXPORT-001 for the per-call rebuild rationale.

    Parameters
    ----------
    ctx:
        The shared ToolContext providing the WorkspaceManager.

    Returns
    -------
    str
        Multi-line text tree of the workspace relationships, or an
        informational message when the workspace is empty or unreadable.
    """
    try:
        raw_objects = ctx.workspace_mgr.get_stix_objects()
    except Exception as e:
        logger.exception("render_graph: failed to read workspace")
        return f"Error reading workspace: {e}"

    g = RelationshipGraph()
    g.build_from_workspace(raw_objects)

    if g.node_count == 0:
        return "No objects in workspace. Run a module first to populate the graph."

    text = g.render_text()
    stats = g.get_stats()
    return text.rstrip() + f"\n\n{stats['node_count']} nodes, {stats['edge_count']} edges"


def _execute_export_workspace(ctx: ToolContext, fmt: str) -> str:
    """Export the workspace as GEXF XML or a STIX bundle JSON string.

    Builds a RelationshipGraph from all STIX objects in the active workspace
    and calls export_gexf() or export_stix_bundle() depending on *fmt*.

    Mirrors cmd2 APConsole._export_gexf and do_export --format stix.
    See DEC-AGENT-GRAPH-EXPORT-001 for the per-call rebuild rationale.

    Parameters
    ----------
    ctx:
        The shared ToolContext providing the WorkspaceManager.
    fmt:
        Export format: "gexf" returns GEXF 1.2 XML string; "stix" returns
        a JSON-serialized STIX 2.1 bundle dict. Any other value returns an
        error string.

    Returns
    -------
    str
        GEXF XML string, JSON-serialized STIX bundle, or an error message.
    """
    import json as _json

    fmt = (fmt or "stix").strip().lower()
    if fmt not in ("gexf", "stix"):
        return (
            f"Unknown export format '{fmt}'. "
            "Supported formats: 'gexf' (GEXF 1.2 XML for Gephi), "
            "'stix' (STIX 2.1 bundle JSON)."
        )

    try:
        raw_objects = ctx.workspace_mgr.get_stix_objects()
    except Exception as e:
        logger.exception("export_workspace: failed to read workspace")
        return f"Error reading workspace: {e}"

    if not raw_objects:
        return "No objects in workspace to export. Run a module first."

    g = RelationshipGraph()
    g.build_from_workspace(raw_objects)

    if fmt == "gexf":
        return g.export_gexf()

    # fmt == "stix"
    bundle = g.export_stix_bundle()
    return _json.dumps(bundle, indent=2)


# ---------------------------------------------------------------------------
# Report interview helpers — DEC-AGENT-REPORT-001
# ---------------------------------------------------------------------------


def _execute_start_report_interview(ctx: ToolContext) -> str:
    """Initialise (or reset) the ReportGenerator and return all interview questions.

    Creates a fresh ReportGenerator on ctx.report_generator, wiping any prior
    answers. Returns the numbered question list so the LLM can present them to
    the analyst one by one.

    Mirrors cmd2 do_report: always starts from blank answers (DEC-REPORT-003).

    Parameters
    ----------
    ctx:
        The shared ToolContext. report_generator is set on ctx after this call.

    Returns
    -------
    str
        Numbered list of the 5 interview questions, with instructions to call
        answer_report_question(index, answer) for each.
    """
    ctx.report_generator = ReportGenerator(ctx.workspace_mgr)
    questions = ReportGenerator.INTERVIEW_QUESTIONS
    lines = [
        "Investigation report interview started. Answer each question with "
        "answer_report_question(question_index, answer):",
        "",
    ]
    for i, q in enumerate(questions):
        lines.append(f"  {i}. {q}")
    lines.append("")
    lines.append(
        "After all 5 answers are set, call generate_report() to produce the Markdown report."
    )
    return "\n".join(lines)


def _execute_answer_report_question(
    ctx: ToolContext,
    question_index: int | None,
    answer: str,
) -> str:
    """Record the analyst's answer for one interview question.

    Sets the answer on the in-session ReportGenerator. Returns a confirmation
    string with the question text so the LLM can relay it to the analyst.

    Parameters
    ----------
    ctx:
        The shared ToolContext holding the session-scoped ReportGenerator.
    question_index:
        Index 0-4 into ReportGenerator.INTERVIEW_QUESTIONS. Returns an error
        string if None or out of range.
    answer:
        The analyst's answer text.

    Returns
    -------
    str
        Confirmation with question text, or an error message.
    """
    if ctx.report_generator is None:
        return "Report interview has not been started. Call start_report_interview() first."
    if question_index is None:
        return "question_index is required (0-4)."
    try:
        question_index = int(question_index)
        ctx.report_generator.set_answer(question_index, answer)
    except (IndexError, ValueError) as e:
        return f"Error setting answer: {e}"

    question = ReportGenerator.INTERVIEW_QUESTIONS[question_index]
    total = len(ReportGenerator.INTERVIEW_QUESTIONS)
    answered = sum(1 for s in ctx.report_generator.sections if s.answer.strip())
    remaining = total - answered
    suffix = (
        " All questions answered — call generate_report() to produce the report."
        if remaining == 0
        else f" ({answered}/{total} answered)"
    )
    return f"Recorded answer for Q{question_index}: '{question}'.{suffix}"


def _execute_generate_report(ctx: ToolContext) -> str:
    """Generate the full Markdown investigation report.

    Calls ReportGenerator.generate() which combines live workspace data (STIX
    objects, module runs, score) with the interview answers stored on ctx.report_generator.
    Returns the complete Markdown string for the LLM to relay to the analyst.

    Parameters
    ----------
    ctx:
        The shared ToolContext holding the session-scoped ReportGenerator.

    Returns
    -------
    str
        Complete Markdown report, or an error/instruction message.
    """
    if ctx.report_generator is None:
        return (
            "Report interview has not been started. "
            "Call start_report_interview() first, then answer_report_question() "
            "for each question, then generate_report()."
        )
    try:
        return ctx.report_generator.generate()
    except Exception as e:
        logger.exception("generate_report failed")
        return f"Error generating report: {e}"
