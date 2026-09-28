# Pivotglass v0.9.8 qualification

Date: 2026-09-27. This receipt covers the release source tree and patched locks.
Public commit, tag, artifact hashes, and signature verification belong to the
GitHub Release's publication receipt, generated after the immutable build.

## Verification

- Full Python suite: **4,245 passed, 2 skipped**, one SQLite datetime-adapter
  deprecation warning, in 233.54 seconds. HTTP integration tests required local
  socket permission; the sandbox-only run was not used as qualification.
- Browser unit tests: 54 passed; aggregate `npm --prefix web test` includes all suites.
- Focused release, documentation, and banner tests: 45 passed; decision-generator
  formatting verification: 6 passed after the final whitespace correction.
- Python Ruff, web ESLint, whitespace checks, Python lock validation, and frozen sync passed.
- Production static browser export built with Next.js 16.3.6.
- Python locked-package advisory audit and npm moderate-or-higher audit: no known
  vulnerabilities found after updates. This is advisory coverage, not a security proof.
- npm registry verification: 31 dependency signatures and 18 attestations verified.
- Redacted repository/history credential scan: zero findings within its bounded rules.
- Documentation local target/anchor validation: zero broken links; see editorial review.
- Real browser synthetic case: four nodes, three stored edges, complete-value wrapping,
  relationship legend/inventory, Novice Q&A unknown-to-next-prompt interaction;
  no browser console errors observed.
- Installed command reports `pivotglass 0.9.8`; default entry, help, Python import,
  explicit home-copy migration, preservation, symlink and overwrite refusal are tested.

## Dependency changes

Focused advisory fixes: aiohttp 3.14.3, anyio 4.14.2, click 8.3.3, idna 3.15,
litellm 1.84.0, urllib3 2.7.0. Browser fixes: Next.js 16.3.6, sharp 0.35.5,
and patched locked baseline-browser-mapping. The lock also resolves typing-extensions
4.16.0. Install the tagged source with the frozen lock for this qualification set.

## Boundaries

macOS was the release host. Passing deterministic fixtures is not live production
qualification of Synapse, SCOT, external APIs, every parser, or another OS. Browser
screenshots use synthetic training data. The historical video remains versioned.
The separate v1.0 assurance pass and owner approval remain required.

See [editorial review](EDITORIAL_REVIEW.md), [release trust](../../RELEASE_TRUST.md),
and [compatibility](../../COMPATIBILITY.md).
