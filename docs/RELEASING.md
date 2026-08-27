# Pivotglass release discipline

Pivotglass treats the version as part of the user-facing contract, not as a
label added after development. Feature-bearing code must never reach `main`
while the repository still advertises an older release.

## Version policy

- Increment the patch version for compatible fixes and small improvements.
- Increment the minor version for a significant new capability or work package.
- Reserve `1.0.0` for the stable public-contract and assurance gates in the
  approved roadmap.

A feature-bearing pull request changes runtime behavior under `src/`, the web
application or its production dependencies under `web/`, or an operational
script under `scripts/`. Such a pull request must advance the version relative
to its target branch.

The following surfaces must agree:

- `pyproject.toml`;
- `src/adversary_pursuit/__init__.py`;
- `uv.lock`;
- `web/package.json` and the root package entry in `web/package-lock.json`;
- the current-release statement and examples in `README.md` and the Quick Start;
- a dated release section in `CHANGELOG.md`.

## Required sequence

1. Branch from the current public `main`; do not reconstruct a release from an
   older feature branch.
2. Advance and synchronize the version and move the completed changelog entries
   from **Unreleased** into the dated release section.
3. Run the release-contract check, lockfile checks, Python and web tests, static
   analysis, production builds, package builds, audits, and a real command/web
   smoke test.
4. Record verified receipts and any explicit, bounded deferrals in the release
   quality record. A deferred external-system test must not be described as
   passed, and the affected capability must remain disabled or fail closed.
5. Merge the release pull request into public `main`.
6. Create `vX.Y.Z` at that exact merge commit, push it, and publish the GitHub
   Release with its wheel and source archive.
7. Read back public `main`, the tag target, release metadata, and downloadable
   assets. The release is not complete until all four agree.

## Preventive enforcement

`scripts/check_release_contract.py` compares the proposed tree with a target
commit and fails when feature-bearing paths change without a greater semantic
version. It also verifies synchronized manifests, operator documentation, and
changelog state. For a release tag it additionally requires the tag and
declared version to match exactly.

The tracked `.githooks/pre-push` guard runs the contract before a direct push to
`main` and before a release tag is published. Enable it once in each clone:

```bash
git config core.hooksPath .githooks
```

The repository intentionally does not publish its locally retained workflow
files. Therefore pull-request review must record a successful explicit check:

```bash
python scripts/check_release_contract.py --base origin/main
```

Repository branch protection should require pull requests into `main`. Direct
feature pushes remain unacceptable even when the local guard would permit a
properly versioned tree.
