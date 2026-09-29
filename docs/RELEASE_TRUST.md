# Release trust artifacts and public readback

Pivotglass release trust is a verifiable chain, not a badge on a build. The
committed Python and npm lockfiles define the dependency set. Final immutable
archives are bound to a machine-readable SBOM and human-reviewable license
inventory by one checksum manifest. The repository owner signs that manifest,
publishes the complete bundle, then downloads and verifies it from the public
release.

This procedure does not claim that a dependency is safe merely because it is
listed or signed. It establishes exactly what was built and whether the
downloaded bytes match the owner's release decision.

The SBOM describes the exact Python and npm lockfiles used to qualify the source
release and build the packaged browser. Python wheel metadata intentionally
uses compatible version ranges, so an unconstrained wheel installer can resolve
newer dependencies. The supported pre-1.0 install is the tagged source checkout
with `uv sync --frozen`; a standalone wheel install is a package-compatibility
check, not a reproduction of the locked environment.

## Generated artifacts

`scripts/generate_release_trust.py` reads `uv.lock` and
`web/package-lock.json` and fails closed when:

- an exact locked Python package is missing from the release environment or
  has a different version, except for the three reviewed platform-conditional
  packages recorded in the generator;
- any Python or npm package lacks a usable license declaration;
- an npm package lacks a registry integrity digest;
- a release archive is missing; or
- artifact basenames are ambiguous or collide with generated names.

For one immutable wheel and source archive it writes:

| Artifact | Purpose |
|---|---|
| `pivotglass.cdx.json` | CycloneDX 1.5 inventory of every Python and npm lockfile component, declared license, integrity digest, scope, and dependency relationship that the lockfiles resolve |
| `THIRD_PARTY_LICENSES.csv` | Human-reviewable exact-version license inventory with the source of each declaration |
| `SHA256SUMS` | SHA-256 binding for the wheel, source archive, SBOM, and license inventory |

The generator uses the checked-out commit timestamp by default so an identical
source tree, environment, and pair of archives produces identical trust files.
An explicit timezone-qualified `--timestamp` may be supplied for a release
ceremony.

## Final build and bundle

Run this from a clean checkout of the exact candidate commit. The directory
must contain only the final candidate output; do not reuse a historical
`dist/` directory.

```bash
PIVOTGLASS_VERSION=0.9.9
PIVOTGLASS_BUNDLE="$(mktemp -d)"

uv lock --check
uv sync --all-extras --frozen
uv run pytest -q
uv run ruff check src tests scripts
npm --prefix web ci
npm --prefix web run lint
npm --prefix web test
npm --prefix web run build
npm --prefix web audit --audit-level=moderate
uv build --out-dir "$PIVOTGLASS_BUNDLE"

uv run python scripts/generate_release_trust.py \
  --output-dir "$PIVOTGLASS_BUNDLE" \
  --artifact "$PIVOTGLASS_BUNDLE/pivotglass-${PIVOTGLASS_VERSION}-py3-none-any.whl" \
  --artifact "$PIVOTGLASS_BUNDLE/pivotglass-${PIVOTGLASS_VERSION}.tar.gz"
```

