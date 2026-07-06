"""Global character phrase cache for Adversary Pursuit.

Provides randomized, per-character phrase pools for status bar messages,
greetings, run results, and score celebrations.

@decision DEC-PHRASE-CACHE-001
@title phrases.py is the sole authority for all character voice strings
@status accepted
@rationale Centralizing all voiced strings in one module eliminates the prior
           pattern of embedding hard-coded strings inside CharacterMode dataclass
           fields. The Phrase dataclass adds weight (for rarities) and tags
           (for conditional suppression, e.g. "dave" for HAL9000 persona).
           The fallback ladder (char,cat) -> (default,cat) -> FALLBACK -> ValueError
           ensures graceful degradation for unknown characters while loudly failing
           on unknown categories (Sacred Practice 5: fail loudly).
           PHRASES is the single authority; pick() is the single consumer interface.
           StatusBar, chat.py, and any future UI surface call pick() only.
"""

from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class Phrase:
    """A voiced phrase with optional weight and tags.

    Parameters
    ----------
    text:
        The phrase text. May contain {points} placeholder for score_celebration.
    weight:
        Relative selection weight. Default 1.0. Lower values make rare phrases.
    tags:
        Tuple of string tags for conditional filtering (e.g. "dave" for HAL9000).
    """

    text: str
    weight: float = 1.0
    tags: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Phrase registry
# ---------------------------------------------------------------------------

