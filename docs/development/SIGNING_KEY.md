# Owner-controlled release signing key

Release signatures bind the owner's decision to the immutable checksum
manifest. A key created by an automated reviewer is not a substitute for the
owner's identity. The owner creates and protects the private key; reviewers
need only the public key and full fingerprint.

## Create a signing key

With GnuPG installed, run this interactively in your own terminal, using the
name and email you want publicly associated with releases:

```bash
gpg --quick-generate-key "Your Name <you@example.org>" ed25519 sign 1y
```

Enter a strong passphrase in GnuPG's prompt. The key expires after one year;
renew or rotate it deliberately before expiry. Display its full fingerprint:

```bash
gpg --list-secret-keys --keyid-format LONG --fingerprint
```

Share the full fingerprint, not the private key or passphrase. GnuPG creates a
revocation certificate in `~/.gnupg/openpgp-revocs.d/`. Keep an offline backup
of the private key and revocation certificate under your control.
[GnuPG key-management reference](https://www.gnupg.org/documentation/manuals/gnupg/OpenPGP-Key-Management.html).

## Publish the public identity

Export only the public key to a file:

```bash
gpg --armor --output pivotglass-release-public-key.asc --export FULL_FINGERPRINT
```

Publish the full fingerprint through an independently controlled channel, such
as the owner's website, so users can check a release key they downloaded from
GitHub. Publish the public key alongside the release-verification instructions.
A public key shipped next to a signature alone does not establish its owner's
identity. Do not commit keyring directories or private material.

## Sign the final manifest

After final archive and inventory generation, use the full fingerprint:

```bash
gpg --local-user FULL_FINGERPRINT --armor --detach-sign \
  --output /absolute/path/to/bundle/SHA256SUMS.asc \
  /absolute/path/to/bundle/SHA256SUMS

gpg --verify /absolute/path/to/bundle/SHA256SUMS.asc \
  /absolute/path/to/bundle/SHA256SUMS
```

Enter the passphrase directly into GnuPG if prompted. Changing any covered
artifact requires a new checksum manifest and signature. Follow the complete
[release trust and public readback ceremony](../RELEASE_TRUST.md); an isolated
successful signature is not a completed public release.
