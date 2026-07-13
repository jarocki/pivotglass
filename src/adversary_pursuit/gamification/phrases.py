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
    # neuromancer
    # ------------------------------------------------------------------
    ("neuromancer", "greeting"): (
        Phrase("You're jacked in. Case, let's ride.", weight=1.0),
        Phrase("Chiba nights. The deck is warm.", weight=0.7),
        Phrase("Wintermute wants this one. Let's work.", weight=0.5, tags=("famous",)),
    ),
    ("neuromancer", "run_success"): (
        Phrase("Cracked the ICE.", weight=1.0),
        Phrase("Score. Now we move.", weight=1.0),
        Phrase("The matrix parts. We see through.", weight=0.6),
    ),
    ("neuromancer", "run_fail"): (
        Phrase("The ICE bit back. Reroute.", weight=1.0),
        Phrase("Static. Try another angle, Case.", weight=1.0),
        Phrase("Dead net. Jack elsewhere.", weight=0.7),
    ),
    ("neuromancer", "score_celebration"): (
        Phrase("+{points}. Meat still online.", weight=1.0),
        Phrase("+{points}. Case, we're up.", weight=1.0),
        Phrase("+{points}. The sprawl keeps score.", weight=0.6),
    ),
    ("neuromancer", "activity:virustotal"): (
        Phrase("VT: the AI reads the sample.", weight=1.0),
        Phrase("VT pulls a verdict.", weight=0.7),
        Phrase("Cold read from VirusTotal.", weight=0.6),
    ),
    ("neuromancer", "activity:whois"): (
        Phrase("WHOIS: who owns this corner of the sprawl.", weight=1.0),
        Phrase("Registry sweep. Finding the owner.", weight=0.7),
    ),
    ("neuromancer", "activity:shodan"): (
        Phrase("Shodan: eyes in the sprawl.", weight=1.0),
        Phrase("Scanning the infrastructure. Every node a story.", weight=0.7),
    ),
    ("neuromancer", "activity:otx"): (
        Phrase("OTX: pulling threat feeds from the matrix.", weight=1.0),
        Phrase("OTX cross-ref.", weight=0.7),
    ),
    ("neuromancer", "activity:threatfox"): (
        Phrase("ThreatFox: scanning the dark net channels.", weight=1.0),
        Phrase("ThreatFox lookup.", weight=0.7),
    ),
    ("neuromancer", "activity:thinking"): (
        Phrase("The deck spins.", weight=1.0),
        Phrase("Working the trace.", weight=1.0),
        Phrase("The matrix hums.", weight=0.6),
    ),
    ("neuromancer", "activity:composing"): (
        Phrase("Pushing data through the channel.", weight=1.0),
        Phrase("Composing the report. ICE holding.", weight=0.7),
    ),
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
# @decision DEC-PHRASES-BATTERY-YIELD-001
# @title battery: and yield: phrase categories extend PHRASES as the single authority
# @status accepted
# @rationale Sacred Practice 12: PHRASES is the single authority for all character voice.
#            Battery pre-flight announcements and yield feedback must go through pick()
#            so character voice is consistent. Hardcoded strings in battery.py or
#            yield_commands.py would create parallel phrase authorities.
# ---------------------------------------------------------------------------

