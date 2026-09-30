# Pivotglass v0.9.9 qualification checkpoint

Date: 2026-09-29. This is a candidate checkpoint, not a public-release receipt.
The earlier Descript edit was accepted as a starting point. The new four-film
revision passed complete decode and timing checks; the owner subsequently
approved the videos and logo. No v0.9.9 tag or public release is claimed here.

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
- [Documentation inventory](DOCUMENTATION_INVENTORY.json): **84 public Markdown
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

## Media recovery history and open publication gate

The working visuals and script were checked against actual UI captures. The
first system-speech rendition was rejected by the owner and its audio removed
from the working video. It is not the accepted final demonstration.

The silent visuals were imported into a private, separate Descript v0.9.9
project. The first requests were blocked by the account's AI-credit limit. An
owner-requested retry cleared that limit and generated an opening preview using
Descript's Jesse neural voice. Inspection of the private preview export found
black video during the opening narration: speech had been inserted before the
visual instead of overlaid on it. That preview does not satisfy synchronization.

Seventeen separate actual scene clips, including the current Save Markdown
report controls, were imported into a new composition in the same private
project. Its first full export fixed the blank video opening but contained only
silence: decoded AAC had mean and maximum volume of -91 dB across 259.2 seconds.
The Descript agent's claim that timed scratch text proved generated speech was
contradicted by that artifact. This export was rejected.

Direct inspection of the Descript editor exposed the actual synthesis error:
the entire narration was one speech block, too long to generate. Inserting real
paragraph breaks between the 17 chapters in Write mode and finishing that edit
generated 17 new audio assets. The new private audio export is 300.16 seconds,
with mean volume -18.7 dB and maximum -0.4 dB; it is no longer silent. Final
visual and caption timing must use this generated speech, not the rejected
259.2-second scratch timings. Oversized burned captions from that rejected
export were removed after a visual review found obstruction and rendering
artifacts. Current report and Nightgrid captures now visibly identify the
export buttons and selected persona.
At that intermediate checkpoint, voice quality, synchronization, captions,
export decode, and playback remained open. The replacement verification below
records which checks subsequently passed; owner listening review was still open
at that checkpoint and was later approved.
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

The separate v1.0.0 assurance pass is now recorded in the
[final assurance review](FINAL_ASSURANCE_REVIEW.md); owner approval and public
release remain open.

See [completion matrix](COMPLETION_MATRIX.md), [newcomer review](NEWCOMER_REVIEW.md),
[release trust](../../RELEASE_TRUST.md), and [compatibility](../../COMPATIBILITY.md).

## Replacement media verification — 2026-09-29

The repository candidate now uses the actual 300.16-second Descript Jesse AAC narration. Seventeen actual UI stills follow generated speech chapter durations. The report capture displays both export buttons; the final capture names Nightgrid. This is an edited walkthrough, not a continuous screen recording.

FFprobe confirms H.264 at 1280 × 816 and AAC. Complete FFmpeg decode passed: mean audio -18.7 dB, maximum -0.4 dB; no detected one-second black interval or one-second silence at -45 dB. The 68 external caption cues retain all 648 spoken-script words, using actual transcript ticks at approximately five-second granularity with short-cue merging within chapters. A dedicated 96-pixel band keeps captions below the interface. These checks establish media integrity and timing; they do not claim subjective listening approval.

A generic browser download listener caught a Facebook tracking request, which the owner denied. That request was not downloaded or retried. Caption text was obtained through the Descript connector’s read-only transcript result instead.

The replacement HTML player was inspected in the in-app browser: playback, pause, English captions, and the report chapter rendered correctly. Chapter seeking passed with a loopback server implementing HTTP byte ranges; the basic Python preview server reset seeking to the opening, so the Quickstart now documents that limitation. Native controls can overlap the caption band while controls are visible. No subjective audio audition is claimed.

Each of the 17 replacement chapters was also decoded independently: every chapter contained audio signal above -40 dB mean volume. Five focused documentation tests passed after the JSON inventory fix, including exact UTF-8 hashes, edit detection, and exclusion of the independent career project.

Review packages built from committed candidate `04655d3` contain the Descript chapter manifest, all 17 public source captures, and all eight marketing documents; the wheel contains Save Markdown. Protected design context and the independent career project remain excluded. The configured proposed-main pre-push guard passed at that commit. These unsigned review packages are not final public release artifacts.

## Four-film revision verification — 2026-09-29

[The series](../../media/series-v0.9.9/README.md) now contains four separate MP4s:
Overview 76.62 s; Analyst 126.92 s; PIVOT Glass 84.10 s; Visualization/Reporting
109.93 s. All use real Descript Jesse neural speech and the existing original
procedural composition/synthesis engine. Actual transcript groups drive the
edit; pitch-preserving acceleration varies by film. Stock synthesis provides
no emotion control, so wonder/excitement remains a listening-review criterion.

The final H.264 Main / AAC 44.1 kHz stereo files passed complete FFmpeg decode.
Maximum audio levels range from -1.8 to -1.7 dB, with no clipping detected.
The [machine receipt](../../media/series-v0.9.9/verification.json) records exact
sizes, stream durations and manifest deltas. Captions preserve every spoken
word; chronological chapter coverage, source existence and deterministic,
bounded score generation have regression coverage. The report regression
also verifies retained technique inputs/outputs, pending analyst disposition,
Markdown fence safety and no ledger mutation. Focused checks: **25 passed**.

The Overview was played and paused in the actual in-app browser with advancing
media time and visible English captions. Native accessibility-control clicks
crashed the preview browser; clicking the visible on-screen Play button worked.
The preview pages now load one film at a time. Direct MP4 downloads and separate
transcripts/captions remain available. No subjective listening approval is claimed.

The agent-authored synthetic Key Assumptions Check was completed through
operator commands, without collection or automatic acceptance. Its actual
run, finding, collection implication and report output were inspected and
captured. The real analyst disposition remains pending. Empty activity views
remain empty. The portal emblem has a real alpha channel spanning 0–255.

Browser regression suite: **58 passed**; TypeScript check passed. Ruff passed
across src/tests/scripts. Complete Python suite: **4,277 passed, 2 skipped**, one existing SQLite
datetime-adapter deprecation warning, in 262.94 seconds. Documentation checks
cover **90 public Markdown files**, zero broken local links/anchors; the five
documentation regression tests passed. Prior package receipts above describe their named historical commits.
Fresh unsigned review packages from `8d11efc` contain all four films, both logo
assets and all eight marketing documents; the wheel contains the SAT report
update. Protected contexts are excluded. The trust generator produced 140
locked components (77 Python, 63 npm), license inventory and checksums in the
fresh review bundle. The configured proposed-main guard passed. Final signed
publication artifacts still require the owner release ceremony.

## Final assurance handoff — 2026-09-29

The owner said the four videos and logo are approved. The new social, LinkedIn,
and Signal copy is tracked in the repository; the final candidate source archive
contains all nine marketing documents. The complete five-lens
[assurance review](FINAL_ASSURANCE_REVIEW.md) records fresh full-suite,
security-diff, capacity, browser, and packaging evidence for the proposed
v1.0.0 stable local core. This v0.9.9 branch remains a candidate until the owner
approves that review and the public release trust ceremony is completed.
