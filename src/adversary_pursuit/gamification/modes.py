"""Character modes for Adversary Pursuit.

Each mode is a configuration profile that affects prompt style, celebration
messages, and run success/failure voice.

The active mode is managed via ModeManager and consulted by APConsole for:
- prompt prefix (do_back, do_use restore mode-aware prompt)
- run/hunt success and failure messages (_execute_hunt)
- score celebration template (formatted with points= kwarg)

@decision DEC-MODE-001
@title CharacterMode as frozen dataclass, ModeManager as thin state machine
@status accepted
@rationale CharacterMode instances are pure configuration — they carry no
           mutable state and are looked up by name. A frozen dataclass is the
           right primitive: immutable, self-documenting, and serializable.
           ModeManager wraps a dict copy of DEFAULT_MODES so tests can mutate
           the manager state without affecting the module-level defaults.
           APConsole holds a single ModeManager; mode switches are reflected
           immediately in prompt and subsequent command output.

@decision DEC-MODE-002
@title score_celebration uses str.format(points=N) — not f-string interpolation
@status accepted
@rationale The score_celebration string is stored as data (not code), so it
           must be evaluated lazily at runtime. {points} is a named placeholder
           that callers format with .format(points=total). This keeps the
           template strings readable as data and avoids eval(). Callers are
           responsible for the format call — they know the point total.

@decision DEC-62-KILL-DOC-LIES-001
@title Delete hint_style (zero consumers, undefined semantics); rewrite personality
@status accepted
@rationale hint_style was added speculatively in Phase 3 planning but never wired
           to any hint subsystem. It has zero consumers and its values ("speed bonuses",
           "combo multipliers", "chaos mode") are false advertising — the feature does
           not exist. Deleting the field removes a documentation lie without any
           behavioural change. personality strings that referenced unimplemented mechanics
           ("speed bonuses", "combo multipliers", "random pivot suggestions") are rewritten
           to describe what the mode actually does: its voice, tone, and message style.
           run_fail is now the single authority for failure voice (DEC-62-KILL-DOC-LIES-001);
           _MODE_TITLE_FLAVORS in error_interpreter.py (F61 drift) is deleted in the same
           change so there is never a parallel authority for mode-error phrasing.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CharacterMode:
    """Immutable configuration profile for a character mode.

    Fields
    ------
    name:
        Canonical mode identifier (lowercase, used as dict key).
    prompt_prefix:
        Emoji/symbol prepended to the console prompt. Empty string for clean.
    greeting:
        Rich-markup string displayed when the mode is activated.
    run_success:
        Rich-markup string displayed after a successful module hunt().
    run_fail:
        Rich-markup string displayed after a hunt() failure (error/no results).
        This is the single authority for mode-flavored failure voice.
        render_interactive() in error_interpreter.py uses this field directly;
        the parallel _MODE_TITLE_FLAVORS dict was removed in F62.
    score_celebration:
        Rich-markup template string. Must contain {points} placeholder.
        Callers format with .format(points=total_gained).
    personality:
        One-line description shown in mode list tables. Must describe only
        what the mode actually does (voice, tone, message style) — no
        unimplemented mechanics ("speed bonuses", "combo multipliers").
    """

    name: str
    prompt_prefix: str
    greeting: str
    run_success: str
    run_fail: str
    score_celebration: str
    personality: str


DEFAULT_MODES: dict[str, CharacterMode] = {
    "default": CharacterMode(
        name="default",
        prompt_prefix="",
        greeting="Welcome to Adversary Pursuit.",
        run_success="Hunt complete. Results stored.",
        run_fail="Hunt failed.",
        score_celebration="+{points} points!",
        personality="Standard analyst mode — neutral tone",
    ),
    "ninja": CharacterMode(
        name="ninja",
        prompt_prefix="🥷",
        greeting="[dim]...[/dim]",
        run_success="[dim]Target acquired. Moving on.[/dim]",
        run_fail="[dim]Missed. Regroup.[/dim]",
        score_celebration="[dim]+{points}[/dim]",
        personality="Minimal output, silent and concise messaging",
    ),
    "full_troll": CharacterMode(
        name="full_troll",
        prompt_prefix="🤡",
        greeting="[bold magenta]LEEEEEROYYY JENKINS![/bold magenta] Welcome to the party!",
        run_success="[bold green]GET REKT ADVERSARY! 🎉🎉🎉[/bold green]",
        run_fail="[bold red]BRUH. Even my grandma could've found that.[/bold red]",
        score_celebration="[bold magenta]🔥 +{points} POINTS BABY! 🔥[/bold magenta]",
        personality="Maximum memes, loud taunt messages",
    ),
    "drunken_master": CharacterMode(
        name="drunken_master",
        prompt_prefix="🍺",
        greeting="*hiccup* Oh hey... we doing this? Let's goooo...",
        run_success="*stumbles* Whoa, we actually found something! Nice!",
        run_fail="*falls over* Ehh, try again... maybe pivot... somewhere...",
        score_celebration="*hiccup* +{points} pointsss!",
        personality="Rambling tipsy energy, unpredictable commentary",
    ),
    "sun_tzu": CharacterMode(
        name="sun_tzu",
        prompt_prefix="📜",
        greeting='"Know thy enemy and know thyself." Let us begin.',
        run_success='"Opportunities multiply as they are seized." Excellent work.',
        run_fail='"In the midst of chaos, there is also opportunity." Try another approach.',
        score_celebration='"Supreme excellence." +{points} points earned.',
        personality="Strategic Sun Tzu quotes for every action",
    ),
    "chuck_norris": CharacterMode(
        name="chuck_norris",
        prompt_prefix="💪",
        greeting="Chuck Norris doesn't hunt threats. Threats surrender to Chuck Norris.",
        run_success="Chuck Norris found all the indicators. On the first try. Obviously.",
        run_fail="This never happens to Chuck Norris. Must be a glitch in the Matrix.",
        score_celebration="Chuck Norris earned +{points} points. The points are honored.",
        personality="Unstoppable confidence, Chuck Norris facts as flavor",
    ),
    "bureaucrat": CharacterMode(
        name="bureaucrat",
        prompt_prefix="📋",
        greeting="Please sign form TPS-001 before proceeding. In triplicate.",
        run_success="Results filed under Form IR-7734. Please initial here, here, and here.",
        run_fail="Your request has been denied. Please submit Form ERR-404 to the help desk.",
        score_celebration="Per Policy §4.2.1, you have been awarded +{points} compliance points.",
        personality="Office Space vibes, everything is a TPS report",
    ),
    "bobby_hill": CharacterMode(
        name="bobby_hill",
        prompt_prefix="😤",
        greeting="That's my purse! I DON'T KNOW YOU! ...Oh wait, this is my workstation.",
        run_success="THAT'S MY PURSE! I mean... nice find!",
        run_fail="I don't know you! And I don't know what went wrong either.",
        score_celebration="That boy ain't right... but +{points} points IS right!",
        personality="'That's my purse!' energy, King of the Hill flavor",
    ),
    "bruce_lee": CharacterMode(
        name="bruce_lee",
        prompt_prefix="🐉",
        greeting='"Be water, my friend." Adapt and flow through the data.',
        run_success='"I fear not the man who has practiced 10,000 kicks once." Focused strike. Clean hit.',
        run_fail='"Don\'t fear failure." Adjust and flow to the next approach.',
        score_celebration="Flow state! +{points} points! 🐉",
        personality="Bruce Lee philosophy, flow-state zen commentary",
    ),
    "columbo": CharacterMode(
        name="columbo",
        prompt_prefix="🔍",
        greeting="Oh, uh, just one more thing... I'm investigating a little something.",
        run_success="Oh! Would you look at that... very interesting. Just one more thing...",
        run_fail="You know, my wife always says I miss the obvious things. She might be right.",
        score_celebration="Oh, almost forgot... +{points} points. Just one more thing...",
        personality="'Just one more thing...' investigative prompts",
    ),
}


class ModeManager:
    """Manages the active character mode for an APConsole session.

    Holds an independent copy of the mode catalogue so that switching modes
    does not mutate the module-level DEFAULT_MODES dict. This is important
    for test isolation and future extensibility (user-defined modes).

    Usage
    -----
    mgr = ModeManager()
    mode = mgr.switch("ninja")
    print(mgr.active.greeting)
    for entry in mgr.list_modes():
        print(entry["name"], entry["personality"])
    """

    def __init__(self) -> None:
        # Independent copy — mutations here don't touch DEFAULT_MODES
        self._modes: dict[str, CharacterMode] = dict(DEFAULT_MODES)
        self._active: str = "default"

    @property
    def active(self) -> CharacterMode:
        """Return the currently active CharacterMode."""
        return self._modes[self._active]

    def switch(self, name: str) -> CharacterMode:
        """Switch to the named mode.

        Parameters
        ----------
        name:
            Mode name matching a key in DEFAULT_MODES (e.g. "ninja").

        Returns
        -------
        CharacterMode
            The newly activated mode.

        Raises
        ------
        ValueError
            If the mode name is not recognised. Message includes available names.
        """
        if name not in self._modes:
            available = ", ".join(sorted(self._modes.keys()))
            raise ValueError(f"Unknown mode: {name!r}. Available: {available}")
        self._active = name
        return self._modes[name]

    def list_modes(self) -> list[dict]:
        """Return a summary list of all modes.

        Returns
        -------
        list[dict]
            Each entry is ``{"name": str, "personality": str}``.
        """
        return [{"name": m.name, "personality": m.personality} for m in self._modes.values()]
