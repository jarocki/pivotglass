# Provider API coverage and next pivots

This inventory records what Pivotglass actually calls and which additional
provider endpoints help an analyst answer an investigative question. An API's
availability does not make every endpoint appropriate for an automatic hunt.
Requests may consume credits, disclose indicators, or change provider state.

Sources: [Shodan API](https://developer.shodan.io/api) and
[account tour](https://account.shodan.io/billing/tour),
[LevelBlue OTX API](https://otx.alienvault.com/api) and its
[published SDK types](https://github.com/AlienVault-OTX/OTX-Python-SDK/blob/master/IndicatorTypes.py),
[AbuseIPDB API](https://docs.abuseipdb.com/), and
[URLScan OpenAPI](https://docs.urlscan.io/apis/urlscan-openapi/scanning/submitscan).
Provider entitlements and endpoint behavior can change; test with the
operator's plan before claiming a capability is available.

| Provider | Endpoint | Pivotglass status | Analytical use and boundary |
| --- | --- | --- | --- |
| Shodan | `GET /api-info` | Credential check | Account access and plan information; this alone does not prove host-lookup entitlement. |
| Shodan | `GET /shodan/host/{ip}` | Implemented | Ports, hostnames, organization, and vulnerability context for an IP. A 404 means no indexed host data. |
| Shodan | `GET /dns/domain/{domain}` | Implemented | Separate, bounded DNS pivot with record timestamps and optional history; may consume query credits. |
| Shodan | `GET /dns/reverse`, `/dns/resolve` | Candidate | Distinct IP-to-name and name-to-IP pivots; limit and label results. |
| Shodan | `GET /shodan/host/search`, `/shodan/host/count` | Candidate, explicit query | Infrastructure discovery. Search filters and pages may consume credits; avoid unattended broad searches. |
| Shodan | `history=true` on host lookup | Candidate, explicit option | Historical service exposure with observation times; plan gated and potentially large. |
| Shodan InternetDB | `GET /{ip}` | Candidate | Free, quick open-port, hostname, CPE, and vulnerability summary; keep its observations separate from paid Shodan host data. |
| Shodan CTLog / CVEDB | Provider-specific read APIs | Candidate | Certificate and vulnerability pivots when tied to a case question. Preserve the returned source and observation time. |
| Shodan | scan, monitoring, streams, bulk datasets, organization administration | Deferred | Active or persistent work, paid tiers, or large ingestion require separate controls and operational design. |
| LevelBlue OTX | `GET /api/v1/indicators/{type}/{value}/general` | Implemented for IP/domain | Pulse and reputation context; IPv6 routing corrected in the current work. URL/file-hash API coverage remains to be designed. |
| LevelBlue OTX | `.../passive_dns` | Implemented for IP/domain | Related infrastructure as separately sourced indicators, bounded to 20 records. |
| LevelBlue OTX | `.../reputation`, `.../malware`, `.../url_list`, file `.../analysis`, pulse details | Candidate | On-demand corroboration and pivots; collect only relevant sections and keep community assertions distinct from observed evidence. |
| LevelBlue OTX | create/update pulse, file/URL submission | Deferred | Changes shared intelligence or transmits samples; requires explicit analyst intent. |
| AbuseIPDB | `GET /api/v2/check` | Implemented | Reputation summary and recent reports. Credential validation now preserves the test IP query parameter. |
| AbuseIPDB | `GET /api/v2/reports` | Candidate | Paginated analyst reports for an IP, capped and attributed. It is not the Shodan API. |
| URLScan | `GET /api/v1/quotas` | Credential check | Confirms account access without submitting a URL. |
| URLScan | `POST /api/v1/scan/` then `GET /api/v1/result/{scanId}/` | Implemented | The `scan_url` action submits and collects a scan. Default visibility is unlisted. The current API accepts both slash forms of the submit path; no automatic retry is used. Require analyst intent before calling this action. |
| URLScan | `GET /api/v1/search` | Implemented for domain and IPv4 | Read-only search of up to ten existing scans before considering a new submission; scan IDs and observation times are preserved. |
| URLScan | screenshot, DOM, response resources | Partly surfaced as links | Screenshot and DOM links may accompany results. Fetch raw page/response material only on explicit analyst request and within size limits. |
| URLScan | available countries | Candidate | Populate or validate optional scan country. Country and tags are accepted as explicit submission options. |
| URLScan | change or reset result visibility | Deferred | Changes public exposure of a scan; never perform as an automatic enrichment step. |

## Workflow rule

Prefer a bounded read-only lookup when it can answer the question. Show the
provider, exact endpoint family, retrieval time, access or rate-limit state,
and which related values were observed versus inferred. Keep scan submissions,
searches that spend credits, and provider-state mutations under deliberate
analyst control. Never turn a credential test into a public scan.