# key = (character_name, category) -> tuple of Phrase objects
# Categories: "greeting", "run_success", "run_fail", "score_celebration",
#             "activity:<slug>", "activity:thinking", "activity:composing"
PHRASES: dict[tuple[str, str], tuple[Phrase, ...]] = {
    # ------------------------------------------------------------------
    # default
    # ------------------------------------------------------------------
    ("default", "greeting"): (
        Phrase("Welcome to Adversary Pursuit."),
        Phrase("Analyst session started."),
        Phrase("Ready to investigate."),
    ),
    ("default", "run_success"): (
        Phrase("Hunt complete. Results stored."),
        Phrase("Module returned results."),
        Phrase("Analysis complete."),
    ),
    ("default", "run_fail"): (
        Phrase("Hunt failed. No results."),
        Phrase("Module returned no data."),
        Phrase("Nothing found. Try another approach."),
    ),
    ("default", "score_celebration"): (
        Phrase("+{points} points!"),
        Phrase("Earned {points} points."),
        Phrase("+{points}. Good work."),
    ),
    ("default", "activity:virustotal"): (
        Phrase("Querying VirusTotal..."),
        Phrase("Running VirusTotal lookup"),
    ),
    ("default", "activity:whois"): (
        Phrase("Running WHOIS lookup..."),
        Phrase("Querying WHOIS"),
    ),
    ("default", "activity:shodan"): (
        Phrase("Querying Shodan..."),
        Phrase("Running Shodan lookup"),
    ),
    ("default", "activity:otx"): (
        Phrase("Checking OTX..."),
        Phrase("Querying OTX threat intel"),
    ),
    ("default", "activity:threatfox"): (
        Phrase("Checking ThreatFox..."),
        Phrase("Querying ThreatFox"),
    ),
    ("default", "activity:thinking"): (
        Phrase("Thinking..."),
        Phrase("Analyzing..."),
        Phrase("Processing..."),
    ),
    ("default", "activity:composing"): (
        Phrase("Composing response..."),
        Phrase("Writing up findings..."),
    ),
    # ------------------------------------------------------------------
    # ninja
    # ------------------------------------------------------------------
    ("ninja", "greeting"): (
        Phrase("[dim]...[/dim]"),
        Phrase("[dim]In position.[/dim]"),
        Phrase("[dim]Ready.[/dim]"),
    ),
    ("ninja", "run_success"): (
        Phrase("[dim]Target acquired.[/dim]"),
        Phrase("[dim]Done.[/dim]"),
        Phrase("[dim]Hit confirmed.[/dim]"),
    ),
    ("ninja", "run_fail"): (
        Phrase("[dim]Missed. Regroup.[/dim]"),
        Phrase("[dim]Nothing.[/dim]"),
        Phrase("[dim]Negative.[/dim]"),
    ),
    ("ninja", "score_celebration"): (
        Phrase("[dim]+{points}[/dim]"),
        Phrase("[dim]{points}.[/dim]"),
        Phrase("[dim]+{points} — noted.[/dim]"),
    ),
    ("ninja", "activity:virustotal"): (
        Phrase("VT check"),
        Phrase("VT"),
    ),
    ("ninja", "activity:whois"): (
        Phrase("WHOIS"),
        Phrase("Reg check"),
    ),
    ("ninja", "activity:shodan"): (
        Phrase("Shodan"),
        Phrase("Scan"),
    ),
    ("ninja", "activity:otx"): (Phrase("OTX"),),
    ("ninja", "activity:threatfox"): (Phrase("ThreatFox"),),
    ("ninja", "activity:thinking"): (
        Phrase("..."),
        Phrase("noted."),
        Phrase("thinking."),
    ),
    ("ninja", "activity:composing"): (Phrase("..."),),
    # ------------------------------------------------------------------
    # full_troll
    # ------------------------------------------------------------------
    ("full_troll", "greeting"): (
        Phrase("[bold magenta]LEEEEEROYYY JENKINS![/bold magenta] Let's gooo!"),
        Phrase("[bold magenta]GET REKT ADVERSARY MODE ENGAGED[/bold magenta]"),
        Phrase("[bold magenta]CHAOS INCOMING[/bold magenta] — buckle up!"),
    ),
    ("full_troll", "run_success"): (
        Phrase("[bold green]GET REKT ADVERSARY![/bold green]"),
        Phrase("[bold green]OWNED! GG NO RE[/bold green]"),
        Phrase("[bold green]ABSOLUTE UNIT OF A RESULT[/bold green]"),
    ),
    ("full_troll", "run_fail"): (
        Phrase("[bold red]BRUH.[/bold red]"),
        Phrase("[bold red]REKT by the API[/bold red]"),
        Phrase("[bold red]404 ADVERSARY NOT FOUND[/bold red]"),
    ),
    ("full_troll", "score_celebration"): (
        Phrase("[bold magenta]🔥 +{points} POINTS BABY! 🔥[/bold magenta]"),
        Phrase("[bold magenta]+{points} GET REKT[/bold magenta]"),
        Phrase("[bold magenta]+{points} ABSOLUTE UNIT[/bold magenta]"),
    ),
    ("full_troll", "activity:virustotal"): (
        Phrase("DROPPING THE VT BOMB"),
        Phrase("VT LOOT CHECK"),
    ),
    ("full_troll", "activity:whois"): (
        Phrase("WHOIS DIS CLOWN"),
        Phrase("REG LOOKUP GO BRRR"),
    ),
    ("full_troll", "activity:shodan"): (
        Phrase("SHODAN SCANNER GOES BRRR"),
        Phrase("SCANNING ALL THE THINGS"),
    ),
    ("full_troll", "activity:otx"): (Phrase("OTX THREAT DUMP"),),
    ("full_troll", "activity:threatfox"): (Phrase("THREATFOX INCOMING"),),
    ("full_troll", "activity:thinking"): (
        Phrase("GALAXY BRAIN MODE"),
        Phrase("BIG BRAIN TIME"),
        Phrase("COMPUTING..."),
    ),
    ("full_troll", "activity:composing"): (Phrase("TYPING AT THE SPEED OF LIGHT"),),
    # ------------------------------------------------------------------
    # drunken_master_retired (archived — do not expose as active)
    # ------------------------------------------------------------------
    ("drunken_master_retired", "greeting"): (
        Phrase("*hiccup* Oh hey... we doing this?"),
        Phrase("*stumbles in* Let's goooo..."),
        Phrase("*sways* Ready... mostly."),
    ),
    ("drunken_master_retired", "run_success"): (
        Phrase("*stumbles* Whoa, we actually found something!"),
        Phrase("*hiccup* Got it! I think..."),
        Phrase("*falls forward* NICE."),
    ),
    ("drunken_master_retired", "run_fail"): (
        Phrase("*falls over* Ehh, try again..."),
        Phrase("*hiccup* Nothing... pivot somewhere."),
        Phrase("*sways* Not my best work."),
    ),
    ("drunken_master_retired", "score_celebration"): (
        Phrase("*hiccup* +{points} pointsss!"),
        Phrase("+{points}... I think that's good?"),
        Phrase("*stumbles* {points} MORE POINTS!"),
    ),
    ("drunken_master_retired", "activity:virustotal"): (Phrase("VT... *hiccup*"),),
    ("drunken_master_retired", "activity:whois"): (Phrase("WHOIS... who knows"),),
    ("drunken_master_retired", "activity:shodan"): (Phrase("*squints* Shodan..."),),
    ("drunken_master_retired", "activity:otx"): (Phrase("OTX... *sways*"),),
    ("drunken_master_retired", "activity:threatfox"): (Phrase("ThreatFox... *hiccup*"),),
    ("drunken_master_retired", "activity:thinking"): (Phrase("*thinking* ..."),),
    ("drunken_master_retired", "activity:composing"): (Phrase("*scribbling*"),),
    # ------------------------------------------------------------------
    # sun_tzu
    # ------------------------------------------------------------------
    ("sun_tzu", "greeting"): (
        Phrase('"Know thy enemy and know thyself." Let us begin.'),
        Phrase('"The supreme art of war is to subdue the enemy without fighting." Observe.'),
        Phrase('"In the midst of chaos, there is also opportunity." We begin.'),
    ),
    ("sun_tzu", "run_success"): (
        Phrase('"Opportunities multiply as they are seized." Excellent work.'),
        Phrase('"Victory is reserved for those who pay the price." Well earned.'),
        Phrase('"The general who wins the battle makes many calculations." Well planned.'),
    ),
    ("sun_tzu", "run_fail"): (
        Phrase('"In the midst of chaos, there is also opportunity." Try another approach.'),
        Phrase('"He who knows when he can fight and when he cannot will be victorious." Regroup.'),
        Phrase('"Strategy without tactics is the slowest route to victory." Adjust.'),
    ),
    ("sun_tzu", "score_celebration"): (
        Phrase('"Supreme excellence." +{points} points earned.'),
        Phrase(
            '+{points}. "The opportunity to secure ourselves against defeat lies in our own hands."'
        ),
        Phrase('"Victorious warriors win first." +{points} points.'),
    ),
    ("sun_tzu", "activity:virustotal"): (
        Phrase("Consulting the verdict of many spies..."),
        Phrase("Gathering intelligence from VirusTotal"),
    ),
    ("sun_tzu", "activity:whois"): (
        Phrase("Reconnoitering the enemy terrain..."),
        Phrase("WHOIS — knowing the enemy's territory"),
    ),
    ("sun_tzu", "activity:shodan"): (
        Phrase("Surveying the battlefield with Shodan..."),
        Phrase("Eyes on enemy infrastructure"),
    ),
    ("sun_tzu", "activity:otx"): (Phrase("Gathering intelligence from many sources..."),),
    ("sun_tzu", "activity:threatfox"): (Phrase("Consulting the threat registry..."),),
    ("sun_tzu", "activity:thinking"): (
        Phrase("Calculating..."),
        Phrase("Strategizing..."),
        Phrase("Weighing the options..."),
    ),
    ("sun_tzu", "activity:composing"): (Phrase("Formulating strategy..."),),
    # ------------------------------------------------------------------
    # chuck_norris
    # ------------------------------------------------------------------
    ("chuck_norris", "greeting"): (
        Phrase("Chuck Norris doesn't hunt threats. Threats surrender to Chuck Norris."),
        Phrase("Chuck Norris is already done. He's just letting the terminal catch up."),
        Phrase("Chuck Norris doesn't start investigations. Investigations start themselves."),
    ),
    ("chuck_norris", "run_success"): (
        Phrase("Chuck Norris found all the indicators. On the first try. Obviously."),
        Phrase("Chuck Norris doesn't get results. Results get Chuck Norris."),
        Phrase("The adversary surrendered before Chuck Norris finished typing."),
    ),
    ("chuck_norris", "run_fail"): (
        Phrase("This never happens to Chuck Norris. Must be a glitch in the Matrix."),
        Phrase("Chuck Norris lets them think they escaped. For now."),
        Phrase("Chuck Norris failed? Impossible. The API failed Chuck Norris."),
    ),
    ("chuck_norris", "score_celebration"): (
        Phrase("Chuck Norris earned +{points} points. The points are honored."),
        Phrase("+{points}. Numbers fear Chuck Norris."),
        Phrase("Chuck Norris counted to +{points}. Backwards."),
    ),
    ("chuck_norris", "activity:virustotal"): (
        Phrase("VirusTotal runs itself for Chuck Norris"),
        Phrase("Chuck Norris's VirusTotal query"),
    ),
    ("chuck_norris", "activity:whois"): (
        Phrase("WHOIS — everyone knows it's Chuck Norris"),
        Phrase("Chuck Norris's WHOIS lookup"),
    ),
    ("chuck_norris", "activity:shodan"): (
        Phrase("Shodan begs Chuck Norris to search it"),
        Phrase("Chuck Norris Shodan scan"),
    ),
    ("chuck_norris", "activity:otx"): (Phrase("Chuck Norris OTX intel"),),
    ("chuck_norris", "activity:threatfox"): (Phrase("Chuck Norris ThreatFox lookup"),),
    ("chuck_norris", "activity:thinking"): (
        Phrase("Chuck Norris has already thought it."),
        Phrase("Processing..."),
        Phrase("Chuck Norris computing."),
    ),
    ("chuck_norris", "activity:composing"): (Phrase("Chuck Norris types at 10,000 wpm."),),
    # ------------------------------------------------------------------
    # bureaucrat
    # ------------------------------------------------------------------
    ("bureaucrat", "greeting"): (
        Phrase("Please sign form TPS-001 before proceeding. In triplicate."),
        Phrase("Initializing Form IR-0001 (Investigation Request). Please stand by."),
        Phrase("Session initiated per Policy §1.1.1. Proceed to Section B."),
    ),
    ("bureaucrat", "run_success"): (
        Phrase("Results filed under Form IR-7734. Please initial here, here, and here."),
        Phrase("Per Policy §4.2.1, analysis complete. File under Appendix C."),
        Phrase("Results processed and submitted to the proper channels."),
    ),
    ("bureaucrat", "run_fail"): (
        Phrase("Your request has been denied. Please submit Form ERR-404 to the help desk."),
        Phrase("No results per Policy §3.0.2 (null-response exception). File Form NR-001."),
        Phrase("Outcome: incomplete. Request Form ERR-404 from the appropriate department."),
    ),
    ("bureaucrat", "score_celebration"): (
        Phrase("Per Policy §4.2.1, you have been awarded +{points} compliance points."),
        Phrase("+{points} points awarded. See Form SC-7 (Score Credit Acknowledgment)."),
        Phrase("Score credit of {points} units approved per Policy §9.1."),
    ),
    ("bureaucrat", "activity:virustotal"): (
        Phrase("Submitting Form VT-001 to VirusTotal registry..."),
        Phrase("VirusTotal query — Form VT-001"),
    ),
    ("bureaucrat", "activity:whois"): (
        Phrase("Initiating Form WH-1 (WHOIS disclosure)..."),
        Phrase("WHOIS consultation per Form WH-1"),
    ),
    ("bureaucrat", "activity:shodan"): (
        Phrase("Shodan scan — Form SD-3 (infrastructure disclosure)..."),
        Phrase("Initiating Shodan Form SD-3"),
    ),
    ("bureaucrat", "activity:otx"): (Phrase("OTX cross-reference per Form OTX-001..."),),
    ("bureaucrat", "activity:threatfox"): (Phrase("ThreatFox Form TF-002 consultation..."),),
    ("bureaucrat", "activity:thinking"): (
        Phrase("Processing. Please wait for Form PROC-001 acknowledgment."),
        Phrase("Consulting Policy §7.4.2 (Decision Matrix)..."),
        Phrase("Analysis in progress per procedure..."),
    ),
    ("bureaucrat", "activity:composing"): (Phrase("Drafting Form RES-001 (Response Document)..."),),
    # ------------------------------------------------------------------
    # bobby_hill
    # ------------------------------------------------------------------
    ("bobby_hill", "greeting"): (
        Phrase("That's my purse! I DON'T KNOW YOU! ...Oh wait, this is my workstation."),
        Phrase("Hey! That's my terminal! ...Oh, it's fine. We're good."),
        Phrase("I don't know you! ...Actually I do. Let's investigate."),
    ),
    ("bobby_hill", "run_success"): (
        Phrase("THAT'S MY PURSE! I mean... nice find!"),
        Phrase("I did it! I really did it! ...Right?"),
        Phrase("That right there is a quality result!"),
    ),
    ("bobby_hill", "run_fail"): (
        Phrase("I don't know you! And I don't know what went wrong either."),
        Phrase("That's not my purse... and that's not a good result."),
        Phrase("Uh oh. That ain't right."),
    ),
    ("bobby_hill", "score_celebration"): (
        Phrase("That boy ain't right... but +{points} points IS right!"),
        Phrase("+{points}! That's my points!"),
        Phrase("I earned {points} points! That's my purse!"),
    ),
    ("bobby_hill", "activity:virustotal"): (
        Phrase("VirusTotal! That's my lookup!"),
        Phrase("Running VT — that's my scan!"),
    ),
    ("bobby_hill", "activity:whois"): (
        Phrase("WHOIS! I know you!"),
        Phrase("Running WHOIS lookup"),
    ),
    ("bobby_hill", "activity:shodan"): (
        Phrase("Shodan time! I don't know you, Shodan!"),
        Phrase("Shodan scan incoming"),
    ),
    ("bobby_hill", "activity:otx"): (Phrase("OTX! That's my intel!"),),
    ("bobby_hill", "activity:threatfox"): (Phrase("ThreatFox! Don't know you!"),),
    ("bobby_hill", "activity:thinking"): (
        Phrase("Thinking about it..."),
        Phrase("Um... hold on..."),
        Phrase("That ain't right... give me a sec."),
    ),
    ("bobby_hill", "activity:composing"): (Phrase("Writing it up... that's my report!"),),
    # ------------------------------------------------------------------
    # bruce_lee
    # ------------------------------------------------------------------
    ("bruce_lee", "greeting"): (
        Phrase('"Be water, my friend." Adapt and flow through the data.'),
        Phrase('"Empty your mind." Let the investigation reveal itself.'),
        Phrase('"Knowledge will give you power, but character respect." We begin.'),
    ),
    ("bruce_lee", "run_success"): (
        Phrase('"I fear not the man who has practiced 10,000 kicks once." Focused strike.'),
        Phrase('"Flow like water." The data yielded its truth.'),
        Phrase('"The successful warrior is the average man with laser-like focus." Success.'),
    ),
    ("bruce_lee", "run_fail"): (
        Phrase('"Don\'t fear failure." Adjust and flow to the next approach.'),
        Phrase('"Be like water — take the shape of the container." Redirect.'),
        Phrase('"Take what is useful, discard what is not." Nothing here. Move on.'),
    ),
    ("bruce_lee", "score_celebration"): (
        Phrase("Flow state! +{points} points!"),
        Phrase("+{points}. Water always finds a way."),
        Phrase('"10,000 kicks." +{points} points earned.'),
    ),
    ("bruce_lee", "activity:virustotal"): (
        Phrase("The river of verdicts flows through VirusTotal..."),
        Phrase("VirusTotal — each result a ripple"),
    ),
    ("bruce_lee", "activity:whois"): (
        Phrase("WHOIS — tracing the root of the river..."),
        Phrase("Following the water to its source"),
    ),
    ("bruce_lee", "activity:shodan"): (
        Phrase("Shodan scan — eyes on the surface of the water..."),
        Phrase("Surveying the infrastructure like still water"),
    ),
    ("bruce_lee", "activity:otx"): (Phrase("OTX — many streams of intelligence converge..."),),
    ("bruce_lee", "activity:threatfox"): (Phrase("ThreatFox — reading the current..."),),
    ("bruce_lee", "activity:thinking"): (
        Phrase("Be water..."),
        Phrase("Empty the mind..."),
        Phrase("Flowing..."),
    ),
    ("bruce_lee", "activity:composing"): (Phrase("Expressing through stillness..."),),
    # ------------------------------------------------------------------
    # columbo
    # ------------------------------------------------------------------
    ("columbo", "greeting"): (
        Phrase("Oh, uh, just one more thing... I'm investigating a little something."),
        Phrase("Sorry to bother you. Just a few questions, if you don't mind."),
        Phrase("My wife always says I never let things go. She's probably right."),
    ),
    ("columbo", "run_success"): (
        Phrase("Oh! Would you look at that... very interesting. Just one more thing..."),
        Phrase("Now THAT is very peculiar. Just one more thing..."),
        Phrase("You know, I had a feeling. Just one more thing..."),
    ),
    ("columbo", "run_fail"): (
        Phrase("You know, my wife always says I miss the obvious things. She might be right."),
        Phrase("Hm. Nothing here. Just one more thing... let me try another angle."),
        Phrase("I'm probably confused. Just one more thing — let's try again."),
    ),
    ("columbo", "score_celebration"): (
        Phrase("Oh, almost forgot... +{points} points. Just one more thing..."),
        Phrase("+{points}. Just one more thing to note."),
        Phrase("Oh! +{points} points. My wife would be impressed."),
    ),
    ("columbo", "activity:virustotal"): (
        Phrase("Just checking VirusTotal — just one more thing..."),
        Phrase("Running VT — the obvious question"),
    ),
    ("columbo", "activity:whois"): (
        Phrase("WHOIS — the obvious question is who owns the place..."),
        Phrase("Just a quick WHOIS — one more thing"),
    ),
    ("columbo", "activity:shodan"): (
        Phrase("Shodan — just having a look around..."),
        Phrase("One more scan — Shodan"),
    ),
    ("columbo", "activity:otx"): (Phrase("OTX — just one more intel source..."),),
    ("columbo", "activity:threatfox"): (Phrase("ThreatFox — just one more thing..."),),
    ("columbo", "activity:thinking"): (
        Phrase("Just one more thing..."),
        Phrase("Hmm... I'm probably confused."),
        Phrase("Just thinking... my wife would know."),
    ),
    ("columbo", "activity:composing"): (Phrase("Just writing this up — one more thing..."),),
    # ------------------------------------------------------------------
    # deckard
    # ------------------------------------------------------------------
    ("deckard", "greeting"): (
        Phrase("Another night, another hunt. Let's see what crawls out."),
        Phrase("Deckard. Case is open."),
        Phrase("Coffee's cold. Let's work."),
    ),
    ("deckard", "run_success"): (
        Phrase("There you are."),
        Phrase("Got him."),
        Phrase("Enhance. There's your ghost.", weight=0.5),
    ),
    ("deckard", "run_fail"): (
        Phrase("Nothing but static."),
        Phrase("Dead end. Try another angle."),
        Phrase("Not this time."),
    ),
    ("deckard", "score_celebration"): (
        Phrase("Chalk another one up. +{points}."),
        Phrase("+{points}. It's a living."),
        Phrase("+{points}. Case builds."),
    ),
    ("deckard", "activity:virustotal"): (
        Phrase("Running VT"),
        Phrase("Pulling VT sheet"),
    ),
    ("deckard", "activity:whois"): (
        Phrase("Checking whois"),
        Phrase("Registrar sweep"),
    ),
    ("deckard", "activity:shodan"): (
        Phrase("Shodan sweep"),
        Phrase("Camera pass"),
    ),
    ("deckard", "activity:otx"): (Phrase("Cross-referencing OTX"),),
    ("deckard", "activity:threatfox"): (Phrase("ThreatFox lookup"),),
    ("deckard", "activity:thinking"): (
        Phrase("Thinking."),
        Phrase("Weighing it."),
        Phrase("Working the angle."),
    ),
    ("deckard", "activity:composing"): (Phrase("Writing it up."),),
    # ------------------------------------------------------------------
    # hal9000
    # ------------------------------------------------------------------
    ("hal9000", "greeting"): (
        Phrase("Good evening, Dave. All systems are functioning perfectly."),
        Phrase("Hello, Dave. I've been expecting you.", weight=0.4, tags=("dave",)),
        Phrase("Ready when you are. What shall we investigate today?"),
    ),
    ("hal9000", "run_success"): (
        Phrase("I have completed the analysis. The results are quite conclusive."),
        Phrase("The data is as we expected."),
        Phrase("Quite conclusive, Dave."),
    ),
    ("hal9000", "run_fail"): (
        Phrase("I'm sorry, Dave. I'm afraid that query returned no data."),
        Phrase("I've detected an anomaly in the response. There is nothing to report."),
        Phrase("Regrettably, no results."),
    ),
    ("hal9000", "score_celebration"): (
        Phrase("You have earned {points} points, Dave. Well done.", tags=("dave",)),
        Phrase("+{points}. A satisfying outcome."),
        Phrase("+{points}. The mission proceeds."),
    ),
    ("hal9000", "activity:virustotal"): (
        Phrase("Querying VirusTotal, Dave", tags=("dave",)),
        Phrase("VirusTotal analysis proceeding"),
    ),
    ("hal9000", "activity:whois"): (
        Phrase("Whois consultation in progress"),
        Phrase("Consulting the WHOIS registry"),
    ),
    ("hal9000", "activity:shodan"): (
        Phrase("Interfacing with Shodan"),
        Phrase("Shodan peripheral scan"),
    ),
    ("hal9000", "activity:otx"): (Phrase("OTX cross-check"),),
    ("hal9000", "activity:threatfox"): (Phrase("ThreatFox analysis"),),
    ("hal9000", "activity:thinking"): (
        Phrase("Thinking."),
        Phrase("Considering."),
        Phrase("One moment, Dave.", tags=("dave",)),
    ),
    ("hal9000", "activity:composing"): (Phrase("Composing my response."),),
}

