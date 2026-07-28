# Adversary Pursuit v0.5.2 quality record

**Release date:** 2026-07-28
**Scope:** current TUI and Pivotglass implementation, shared command surface,
workspace/graph/evidence changes, public character system, procedural music,
documentation, and release media.

## Behavioral contracts

- The public deck is Default (Analyst), Chuck Norris, HAL9000, Troll, Sherlock
  Holmes, Neuromancer, and The Matrix; stored legacy identifiers remain
  readable through deterministic migration.
- Pivotglass and the TUI use shared local command completion and deterministic
  routing before model fallback.
- Visible graph/artifact labels are indicators, not STIX IDs.
- Vendor metadata remains additive, source-attributed, and distinguishable from
  inference.
- Character flavor rotates reviewed local lines. The only newly generated
  flavor uses the existing bounded narration call and explicitly cannot add
  evidence, certainty, results, score, or control state.
- Music is opt-in, local, layered, procedural, cross-faded, and presentation
  only. Enabled state survives character changes.

## Verification completed

- Complete Python suite: 3,877 passed, 1 skipped.
- Complete Ruff check: passed.
- Pivotglass TypeScript check and optimized static build: passed.
- Procedural web-music harness: seven deterministic, rhythmically distinct
  character score planners passed.
- Release media: four-frame TUI GIF and seven-frame Pivotglass GIF generated
  from isolated real-interface sessions and visually inspected.

## Release verification

- Git diff whitespace and staged-scope checks: passed.
- Protected design context and the separate `career-narrative/` project are not
  part of the release diff.
