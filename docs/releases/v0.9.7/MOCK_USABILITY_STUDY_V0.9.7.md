# Mock usability review: make the next action obvious

Dates: 2026-09-22–23 · implementation candidate: 0.9.7

**This is a simulated, task-based heuristic review, not recruited human research.**
Three virtual reviewers examined analyst workflows, accessibility/focus, and
learning/TUI behavior. The fictional cohort below broadened the questions we
asked; it did not produce interviews, quotes, satisfaction scores, or measured
human task times. Software verification is recorded separately in the
[quality record](QA_V0.9.7.md).

## Review brief

Can someone arriving at 3 a.m. answer: **Where am I? What do we know? What is
missing? What should I do next?** The answer must not depend on remembering
decorative symbols, recovering lost keyboard focus, or guessing whether an
operation actually succeeded.

Keep analytical truth unchanged. Coverage is not confidence or maliciousness.
Country flags describe source-reported location, not attacker identity. Adding
an extracted indicator is not enrichment. A tutorial, character voice, or
visual effect must not change evidence or silently start an investigation.

## Fictional cohort design

These are scenario profiles, not actual people or diagnoses. Access needs vary
within every group; none is inferred from age, gender, profession, or neurotype.
ADHD, autism, dyslexia, and color-vision differences below are overlapping review
lenses, not explanations for anyone's competence or behavior. Product settings
are available to everyone and do not collect diagnostic information.

| Profile | Age / generation | Gender | Role | Additional access lenses |
| --- | --- | --- | --- | --- |
| 01 | 26 / Z | Woman | New SOC analyst | ADHD |
| 02 | 31 / Millennial | Man | Incident responder | ADHD, dyslexia |
| 03 | 34 / Millennial | Woman | Threat-intelligence analyst | ADHD, color vision |
| 04 | 39 / Millennial | Man | Nation-state threat hunter | ADHD |
| 05 | 42 / Millennial | Woman | Forensic analyst | ADHD |
| 06 | 44 / Millennial | Man | Malware analyst | ADHD, autism |
| 07 | 52 / X | Woman | Intelligence team lead | Keyboard-only workflow |
| 08 | 28 / Z | Man | Infrastructure researcher | ADHD, color vision |
| 09 | 22 / Z | Woman | Final-year undergraduate | ADHD, dyslexia |
| 10 | 24 / Z | Man | Career-transition college student | ADHD |
| 11 | 25 / Z | Woman | Incoming analyst / graduate student | ADHD, autism |
| 12 | 15 / Alpha | Nonbinary | Supervised educational learner | Dyslexia |
| 13 | 37 / Millennial | Man | Cybersecurity professor | Classroom projection |
| 14 | 54 / X | Woman | Information-design professor | Color vision |
| 15 | 59 / X | Man | Intelligence-studies professor | Larger text |
| 16 | 27 / Z | Woman | Security PhD candidate | ADHD |
| 17 | 29 / Z | Man | HCI PhD candidate | ADHD, dyslexia |
| 18 | 30 / Millennial | Woman | Cognitive-science PhD candidate | ADHD, autism |
| 19 | 35 / Millennial | Man | Behavioral psychologist | Interruption recovery |
| 20 | 41 / Millennial | Woman | Behavioral psychologist | ADHD |
| 21 | 44 / Millennial | Man | Psychologist | Choice and task predictability |
| 22 | 32 / Millennial | Woman | UX researcher | ADHD, color vision |
| 23 | 28 / Z | Man | Interaction designer | Dyslexia |
| 24 | 23 / Z | Nonbinary | Anthropologist | ADHD, autism |

Composition: 24 profiles; 17 aged 25–45; 11 women, 11 men, and two nonbinary
profiles. Generations: three X, eleven Millennials, nine Z, one Alpha. Sixteen
profiles include an ADHD lens, five dyslexia, four color-vision differences, and
four autism. The Alpha scenario is education-only, with synthetic data and
supervision, not a claim that a minor is a professional analyst.

Design lenses cross roles rather than being assigned by demographic:

- **Form follows function:** primary actions should read like the analyst's task.
- **Tufte-informed:** prioritize useful comparisons, stable scales, dense but
  readable evidence, and source context over ornamental encoding.
- **Norman-informed:** labels, visible state, feedback, and recovery should make
  the effect of an action predictable.
- **Apple-design affinity:** clear hierarchy, consistent controls, progressive
  disclosure, and restrained motion. No reviewer claims Apple employment or
  endorsement.
- **Behavioral and anthropological:** support interruption/resumption, explain
  local jargon, avoid blame, and preserve different team working practices.

## Tasks reviewed across the product

1. Orient to a workspace; enter one indicator or start with a report/list.
2. Preview a source, review more than 100 candidates, select across pages,
   ingest, and confirm the persistent library receipt.
