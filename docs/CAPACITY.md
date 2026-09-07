# Pivotglass capacity envelope

Capacity is a truth boundary. Pivotglass must say when a view is bounded and
must keep omitted evidence stored and exportable. A fast benchmark on one
computer is not a universal promise, so this guide separates enforced limits,
qualified release sizes, measured examples, and work that remains unqualified.

## Qualified v0.9.6 local envelope

The stable local cockpit is qualified for:

- workspaces containing up to **5,000 stored entities** in the measured
  evidence-only scenario;
- connected relationship views containing up to **1,000 entities**, subject to
  the combined 5,000-record visualization envelope;
- up to **5,000 rows, nodes, and edges combined** in any one visualization
  intent;
- up to **555 indicators** in the Investigation Constellation, represented as
  4,995 exact indicator/dimension rows;
- a force-layout canvas showing **48 filtered entities at a time**, while the
  bounded inventory, exact-data view, and complete graph export remain
  available;
- one explicitly selected local document up to **10 MiB** through the v0.9.6
  preview-and-admit path.

Larger workspaces are not deleted or rewritten. The relationship view keeps up
to 1,000 of the most connected entities and prioritizes analyst judgments,
stored relationships, then property pivots. The exact omission count and a
plain explanation travel with the visualization. `graph export` continues to
use the complete stored graph.

The Constellation keeps the newest 555 indicators and reports how many are
omitted from the view. Sort and filter are presentation tools; they do not
remove evidence. A workspace larger than the qualified envelope may continue
to work, but it is not a supported performance claim for this release.

## Enforced parser and visualization limits

| Boundary | Limit | Exceeding it |
|---|---:|---|
| Browser document JSON request | 14 MiB | Request fails visibly before parsing |
| Raw document preview | 10 MiB | Preview rejects the file |
| Browser parser output | 100,000 characters | Output is visibly truncated |
| Browser entity candidates | 2,000 extracted; 100 displayed | Exact additional count is shown |
| Internal parser output | 2,000,000 characters | Parser receipt records truncation |
| Internal entity candidates | 10,000 | Extraction fails at the authority boundary |
| Visualization data | 5,000 combined records | Intent construction rejects an unbounded payload |
| Relationship view | 1,000 entities within 5,000 combined records | View is bounded with an omission count; storage and export remain complete |
| Cluster snapshot | 50,000 nodes and 100,000 edges | Capture fails before writing a partial snapshot |

No limit is allowed to produce a silent partial evidence record.

## Reproducible measurement

Run the committed offline benchmark from a source checkout:

```bash
uv run python scripts/measure_capacity.py \
  --storage-entities 5000 \
  --graph-nodes 1000 \
  --output capacity-receipt.json
```

It creates temporary workspaces with IANA-reserved synthetic values, performs
no provider or model request, and deletes its temporary data when complete.
The JSON receipt records the environment, enforced limits, elapsed time,
traced Python allocation peak, database size, cockpit payload size, visible and
omitted records, and portable-export size.

On the v0.9.5 qualification host—Apple arm64, macOS 15.7.4, Python 3.14.6—the
5,000-entity evidence scenario measured:

| Operation | Elapsed | Traced Python peak |
|---|---:|---:|
| Empty cockpit startup | 0.235 s | 3.0 MiB |
| Store 5,000 synthetic entities | 7.840 s | 1.4 MiB |
| Build complete cockpit state | 3.851 s | 28.5 MiB |
| Serialize 3.00 MB cockpit payload | 0.140 s | 5.7 MiB |
| Build portable workspace export | 0.197 s | 14.4 MiB |
| Serialize 5.12 MB export | 0.213 s | 9.8 MiB |

The resulting SQLite workspace was 6.32 MB. The Constellation returned 4,995
rows for 555 indicators and explicitly counted 4,445 omitted indicators.

The 1,000-node/999-edge connected graph built complete cockpit state in 1.113
seconds with a 19.8 MiB traced Python peak and no omitted graph records. An
overflow rehearsal with 1,500 nodes/1,499 edges completed in 1.543 seconds,
kept 1,000 nodes and 999 edges in the bounded view, reported 1,000 omitted
node/edge records, and retained all 2,999 stored entity/relationship
observations.

These measurements are evidence about one run, not a latency service-level
agreement. Disk speed, Python build, browser, graph density, annotations,
observation count, and concurrent enrichment change the result.

## Not qualified in v0.9.6

- batch document admission and aggregate batch memory;
- interactive graph rendering beyond the bounded 1,000-node intent or 48-node
  force canvas;
- workspaces beyond 5,000 stored entities;
- cancellation latency for an enrichment already inside a provider call;
- concurrent multi-user or authenticated remote deployment;
- SCOT4 or Synapse production-scale authority workloads.

Cancellation is cooperative: Pivotglass acknowledges the request immediately,
lets the active enrichment return safely, then cancels remaining work. Its
worst-case time therefore depends on the active provider's timeout. A bounded
interruptible provider contract is a v1.0 gate; v0.9.6 does not advertise a
fixed cancellation latency.
