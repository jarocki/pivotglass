# Pivotglass v0.9.3 quality record

**Release date:** 2026-08-31

**Release branch:** `codex/v0.9.3-ingestion`

**Focus:** exact-location entity candidates and longitudinal graph-cluster
change

## Candidate verification

- Complete Python suite: **4,122 passed, 2 skipped**. The one warning is the
  existing Python 3.12+ SQLite datetime-adapter deprecation exercised by the
  schema-v7 presentation-layout reconciliation test; it is not a failure.
- Repository-wide Python static analysis across `src/`, `tests/`, and
  `scripts/`: passed.
- Exact-span extraction, schema migration, workspace, and cluster-history
  focused suite: **102 passed**.
- Shared Pivotglass/TUI snapshot command and web regressions: **105 passed**.
- Python static analysis for all added and affected modules passed.
- Release-contract version synchronization passed.
- TypeScript and five visualization-behavior tests passed; the Next.js 16.3.0
  production static export passed and was regenerated.
- Production npm vulnerability audit reported zero known vulnerabilities.
- Wheel and source archive built as
  `adversary_pursuit-0.9.3-py3-none-any.whl` and
  `adversary_pursuit-0.9.3.tar.gz`.

The npm signature audit and clean-checkout launch remain frozen-candidate
gates. They are not counted here until they run against the complete v0.9.3
change set.

## Extraction receipt

- Plain IPv4/IPv6 addresses, domains, HTTP(S) URLs, email addresses,
  MD5/SHA-1/SHA-256 values, CVE identifiers, and ATT&CK technique identifiers
  use versioned deterministic rules.
- Each candidate identifies its exact document occurrence and parser receipt,
  raw value, normalized value, parser-output character and UTF-8 byte offsets,
  start/end line and column, bounded context, rule ID/version, and any
  normalization caveat.
- Rule precedence prevents a domain nested inside an extracted URL or email
  from becoming an unexplained duplicate candidate.
- Candidate and extraction-receipt identifiers are content/configuration
  stable. Repeating a pass reuses persisted results.
- Invalid IP addresses are rejected. Candidate-count exhaustion becomes an
  explicit partial result rather than silent omission.
- Embedded URL credentials remain in the immutable source text but are removed
  from the normalized candidate with a visible normalization note.
- Extraction writes no STIX object, observation, relationship, graph node,
  confidence assessment, verdict, behavior mapping, or actor attribution.

## Longitudinal receipt

- Snapshot capture uses the canonical graph repository and the stable evidence
  cluster projection. Node and edge limits are checked before persistence.
- Diff output separates added, removed, and changed entity-layer nodes and
  relationships, then reports changes in exact cluster membership.
- Only explicit governed `contradicts`/`contradiction` edges appear under
  recorded contradictions. Unrelated graph differences are not relabeled as
  analytical conflict.
- Snapshot writes are presentation history. They do not rewrite evidence or
  framework mapping state.
- Local snapshot capture/list/diff is implemented in both command interfaces.
  SCOT publication and live Synapse-backed comparison remain preview gates.

## Migration receipt

- Workspace schema v9 migrates backup-first to v10.
- The new extraction-receipt, candidate, and cluster-snapshot tables are
  additive; prior document receipts, STIX evidence, graph edges, scientific
  records, framework mappings, and layouts are not rewritten.
