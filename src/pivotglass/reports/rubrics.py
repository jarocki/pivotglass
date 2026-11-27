"""The actor capability rubric (#55, type 10).

Scores are only comparable if every analyst means the same thing by a 3. Each
axis defines levels 1 to 5; a score is an analyst claim
(``capability:<axis>``) that cites the evidence for the level chosen.
"""

from __future__ import annotations

RUBRIC_VERSION = "capability-rubric-1.0"

LEVEL_NAMES = {1: "Commodity", 2: "Developing", 3: "Capable", 4: "Advanced", 5: "Tier one"}

CAPABILITY_AXES: dict[str, tuple[str, dict[int, str]]] = {
    "access": (
        "Initial access and exploit development",
        {
            1: "Buys or reuses public access: commodity phishing kits, purchased credentials.",
            2: "Tailors phishing and uses public exploits for known vulnerabilities.",
            3: "Weaponises disclosed vulnerabilities within weeks of disclosure.",
            4: "Weaponises disclosed vulnerabilities within days; occasional zero-day use.",
            5: "Develops or acquires zero-days and uses them repeatedly.",
        },
    ),
    "malware": (
        "Malware engineering",
        {
            1: "Uses unmodified public or commodity malware.",
            2: "Modifies public tooling or uses paid crimeware.",
            3: "Maintains custom tooling with routine updates.",
            4: "Modular, memory-resident implants with custom protocols or encryption.",
            5: "Multiple bespoke frameworks, firmware or supply-chain implants.",
        },
    ),
    "evasion": (
        "Defence evasion and OPSEC",
        {
            1: "No meaningful evasion; reused infrastructure and tooling.",
            2: "Basic obfuscation and packing.",
            3: "Living off the land; log clearing; some infrastructure separation.",
            4: "Disables or blinds security tools (for example vulnerable drivers); strict separation.",
            5: "Sustained anti-forensics and deception; very few attributable mistakes.",
        },
    ),
    "movement": (
        "Lateral movement and persistence",
        {
            1: "Single-host activity with little persistence.",
            2: "Standard persistence and remote tools with stolen credentials.",
            3: "Domain-wide movement with credential theft.",
            4: "Identity-provider and cloud-control-plane abuse; redundant persistence.",
            5: "Persistence that survives rebuilds (firmware, supply chain, trusted relationships).",
        },
    ),
    "infrastructure": (
        "Infrastructure resilience",
        {
            1: "Single servers on mainstream hosting, quickly taken down.",
            2: "Rotating commodity VPS and domains.",
            3: "Tiered infrastructure with redirectors.",
            4: "Compromised relay networks or bulletproof hosting; fast rebuild after takedown.",
            5: "Operational relay networks of compromised devices at scale.",
        },
    ),
}
