# Pivotglass v0.9.9 qualification checkpoint

Date: 2026-09-28. This is a candidate checkpoint, not a public-release receipt.
The requested natural Descript voice and synchronized final video remain an
open acceptance gate. No v0.9.9 tag or public release is claimed here.

## Completed checks

- Full Python suite: **4,272 passed, 2 skipped**, one SQLite datetime-adapter
  deprecation warning, in 230.20 seconds. Loopback HTTP tests ran with socket
  permission. The earlier sandbox failures and stale banner-width tests were
  corrected before this run.
- Browser suite including Markdown save: **58 passed**; TypeScript checks and
  the production static export passed. The new backend report-metadata test
  passed and preserves the original workspace/version after a workspace switch.
- The actual browser exposes both **PRINT / SAVE PDF** and **SAVE MARKDOWN**.
  Clicking Save Markdown produced no download-handler JavaScript error.
  DOM-boundary tests validate the exact UTF-8 Markdown Blob, MIME, sanitized
  filename, anchor click, and cleanup. The in-app automation did not expose a
  saved-file receipt; destination-file delivery is not claimed verified.
- Ruff, whitespace checks, synchronized v0.9.9 version surfaces, frozen lock
  validation/sync, and release-contract check against public v0.9.8 passed.
- Advisory audits: **74 applicable locked Python dependencies**, zero reported
  vulnerabilities or skipped packages; npm reports zero known vulnerabilities.
  These are dated advisory checks, not proof of security.
- npm verification: **31 registry signatures and 18 attestations** verified.
- [Documentation inventory](DOCUMENTATION_INVENTORY.json): **83 public Markdown
  files**, zero broken local targets/anchors. Expert and newcomer review records
  describe substantive review and its limits.
- Candidate wheel and source archive built. An isolated wheel install reports
  `pivotglass 0.9.9` and exposes the actual renamed command/help surfaces.
  Unconstrained wheel dependency resolution is a compatibility smoke check;
  use the frozen tagged source for the qualified dependency set.

## Actual interaction and recovery evidence

The isolated synthetic browser case was created without provider or model calls.
The analyst completed the six-question Novice coach, explicitly recorded an
unknown origin, edited and saved a question, and recorded a practice reflection.
The workbench retained competing explanations and an unresolved contradiction.

A local synthetic document was previewed and its two selected candidates were
explicitly admitted together. The source survived a service restart. History
shows document admission, an analyst group, and the two candidate branches. The
relationship graph shows six entities plus a group, three stored edges and two
analyst-group edges; the long URL wraps completely. Grouping is not a common-
control judgment. The joint-admission state/degree failure discovered during
this exercise was fixed and covered by service-level regression tests.

The browser command recorded an explicit ledger evidence link and rationale,
without collection, a model call, or mutation of the underlying observation.
The regenerated report retained questions, alternatives, evidence links,
contradictions, collection requirements, and uncertainty. File values now show
hashes/names instead of backend IDs.

The operations recovery recipe was executed on an isolated backup copy; it
validated schema, SQLite integrity, and original-document hashes. A tampered
source was rejected while the original backup remained unchanged. See the
[expert receipt](EXPERT_EDITORIAL_REVIEW.md).

## Media acceptance and publication remain open

The working visuals and script were checked against actual UI captures. The
first system-speech rendition was rejected by the owner and its audio removed
from the working video. It is not the accepted final demonstration.

The silent visuals were imported into a private, separate Descript v0.9.9
project. The request for natural neural/LLM narration and scene-by-scene timing
was blocked by the account's AI-credit limit. Final voice quality, synchronization,
captions, export decode, and playback must be checked after that limit is resolved.
The earlier HTML player checks validate the Play/Pause/chapter approach, not
completion of the replacement voice requirement.

The configured pre-push guard passed for the proposed main update at candidate
commit `943e1da`. A fresh wheel and source archive built from that commit contain
the Save Markdown interface and all eight public marketing files; protected
design context and the separate career project are excluded. These are package
verification files, not final signed release artifacts.

Final immutable artifacts, the owner signature, final publication guard
execution, public main/tag/release, and downloaded readback remain publication
gates. Do not reuse the preliminary package files as signed release artifacts.
No social post, Signal message, or jarocki.org update has been sent.

The separate v1.0.0 assurance pass and owner approval remain future work.

See [completion matrix](COMPLETION_MATRIX.md), [newcomer review](NEWCOMER_REVIEW.md),
[release trust](../../RELEASE_TRUST.md), and [compatibility](../../COMPATIBILITY.md).
