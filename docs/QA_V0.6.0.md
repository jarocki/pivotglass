# Pivotglass v0.6.0 quality record

> Development checkpoint. No public `v0.6.0` tag was created; this work is
> included in the v0.7.0 release.

**Release date:** 2026-07-30
**Scope:** semantic visual analysis, relationship exploration, fog atmosphere,
command-completion stacking, replayable character diversions, static-delivery
freshness, and synchronized operator documentation.

## Behavioral contracts

- Python owns the deterministic analyst-question and visualization-intent
  policy. Flint 0.3.0 compiles supported semantic charts; native views cover
  calendar, task-matrix, and force-directed graph interactions.
- The relationship graph labels actual observables, draws only stored
  relationships or explicitly labeled conservative property pivots, and keeps
  every exact row available in the accessible table and export.
- Cross-type records with the same normalized observable value are linked as
  `same-observable-value` property pivots. They are navigation aids, not
  asserted STIX facts.
- Command completion is the topmost ordinary cockpit interaction while focused.
  Dialogs retain the higher modal layer.
- Fog remains behind evidence and focus indicators. Reduced motion freezes a
  faint band; disabled effects remove it.
- Arcade randomness is local presentation state and cannot change evidence,
  confidence, dossier, commands, or investigation state.
- An editable checkout refuses to launch a stale static export. Exported web
  assets are served without browser caching.

## Automated verification

- Focused visualization, graph, web-server, stale-export, release-matrix, and
  version tests: passed.
- Arcade engine: 6 tests passed, including 800 generated Neuromancer maps with
  reachable data and exit objectives.
- Complete Python suite: 3,888 passed, 2 skipped.
- Ruff, TypeScript, and optimized Next.js static build: passed.
- npm vulnerability audit: 0 vulnerabilities.
- npm supply-chain check: all 31 packages have verified registry signatures;
  17 also have verified attestations.
- Both `ap --version` and `.venv/bin/ap --version`: `0.6.0`.
- Export freshness check: source export selected and not stale.

## Browser interaction QA

The rebuilt export was exercised through the same local server used by `ap`.

- The Visual Analysis pane is expanded after the one-time migration and opens
  on the Flint-compiled dossier radar.
- The default workspace rendered a force-directed graph with 48 visible nodes
  and 48 provenance-labeled property edges. Zoom changed the graph transform
  from scale 1.0 to 1.2; maximize used the current viewport without document
  overflow.
- The completion menu was tested at its physical overlap with Systems. Browser
  hit-testing identified the completion button as the topmost target.
- The full-motion fog band measured approximately 101 pixels high at desktop
  size. Reduced motion removed animation, lowered opacity, and retained a
  stationary 108-pixel ambient band.
- Neuromancer opened as a 5×5 level-one run with score, data objective, trace
  budget, ICE, cache, and jackpoint. **Burn ID / New Run** produced a different
  layout.
- At 320×800, the arcade dialog remained inside the viewport and scrolled
  internally; the underlying cockpit had no horizontal overflow. The same
  no-overflow condition passed at 1024×768 and desktop size.

## Review provenance and deferred human testing

The arcade review used five synthetic gamer perspectives, not claimed human
participants. Findings and remaining real-world test needs are recorded in
[`reviews/V0.6_ARCADE_SYNTHETIC_PLAYTEST.md`](reviews/V0.6_ARCADE_SYNTHETIC_PLAYTEST.md).
