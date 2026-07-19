# Repository Governance

## Purpose

This repository is the source of truth for Adversary Pursuit: an AI-augmented,
gamified framework for hunting, pivoting, and discovering adversary
infrastructure, indicators, and TTPs. Changes should strengthen analytical
truthfulness, operator agency, deterministic evidence collection, coherent
system design, and a distinctive but usable terminal experience.

## Guiding philosophy

`PHILOSOPHY.md` is the repository's highest-level judgment framework. Human and
computational contributors must read and apply it before making substantial
product, architectural, or operational decisions, especially when more
specific instructions do not adequately address the situation.

Explicit human direction and accepted project decisions remain controlling.
The philosophy guides judgment in the space they leave open; it does not
replace them.

## Collaboration standards

- Keep claims proportional to evidence and make uncertainty visible.
- Prefer deterministic verification over persuasive confidence.
- Surface conflicts between purpose, procedure, principles, and implementation
  constraints instead of concealing them.
- Preserve optionality and human authority for consequential or irreversible
  choices.
- State genuine trade-offs and substantive disagreement rather than
  manufacturing consensus.
- Improve the system and the capability of future collaborators, not only the
  artifact immediately requested.

## Product and analytical standards

- Deterministic local logic and direct APIs are the default execution path.
  Use an LLM where synthesis, interpretation, or genuine reasoning adds value,
  not for work that can be performed more reliably without one.
- Evidence must remain distinguishable from inference. Do not present a model's
  synthesis, a persona's voice, or a visual flourish as observed fact.
- Preserve operator agency during automated work. Long-running hunts must
  expose meaningful state and honor supported stop, focus, add, and skip
  controls.
- Keep the AI-augmented cyberdeck (`ap`) as the primary user experience. The
  classic console (`ap basic` / `ap repl`) is a supported direct-control
  surface, not the default interface.
- Personas are durable product features. Deprecation does not authorize
  deletion, and character voice must not weaken analytical accuracy.

## Engineering standards

- Establish a single authority for each policy, state transition, or data
  contract. Avoid parallel implementations and fallback paths that can drift.
- Prefer focused, reversible changes that preserve coherent boundaries and
  future choices.
- Preserve existing user work and unrelated changes. Inspect repository state
  before editing and never discard uncommitted material without explicit
  authorization.
- Add or update tests for behavior changes. Run focused tests first, then widen
  verification in proportion to the risk and affected surface.
- Treat passing tests as evidence, not proof. Also inspect the real command
  path, rendered interface, or generated artifact when the behavior depends on
  integration or presentation.
- Keep documentation, help output, and executable behavior consistent. When a
  user-facing contract changes, update all three in the same iteration.

## Preservation and scope boundaries

- `storyboard/` and `reckonings/UX-team.md` are protected design context. Do not
  overwrite or remove them as cleanup.
- `career-narrative/` is a completely separate project. It is read-only and
  outside AP's modification, staging, and commit scope.
- AP's owned copy of the shared principles is `PHILOSOPHY.md`. Future changes to
  it should be deliberate, explained, and preserve a visible history of what
  changed and why.

## Backlog discipline (DEC-BACKLOG-DISCIPLINE-001)

Every newly filed GitHub issue must be scheduled or closed within 24 hours:

- Assign at least one target-phase label, milestone, or triage label
  (`triage-stale`, `triage-defer`, or `triage-accept`).
- If no disposition applies within 24 hours, close the issue as `wontfix` or
  `not-planned` with a concise reason. It may be reopened if circumstances
  change.
- An issue may remain `triage-defer` for at most 30 days before closure.

The reckoning process audits adherence and reports unscheduled issue count.