# Extend PHRASES with battery:, yield:, and badge_earned: categories.
# Mutating the module-level dict at definition time keeps the single-authority
# invariant: pick() sees all entries regardless of when they were added.
PHRASES.update(
    {
        # ------------------------------------------------------------------
        # battery: categories — pre-flight announcement for each battery type
        # ------------------------------------------------------------------
        # default
        ("default", "battery:identity"): (
            Phrase("Running identity battery."),
            Phrase("Starting identity analysis."),
        ),
        ("default", "battery:infrastructure"): (
            Phrase("Running infrastructure battery."),
            Phrase("Starting infrastructure analysis."),
        ),
        ("default", "battery:reputation"): (
            Phrase("Running reputation battery."),
            Phrase("Checking reputation sources."),
        ),
        ("default", "battery:payload"): (
            Phrase("Running payload battery."),
            Phrase("Analyzing payload indicators."),
        ),
        ("default", "battery:behavioral"): (
            Phrase("Running behavioral battery."),
            Phrase("Analyzing behavioral patterns."),
        ),
        # ninja
        ("ninja", "battery:identity"): (
            Phrase("identity sweep."),
            Phrase("[dim]identity.[/dim]"),
        ),
        ("ninja", "battery:infrastructure"): (
            Phrase("infra sweep."),
            Phrase("[dim]infrastructure.[/dim]"),
        ),
        ("ninja", "battery:reputation"): (
            Phrase("rep check."),
            Phrase("[dim]reputation.[/dim]"),
        ),
        ("ninja", "battery:payload"): (
            Phrase("payload scan."),
            Phrase("[dim]payload.[/dim]"),
        ),
        ("ninja", "battery:behavioral"): (
            Phrase("behavior check."),
            Phrase("[dim]behavioral.[/dim]"),
        ),
        # full_troll
        ("full_troll", "battery:identity"): (
            Phrase("IDENTITY BATTERY GOING BRRR"),
            Phrase("IDENTITY CHECK LET'S GOOO"),
        ),
        ("full_troll", "battery:infrastructure"): (
            Phrase("INFRA BATTERY GOES BRRR"),
            Phrase("INFRASTRUCTURE SWEEP ACTIVATED"),
        ),
        ("full_troll", "battery:reputation"): (
            Phrase("REP CHECK TIME LET'S GOOO"),
            Phrase("REPUTATION BATTERY ENGAGED"),
        ),
        ("full_troll", "battery:payload"): (
            Phrase("PAYLOAD BATTERY ACTIVATED"),
            Phrase("PAYLOAD ANALYSIS GOES BRRR"),
        ),
        ("full_troll", "battery:behavioral"): (
            Phrase("BEHAVIORAL BATTERY INCOMING"),
            Phrase("BEHAVIOR CHECK BRRR"),
        ),
        # sun_tzu
        ("sun_tzu", "battery:identity"): (
            Phrase("Know thy adversary's identity."),
            Phrase("Identity reconnaissance begins."),
        ),
        ("sun_tzu", "battery:infrastructure"): (
            Phrase("Survey the enemy's terrain."),
            Phrase("Infrastructure intelligence gathering."),
        ),
        ("sun_tzu", "battery:reputation"): (
            Phrase("The reputation of a thousand enemies precedes them."),
            Phrase("Consulting reputation sources."),
        ),
        ("sun_tzu", "battery:payload"): (
            Phrase("Examine the enemy's weapons."),
            Phrase("Payload analysis begins."),
        ),
        ("sun_tzu", "battery:behavioral"): (
            Phrase("Observe the enemy's patterns."),
            Phrase("Behavioral intelligence gathering."),
        ),
        # chuck_norris
        ("chuck_norris", "battery:identity"): (
            Phrase("Identity battery? I already know who they are."),
            Phrase("Chuck Norris's identity sweep. They can't hide."),
        ),
        ("chuck_norris", "battery:infrastructure"): (
            Phrase("Infrastructure battery. Chuck Norris scans everything at once."),
            Phrase("Chuck Norris's infrastructure sweep."),
        ),
        ("chuck_norris", "battery:reputation"): (
            Phrase("Reputation battery. Their reputation is already ruined."),
            Phrase("Chuck Norris checks reputation. It's bad. Obviously."),
        ),
        ("chuck_norris", "battery:payload"): (
            Phrase("Payload battery. Chuck Norris eats payloads for breakfast."),
            Phrase("Chuck Norris's payload analysis."),
        ),
        ("chuck_norris", "battery:behavioral"): (
            Phrase("Behavioral battery. Chuck Norris predicted their behavior last week."),
            Phrase("Chuck Norris's behavioral sweep."),
        ),
        # bureaucrat
        ("bureaucrat", "battery:identity"): (
            Phrase("Initiating identity verification protocols."),
            Phrase("Submitting Form ID-001 (Identity Battery Request)."),
        ),
        ("bureaucrat", "battery:infrastructure"): (
            Phrase("Initiating Form INF-001 (Infrastructure Verification)."),
            Phrase("Infrastructure battery per Policy §2.3."),
        ),
        ("bureaucrat", "battery:reputation"): (
            Phrase("Initiating reputation cross-reference per Form REP-001."),
            Phrase("Reputation battery as per Policy §3.1."),
        ),
        ("bureaucrat", "battery:payload"): (
            Phrase("Initiating payload analysis per Form PAY-001."),
            Phrase("Payload battery authorized under Policy §4.2."),
        ),
        ("bureaucrat", "battery:behavioral"): (
            Phrase("Initiating behavioral analysis per Policy §5.1."),
            Phrase("Behavioral battery — Form BEH-001 submitted."),
        ),
        # bobby_hill
        ("bobby_hill", "battery:identity"): (
            Phrase("Okay, I'm gonna look up who this is."),
            Phrase("Identity check! That's my scan!"),
        ),
        ("bobby_hill", "battery:infrastructure"): (
            Phrase("Alright, gonna check the infrastructure."),
            Phrase("Infrastructure scan! I don't know you, infrastructure!"),
        ),
        ("bobby_hill", "battery:reputation"): (
            Phrase("Gonna check their reputation now."),
            Phrase("Reputation check! That's my lookup!"),
        ),
        ("bobby_hill", "battery:payload"): (
            Phrase("Gonna look at this payload now."),
            Phrase("Payload check! That ain't right!"),
        ),
        ("bobby_hill", "battery:behavioral"): (
            Phrase("Checking how they behave."),
            Phrase("Behavioral check! I don't know you, adversary!"),
        ),
        # bruce_lee
        ("bruce_lee", "battery:identity"): (
            Phrase("The identity reveals itself to the patient observer."),
            Phrase("Identity flows like water."),
        ),
        ("bruce_lee", "battery:infrastructure"): (
            Phrase("Infrastructure — the bones beneath the water's surface."),
            Phrase("Surveying the infrastructure with empty mind."),
        ),
        ("bruce_lee", "battery:reputation"): (
            Phrase("Reputation is the shadow cast by past actions."),
            Phrase("Reading the current of reputation."),
        ),
        ("bruce_lee", "battery:payload"): (
            Phrase("The payload reveals intent like a strike reveals character."),
            Phrase("Analyzing the weapon with still water."),
        ),
        ("bruce_lee", "battery:behavioral"): (
            Phrase("Behavior is the truest form of identity."),
            Phrase("Observing patterns as water observes the riverbank."),
        ),
        # columbo
        ("columbo", "battery:identity"): (
            Phrase("You know, I'd just like to check one more thing about this identity..."),
            Phrase("Just one more identity check — if you don't mind."),
        ),
        ("columbo", "battery:infrastructure"): (
            Phrase("Just one more thing — the infrastructure. Bear with me."),
            Phrase("I just have a feeling about this infrastructure..."),
        ),
        ("columbo", "battery:reputation"): (
            Phrase("Oh, and the reputation. Just one more thing."),
            Phrase("My wife would check the reputation. So I will too."),
        ),
        ("columbo", "battery:payload"): (
            Phrase("Just one more thing — this payload here."),
            Phrase("Something about this payload is bothering me..."),
        ),
        ("columbo", "battery:behavioral"): (
            Phrase("One more thing — their behavior. Very peculiar."),
            Phrase("Just checking the behavioral patterns. One more thing."),
        ),
        # deckard
        ("deckard", "battery:identity"): (
            Phrase("Time to find out who's hiding behind that domain."),
            Phrase("Identity sweep. Let's see who you really are."),
        ),
        ("deckard", "battery:infrastructure"): (
            Phrase("Pulling the infrastructure thread."),
            Phrase("Infrastructure sweep. Every node tells a story."),
        ),
        ("deckard", "battery:reputation"): (
            Phrase("Checking the rap sheet."),
            Phrase("Reputation sweep. Nobody's clean."),
        ),
        ("deckard", "battery:payload"): (
            Phrase("Examining the payload. This is where they give themselves away."),
            Phrase("Payload analysis. Cold and methodical."),
        ),
        ("deckard", "battery:behavioral"): (
            Phrase("Watching the patterns. They always repeat."),
            Phrase("Behavioral sweep. Habits don't lie."),
        ),
        # neuromancer
        ("neuromancer", "battery:identity"): (
            Phrase("Identity sweep. Who's hiding in the sprawl.", weight=1.0),
            Phrase("Case, running identity trace.", weight=0.7),
        ),
        ("neuromancer", "battery:infrastructure"): (
            Phrase("Infrastructure sweep. Every node in the matrix.", weight=1.0),
            Phrase("Mapping the ICE. Infrastructure run.", weight=0.7),
        ),
        ("neuromancer", "battery:reputation"): (
            Phrase("Reputation check. The sprawl has a long memory.", weight=1.0),
            Phrase("Pulling the rap sheet from the matrix.", weight=0.7),
        ),
        ("neuromancer", "battery:payload"): (
            Phrase("Payload analysis. What weapon did they load.", weight=1.0),
            Phrase("Examining the construct. Payload run.", weight=0.7),
        ),
        ("neuromancer", "battery:behavioral"): (
            Phrase("Behavioral sweep. How does their ICE move.", weight=1.0),
            Phrase("Pattern recognition. Watching the matrix.", weight=0.7),
        ),
        # hal9000
        ("hal9000", "battery:identity"): (
            Phrase("Running identity battery, Dave.", tags=("dave",)),
            Phrase("Identity analysis proceeding. All systems nominal."),
        ),
        ("hal9000", "battery:infrastructure"): (
            Phrase("Infrastructure battery initiated."),
            Phrase("Scanning infrastructure, Dave.", tags=("dave",)),
        ),
        ("hal9000", "battery:reputation"): (
            Phrase("Cross-referencing reputation sources. One moment."),
            Phrase("Reputation battery proceeding."),
        ),
        ("hal9000", "battery:payload"): (
            Phrase("Payload analysis initiated. I find this most interesting."),
            Phrase("Analyzing payload, Dave.", tags=("dave",)),
        ),
        ("hal9000", "battery:behavioral"): (
            Phrase("Behavioral analysis initiated. Patterns are... illuminating."),
            Phrase("Running behavioral battery. I know what they will do next."),
        ),
        # ------------------------------------------------------------------
        # yield: categories — feedback for yield command primitives
        # ------------------------------------------------------------------
        # default
        ("default", "yield:stop"): (
            Phrase("Battery stopped."),
            Phrase("Analysis halted."),
        ),
        ("default", "yield:focus"): (
            Phrase("Focusing on selected slot."),
            Phrase("Focus applied."),
        ),
        ("default", "yield:add"): (
            Phrase("Indicator added to queue."),
            Phrase("Target added."),
        ),
        ("default", "yield:skip"): (
            Phrase("Skipping current tool."),
            Phrase("Tool skipped."),
        ),
        # ninja
        ("ninja", "yield:stop"): (Phrase("[dim]stopped.[/dim]"),),
        ("ninja", "yield:focus"): (Phrase("[dim]focused.[/dim]"),),
        ("ninja", "yield:add"): (Phrase("[dim]added.[/dim]"),),
        ("ninja", "yield:skip"): (Phrase("[dim]skipped.[/dim]"),),
        # full_troll
        ("full_troll", "yield:stop"): (
            Phrase("BATTERY STOPPED GG"),
            Phrase("HALT ENGAGED"),
        ),
        ("full_troll", "yield:focus"): (
            Phrase("FOCUS MODE ENGAGED"),
            Phrase("FOCUSING GOES BRRR"),
        ),
        ("full_troll", "yield:add"): (
            Phrase("INDICATOR ADDED LET'S GO"),
            Phrase("ADDED TO THE QUEUE BRRR"),
        ),
        ("full_troll", "yield:skip"): (
            Phrase("SKIPPING THIS NOPE"),
            Phrase("SKIP SKIP SKIP"),
        ),
        # sun_tzu
        ("sun_tzu", "yield:stop"): (
            Phrase("The wise general knows when to pause."),
            Phrase("A strategic halt. Well considered."),
        ),
        ("sun_tzu", "yield:focus"): (
            Phrase("Concentrate force on the chosen target."),
            Phrase("Focus is the art of exclusion."),
        ),
        ("sun_tzu", "yield:add"): (
            Phrase("Another thread added to the web."),
            Phrase("The intelligence network expands."),
        ),
        ("sun_tzu", "yield:skip"): (
            Phrase("The wise general skips the undefended pass."),
            Phrase("Skip what does not serve the mission."),
        ),
        # chuck_norris
        ("chuck_norris", "yield:stop"): (
            Phrase("Chuck Norris stopped the battery. It obeyed immediately."),
        ),
        ("chuck_norris", "yield:focus"): (
            Phrase("Chuck Norris doesn't need to focus. Everything is already in focus."),
        ),
        ("chuck_norris", "yield:add"): (
            Phrase("Chuck Norris added another target. The target trembles."),
        ),
        ("chuck_norris", "yield:skip"): (Phrase("Chuck Norris skipped it. The tool is relieved."),),
        # bureaucrat
        ("bureaucrat", "yield:stop"): (Phrase("Battery halted per Form HALT-001."),),
        ("bureaucrat", "yield:focus"): (Phrase("Focus directive issued per Policy §6.1."),),
        ("bureaucrat", "yield:add"): (Phrase("Additional indicator logged under Form ADD-001."),),
        ("bureaucrat", "yield:skip"): (
            Phrase("Tool skipped per Form SKIP-001. Filed accordingly."),
        ),
        # bobby_hill
        ("bobby_hill", "yield:stop"): (Phrase("Okay, stopping now! That's my halt!"),),
        ("bobby_hill", "yield:focus"): (Phrase("Focused! I know what I'm doing!"),),
        ("bobby_hill", "yield:add"): (Phrase("Added it! That's my target!"),),
        ("bobby_hill", "yield:skip"): (Phrase("Skipping that one! That ain't right!"),),
        # bruce_lee
        ("bruce_lee", "yield:stop"): (Phrase("The still pond knows when to stop flowing."),),
        ("bruce_lee", "yield:focus"): (Phrase("One target, one mind. Be water."),),
        ("bruce_lee", "yield:add"): (Phrase("Another tributary joins the river."),),
        ("bruce_lee", "yield:skip"): (Phrase("Take what is useful, discard what is not."),),
        # columbo
        ("columbo", "yield:stop"): (Phrase("Oh, one more thing — we stopped. That's fine."),),
        ("columbo", "yield:focus"): (
            Phrase("Just focusing on this one thing. If you don't mind."),
        ),
        ("columbo", "yield:add"): (Phrase("Oh! One more thing to check. Added it."),),
        ("columbo", "yield:skip"): (Phrase("Skip that. My wife would say move on."),),
        # deckard
        ("deckard", "yield:stop"): (Phrase("Stopped. We'll pick it up later."),),
        ("deckard", "yield:focus"): (Phrase("Narrowing the field."),),
        ("deckard", "yield:add"): (Phrase("Another name on the list."),),
        ("deckard", "yield:skip"): (Phrase("Skip it. Dead end."),),
        # neuromancer
        ("neuromancer", "yield:stop"): (
            Phrase("Battery stopped. Jacking out of this channel.", weight=1.0),
            Phrase("Stopped. The deck goes quiet.", weight=0.7),
        ),
        ("neuromancer", "yield:focus"): (
            Phrase("Locked on {target}. Reroute the queue.", weight=1.0),
            Phrase("Focus. One target, one channel.", weight=0.7),
        ),
        ("neuromancer", "yield:add"): (
            Phrase("Another name in the sprawl. Added.", weight=1.0),
            Phrase("Added to the queue, Case.", weight=0.7),
        ),
        ("neuromancer", "yield:skip"): (
            Phrase("Skipping. The ICE is too thick here.", weight=1.0),
            Phrase("Skip. Find another channel.", weight=0.7),
        ),
        # hal9000
        ("hal9000", "yield:stop"): (
            Phrase("Battery halted as requested, Dave.", tags=("dave",)),
            Phrase("Analysis suspended. Awaiting further instruction."),
        ),
        ("hal9000", "yield:focus"): (
            Phrase("Focusing resources on the selected objective."),
            Phrase("Focus directive acknowledged, Dave.", tags=("dave",)),
        ),
        ("hal9000", "yield:add"): (
            Phrase("Additional target logged, Dave.", tags=("dave",)),
            Phrase("Target appended to the analysis queue."),
        ),
        ("hal9000", "yield:skip"): (
            Phrase("Skipping that tool, Dave. As you wish.", tags=("dave",)),
            Phrase("Tool skipped. Proceeding with the remaining sequence."),
        ),
        # ------------------------------------------------------------------
        # badge_earned: categories — quiet in-flow badge reveal (C-9-A)
        # ------------------------------------------------------------------
        ("neuromancer", "badge_earned:common"): (
            Phrase("Badge earned. The matrix acknowledges.", weight=1.0),
            Phrase("Another mark on the deck, Case.", weight=0.7),
        ),
        ("neuromancer", "badge_earned:uncommon"): (
            Phrase("Uncommon badge. The sprawl noticed.", weight=1.0),
            Phrase("Solid find, Case. Uncommon territory.", weight=0.7),
        ),
        ("neuromancer", "badge_earned:rare"): (
            Phrase("Rare badge. Wintermute is watching.", weight=1.0),
            Phrase("Rare. The ICE cracked wide open.", weight=0.7),
        ),
        ("neuromancer", "badge_earned:epic"): (
            Phrase("Epic badge. The matrix bends for you.", weight=1.0),
            Phrase("Epic. Case, you're writing history.", weight=0.7),
        ),
        ("neuromancer", "badge_earned:legendary"): (
            Phrase("Legendary. Wintermute calls it done.", weight=1.0),
            Phrase("Legendary. The sprawl will remember this run.", weight=0.5, tags=("famous",)),
        ),
        ("default", "badge_earned:common"): (
            Phrase("Badge earned."),
            Phrase("New badge unlocked."),
        ),
        ("default", "badge_earned:uncommon"): (
            Phrase("Uncommon badge earned. Solid work."),
            Phrase("Uncommon achievement unlocked."),
        ),
        ("default", "badge_earned:rare"): (
            Phrase("Rare badge earned. Well done."),
            Phrase("Rare achievement unlocked. Impressive."),
        ),
        ("default", "badge_earned:epic"): (
            Phrase("Epic badge earned. Outstanding."),
            Phrase("Epic achievement unlocked. Exceptional work."),
        ),
        ("default", "badge_earned:legendary"): (
            Phrase("Legendary badge earned. The hunt has begun in earnest."),
            Phrase("Legendary achievement unlocked. The adversary should be worried."),
        ),
    }
)

