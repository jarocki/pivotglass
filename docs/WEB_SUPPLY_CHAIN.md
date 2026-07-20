# Pivotglass web supply-chain policy

The local web cockpit does not claim that third-party software is defect-free.
It uses concrete cryptographic controls to establish artifact integrity and
available publisher provenance:

1. Production and build dependencies use exact versions in `web/package.json`.
2. `web/package-lock.json` records SHA-512 integrity for the complete npm graph.
3. `npm ci` must reproduce that graph without modifying the lockfile.
4. `npm audit signatures` must verify registry signatures and available SLSA
   provenance attestations before release.
5. `npm audit --audit-level=moderate` must report zero known vulnerabilities.
6. The production UI is a static export served from AP itself on `127.0.0.1`.
   It loads no CDN scripts, fonts, telemetry, or remote UI code.
7. The Python lockfile retains hashes for the analysis engine dependencies.

Initial verified direct artifacts on 2026-07-19:

| Package | Version | Registry integrity/provenance |
|---|---:|---|
| Next.js | 16.2.10 | SHA-512 integrity + SLSA provenance |
| React | 19.2.7 | SHA-512 integrity + SLSA provenance |
| React DOM | 19.2.7 | SHA-512 integrity + SLSA provenance |
| Microsoft Flint | 0.3.0 | SHA-512 integrity + SLSA provenance |
| PostCSS override | 8.5.20 | SHA-512 integrity + SLSA provenance |
| Chart.js | 4.5.1 | SHA-512 integrity; no publisher attestation advertised |

The absence of a publisher attestation is visible rather than silently equated
with provenance. Chart.js remains independently integrity-locked. A future
release gate may replace it with a renderer providing signed provenance if that
becomes a strict requirement.
