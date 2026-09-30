# Pivotglass v1.1.0 credential recovery qualification

Date: 2026-09-30. This release responds to a live v1.0.0 trial in which
intelligence-service credentials were discarded when their immediate access
test failed. The already published, signed v1.0.0 tag remains immutable.

## Changed behavior

- An explicit **SAVE, THEN TEST** stores entered service credentials before
  testing access. The result distinguishes saved configuration from provider
  acceptance, network reachability, and service enablement.
- Each credential field displays a fixed masked presence label for stored,
  environment-supplied, or missing values. The browser never receives the
  credential or its length. The replacement field remains empty.
- **TEST** reuses stored fields when its input is blank. Disabled-service
  failures identify the enablement action instead of reporting an unknown
  failure.
- VirusTotal, URLScan, and HIBP checks use documented authenticated API
  endpoints. A validation network exception cannot echo a key-bearing URL;
  rate limits and access-denied responses do not overstate key validity.
- Censys Platform accepts a PAT plus an optional organization ID and sends the
  latter in `X-Organization-ID` for both validation and host lookup. Free
  accounts can use a PAT alone.

## Verification

| Check | Result |
| --- | --- |
| Final full Python run | 4,297 passed, 2 skipped; one SQLite adapter deprecation warning |
| Initial full Python run | 4,290 passed, 2 skipped; seven failures were changed-version and Censys-shape assertions, corrected before the final run |
| All nine configured service paths | Saved fields reach the intended module through the shared credential resolver |
| Censys and credential focused tests | 256 passed; the final HTTP 403/429 classification change passed 135 focused tests |
| Web server integration | 63 passed with localhost socket access |
| Browser unit suite | 58 passed |
| TypeScript and production browser build | Passed |
| Ruff and Python lock consistency | Passed |
| npm advisory audit | Zero reported vulnerabilities |
| Candidate package and trust bundle | Wheel and source archive built; wheel includes browser assets; 77 Python and 63 npm components inventoried |
| Release contract | v1.1.0 passes against `main` |
| Isolated browser interaction | A fake key was saved despite a stubbed unreachable provider; masked presence and **SAVED · ACCESS UNREACHABLE** appeared on its card; retest worked with an empty input |

These tests establish the local save, resolution, request construction, and
presentation behavior. No real user keys were read or exposed for this review,
and provider-side acceptance remains to be verified by the operator using
their own account and quota.

## Publication gate

Rerun final tests and static checks after the last edit, build artifacts from
the committed tree, sign the checksum manifest, and read back public `main`,
the matching tag, GitHub Release, and downloaded artifacts. This document is
a candidate receipt until those steps are complete.