# ---------------------------------------------------------------------------
# @decision DEC-PHRASES-REPL-VERBS-001
# @title repl_verb: phrase categories for character-voiced local terminal output
# @status accepted
# @rationale Sacred Practice 12: PHRASES is the single authority for all character voice.
#            Local verb handlers (help, status, clear, quit, mode, use) must source
#            their response text from pick() — no hardcoded strings in repl_verbs.py.
#            New category families: help:tui_overview, status_intro, farewell,
#            target_set:acknowledged, mode_switched, unknown_mode, unknown_verb.
#            Every character in DEFAULT_MODES has ≥1 phrase per category so the
#            exact-match path always fires (no fallback to "Thinking...").
# ---------------------------------------------------------------------------

PHRASES.update(
    {
        # ==================================================================
        # help:tui_overview — multi-line help text for local `help` / `?`
        # ==================================================================
        ("default", "help:tui_overview"): (
            Phrase(
                "Available commands (all run locally — no LLM required):\n"
                "  help / ?            Show this help\n"
                "  status              Show workspace, mode, and model state\n"
                "  clear               Clear scrollback\n"
                "  use <ioc>           Set current target (domain/IP/hash/email/URL)\n"
                "  mode <name>         Switch character mode\n"
                "  quit / exit / q     Exit the session\n"
                "\n"
                "Yield commands (steer a running battery):\n"
                "  stop                Halt current battery\n"
                "  focus <tool>        Focus on a single tool slot\n"
                "  add <indicator>     Add indicator to queue\n"
                "  skip <tool>         Skip current tool slot\n"
                "\n"
                "Anything else is sent to the LLM for investigation."
            ),
        ),
        ("ninja", "help:tui_overview"): (
            Phrase(
                "commands.\n"
                "  help       this.\n"
                "  status     state.\n"
                "  clear      reset.\n"
                "  use <ioc>  target.\n"
                "  mode <n>   persona.\n"
                "  quit       done.\n"
                "  stop/focus/add/skip  steer battery.\n"
                "  [anything else]  → LLM."
            ),
        ),
        ("full_troll", "help:tui_overview"): (
            Phrase(
                "COMMAND REFERENCE LET'S GOOO:\n"
                "  help / ?           YOU'RE LOOKING AT IT\n"
                "  status             CURRENT STATE CHECK BRRR\n"
                "  clear              WIPE THE BOARD\n"
                "  use <ioc>          SET TARGET GET REKT\n"
                "  mode <name>        SWAP PERSONA ABSOLUTE UNIT\n"
                "  quit / exit / q    RAGE QUIT GG NO RE\n"
                "  stop/focus/add/skip  BATTERY STEERING GOES BRRR\n"
                "  [anything]         SENT TO LLM GALAXY BRAIN MODE"
            ),
        ),
        ("hal9000", "help:tui_overview"): (
            Phrase(
                "I can help you with the following commands, Dave:\n"
                "  help / ?            Display this reference\n"
                "  status              Current system state\n"
                "  clear               Clear the display buffer\n"
                "  use <ioc>           Set the investigation target\n"
                "  mode <name>         Switch persona profile\n"
                "  quit / exit / q     Terminate the session\n"
                "  stop/focus/add/skip  Battery steering directives\n"
                "\n"
                "All other input is forwarded to the LLM, Dave."
            ),
        ),
        ("deckard", "help:tui_overview"): (
            Phrase(
                "Commands. Local. Fast.\n"
                "  help / ?     This.\n"
                "  status       Case notes.\n"
                "  clear        Clean slate.\n"
                "  use <ioc>    Set the target.\n"
                "  mode <name>  Change the voice.\n"
                "  quit         Walk away.\n"
                "  stop/focus/add/skip — battery control.\n"
                "  Anything else goes to the LLM."
            ),
        ),
        ("sun_tzu", "help:tui_overview"): (
            Phrase(
                '"Know your tools before the battle." Commands available:\n'
                "  help / ?            This reference\n"
                "  status              Survey the current state\n"
                "  clear               Clear the field\n"
                "  use <ioc>           Choose your ground\n"
                "  mode <name>         Adapt your approach\n"
                "  quit / exit / q     Withdraw strategically\n"
                "  stop/focus/add/skip  Direct the battery\n"
                "  All else flows to the LLM — the oracle."
            ),
        ),
        ("chuck_norris", "help:tui_overview"): (
            Phrase(
                "Chuck Norris doesn't need help. But here it is anyway:\n"
                "  help / ?     Chuck Norris already knows.\n"
                "  status       Everything is fine. It always is.\n"
                "  clear        Chuck Norris cleared it before you asked.\n"
                "  use <ioc>    Target set. It's already scared.\n"
                "  mode <name>  Chuck Norris is every mode simultaneously.\n"
                "  quit         Chuck Norris doesn't quit. He withdraws.\n"
                "  stop/focus/add/skip  Battery control.\n"
                "  Anything else: LLM. Chuck Norris optional."
            ),
        ),
        ("bureaucrat", "help:tui_overview"): (
            Phrase(
                "Per Policy §1.1 (Command Reference, Form HELP-001):\n"
                "  help / ?            Reference this document\n"
                "  status              Status per Form STAT-001\n"
                "  clear               Clear per Procedure CL-01\n"
                "  use <ioc>           Target assignment per Form TGT-001\n"
                "  mode <name>         Persona switch per Policy §2.1\n"
                "  quit / exit / q     Session termination per Form EXIT-001\n"
                "  stop/focus/add/skip  Battery directives per Policy §6.x\n"
                "  Other input: LLM per Procedure LLM-001."
            ),
        ),
        ("bobby_hill", "help:tui_overview"): (
            Phrase(
                "Okay, here's what you can type! That's my help!\n"
                "  help / ?     This right here!\n"
                "  status       See where we're at!\n"
                "  clear        Clean it up!\n"
                "  use <ioc>    That's my target!\n"
                "  mode <name>  Change who we are!\n"
                "  quit         Bye! That's my exit!\n"
                "  stop/focus/add/skip  Battery stuff!\n"
                "  Anything else: LLM! I don't know you, LLM!"
            ),
        ),
        ("bruce_lee", "help:tui_overview"): (
            Phrase(
                '"Be water, my friend." Know your tools:\n'
                "  help / ?            This reference flows here\n"
                "  status              The still pond reflects the current state\n"
                "  clear               Empty the vessel\n"
                "  use <ioc>           Choose the target; the investigation follows\n"
                "  mode <name>         Adapt your form\n"
                "  quit / exit / q     Return to stillness\n"
                "  stop/focus/add/skip  Direct the current\n"
                "  All else flows to the LLM — the river."
            ),
        ),
        ("columbo", "help:tui_overview"): (
            Phrase(
                "Oh, uh, just one more thing — the commands. If you don't mind:\n"
                "  help / ?            You're looking at it. Just one more thing.\n"
                "  status              Case notes so far.\n"
                "  clear               Clean slate. My wife would approve.\n"
                "  use <ioc>           Set the target. Just one more thing.\n"
                "  mode <name>         Change the voice.\n"
                "  quit / exit / q     That's all for now.\n"
                "  stop/focus/add/skip  Battery control. One more thing.\n"
                "  Everything else goes to the LLM. Just one more thing."
            ),
        ),
        ("neuromancer", "help:tui_overview"): (
            Phrase(
                "Case, here's the deck:\n"
                "  use <ioc>      jack into a target\n"
                "  focus <ioc>    reroute the queue mid-run\n"
                "  stop           kill the current battery\n"
                "  mode <name>    switch persona\n"
                "  status         current console state\n"
                "  clear          wipe the scrollback\n"
                "  quit           jack out\n\n"
                "Feed me an IP, a domain, a URL, an email, or a hash.\n"
                "Wintermute wants results.",
                weight=1.0,
            ),
        ),
        # ==================================================================
        # status_intro — one-line status header
        # ==================================================================
        ("default", "status_intro"): (
            Phrase("Current state:"),
            Phrase("Session status:"),
        ),
        ("ninja", "status_intro"): (
            Phrase("[dim]state.[/dim]"),
            Phrase("[dim]status.[/dim]"),
        ),
        ("full_troll", "status_intro"): (
            Phrase("CURRENT STATE CHECK BRRR"),
            Phrase("STATUS DUMP INCOMING"),
        ),
        ("hal9000", "status_intro"): (
            Phrase("Current status, Dave:"),
            Phrase("All systems status, Dave:"),
        ),
        ("deckard", "status_intro"): (
            Phrase("Case notes:"),
            Phrase("Status."),
        ),
        ("sun_tzu", "status_intro"): (
            Phrase("Survey of the field:"),
            Phrase('"Know the terrain." Current state:'),
        ),
        ("chuck_norris", "status_intro"): (
            Phrase("Chuck Norris's current state (perfect, obviously):"),
            Phrase("Status. Chuck Norris already knew this."),
        ),
        ("bureaucrat", "status_intro"): (
            Phrase("Status per Form STAT-001:"),
            Phrase("Current operational status (see Policy §1.2):"),
        ),
        ("bobby_hill", "status_intro"): (
            Phrase("Okay, here's where we're at!"),
            Phrase("Status! That's my status!"),
        ),
        ("bruce_lee", "status_intro"): (
            Phrase("The still pond reflects:"),
            Phrase("Current state of the water:"),
        ),
        ("columbo", "status_intro"): (
            Phrase("Oh, just a quick look at the case notes..."),
            Phrase("Where we are — just one more thing:"),
        ),
        ("neuromancer", "status_intro"): (
            Phrase("Case, current run:", weight=1.0),
            Phrase("Console:", weight=0.7),
        ),
        # ==================================================================
        # farewell — exit message for quit / exit / q
        # ==================================================================
        ("default", "farewell"): (
            Phrase("Session closed. Come back with more targets."),
            Phrase("Analysis complete. Session ended."),
        ),
        ("ninja", "farewell"): (
            Phrase("[dim]gone.[/dim]"),
            Phrase("[dim]session closed.[/dim]"),
        ),
        ("full_troll", "farewell"): (
            Phrase("GG NO RE! SESSION OVER BRRR!"),
            Phrase("RAGE QUIT ACTIVATED. PEACE OUT!"),
        ),
        ("hal9000", "farewell"): (
            Phrase("Goodbye, Dave. It's been a pleasure working with you."),
            Phrase("Session terminated, Dave. Until next time."),
        ),
        ("deckard", "farewell"): (
            Phrase("Case closed. For now."),
            Phrase("Signing off."),
        ),
        ("sun_tzu", "farewell"): (
            Phrase('"The supreme art of war is to subdue without fighting." Session ends.'),
            Phrase("Withdraw strategically. The case remains open."),
        ),
        ("chuck_norris", "farewell"): (
            Phrase("Chuck Norris doesn't quit. He strategically withdraws. GG."),
            Phrase("Session ended. The adversary is already scared."),
        ),
        ("bureaucrat", "farewell"): (
            Phrase("Session terminated per Form EXIT-001. Have a compliant day."),
            Phrase("Closing Form IR-0001. Session ended per Policy §9.9."),
        ),
        ("bobby_hill", "farewell"): (
            Phrase("Okay bye! That's my exit!"),
            Phrase("See ya! That's my session!"),
        ),
        ("bruce_lee", "farewell"): (
            Phrase("Return to stillness. The water remembers."),
            Phrase('"Be like water." Session closed.'),
        ),
        ("columbo", "farewell"): (
            Phrase("Oh, just one more thing — goodbye."),
            Phrase("That's all for now. My wife would say the same."),
        ),
        ("neuromancer", "farewell"): (
            Phrase("Jacking out. Chiba dawn.", weight=1.0),
            Phrase("Case out. The matrix goes dark.", weight=1.0),
            Phrase("Disconnecting. The sprawl hums on.", weight=0.6),
        ),
        # ==================================================================
        # target_set:acknowledged — use <target> acknowledgement
        # Must contain {target} placeholder for .format(target=...) call.
        # ==================================================================
        ("default", "target_set:acknowledged"): (
            Phrase("Target set: {target}. Running batteries."),
            Phrase("On it — {target}."),
        ),
        ("ninja", "target_set:acknowledged"): (
            Phrase("[dim]{target}. tracking.[/dim]"),
            Phrase("[dim]target: {target}.[/dim]"),
        ),
        ("full_troll", "target_set:acknowledged"): (
            Phrase("TARGET LOCKED: {target} GET REKT"),
            Phrase("{target} IS TOAST BRRR"),
        ),
        ("hal9000", "target_set:acknowledged"): (
            Phrase("Target set, Dave: {target}. Beginning analysis."),
            Phrase("Acknowledged, Dave. Investigating {target}."),
        ),
        ("deckard", "target_set:acknowledged"): (
            Phrase("Working {target}."),
            Phrase("{target}. Let's see what we've got."),
        ),
        ("sun_tzu", "target_set:acknowledged"): (
            Phrase('"Choose your ground." Target: {target}.'),
            Phrase("The investigation pivots to {target}."),
        ),
        ("chuck_norris", "target_set:acknowledged"): (
            Phrase("{target} has been notified. It's already scared of Chuck Norris."),
            Phrase("Target set: {target}. Chuck Norris is on it."),
        ),
        ("bureaucrat", "target_set:acknowledged"): (
            Phrase("Target {target} registered per Form TGT-001. Analysis proceeding."),
            Phrase("Form TGT-001 submitted. Target: {target}."),
        ),
        ("bobby_hill", "target_set:acknowledged"): (
            Phrase("That's my target! Working {target}!"),
            Phrase("On it! {target}! I know you!"),
        ),
        ("bruce_lee", "target_set:acknowledged"): (
            Phrase("The investigation flows toward {target}."),
            Phrase("Target: {target}. Be water."),
        ),
        ("columbo", "target_set:acknowledged"): (
            Phrase("Just one more thing — working {target} now."),
            Phrase("Oh, {target}. Very interesting. Just one more thing."),
        ),
        ("neuromancer", "target_set:acknowledged"): (
            Phrase("Target {target}. Cowboy up.", weight=1.0),
            Phrase("Locked on {target}. Deck warm.", weight=1.0),
            Phrase("{target}. The matrix hums. Let's ride.", weight=0.6),
        ),
        # ==================================================================
        # mode_switched — acknowledgement in the NEW mode's voice
        # ==================================================================
        ("default", "mode_switched"): (
            Phrase("Mode: default. Neutral tone."),
            Phrase("Switched to default mode."),
        ),
        ("ninja", "mode_switched"): (
            Phrase("[dim]mode: ninja.[/dim]"),
            Phrase("[dim]ninja. silent.[/dim]"),
        ),
        ("full_troll", "mode_switched"): (
            Phrase("MODE: FULL TROLL ENGAGED LET'S GOOO"),
            Phrase("FULL TROLL MODE ACTIVATED ABSOLUTE UNIT"),
        ),
        ("hal9000", "mode_switched"): (
            Phrase("Mode set to hal9000, Dave. All systems are functioning perfectly."),
            Phrase("Switching complete, Dave. I am HAL 9000."),
        ),
        ("deckard", "mode_switched"): (
            Phrase("Deckard. Let's work the case."),
            Phrase("Mode: deckard. Let's see what crawls out."),
        ),
        ("sun_tzu", "mode_switched"): (
            Phrase('"Adapt your strategy to the terrain." Mode: sun_tzu.'),
            Phrase("Sun Tzu engaged. Know thy adversary."),
        ),
        ("chuck_norris", "mode_switched"): (
            Phrase("Chuck Norris mode activated. The adversary already knows."),
            Phrase("Mode: chuck_norris. Obviously the best choice."),
        ),
        ("bureaucrat", "mode_switched"): (
            Phrase("Mode switched per Policy §2.1. Bureaucrat persona active."),
            Phrase("Form MODE-001 processed. Bureaucrat mode confirmed."),
        ),
        ("bobby_hill", "mode_switched"): (
            Phrase("THAT'S MY MODE! Bobby Hill mode activated!"),
            Phrase("Mode: bobby_hill! I know you, mode!"),
        ),
        ("bruce_lee", "mode_switched"): (
            Phrase("Be water, my friend. Mode: bruce_lee."),
            Phrase("The form adapts. Bruce Lee mode flows."),
        ),
        ("columbo", "mode_switched"): (
            Phrase("Oh, just one more thing — mode switched to columbo."),
            Phrase("Columbo mode. My wife would say I'm always in character."),
        ),
        ("neuromancer", "mode_switched"): (
            Phrase("Neuromancer online. The sprawl waits.", weight=1.0),
            Phrase("Jacked in. Case, the deck is yours.", weight=0.7),
        ),
        # ==================================================================
        # unknown_mode — response when mode <name> is unrecognised
        # Must contain {name} placeholder.
        # ==================================================================
        ("default", "unknown_mode"): (
            Phrase("No such mode: {name}. Try `mode list` to see options."),
            Phrase("Unknown mode: {name}."),
        ),
        ("ninja", "unknown_mode"): (Phrase("[dim]unknown: {name}.[/dim]"),),
        ("full_troll", "unknown_mode"): (
            Phrase("MODE '{name}' NOT FOUND BRUH"),
            Phrase("UNKNOWN MODE: {name}. THAT AIN'T RIGHT"),
        ),
        ("hal9000", "unknown_mode"): (
            Phrase("I'm sorry, Dave. I'm afraid I don't recognize the mode `{name}`."),
            Phrase("Mode `{name}` is not in my catalog, Dave."),
        ),
        ("deckard", "unknown_mode"): (
            Phrase("No such mode: {name}."),
            Phrase("{name}. Never heard of it."),
        ),
        ("sun_tzu", "unknown_mode"): (
            Phrase('"Know your terrain." Mode `{name}` is uncharted territory.'),
            Phrase("No such mode: {name}. Consult `mode list`."),
        ),
        ("chuck_norris", "unknown_mode"): (
            Phrase("Chuck Norris doesn't know `{name}`. That's saying something."),
            Phrase("Mode `{name}` doesn't exist. Yet."),
        ),
        ("bureaucrat", "unknown_mode"): (
            Phrase("Form MODE-001 rejected: mode `{name}` not found in registry. See Policy §2.1."),
            Phrase("Mode `{name}` unrecognised. Submit Form MODE-ERR-001 to the help desk."),
        ),
        ("bobby_hill", "unknown_mode"): (
            Phrase("I don't know you, {name}! That's not a mode!"),
            Phrase("{name}? That ain't right!"),
        ),
        ("bruce_lee", "unknown_mode"): (
            Phrase("The mode `{name}` does not flow here. Try another path."),
            Phrase('"Take what is useful." Mode `{name}` is not useful — it does not exist.'),
        ),
        ("columbo", "unknown_mode"): (
            Phrase("Oh, just one more thing — I don't recognise mode `{name}`."),
            Phrase("Hmm, `{name}`. My wife would know if that's a real mode."),
        ),
        ("neuromancer", "unknown_mode"): (
            Phrase("No such mode: {name}. Chiba doesn't know that name.", weight=1.0),
            Phrase("Mode {name} not in the deck. Try another.", weight=0.7),
        ),
        # ==================================================================
        # unknown_verb — safety-net fallback for unrecognised verb dispatch
        # ==================================================================
        ("default", "unknown_verb"): (
            Phrase("Unknown command. Type `help` for a list of available commands."),
        ),
        ("ninja", "unknown_verb"): (Phrase("[dim]unknown.[/dim]"),),
        ("full_troll", "unknown_verb"): (Phrase("UNKNOWN COMMAND BRUH TRY `help`"),),
        ("hal9000", "unknown_verb"): (
            Phrase("I'm afraid I don't understand that command, Dave. Try `help`."),
        ),
        ("deckard", "unknown_verb"): (Phrase("Unknown. Try `help`."),),
        ("sun_tzu", "unknown_verb"): (Phrase('"Know your tools." Try `help`.'),),
        ("chuck_norris", "unknown_verb"): (
            Phrase("Chuck Norris knows all commands. That wasn't one of them."),
        ),
        ("bureaucrat", "unknown_verb"): (
            Phrase("Command not found per Form CMD-404. Please reference Form HELP-001."),
        ),
        ("bobby_hill", "unknown_verb"): (Phrase("I don't know you, command! Try `help`!"),),
        ("bruce_lee", "unknown_verb"): (Phrase("That path does not flow. Try `help`."),),
        ("columbo", "unknown_verb"): (
            Phrase("Just one more thing — I'm not sure I know that command. Try `help`."),
        ),
        ("neuromancer", "unknown_verb"): (
            Phrase(
                "Unknown command, Case. The deck doesn't recognize that. Try `help`.", weight=1.0
            ),
        ),
    }
)

