# Operate, maintain, and recover Pivotglass

[Implementation](IMPLEMENTATION.md) · [Infrastructure](INFRASTRUCTURE.md) · [Failure recovery](../FAILURE_RECOVERY.md) · [Workspace migration](../WORKSPACE_MIGRATIONS.md)

This runbook covers the local product and external automation an administrator
may arrange. Pivotglass does not currently supply an unattended hunt scheduler,
service installer, centralized fleet controller, or multi-user server. Automated
maintenance must preserve evidence and the analyst's authority.

## Ownership and cadence

These are suggested starting intervals; the data owner chooses retention and
the operations owner chooses the actual cadence for the environment.

| Task | Suggested trigger | Owner | Evidence / action |
| --- | --- | --- | --- |
| Confirm case and enabled services | Start of each investigative session | Analyst | Workspace identity, authorized scope, service configuration |
| Review failed and incomplete jobs | During collection and before handoff | Analyst | Source faults, empty/partial results, targeted retry decision |
| Review contradictions and open requirements | Before conclusion or shift handoff | Analyst lead | Unresolved conflicts and next decision-changing information |
| Full stopped-home backup | After material work and before upgrades | Local administrator | New backup directory plus validation record |
| Restore rehearsal | Initial implementation and periodically after changes | Recovery owner | Isolated copy, integrity result, report/content verification |
| Credential review / rotation | Provider policy, compromise, role change | Credential owner | Updated approved access; masked check receipt |
| Dependency and release review | Before planned upgrade | Release / operations owner | Version, lock, signatures/checksums, advisories and release limits |
| Retention and purge | Data-owner schedule | Data owner with administrator | Separate review of live case, backups, reports, exports, and local drafts |
| Capacity trend | Growth or performance complaint | Operations owner | Workload, environment, timing, sizes, missing/omitted counts |

## Normal session

From the selected source checkout, start `uv run pivotglass`. Keep the launch
terminal accessible. In the application, use:

```text
workspace list
status
config show
model show
integration status
```

These inspect local state. A configured service is not automatically a verified
service. Provider-specific checks and collection require explicit actions and
may transmit data. Select the intended workspace before framing a question,
admitting documents, collecting, generating reports, or exporting.

Review Activity & Errors and Attention Needed. An empty result differs from a
failed call, and either differs from evidence that an indicator is benign.
Cancellation is cooperative: allow the current provider call to finish and
inspect terminal state. Do not promise a fixed stop latency.

End a case session by reviewing open work, generating the intended handoff,
and stopping the server from its launch terminal. Do not leave an exposed
local service running merely because the browser tab is closed.

## Backup and restoration

### What a recoverable backup contains

Copy the stopped application home, including configuration, all workspace
SQLite files and any sidecars, sibling raw-document `.content` directories,
and retained application artifacts. Reports or exports written elsewhere need
separate inclusion. Browser local storage is separate; saved notebook questions
are in the database, but Q&A answers and reflections are not.

A JSON export is useful for exchanging records and provenance. It does not
contain admitted original document bytes. A lone `.db` file is therefore not a
complete documentary case backup. Migration backups are database recovery
artifacts, not a general backup policy.

### Make a stopped-home backup

1. Ask analysts to pause work and stop every Pivotglass process writing this home.
2. Confirm no old/new installation still uses the same files.
3. Choose a new absent backup path outside the source. Protect its parent
   location according to the data owner's requirements.
4. From the application checkout, use the explicit copy command:

```bash
uv run pivotglass migrate-home --from "$HOME/.pivotglass" --to /absolute/private/backup/pivotglass-2026-09-28 --confirm-stopped
```

The date/path is an example. Use a new location for each retained backup. The
command refuses an existing destination, symbolic links, or a destination
inside the source. It preserves the source and publishes the copy after
completion. `--confirm-stopped` is an operator assertion, not process detection;
the command does not independently prove that every writer has stopped.

5. Review its receipt and validate a copy before relying on it. Keep the
   original backup unchanged during a restoration exercise.

### Validate an isolated recovery copy

This example verifies a stopped backup without pointing the normal cockpit at
it. Run it from the selected checkout. Adjust only the explicit path and case
name; it writes a temporary copy and may migrate that copy when opening it.

```bash
uv run python - <<'PY'
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
from pivotglass.core.legacy_migration import migrate_home
from pivotglass.core.workspace import WorkspaceManager
from pivotglass.core.analytic_ledger import AnalyticLedger
from pivotglass.core.document_library import DocumentLibraryService

backup = Path('/absolute/private/backup/pivotglass-2026-09-28')
case = 'authorized-case'
with TemporaryDirectory(prefix='pivotglass-restore-check-') as temporary:
    copied = migrate_home(backup, Path(temporary) / 'home')
    manager = WorkspaceManager(workspace_dir=copied / 'workspaces')
    if case not in manager.list_workspaces():
        raise SystemExit('Expected workspace is absent from the backup')
    before = manager.get_workspace_schema_status(case)
    if not before['supported'] or before['sqlite_integrity'] != 'ok':
        raise SystemExit('Backup schema or SQLite integrity needs review')
    manager.switch(case)
    after = manager.get_workspace_schema_status()
    if not after['valid']:
        raise SystemExit('Restored copy failed schema validation')
    documents = DocumentLibraryService(manager).list()
    for record in documents:
        digest = record.content_sha256
        raw = copied / 'workspaces' / f'{case}.content' / 'sha256' / digest[:2] / digest
        with raw.open('rb') as source:
            if hashlib.file_digest(source, 'sha256').hexdigest() != digest:
                raise SystemExit('Restored source bytes failed hash validation')
    snapshot = AnalyticLedger(manager).snapshot()
    print({'workspace': case, 'questions': len(snapshot['questions']),
           'hypotheses': len(snapshot['hypotheses']),
           'contradictions': len(snapshot['contradictions']),
           'documents_checked': len(documents), 'sqlite_integrity': after['sqlite_integrity']})
PY
```

