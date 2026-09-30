# v0.9.9 newcomer editorial review

Date: 2026-09-28. Review role: agent-assisted newcomer editor focused on clarity,
pacing, emotional tone, visible uncertainty, and practical task completion.
This is an editorial review of actual artifacts and source contracts. It is
not a real-user usability study, a human endorsement, or proof of improved
analyst performance.

## Scope and method

Reviewed the current landing page, documentation index, Quick Start, User Guide,
learning/analysis references, and operational reading paths. Checked the new
operator commands against the command adapter, separated old release receipts
from current qualification, and inspected actual screenshots. Read the demo
manifest, transcript, and captions and inspected its streams with `ffprobe`.
The root release agent separately verified the initial player and captions.
The owner then rejected the system voice; that audio was removed. The requested
natural Descript voice was subsequently generated and synchronized in the
replacement candidate. See the root verification addendum below. The HTML
player provides explicit accessible Play/Pause and chapter controls.

## Findings and concrete corrections

| Finding | Correction delivered | Why it matters to a new reader |
| --- | --- | --- |
| The current landing page and guide still relied on old demo/screenshots | Linked the new current tour and inspected v0.9.9 UI captures; old media retained as history | A reader should see the interface they are being instructed to use |
| The product story was buried in repetitive feature detail | Rewrote README around analyst needs, why the tool exists, boundaries, and novice/experienced/operator paths | A first-time reader can choose a starting point and understand what the product provides |
| The first-use path configured providers before proving an offline case | Moved optional configuration after the synthetic question/evidence/analysis/report exercise | A new user can practice the real workflow without credentials or inadvertent collection |
| Questions were described without sufficient executable method practice | Added a concrete Q&A exercise, an alternative-explanation checkpoint, Key Assumptions practice, and restart checks | An unknown becomes a useful next question rather than an invitation to invent a cause |
| Experienced workflows lacked a clear correction and handoff routine | Added explicit correction actions, seven handoff checks, and lifecycle commands | A changed judgment can remain reviewable, and the next analyst can reconstruct the case |
| Manual evidence linking was described but not exposed to the operator | Escalated the missing command; implementation added `analysis link`; guide now gives exact syntax, IDs, rationale, receipt, and matrix checks | Method guidance must correspond to an action the reader can actually perform |
| Graph/history screenshots showed controls while their actual diagrams were below the viewport | Flagged the mismatch; recaptured and inspected full graph canvas/legend and document→group→candidate branches | The illustration now demonstrates the visual distinction its caption explains |
| Joint admission revealed a real state refresh/degree failure | Reported through the live release work; corrected degree handling so state refresh remains available; verified the replacement screenshots show seven nodes/five edges | A reader can distinguish analyst grouping from source relationships without a broken state view |
| Export and database-copy language could imply a full recoverable backup | Distinguished workspace-record export from original document bytes and linked stopped-tree backup/restore instructions | Recovery guidance must preserve source material, not just a database or JSON projection |
| Historical receipts remained in current navigation as if current | Moved active reading paths to role/outcome groups, retained dated release records, and added a completion matrix | Passing tests from an earlier release do not qualify the present candidate |
| The demo could be misread as a continuous screen recording | Disclosed edited actual UI states, synthetic case data, and local narration | Users can understand what the media demonstrates and what it does not prove |
| Participation and efficiency claims risked becoming stronger than their evidence | Kept guidance levels manual, practice counts non-certifying, and benefits as design mechanisms | Learning should support honest uncertainty and feedback rather than pressure for confident answers |

## Inspected visual evidence

Current captures inspected: cockpit, question coach, scientific notebook,
constellation, source/indicator detail, preview intake, stored-source library,
provenance history, relationship graph and promotion group, evidence-link
receipt, Dossier report, configuration, theme, and demo poster.

The graph example shows six synthetic entities plus one analyst group. Three
stored edges and two dotted analyst-group edges are visibly distinguished by
labels and legend. The long URL is fully wrapped. The history branches state
explicit admission and promotion decisions and disclose that grouping does not
assert common adversary ownership or activity.

## Document verification and remaining gates

Local file targets and heading anchors were checked for the assigned guides;
whitespace checks pass. Candidate-wide link checks, every Python/browser test,
media/caption playback qualification, immutable build/signing, and public
readback belong to the release QA and publication receipts. The HTML player was checked through its accessible Play/Pause controls;
the in-app browser's native media-control automation limitation is recorded
in the QA receipt. No marketing message or website change was performed by this review.

The v1.0.0 final correctness, resilience, efficiency, security, and usability
review remains separate and requires owner approval.

## Reviewed artifacts

- [User Guide](../../USER_GUIDE.md)
- [Quick Start](../../QUICKSTART.md)
- [Documentation paths](../../README.md)
- [Product story](../../../README.md)
- [Request completion matrix](COMPLETION_MATRIX.md)
- [Current transcript](../../media/pivotglass-guided-demo-transcript-v1.0.0.md)
- [Release trust](../../RELEASE_TRUST.md)

## Replacement candidate — root verification addendum, 2026-09-29

The root release agent inspected the replacement report, named Nightgrid, unknown-answer, and grouping-graph captures; they retain the controls and distinctions described by the narration. The actual HTML player rendered the report chapter and external captions below the interface, with Play/Pause and chapter seeking verified using HTTP byte-range support. The replacement has 17 speech-timed scenes over 300.16 seconds, with real Descript Jesse neural speech and all 648 spoken words retained in 68 caption cues. The complete decode and per-chapter audio checks passed.

The follow-up newcomer review was stopped before it produced a separate completed receipt. This addendum records root checks, not a new reviewer endorsement or human listening approval. Owner listening review remains open.