Review the generated component counts, every non-standard license declaration,
and any platform-conditional package before signing. The generator's three
curated declarations are exact-version records for Colorama 0.4.6, greenlet
3.5.0, and pyreadline3 3.5.4; changing one of those lockfile versions without a
new reviewed declaration fails closed. The declaration evidence links directly
to the exact [Colorama](https://pypi.org/project/colorama/0.4.6/),
[greenlet](https://pypi.org/project/greenlet/3.5.0/), and
[pyreadline3](https://pypi.org/project/pyreadline3/3.5.4/) upstream package
metadata in the generated inventory.

## Verify the current guided media before freezing the candidate

The current demo is an edited narrated sequence of actual local browser states
from an isolated synthetic workspace. Its caption file, transcript, poster,
chapter manifest, screenshots, and MP4 are under `docs/media/` with v0.9.9 in
their filenames. The transcript discloses the method; the video is not a
continuous screen recording or evidence of a live provider round trip.

Before archiving, check the following against the actual files:

1. The MP4 decodes, its video/audio/subtitle streams are readable, and ordinary
   playback exposes the intended scene and caption transitions.
2. Caption cues are ordered, bounded by the media duration, and match the
   spoken content and transcript. The visible scene must support its caption:
   graph footage must show the graph, not only its toolbar.
3. Synthetic labels, complete indicator values, branch and edge distinctions,
   explicit save/admission receipts, and analyst interpretation are preserved.
4. Screens contain no credential, private source, personal data, or live-case
   indicator. The chapter manifest describes what was actually recorded.
5. Current guide links open the new files; historical media stays labeled in
   the release record rather than serving as the current tour.

A maintainer can inspect streams and decode the file with local media tools:

```bash
ffprobe -v error -show_streams -show_format docs/media/pivotglass-guided-demo-v0.9.9.mp4
ffmpeg -v error -i docs/media/pivotglass-guided-demo-v0.9.9.mp4 -f null -
```

Media verification is additional to application tests. The signed source
archive binds the tracked media bytes it includes. If media is also attached
separately to a release, supply those final files as additional repeatable
`--artifact` inputs to the trust generator before signing. Any later media
change requires a regenerated manifest and signature, just like a code change.

## Release signing identity

The owner supplied signing fingerprint
`4CB08BD1D0B3281613DD15DB1DCCDF47FEEDEEEF` (John Jarocki,
`john@jarocki.org`; expires 2027-09-28). The [public key](releases/RELEASE_SIGNING_KEY.asc)
is included for verification. Confirm this fingerprint through an independently
controlled owner channel before treating it as authenticated identity.

## Sign the immutable manifest

If the owner has no signing key yet, follow [owner-controlled key setup](development/SIGNING_KEY.md) before the final ceremony.

Use an owner-controlled signing key whose full fingerprint is published through
an independently controlled channel. Never place a private key or passphrase in
this repository, a shell history, a release attachment, or an automated model
prompt.

```bash
gpg --armor --detach-sign \
  --output "$PIVOTGLASS_BUNDLE/SHA256SUMS.asc" \
  "$PIVOTGLASS_BUNDLE/SHA256SUMS"

gpg --verify \
  "$PIVOTGLASS_BUNDLE/SHA256SUMS.asc" \
  "$PIVOTGLASS_BUNDLE/SHA256SUMS"
```

Signing `SHA256SUMS` binds the two package archives and both inventories. The
signature is separate because including it in the manifest would be recursive.
Record the signing-key fingerprint and the exact candidate commit in the
release notes.

## Publish and read back

Attach all six files to the GitHub Release: wheel, source archive, SBOM, license
inventory, checksum manifest, and detached signature. Then verify the public
state from a new directory; do not verify the local upload source.

```bash
PIVOTGLASS_READBACK="$(mktemp -d)"
gh release download "v${PIVOTGLASS_VERSION}" \
  --repo jarocki/pivotglass \
  --dir "$PIVOTGLASS_READBACK"

gpg --verify \
  "$PIVOTGLASS_READBACK/SHA256SUMS.asc" \
  "$PIVOTGLASS_READBACK/SHA256SUMS"

(cd "$PIVOTGLASS_READBACK" && shasum -a 256 -c SHA256SUMS)
```

Finally read back and record that public `main`, the tag target, GitHub Release
metadata, and downloaded package metadata all identify the same commit and
version. A local build, local tag, successful upload, or green workflow alone
is not a completed release.

## Current boundary

The v0.9.9 candidate source tree contains the generator, deterministic tests, support
guidance, and this manual ceremony because release workflows are intentionally
kept out of the public repository. The final signature and public readback can
exist only after the immutable candidate is approved and published. Until then,
they remain publication gates rather than claimed receipts.
