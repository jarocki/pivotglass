# Repository map

Start at [the product story](../../README.md), [documentation routes](../README.md),
or [the user guide](../USER_GUIDE.md).

| Location | What belongs here |
|---|---|
| `src/pivotglass/` | Installed Python runtime and its authoritative data/command contracts |
| `src/pivotglass/core/` | Workspaces, evidence, analytic ledger, intake, graphs, and music score |
| `src/pivotglass/agent/` | Orchestration, tool routing, classic console, and terminal cockpit |
| `src/pivotglass/web/` | Local HTTP service and packaged static browser assets |
| `src/pivotglass/integrations/` | Explicit adapters, execution receipts, and external-system boundaries |
| `web/app/` | Browser cockpit, guidance, visualization, accessibility, and presentation |
| `web/scripts/` | Browser logic and component tests |
| `web/out/` | Generated static export shipped in the Python wheel; rebuild from `web/app/` |
| `tests/` | Python unit, contract, integration, resilience, and PTY tests |
| `scripts/` | Release checks, inventory, decision generation, and integration validation |
| `docs/` | Current operator and reference documentation |
| `docs/architecture/` | System structure, data flow, and authority diagrams |
| `docs/analysis/` | Scientific process, SATs, worked investigations, visual interpretation, and learning |
| `docs/development/` | Contributor navigation and generated decision registry |
| `docs/plans/` | Current roadmap plus retained detailed planning history |
| `docs/releases/vX.Y.Z/` | Dated qualification receipts, announcements, and release handoffs |
| `docs/operations/` | Implementation, infrastructure, maintenance, automation, backup, and recovery |
| `docs/marketing/` | Tracked public pitches and channel-specific publication drafts |
| `docs/examples/` | Clearly labeled synthetic, reproducible input fixtures |
| `docs/media/` | Labeled screenshots and walkthrough media; filenames identify the demonstrated version |
| `.githooks/` | Tracked publication guard |

## Root files

`README.md` is the landing page. `CHANGELOG.md` records release changes.
`PHILOSOPHY.md` and `AGENTS.md` define judgment and collaboration rules.
`SUPPORT.md` and `LICENSE` define support and licensing. `pyproject.toml` and
`uv.lock` define Python packaging and dependencies. npm manifests live in `web/`.

Large historical plans moved to [docs/plans/MASTER_PLAN.md](../plans/MASTER_PLAN.md).
The generated decision registry moved to [docs/development/DECISIONS.md](DECISIONS.md).
Regenerate it with `python scripts/regen_decisions.py`; do not maintain a second
manual decision authority.

## Preservation and generated files

Private locally retained design and operational folders remain in place and
ignored by Git. The separate nested career project is not part of Pivotglass.
Build caches, virtual environments, local scratch, and `dist/` remain ignored.
This reorganization does not discard existing local work or change evidence
schema merely to make folders look tidy.