3. Recover from a library error; switch workspace with pending intake.
4. Choose an admitted indicator and explicitly begin enrichment.
5. Read the constellation, task state, gaps, evidence, and contradictions.
6. Explore a graph or timeline without confusing navigation with a threat edge.
7. Produce a report or export; find model/API configuration without exposing keys.
8. Open Help/Utilities, operate entirely by keyboard, close, and resume work.
9. Reduce distractions, enlarge text, and retain personal preferences.
10. Read all TUI Help at small terminal sizes without losing input/history.

The review inspected these workflows; it is not a claim of exhaustive live
provider, model, integration, or screen-reader testing.

## Findings and changes

Priorities reflect observed software behavior and potential task consequences,
not fictional participant vote counts.

| Priority | Finding | Implemented response |
| --- | --- | --- |
| High | Utilities could disable its own controls while lacking the normal modal focus handling. | Containment-based background isolation, live Tab traversal, Escape, persistent opener restoration. |
| High | Intake could retain stale workspace state and late library responses. | Workspace-keyed component, stale-response guards, explicit workspace checks under the server write lock. |
| High | Only the first 100 candidates were reachable. | All bounded candidates (up to 2,000), 50 per page; additive page selection with no unseen auto-selection. |
| High | A failed library load looked like an empty library. | Separate loading, error, stale-list, and Retry states. |
| Medium | Tutorial labels did not match their destinations. | Preview action targets Preview; admission action targets successfully added indicators, which only prepare the command. |
| Medium | Reporting and exports required prior command knowledge. | Named routes in More and Help; no automatic export merely from opening the route. |
| Medium | Incidental dimming and small text can impede reading. | Explicit Larger text, spotlight off by default, and Quiet workspace. Hover never owns keyboard focus. |
| Medium | TUI Help could clip content at small terminal sizes. | Viewport-sized scrollable Help, persistent close instructions, guarded input, history-preserving return. |
| Medium | Constellation symbols imposed unnecessary recall. | Earlier candidate work retained: familiar coverage marks, readable headings, sourced country flags, focus/hover explanations and stable details. |

Quiet workspace disables decorative effects, music, device voice, unsolicited
character advice, and incidental spotlight. It does **not** suppress work or
error alerts or manual Help. Guidance is separately selectable as Novice,
Adept, or Expert. Larger text is an option, not a diagnosis-specific font or
an assumption about any group. Standard density remains available.

## Tradeoffs and remaining hypotheses

- A dense matrix is useful for comparison, but larger text may require internal
  horizontal scrolling. Preserve labels and full explanations rather than
  shrinking everything to fit.
- Spotlight can help one person and disrupt another. Keep it opt-in; tutorial
  highlighting must remain dismissible and must not move keyboard focus on hover.
- Rich characters and music remain optional. A calm mode is not a lesser feature
  set and should never suppress warnings.
- The graph command opens a **graph summary**; its label must not promise the
  interactive visualization. Interactive graphs remain in Visualize.
- Unified non-constellation tooltip behavior, fuller terminal document-ingestion
  parity, and usability of all live provider errors still need dedicated work.
- A passing browser or contrast test does not establish cognitive accessibility,
  screen-reader usability, or clinical benefit.

## Real research follow-up

Recruit consenting adults with varied experience and voluntarily expressed
access preferences. Use synthetic hunts; do not require diagnosis disclosure.
Run keyboard/screen-reader, interruption/resumption, multi-source ingestion,
reporting, and handoff tasks. Measure wrong-workspace actions, lost focus,
unintended enrichment, assistance needed, confidence calibrated to evidence,
and successful recovery. Ask participants what the coverage marks mean before
explaining them. Treat educational/minor participation as a separate supervised
protocol with appropriate consent. No human outcome is claimed until that
research actually happens.

## Reference rationale

- W3C [On Focus](https://www.w3.org/WAI/WCAG22/Understanding/on-focus.html):
  focus should not unexpectedly change context.
- W3C [Dialog pattern](https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/):
  dialog containment and predictable keyboard exit/return.
- W3C [Consistent Help](https://www.w3.org/WAI/WCAG22/Understanding/consistent-help.html):
  help remains in a predictable location.
- W3C [Animation from Interactions](https://www.w3.org/WAI/WCAG22/Understanding/animation-from-interactions.html):
  user control of nonessential motion.
- W3C [Target Size](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html):
  sufficiently operable controls, especially dense interfaces.
- W3C [Content on Hover or Focus](https://www.w3.org/WAI/WCAG22/Understanding/content-on-hover-or-focus.html):
  explanations must be reachable and dismissible.

These references guide implementation; this review is not a WCAG certification.