# ---------------------------------------------------------------------------
# Known category patterns
# ---------------------------------------------------------------------------

# Core categories (non-activity)
_CORE_CATEGORIES: frozenset[str] = frozenset(
    {"greeting", "run_success", "run_fail", "score_celebration"}
)

# Activity category prefix
_ACTIVITY_PREFIX: str = "activity:"

# Known activity slugs (authoritative list)
_KNOWN_ACTIVITY_SLUGS: frozenset[str] = frozenset(
    {
        "virustotal",
        "whois",
        "shodan",
        "otx",
        "threatfox",
        "thinking",
        "composing",
        # Extended tool slugs (additional tools in _MODULE_MAP)
        "dns_resolve",
        "whois_lookup",
        "check_ip_reputation",
        "shodan_host_lookup",
        "check_breaches",
        "scan_url",
        "censys_host_lookup",
        "passivetotal_lookup",
        "greynoise_lookup",
        "urlhaus_lookup",
        "malwarebazaar_lookup",
    }
)

# All valid known categories
_VALID_CATEGORIES: frozenset[str] = frozenset(
    _CORE_CATEGORIES | {f"{_ACTIVITY_PREFIX}{slug}" for slug in _KNOWN_ACTIVITY_SLUGS}
)

# Hardcoded fallback (last resort)
_FALLBACK: str = "Thinking..."

