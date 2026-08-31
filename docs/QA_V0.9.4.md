# Pivotglass v0.9.4 quality record

**Release date:** 2026-08-31

**Release branch:** `codex/v0.9.4-proposals`

**Focus:** span-grounded entity, relationship, and candidate-behavior
proposals with human review authority

## Candidate verification

- Complete Python suite: **4,128 passed, 2 skipped**. The one warning is the
  existing Python 3.12+ SQLite datetime-adapter deprecation exercised by the
  schema-v7 presentation-layout reconciliation test; it is not a failure.
- Repository-wide Python static analysis across `src/`, `tests/`, and
  `scripts/`: passed.
- Proposal, exact-span extraction, document intake, workspace, and migration
  focused suite: **108 passed**.
- Python static analysis for every added and affected module passed.
- Release-contract version synchronization passed.
- TypeScript and five visualization-behavior tests passed; the Next.js 16.3.0
  production static export passed and was regenerated.
- Production npm vulnerability audit reported zero known vulnerabilities.
- Wheel and source archive built as
  `adversary_pursuit-0.9.4-py3-none-any.whl` and
  `adversary_pursuit-0.9.4.tar.gz`.

The npm signature audit and clean-checkout launch remain open until they run
against the frozen candidate.

## Proposal receipt

- Every proposal cites 1–100 real candidate IDs from the current workspace.
  Source citations preserve document occurrence, parser receipt, raw and
  normalized value, character and UTF-8 byte spans, line and column, context,
  and extraction rule/version.
- Model-origin proposals require provider/model identifiers and lowercase
  SHA-256 prompt/response receipts. Raw model prompts and responses are not
  stored by this authority.
- Relationship proposals require two distinct cited candidate endpoints,
  relation, and rationale.
- Behavior proposals require a behavior description. ATT&CK identifiers are
  syntax checked and paired with the pinned 19.2 version, but remain
  `unverified_candidate_reference` until content and evidence mapping review.
- No-match behavior is labeled `unmatched_candidate_behavior` with an explicit
  warning that it is not an automatically discovered TTP.
- Identical proposals are idempotent; human dispositions are append-only.

## Human authority receipt

- A proposal cannot be dispositioned unless the caller asserts an explicit
  human decision and supplies a reviewer and reason.
- Acceptance additionally requires at least one admitted evidence-observation
  reference, one alternative explanation, a formal low/moderate/high
  confidence level, and confidence rationale.
- Unknown evidence references fail closed.
- Acceptance does not materialize or publish the proposal. Graph and framework
  authorities remain separate.

## Migration receipt

- Workspace schema v10 migrates backup-first to v11.
- Proposal records and dispositions are additive. Existing documents,
  candidates, evidence, graphs, framework mappings, and presentations are not
  rewritten.
