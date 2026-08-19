# Framework projections

Pivotglass can present the same evidence through different analytical lenses.
The framework projection layer provides one durable contract for ATT&CK,
Cyber Kill Chain, and Diamond Model mappings. These are perspectives over the
workspace evidence—not independent stores of truth.

## What a mapping means

A mapping is a derived analytical view, not an observation. Every mapping
records:

- the framework and pinned content version;
- the framework content identifier and label;
- one or more immutable observation IDs and a plain-language basis;
- mapper identity and mapper version;
- origin (`human`, `automated`, or `model`);
- confidence and its rationale; and
- the current state (`proposed`, `accepted`, `rejected`, `superseded`, or
  `revoked`).

The authority rejects a mapping when any referenced observation does not exist.
Model and automated mappings remain proposals until an analyst dispositions
them. A revoked mapping requires a reason. A projection never creates a
relationship, observation, hypothesis, or confidence assessment in another
part of the workspace.

## Pinned framework content

Pivotglass currently pins Enterprise ATT&CK 19.2 to the official MITRE STIX
bundle and verifies it before use:

```text
URL: https://raw.githubusercontent.com/mitre-attack/attack-stix-data/v19.2/enterprise-attack/enterprise-attack.json
SHA-256: dc1639caa5501d720e280cf1cbd8fbe009884a0c9b3e6e9ed9d0c25166c3d8f4
Local path: ~/.ap/frameworks/enterprise-attack-19.2.json
Navigator layer: 4.5 (Navigator 5.3.2)
```

Pivotglass does not silently download or update this 54 MB content package.
`framework manifest` prints the authoritative URL, digest, and expected local
path. The parser rejects a digest, collection name, or version mismatch and
filters revoked and deprecated ATT&CK content.

The Cyber Kill Chain perspective uses the explicit version label
`lockheed-martin-2011`. A phase assignment does not imply a linear sequence;
only evidence-backed `precedes`, `loops_to`, `parallel_with`, or `ambiguous`
transitions do. The Diamond perspective uses `diamond-model-1.0`, preserves
unknown adversary/capability/infrastructure/victim vertices, and labels an
event provisional until its mappings are accepted.

## Commands

The TUI and shared command adapter expose the current records consistently:

```text
framework manifest
framework list [attack|kill_chain|diamond]
framework show attack [19.2]
framework show kill_chain [lockheed-martin-2011]
framework show diamond [diamond-model-1.0]
framework map <framework> <version> <content-id> <observation-id[,observation-id...]> | <label> | <basis> | <low|moderate|high> | <confidence rationale>
framework accept <mapping-id> | <review note>
framework reject <mapping-id> | <review note>
framework revoke <mapping-id> | <reason>
framework navigator
```

Omit the version from `framework show` to use the pinned default. `framework
navigator` verifies the local ATT&CK bundle, then exports a Navigator 4.5 layer.
Colors distinguish proposed, accepted, rejected, superseded, and revoked
mappings. Layer metadata retains the mapping ID, observation IDs, mapper,
confidence, and content digest.

The Pivotglass web cockpit shows a collapsed aggregate lens—versions plus
accepted/proposed counts—in its normal state. It does not place evidence IDs or
mapping rationales in the continuously polled payload. Opening a perspective
is an explicit command action.

## Migration and exchange

Fresh workspaces use schema v5. Existing workspaces migrate forward with the
same backup-first migration process used by v0.8. The new table is additive and
does not rewrite observations or analytic records. `framework list` exports a
secret-free envelope with schema version `framework-mappings-1.0`.

The remaining 0.9 work connects explicit framework gaps to the scientific
investigation's intelligence-requirement lifecycle and adds read-only
Synapse/SCOT adapters while continuing to use this mapping authority.
