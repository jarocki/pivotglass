# Vertex Synapse and SCOT4 integrations

Pivotglass 0.9 begins both integrations as bounded, read-only MCP clients. A
remote result is labelled `remote-preview`; it is not silently promoted to
local evidence, a relationship, or an analytic conclusion.

## Safety and authority

- Synapse Storm runs only after validation and always receives
  `opts.readonly=true`.
- Storm pages, returned records, elapsed time, and response size are bounded.
  Pivotglass cancels the Synapse cursor when one of those limits is reached.
- The SCOT4 adapter exposes object search, object detail, entries, and related
  entities. It exposes no remote write operation.
- Receipts contain a digest of the request, timing, page and record counts,
  completion state, and the boundary that stopped an incomplete read. They do
  not contain the API key or raw Storm query.
- Every mapped record retains the remote system, type, ID, revision,
  permissions when supplied, retrieval time, and a stable conflict key.

## Configure

Add the endpoint settings to `~/.ap/config.toml`:

```toml
[integrations]
synapse_mcp_url = "https://synapse.example/api/v1/mcp"
scot_mcp_url = "https://scot.example/mcp"
timeout_seconds = 20.0
max_pages = 10
max_records = 1000
max_elapsed_seconds = 30.0
allow_insecure_http = false

[api_keys]
synapse = "..."
scot = "..."
```

The same values can be supplied without editing the file:

```text
AP_SYNAPSE_MCP_URL
AP_SYNAPSE_API_KEY
AP_SCOT_MCP_URL
AP_SCOT_API_KEY
```

Stored configuration takes precedence over environment variables. Cleartext
HTTP is limited to loopback by default. Set `allow_insecure_http=true` only
when a deliberately isolated deployment requires it; the traffic, including
credentials, is otherwise visible on that network.

Synapse's Cortex MCP endpoint is `/api/v1/mcp`. SCOT4 must have its MCP server
enabled, and its mounted path is normally `/mcp`. Use the complete endpoint
URL supplied by the administrator.

## Read-only commands

```text
integration status
integration synapse status
integration synapse model <pattern>
integration synapse lookup <STIX-type> <indicator>
integration synapse query <Storm query>
integration scot status
integration scot get <object-type> <object-id>
integration scot search <object-type> [filters-json]
integration scot entries <object-type> <object-id> [plain|flaired|all]
integration scot entities <object-type> <object-id>
```

`integration status` is local and makes no network request. A system-specific
`status` command opens an MCP session and lists the tools visible to that
credential. Every query is an explicit operator action; Pivotglass does not run
Storm or search SCOT in the background.

`synapse lookup` maps IPv4, IPv6, domain, URL, email, and MD5/SHA indicator
types to pinned Synapse forms. Values travel as Storm variables rather than
being interpolated into query text.

Example incremental SCOT preview:

```text
integration scot search incident {"modified":"2026-08-01"}
```

The accepted SCOT filter grammar is owned by the connected SCOT4 deployment.
Pivotglass passes the JSON object to SCOT and preserves the resulting revision
metadata. It does not infer that a returned object is current when the read was
stopped by a budget.

## Deliberately unfinished

This slice establishes transport, mapping, receipts, and protocol fixtures.
Before either integration is release-complete, it still needs:

- disposable live-system round-trip tests;
- durable incremental cursor/checkpoint state and conflict review;
- a reviewed mapping from remote records into Pivotglass evidence authority;
- Synapse relationship/time mapping fixtures;
- SCOT outbound previews followed by approval-gated write-back.

Automatic SCOT or Synapse write-back remains out of scope.
