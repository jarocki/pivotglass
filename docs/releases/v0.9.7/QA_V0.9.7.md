# Pivotglass v0.9.7 quality record

Date: 2026-09-20

Status: implementation candidate verified; public release media refresh remains
open.

## Scope

This record covers the v0.9.7 Investigate-first document intake, explicit
candidate admission, resilient JSON recognition, interrupted-admission recovery,
and graduated task-relative guidance.

## Automated receipts

- Python static checks: `ruff check .` passed.
- Complete Python regression suite: **4,204 passed, 2 skipped, 1 warning** in
  288.19 seconds.
- Release-critical intake, library, web adapter, release contract, and trust
  matrix: **113 passed**.
- Focused malformed/encoded JSON and admission-recovery set: **34 passed**.
- Guidance placement/profile unit tests: **6 passed**.
- TypeScript: `tsc --noEmit` passed.
- Static web export: `next build` passed and generated all routes.

The one warning is the existing SQLAlchemy notice about Python's deprecated
default SQLite datetime adapter. It is not introduced by v0.9.7 and does not
change a test result.

## Use and abuse cases

The verified cases include:

- JSON detected from content despite a `.txt` name and `text/plain` metadata;
- UTF-8 BOM, UTF-16, and UTF-32 JSON decoding;
- strict JSONL fallback for multiple records in a `.json` file;
- duplicate keys preserved as bounded raw text with a warning rather than
  silently overwritten in the analyst preview;
- malformed JSON retained as bounded, explicitly untrusted text when it remains
  reviewable;
- non-finite `NaN`/`Infinity` values and excessive nesting rejected;
- preview remaining non-persistent;
- tampered selection keys rejected before source storage;
- the original first-100 selection boundary (superseded by the paginated review
  described below);
- source storage surviving an interrupted entity-admission transaction;
- generic browser error text not leaking internal exception details;
- an idempotent retry admitting the reviewed selection without storing another
  source occurrence or duplicating an existing entity; and
- ambiguous requests containing both candidate IDs and selection keys rejected.

## Browser and visual QA

An isolated loopback-only server and disposable synthetic workspace were used;
no user document library, credential, or live target appears in release media.

- At 1,440 × 900, the novice guide computed as `position: fixed`, z-index
  19,000, at y=311 immediately below the focused command area ending at y=301.
- The guide remains inside 320 × 568, 390 × 844, 1,024 × 768, and 1,440 × 900
  viewports in deterministic placement tests.
- The broad page-flow selector explicitly excludes the guide layer. This
  regression guard prevents the guide from falling to the bottom of the
  document again.
- The current screenshot shows an opaque high-contrast card, redundant border
  and label treatment, visible actions, dimmed unrelated content, and a
  non-modal dismissal path.
- A synthetic `provider-export.txt` carrying UTF-8-BOM JSON was correctly
  identified as `application/json`; its bounded preview produced three review
  candidates and no stored source.

Current captures:

- `media/pivotglass-guidance-v0.9.7.png`
- `media/pivotglass-json-intake-v0.9.7.png`

## Constellation clarity review — 2026-09-22

Two virtual UX/human-behavior and visual/accessibility reviewers informed the
redesign. Coverage uses a check, half-circle, open circle, and dash with readable
headings. No analytical policy or evidence record was changed by the redesign.

Verification:

- 97 targeted Python tests passed across visualization intent, UI regression
  contracts, and web API behavior. Socket-backed tests were rerun with local
  socket permission after an initial sandbox-only bind failure.
- Five constellation tests and five visualization tests passed. These cover
  rendered shape differences, accessible labels, malformed/unknown countries,
  tooltip edge placement, and graph/export behavior.
- Automated contrast checks cover all seven character palettes in both Day
  and Night modes: small text at least 4.5:1 and status icons at least 3:1 on
  the grid and highlighted-row backgrounds.
- TypeScript validation and the production static build passed.
- Browser checks used seven synthetic, reserved/example indicators in an
  isolated workspace; no analyst workspace or external intelligence API was used.
- At 320, 1024, and 1440 CSS pixels, the document had no horizontal overflow.
  The narrow grid scrolls internally and retains a 180-pixel indicator column.
- Keyboard End reached the ninth dimension at phone width. The measured
  tooltip remained inside the viewport and described only its owning control.
- Selecting a cell left the table top unchanged at 322.5234375 CSS pixels.
  Details appeared below it; Escape dismissed the tooltip without losing focus.