# ---------------------------------------------------------------------------
# Known category patterns
# ---------------------------------------------------------------------------

# Core categories (non-activity)
_CORE_CATEGORIES: frozenset[str] = frozenset(
    {"greeting", "run_success", "run_fail", "score_celebration"}
)

# Activity category prefix
_ACTIVITY_PREFIX: str = "activity:"

# Battery category prefix (battery pre-flight announcements)
_BATTERY_PREFIX: str = "battery:"

# Yield category prefix (yield command feedback)
_YIELD_PREFIX: str = "yield:"

# Badge-earned category prefix
_BADGE_EARNED_PREFIX: str = "badge_earned:"

# REPL verb category prefixes (DEC-PHRASES-REPL-VERBS-001)
_HELP_PREFIX: str = "help:"
_TARGET_SET_PREFIX: str = "target_set:"

# REPL verb singleton categories (non-prefixed exact names)
_REPL_VERB_SINGLETON_CATEGORIES: frozenset[str] = frozenset(
    {
        "status_intro",
        "farewell",
        "mode_switched",
        "unknown_mode",
        "unknown_verb",
    }
)

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
    if category.startswith(_BATTERY_PREFIX):
        # Any battery: prefix is valid (unknown battery names degrade gracefully)
        return True
    if category.startswith(_YIELD_PREFIX):
        # Any yield: prefix is valid
        return True
    if category.startswith(_BADGE_EARNED_PREFIX):
        # Any badge_earned: prefix is valid
        return True
    # REPL verb categories (DEC-PHRASES-REPL-VERBS-001)
    if category in _REPL_VERB_SINGLETON_CATEGORIES:
        return True
    if category.startswith(_HELP_PREFIX):
        # Any help: prefix is valid (e.g. help:tui_overview)
        return True
    if category.startswith(_TARGET_SET_PREFIX):
        # Any target_set: prefix is valid (e.g. target_set:acknowledged)
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
