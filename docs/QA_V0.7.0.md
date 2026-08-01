# Pivotglass v0.7.0 quality record

**Release date:** 2026-08-01
**Scope:** semantic visualization, relationship exploration, the persistent
Investigation Constellation, model and API configuration, expanded character
arcades, current documentation, and the guided demonstration.

## Behavioral contracts

- Deterministic code and direct APIs own evidence collection, state changes,
  graph relationships, and standard chart selection. Model output may explain
  evidence, but it cannot create telemetry or rewrite stored evidence.
- Visual Analysis begins with an analyst question. Every chart identifies its
  source scope and missing-data treatment, includes an accessible exact-data
  table, and exports the values that were plotted.
- The relationship graph shows actual indicator values and only admits stored,
  provenance-backed relationships. Moving a node changes presentation, not
  evidence.
- The Investigation Constellation keeps one row per stored indicator and one
  column per canonical Dossier dimension. Blank cells expose uncertainty; they
  are not silently filled.
- Ordinary configuration reads expose masked state only. A newly entered secret
  exists transiently in the masked field and explicit local save or test
  request; stored secrets are not returned by polling, logged, exported, or
  sent to a model.
- Character narration, music, and games remain presentation. They do not add
  evidence, trigger background provider requests, or take command focus.

## Automated verification

- Complete Python suite: **3,907 passed, 2 skipped**.
- Ruff over product source and tests: passed.
- TypeScript checking and optimized Next.js **16.2.12** static build: passed.
- Arcade engine: **6 passed**, including deterministic variation and 800
  generated Neuromancer maps with a reachable objective.
- npm dependency audit: **0 vulnerabilities**.
- npm supply-chain verification: all **31 packages** have verified registry
  signatures; **17** have verified attestations.
- Source, Python package, web package, lockfiles, and installed `ap` entry point
  agree on version **0.7.0**.
- Python source distribution and wheel builds completed successfully from the
  release tree.
- All repository Markdown files in the root and `docs/` pass the local-link
  check.
- Git whitespace validation passes.

The release suite originally exposed a test that patched one temporary WHOIS
module instance while the product correctly created another instance for the
actual run. The test now patches the module class boundary, preventing an
accidental external WHOIS request and making both success-gate cases
deterministic.

## Interface review

- Command completion renders above Systems, Intelligence, and maximized panes;
  dialogs remain above completion.
- The screen atmosphere is a broad, soft fog band behind evidence and focus
  indicators. Reduced-motion mode pauses it.
- Visual Analysis exposes the Dossier radar view, UTC activity heatmap,
  distribution views, Investigation Constellation, and force-directed
  relationship graph with plain-language scope and caveats.
- Configuration and model views keep stored credentials masked, distinguish
  configuration from verified access, and show provider-visible models without
  inventing quality claims.
- The current cockpit, model catalog, Constellation, graph, and report states
  were reviewed at 910×512 in both the guided demonstration and release
  screenshots.

## Documentation and media

- README, Quick Start, User Guide, documentation index, changelog, historical
  plan headers, music guide, supply-chain record, generated decision index, and
  command help were reconciled with the executable behavior.
- Historical 0.6 documents are labeled as development checkpoints rather than
  public releases. The last public tag before this release was v0.5.2.
- The guided demonstration uses synthetic investigation data and a mock model
  provider. Its narration explicitly separates the demonstration from a live
  intelligence-provider result.
- Guided video: H.264/AAC, 910×512, approximately 132 seconds.
- Video SHA-256:
  `aa20111d2a12bdf63381c1ced3a21aca0dbc3b969a6e7e07f468bc7b0b366a85`.
- A poster image, accessible transcript, and five task-specific screenshots are
  included beside the video in `docs/media/`.

## Release disposition

Pivotglass v0.7.0 is suitable for early availability. The 0.6 development
checkpoints are consolidated into this release rather than published as
separate tags.