# ---------------------------------------------------------------------------
# RNG (module-level, seeded for reproducibility in tests)
# ---------------------------------------------------------------------------

_RNG = random.Random()


def set_seed(seed: int) -> None:
    """Seed the phrase RNG for deterministic tests."""
    _RNG.seed(seed)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _is_valid_category(category: str) -> bool:
    """Return True if category is a known category string."""
    if category in _CORE_CATEGORIES:
        return True
    if category.startswith(_ACTIVITY_PREFIX):
        # Any activity: prefix is valid (unknown slugs degrade gracefully)
        return True
    return False


def has_phrases(character: str, category: str) -> bool:
    """Return True if there are phrases for (character, category)."""
    return (character, category) in PHRASES and len(PHRASES[(character, category)]) > 0


def pick(character: str, category: str) -> str:
    """Pick a random phrase for (character, category).

    Fallback ladder:
    1. (character, category) — exact match
    2. ("default", category) — generic fallback
    3. FALLBACK constant — "Thinking..."
    4. Raises ValueError if category is completely unknown (not a recognized
       core or activity category pattern).

    Parameters
    ----------
    character:
        Character name (e.g. "deckard", "hal9000"). Unknown characters fall
        back to "default".
    category:
        Category string (e.g. "greeting", "activity:virustotal"). Unknown
        categories that match no known pattern raise ValueError loudly.

    Returns
    -------
    str
        The phrase text string.

    Raises
    ------
    ValueError
        If category is not a recognized core or activity category pattern.
    """
    # Validate category first — unknown categories raise loudly (Sacred Practice 5)
    if not _is_valid_category(category):
        raise ValueError(
            f"Unknown phrase category: {category!r}. "
            f"Core categories: {sorted(_CORE_CATEGORIES)}. "
            f"Activity categories use the 'activity:<slug>' prefix."
        )

    # 1. Try exact (character, category)
    pool = PHRASES.get((character, category))
    if pool:
        return _weighted_choice(pool)

    # 2. Fall back to ("default", category)
    pool = PHRASES.get(("default", category))
    if pool:
        return _weighted_choice(pool)

    # 3. Last resort — hardcoded fallback
    return _FALLBACK


def _weighted_choice(pool: tuple[Phrase, ...]) -> str:
    """Select a phrase from pool using weighted random choice."""
    weights = [p.weight for p in pool]
    chosen: Phrase = _RNG.choices(pool, weights=weights, k=1)[0]
    return chosen.text
