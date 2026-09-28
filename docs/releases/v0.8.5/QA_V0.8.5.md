# Pivotglass v0.8.5 quality record

**Release date:** 2026-08-07
**Release branch:** `codex/v0.8.5-ux-redesign`
**Focus:** cockpit clarity, progressive disclosure, utility status, and
responsive inspector behavior

## Verified

- TypeScript lint: passed.
- Next.js production build: passed on Next.js 16.3.0.
- Advisor idle tests: 2 passed.
- Arcade engine tests: 6 passed.
- Static diff hygiene: `git diff --cached --check` passed.
- `uv lock --check`: passed.
- `npm ci`: passed with the lockfile unchanged.
- Production npm audit: zero vulnerabilities.
- Registry signature audit: 31 verified signatures and 17 attestations.
- Browser verification at the live LAN cockpit confirmed:
  - Pursuit, Dossier, Charts & Evidence, and Service Status navigation;
  - Focus View hides secondary surfaces and Full Cockpit restores them;
  - opening Dossier exits Focus View and keeps the selected pane visible;
  - the Scientific Workbench exposes review sections progressively;
  - desktop document width remains within the viewport.

## Product behavior preserved

Existing command completion, `/`, `F6`, `?`, Escape, URL pane aliases,
evidence detail, exports, configuration, activity filtering, acknowledgement,
and backend analytical state remain unchanged. Utilities and Inspector are
presentation layers; they do not create, alter, or infer evidence.

## Responsive note

The browser viewport override did not produce a true 320px replay in this
environment. The responsive CSS contract, touch-target rules, single-column
breakpoint, and horizontal data-table containment remain covered by the
existing responsive checks. A physical-device 320px walkthrough remains a
follow-on release-quality check.
