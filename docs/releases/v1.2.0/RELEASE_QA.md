# Pivotglass v1.2.0 provider API candidate qualification

Date: 2026-09-30. This is a candidate on `codex/provider-api-pivots-1.2.0`.
It does not claim a public tag or GitHub Release.

## What changed

- Shodan and AbuseIPDB credential checks now preserve the query parameters in
  their documented validation requests. The previous empty `params` argument
  removed them and produced false 401 and 422 failures.
- A bounded Shodan DNS lookup and a read-only URLScan history search are
  available as explicit pivots. The evidence detail view labels their source
  and shows scan IDs, observation times, and DNS record times.
- URLScan submission accepts optional country and tags, keeps unlisted as the
  explicit default, and exposes documented screenshot and DOM links. Polling
  uses a validated scan UUID and a fixed URLScan host; it does not forward the
  analyst's API key to a URL supplied by the submit response.
- OTX IPv6 routing and STIX typing are corrected. The module advertises only
  the indicator types it currently implements.

The [provider coverage inventory](../../integrations/PROVIDER_API_COVERAGE.md)
records endpoint choices, plan boundaries, and deferred state-changing APIs.

## Verification

| Check | Result |
| --- | --- |
| Focused URLScan, Shodan DNS, evidence detail | 69 passed |
| Historical tool-catalog tests | 57 passed after updating the expected catalog for two new tools |
| Localhost integration tests with socket permission | 71 passed |
| Browser unit suite | 58 passed |
| Production browser build | Passed; generated `web/out` refreshed |
| Ruff on changed Python paths | Passed |
| `uv lock --check` with writable cache | Passed |
| Release contract against `origin/main` | Passed for v1.2.0 |
| Final full Python suite with socket permission | 4,311 passed, 2 skipped, 1 SQLite adapter deprecation warning |

Earlier live checks against the isolated demo configuration returned provider
acceptance for the stored Shodan and AbuseIPDB credentials. A read-only
Shodan DNS lookup and URLScan history search also returned bounded results.
No new URLScan scan was submitted during this qualification. OTX was not
tested against a stored key in the isolated demo, so its correction is covered
by request-construction tests rather than live provider acceptance.

## Publication gate

Run final verification from the completed tree, exercise the refreshed local
demo, then create a reviewable commit and pull request. A release still needs
the repository's pre-push guard, public main commit, matching signed or
annotated tag, GitHub Release and artifacts, and public readback. The v1.1.0
release remains the public baseline until those objects are verified.