- Browser QA caught and corrected inherited gray icon colors, maximized-panel
  stacking, focus-transition dimming, and mobile sticky-column expansion.
- Hover explanations are also available by focus and selection. Long tooltip
  content is scrollable; the pointer can cross into the explanation without
  immediate dismissal. Pointer-event lifecycle was reviewed in code; keyboard
  interaction and placement were exercised in the browser.

Current synthetic-data captures:

- `media/pivotglass-constellation-night-v0.9.7.png`
- `media/pivotglass-constellation-day-v0.9.7.png`

This is targeted change verification, not a new full-suite release receipt.

## Mock usability review and implementation — 2026-09-22–23

The [mock study](MOCK_USABILITY_STUDY_V0.9.7.md) documents 24 fictional profiles
and three virtual review lenses. It is not human-participant research. Age,
gender, diagnosis, and design affiliation were not used to predict a person's
behavior, and no human task-time or satisfaction result is claimed.

Implemented findings: modal focus repair, workspace-bound document intake,
50-candidate review pages, explicit library failures/retry, accurate tutorial
destinations, admitted-indicator handoff, visible reporting/export routes,
larger text, optional spotlight, Quiet workspace, and scrollable TUI Help.

Behavior receipts:

- Utilities opens without an inert ancestor; Tab wraps from Close to the first
  control and Shift+Tab wraps back. Escape removes background isolation and
  returns to Deck. No hidden dialog retains input.
- In a disposable synthetic workspace, Preview accepted 121 reserved/example
  domains. Candidate 1 and candidate 121 were selected on separate pages;
  ingestion admitted exactly two entities and retained one source occurrence
  with 121 reviewable candidates. No live enrichment ran.
- The novice Preview action focused `preview-document`. Review candidates
  focused the first checkbox; Choose an added indicator focused the successful
  admission action. Using candidate 121 focused the command with that exact
  value and left activity at zero tasks and zero events.
- More → Export workspace data opened four format choices without exporting.
  More → Create printable report opened a reviewable Dossier report with
  Print / Save PDF; the browser print action was not executed.
- Larger text and Quiet workspace survived reload. Help remained inside the
  320 × 720 viewport, including its close control. At 320, 1024, and 1440 pixels,
  larger-text views had zero horizontal document overflow; the matrix scrolls
  internally. End moved to the ninth dimension at phone width.
- A new real-browser screenshot records the reading controls:
  `media/pivotglass-reading-v0.9.7.png`.
- Real TUI PTYs at 80 × 24 and 120 × 40 checked arrows, Page Up/Down, Home/End,
  mouse-wheel scrolling, visible close instructions, Tab containment, guarded
  typing, and preserved history/command focus. Scrollbar rendering is covered;
  direct scrollbar click/drag was not exercised by this new PTY test.

The first full regression run had one obsolete source-contract assertion that
required tutorials to expand every detail panel. It was replaced with checks
for action-specific navigation; targeted rerun passed. This correction does not
replace the real browser destination checks above.

Final receipts:

- Full Python rerun: **4,216 passed, 2 skipped**, one pre-existing SQLite
  datetime-adapter deprecation warning, in 306.31 seconds.
- Final review then added two Help/Quiet source-contract tests: the complete
  focused UI regression file passed **27 tests**. This was a targeted rerun,
  not another full-suite count.
- Real PTY Help tests rerun after adding explicit Up/Page Up coverage: **2 passed**.
- All frontend behavior tests: **43 passed**, including **19** dedicated
  usability/intake/focus/preference tests.
- Ruff, TypeScript, production static export, and whitespace checks passed.
- Independent final review found and corrected a competing Help focus-restore
  timer and remaining nonessential pulse/guide animations. Browser readback
  confirmed Help → Start focused the non-inert command, Help → Find a control
  retained typed text in the palette, report close restored Deck, and Quiet
  mode gave the guide `animation-name: none`. Pulse suppression also has a
  source-contract guard; an active external enrichment was not started to test it.
- No browser console errors appeared during the final isolated walkthrough.

This is targeted accessibility and interaction assurance, not a screen-reader
certification, recruited usability test, or live-provider integration study.

## Open publication gate

The repository's linked two-minute walkthrough is still explicitly labeled
v0.9.5. It must be recaptured from the v0.9.7 synthetic workflow, captioned,
transcribed, and read back before the v0.9.7 tag or GitHub Release is presented
as complete. Existing historical media must not be renamed to imply current
coverage.