The script validates SQLite integrity, required tables, and each admitted
document's content hash in a temporary copy. Counts are only an orientation
check: compare the expected questions, observations, contradictions, and
source receipts to your known case. Do not display sensitive raw bytes in a
support log. If files are missing or integrity fails, preserve
the backup and investigate before deleting the live case.

For an actual restoration, stop all writers, preserve the current application
home under another new name, and restore the verified copy into the default
home only after that destination is absent. The copy command never overwrites
an existing home. Restoring credentials is consequential: review their currency
and access before enabling providers. Opening a restored database does not
authorize replaying remote publication; inspect retained execution receipts and
reconcile uncertain SCOT/Synapse outcomes with their owners.

## Upgrade and rollback

1. Read the release scope and qualification receipt. Preserve local code changes
   rather than forcing a checkout.
2. Stop writers and back up the complete data home as above.
3. Use a clean checkout of the explicitly selected public tag:

```bash
git fetch --tags origin
git checkout v1.0.0
uv sync --extra agent --frozen
uv run pivotglass --version
```

These commands require that v1.0.0 has been published. While it is a candidate,
record the actual reviewed commit; do not describe it as a public release.

4. Validate a disposable restored copy and a synthetic learning workspace before
   opening valuable cases. In the application, `workspace schema case-name`
   reports the database version, integrity, and required migration.
5. Opening an older workspace can migrate it forward with a sibling backup.
   Verify expected questions, observations, contradictions, and source content.
6. Keep the prior source checkout and full data backup until acceptance.

In-place database downgrade is unsupported. If rollback is required, use the
older release against the corresponding preserved pre-upgrade copy. Keep the
newly migrated state separately for investigation. Do not run both releases
against the same live SQLite files. The [migration reference](../WORKSPACE_MIGRATIONS.md)
describes schema-specific backup names and recovery.

## Safe automation boundaries

An administrator may use their existing scheduler to run read-only checks and
reminders. This document does not create an automation or install a service.
Do not schedule automatic enrichment, candidate admission, hypothesis acceptance,
confidence changes, or external publication as routine maintenance.

| Automation candidate | Permitted scope | Constraint |
| --- | --- | --- |
| Loopback health probe | Read `/api/health` of an already running service | Health does not establish evidence integrity or provider readiness |
| Backup reminder | Notify the recovery owner of the agreed stop window | A reminder is not a backup receipt |
| Backup copy | Run only in a verified stopped-writer window with a new destination | Abort if writers cannot be confirmed stopped; no silent overwrite |
| Dependency advisory check | Review current lock against advisories | Do not auto-update the live environment or claim absence of all vulnerabilities |
| Capacity measurement | Synthetic temporary workload | Bound resource use and record host/version; do not alter real evidence |
| Retention reminder | Present separately owned artifacts for review | No automatic case, backup, report, or source deletion |

A minimal health command is:

```bash
curl --fail --silent --show-error http://127.0.0.1:8765/api/health
```

A failed probe can mean the application is intentionally stopped. Record that
context; do not automatically launch a hunt or retry a remote write. A useful
maintenance record contains task, timestamp, owner, application version,
observed result, and follow-up. Exclude keys, private indicator values, and raw
source text from shared monitoring receipts.

For source/dependency maintenance, use the tracked release gates in
[Releasing](../RELEASING.md) and [Web supply chain](../WEB_SUPPLY_CHAIN.md).
Running every test suite is a release qualification task, not a silent repair
of an analyst's active environment.

## Retention, removal, and incident response

Workspace clear/delete require their exact confirmation and deliberately leave
migration backups and generated reports under separate control. Deleting a
package does not delete user data. Decide separately whether to retain or purge
backups, exports, reports, logs, admitted source bytes, and shared-browser drafts.
Document the decision and owner. Do not treat the existence of a purge command
as permission to delete an investigation.

If a credential may be exposed, stop transmitting case data, preserve relevant
receipts, rotate the credential through its provider, and review stored/logged
artifacts without pasting secrets into an issue. For product failures, preserve
the data and sanitized diagnostic identifier, then follow [Support](../../SUPPORT.md)
and [Failure recovery](../FAILURE_RECOVERY.md). Optional remote writes with
uncertain outcomes require manual reconciliation; do not repeat them blindly.
