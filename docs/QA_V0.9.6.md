# Pivotglass v0.9.6 quality record

**Release date:** 2026-09-07  
**Release branch:** `codex/v0.9.6-document-pivots`  
**Focus:** governed document admission, persistent source library, workflow
pivot graph/timeline, theme-correct Investigation Constellation, and stable
dense hover interaction

## Candidate verification

| Gate | Receipt |
|---|---|
| Complete Python suite | **4,187 passed, 2 skipped** in 273.57 seconds; one existing SQLite datetime-adapter deprecation warning |
| Python static analysis | Repository-wide Ruff analysis of `src/` and `tests/` passed |
| TypeScript and production export | Next.js lint/type check and production static export passed; `web/out` was regenerated from the matching source |
| Web behavior | Advisor **2 passed**, arcade **6 passed**, visualization policy **5 passed** |
| Dependency integrity | npm reported zero known vulnerabilities; **31** registry signatures and **17** provenance attestations verified |
| Package build | Wheel and source archive built as version 0.9.6 |
| Release contract | Runtime, Python, npm, lock, documentation, and static-export identities agree on 0.9.6 |

## Browser interaction receipt

`scripts/qa_web_v096.mjs` drove installed Chrome through the real local web
service using the Chrome DevTools protocol. It passed **14 character/display
combinations**: Default, Chuck Norris, HAL 9000, Troll, Sherlock Holmes,
Neuromancer, and The Matrix in both Day and Night modes.

For every combination the replay checked theme-owned matrix surfaces, readable
foreground/background contrast tokens, document width, and unchanged matrix
cell geometry during real pointer hover. The tooltip is viewport-fixed and no
longer changes a scroll container's layout, eliminating the former row
"shudder." Full text remains available by keyboard and accessible name.

The same replay performed the complete document workflow through the visible
interface:

1. select and preview a unique local source;
2. inspect the exact SHA-256 and temporary candidates;
3. explicitly ingest that exact preview;
4. observe the admission receipt and persistent Source library entry; and
5. open the Pivot trail and verify the corresponding chronological event.

Responsive replay passed at 320, 1024, and 1440 CSS pixels without horizontal
document overflow. The machine-readable receipt is
[`media/pivotglass-web-qa-v0.9.6.json`](media/pivotglass-web-qa-v0.9.6.json).

## Truth and safety boundaries

- Preview creates no durable record.
- Ingestion is an explicit action bound to the preview SHA-256.
- Stored source bytes and receipts are workspace-owned; browser state never
  receives the stored raw bytes during routine polling.
- Extracted matches remain candidates. Only an independently admitted,
  normalized entity can receive a `matches-admitted-entity` bridge.
- `contains-candidate` is structural, not threat evidence.
- `pivoted-to` and the Pivot trail record analyst navigation, not a threat
  relationship. They are visibly classified as derived navigation.
- Workspace export carries document metadata, receipts, candidates, and pivot
  events. Workspace merge copies raw source bytes only after SHA-256
  verification.

## Current release boundaries

Version 0.9.6 does not claim PDF text extraction/OCR, Office or image parsing,
archive expansion, URL/RSS acquisition, automatic candidate admission, or
Synapse/SCOT as production authorities. Those remain later gates rather than
silent fallbacks.

The current screenshots were captured from this candidate and show the Pursuit
Brief, theme-aware Investigation Constellation, explicit document admission and
library, and chronological Pivot trail. The v0.9.5 guided walkthrough remains a
historical tour of the unchanged core workflow and is labeled as such.
