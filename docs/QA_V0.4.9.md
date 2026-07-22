# v0.4.9 Quality Assurance Record

This record closes W-042-08 for the pre-0.5 release candidate. It records
repeatable gates, not a claim that passing automation proves perfect behavior.

## Automated matrix

- Python behavior: complete `pytest` suite.
- Python quality: repository-wide `ruff check src tests` with no exemptions
  added for this release.
- Pivotglass: TypeScript checking and optimized static Next.js build.
- Character contract: every selectable mode has one matching visual theme,
  cockpit profile, presentation contract, voice policy, repetition budget, and
  procedural-music palette.
- Accessibility: semantic Flint data table, focus-trapped dialogs, compact
  viewport bounds, reduced-motion behavior, and effects-off equivalence.
- Packaging: source distribution and wheel built from the declared backend.
- Supply chain: exact npm lock, registry signatures, available attestations,
  and production advisory audit.

## Manual browser matrix

The production build was exercised at desktop and 320-pixel widths. Checks
covered the DECK and command controls, M4TR1X code-rain/rabbit layer, The Sprawl
grid, generative-music enable and immediate mute, effects-off removal of ambient
layers, menu stacking, feed availability, and absence of horizontal overflow.

## Truthfulness and graceful degradation

- Music begins muted and conveys no evidence, confidence, severity, or hunt
  completion state.
- The terminal reports audio unavailability when no supported local player is
  installed; investigation controls remain independent.
- Visual effects can be reduced or disabled without removing operational state.
- Character narration remains presentation; evidence and inference retain
  their explicit labels and drill-down paths.
