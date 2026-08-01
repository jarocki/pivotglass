# Pivotglass v0.5.1 QA record

> Historical checkpoint. Later release records contain the final broad-suite
> verification for the work that followed this focused pass.

Date: 2026-07-21

## Scope

This release is a focused interaction-density, Help, diversion, and procedural
music correction after manual v0.5.0 use. Three independent read-only reviews
examined progressive disclosure and pointer behavior, Help/navigation and
easter eggs, and both audio renderers before implementation.

## Interaction contracts

- One enrichment source produces one task tile regardless of lifecycle-transition
  count. Its ordered source events remain available in the expanded detail.
- Tile lifecycle is exposed by accessible text and a visible glyph, never RGB
  or motion alone. Twinkle is limited to discovery, contradiction, and source
  fault events; reduced/off effects retain static meaning.
- Hover and keyboard focus expose the same action preview. Enter, Space, click,
  and touch activation use the same semantic button.
- Every primary pane has an explicit collapse button with `aria-expanded` and
  `aria-controls`. State persists locally; pane navigation expands and focuses
  its destination.
- Help is a centered, frontmost dialog whose tasks perform their described
  route. `?` remains ordinary input inside editable controls.
- Flow Dojo is opt-in, bounded, local, keyboard/touch operable, and labeled as
  a diversion with no analytical meaning.

## Music contracts

- Playback remains local, muted by default, operator-controlled, and
  independent of evidence values and investigation ordering.
- The web renderer schedules ahead on Web Audio time and layers drone, bass,
  motif, and countervoice material through presentation phases.
- The terminal renderer deterministically produces a 32-second, 22.05 kHz
  mono movement with four broad sections and bounded amplitude.
- No recording, sample, copied melody, network request, or telemetry is used.

## Verification evidence

- `npm run lint` — TypeScript passes.
- `npm run build` — optimized Next.js export succeeds.
- Focused Python tests — 17 passed across music, QA contracts, and web server.
- Browser — Help opens with executable tasks; typing `?` in the target input
  opens no dialog; Intelligence collapse persists across reload.
- Responsive browser — document width equals client width at 320 pixels and
  1024 pixels; no horizontal page overflow remains.
- Visual inspection — desktop cockpit hierarchy, collapse affordances, dossier
  buttons, and Flint chart remain legible and aligned.

The full repository suite remains required before release publication.
