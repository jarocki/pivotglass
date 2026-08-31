# Pivotglass support

Pivotglass is early-availability software. Support is public, evidence-driven,
and limited to the latest published release. A development branch, local
version string, or planned tag is not a published release; use the latest entry
on the [Pivotglass Releases page](https://github.com/jarocki/pivotglass/releases)
as the authority.

## Supported versions

Before 1.0, only the latest published release receives compatibility, defect,
and security fixes. Older versions remain available for workspace recovery,
but are not actively supported. Never open a valuable workspace with a newer
release until its backup-first migration preview has been reviewed.

The stable, preview, and deferred boundaries for the latest source tree are in
the [compatibility matrix](docs/COMPATIBILITY.md). The corresponding release
quality record is the authority for what was actually verified.

## Ask for help or report a defect

Use [GitHub Issues](https://github.com/jarocki/pivotglass/issues) for ordinary
defects, installation problems, documentation gaps, and feature requests.
Search existing issues first. Include:

- the exact `ap --version` output and operating system;
- the interface used: Pivotglass browser, `ap tui`, or `ap basic`;
- the smallest repeatable steps, expected result, and observed result;
- a diagnostic ID or the downloaded **sanitized** Activity & Errors record,
  after reviewing it locally; and
- whether the problem reproduces in `workspace learn <temporary-name>`.

Do not attach credentials, authorization headers, private reports, raw
workspace databases, unreviewed logs, confidential indicators, or source
documents. A sanitized diagnostic is useful context, not permission to share
case data.

## Security reports

Do not place exploit details or sensitive vulnerability information in a
public issue. As of 2026-08-31, GitHub private vulnerability reporting is not
enabled for this repository and no owner-approved `SECURITY.md` reporting route
exists. That is an explicit open v1.0 release gate, not an invitation to use a
public channel. The repository owner must approve a private contact route,
supported-version window, response expectations, disclosure process, and
accepted-risk boundaries before Pivotglass claims a vulnerability-reporting
policy.

## What support cannot promise

- Preview integrations and formats do not receive stable compatibility
  guarantees.
- Public issue discussion is not a confidential incident-response channel.
- A bounded browser view is not the complete stored case; use an export before
  diagnosing apparent omissions.
- Support cannot recover an overwritten database, revoked provider account, or
  secret that was disclosed outside Pivotglass.

For safe backup, recovery, and sharing guidance, see [Data ownership and
safety](docs/DATA_SAFETY.md) and [Failure and recovery](docs/FAILURE_RECOVERY.md).
