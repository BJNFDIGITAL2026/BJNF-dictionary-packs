# BJNF Dictionary Packs

Official public pack host for BJNF AI Keyboard. Only language packs with verified BJNF commercial distribution rights may be published here.

## Current Android app download contract

The current BJNF V1.2.6 language-pack client expects these exact raw GitHub paths:

- Manifest: `packs/packs.txt`
- Pack data: `packs/<language-code>.txt`

The manifest is UTF-8 text, one tab-separated row per released pack:

```text
<code>\t<version-integer>\t<sha256-lowercase-hex>\t<word-count>\t<byte-count>
```

Example format only (not a published pack):
`te<TAB>1<TAB><64-character SHA-256><TAB><word count><TAB><byte count>`

Do not add an example row with dummy values. The manifest currently contains no published packs until actual data passes BJNF's legal and linguistic release checks.

The client downloads `packs/<code>.txt`, verifies exact byte count and SHA-256, and stores the selected pack on-device. No JSON manifest or versioned nested path is consumed by this current app client. The root `manifest.json` is repository planning metadata only.

## Upload and release process

1. Put the exact one-word-per-line UTF-8 pack at `packs/<code>.txt`.
2. Put the matching legal record and attribution in `licenses/<code>/`.
3. Confirm BJNF has documented worldwide commercial use, modification, hosting and redistribution rights for every included entry.
4. Run language/script validation, Unicode NFC normalization, deduplication, native-speaker review and device tests.
5. Compute the exact SHA-256 and byte count from the final file.
6. Add a row to `packs/packs.txt` only after all checks pass.
7. Increment the integer version for any replacement. Keep an archived copy of previous releases under `archive/<code>/<version>/` for internal traceability; do not point the current app manifest at nested paths.

## Legal rule

Public hosting does not grant data rights. Do not publish scraped or third-party lists merely because they are accessible online. Quarantine entries with unknown provenance. See [LICENSES/README.md](LICENSES/README.md) and the BJNF locked language/legal policy in the private app repository.

## Supported coverage

The application architecture may support all 22 Scheduled Indian Languages plus English and additional languages. A language is offered for download only when a real, legally cleared, quality-reviewed pack has been published in the manifest. Do not advertise empty or untested packs.
