# Pivotglass v0.6.1 quality record

> Development checkpoint. No public `v0.6.1` tag was created; this work is
> included in the v0.7.0 release.

**Release date:** 2026-07-30
**Scope:** shared model/API configuration, account-visible model catalog,
operational enable/disable controls, character-voiced configuration guidance,
completion-menu stacking, and the persistent Investigation Constellation.

## Behavioral contracts

- Pivotglass, the terminal cyberdeck, and shared completion grammar use one
  local model/configuration command authority.
- `model show`, repair, enable/disable, and masked configuration reads make no
  provider or model request.
- A provider is contacted only after an explicit check, list, selection, or
  Save + Test action.
- Model selection accepts only an identifier returned by that provider.
- Capability notes distinguish provider visibility, local metadata, and
  unknown suitability; they are not model-quality rankings.
- Disabled model synthesis cannot call the model. Disabled intelligence
  services are blocked before credential resolution while their stored
  credentials remain intact.
- Configuration polling returns only masked state. Password fields begin empty,
  and environment-owned credentials are read-only. A newly entered secret exists
  transiently in the password field and explicit local save/test request; stored
  secrets are not repopulated, logged, exported, or sent to a model.
- Character configuration suggestions are throttled local narration. They spend
  no tokens, make no provider request, add no evidence, and never take focus.
- Command completion has an explicit stacking layer above Systems,
  Intelligence, and maximized panes. Viewport dialogs remain above completion.
- Constellation state is derived from persistent stored indicators and the
  canonical nine-dimension Dossier inference authority, not transient enrichment
  jobs. Each row includes the indicator and evidence in its direct graph
  neighborhood; filtering and coverage use only admitted graph edges.
- The initial stack is newest last-seen first. Search, IoC type, mapped
  completeness, first/last seen, related indicator, and sort controls change
  presentation only.

## Automated verification

- Focused model control, configuration, web server, credential gating, command
  completion, static delivery, and release-matrix tests: passed.
- Complete Python suite: 3,905 passed, 2 skipped.
- Ruff over product source and tests: passed.
- TypeScript checking and optimized Next.js 16.2.12 static build: passed.
- Arcade engine: 6 tests passed.
- npm vulnerability audit: 0 vulnerabilities.
- npm supply-chain verification: all 31 packages have verified registry
  signatures; 17 have verified attestations.
- Both source and installed entry points report `0.6.1`.

## Browser interaction QA

The static export was exercised through the same loopback server used by `ap`.

- `model show` opened a deterministic command result with effective provider,
  model, selection source, masked credential source, enabled state, and advisor
  state. No model was invoked.
- The Configuration center opened in the current viewport, focused its Close
  control, trapped keyboard navigation, closed with Escape, and restored focus
  to its opener.
- All password fields were empty even where stored credentials existed; the
  page source and live DOM contained no credential values.
- At 320×800 the Configuration center stayed fully inside the viewport,
  scrolled internally, and caused no horizontal document overflow.
- The shared completion route returned `model check` for `model ch`.
- With the full completion menu crossing Systems and Intelligence, browser
  hit-testing at three overlap points resolved to completion rows. Computed
  layers were 12,001 for completion, 12,000 for its focused command rail, and
  1 for Systems; the completion background was fully opaque.
- The asynchronous suggestion appeared as character-labeled Configuration
  Advisor narration, without opening a dialog or moving focus.
- Visual Analysis opened to the Investigation Constellation with all 452 stored
  indicators and all nine Dossier dimensions (4,068 cells) in the default
  workspace. The initial sort was newest last-seen first.
- Filtering to `domain-name` produced 287 matching indicators; filtering by a
  selected directly related indicator produced two evidence-backed neighbors.
  Reset restored the complete stack.
- At 320×800 the sort/filter controls collapsed to one readable column, the
  matrix scrolled within its pane, and document horizontal overflow remained
  zero.
- No rendered user-facing text contained the retired active-contact term;
  Enrichment Bay, Enrichment Activity, and Indicator enrichment activity were
  visible instead.
