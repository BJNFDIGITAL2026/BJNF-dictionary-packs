# BJNF Dictionary Packs

Official public pack host for BJNF AI Keyboard. Only language packs with verified BJNF commercial distribution rights may be published here.

## Current Android app download contract (V1.3.1 and later)

The app (`LanguagePackPolicy.kt`, `LanguagePackManager.kt`) reads these raw GitHub paths from `main`:

- Manifest: `manifest.json` - `{"schema": 1, "packs": [{"code", "version", "path", "sha256", "bytes", "words", "license_file"}]}`
- Pack data: `packs/<code>/<version>/<code>.txt.gz` - gzip, UTF-8, one word per line, most common first
- Licence: `licenses/<code>/SOURCES_AND_LICENCES.txt`

`sha256` and `bytes` describe the compressed file. The app rejects any entry whose `path` is not exactly
`packs/<code>/<version>/<code>.txt.gz`. A published version folder is never changed; raise the version instead.
`packs/packs.txt` is the old V1.2.6 format and is kept only for old test builds.

## How packs are built

`tools/build_corpus_pack.py` (run by the GitHub Action "Build word packs") reads the AI4Bharat IndicCorp v2
corpus (CC0) and keeps **only single words and their counts** - never sentences. It writes the pack, the
licence record, a native-speaker review sheet under `review/<code>/` and `checksums/SHA256SUMS.txt`.
Packs are built on a `build/...` branch and merged to `main` only after review.

## Upload and release process

1. Build the pack on a `build/...` branch (Actions > "Build word packs"), or put a gzip one-word-per-line pack at `packs/<code>/<version>/<code>.txt.gz`.
2. Put the matching legal record and attribution in `licenses/<code>/SOURCES_AND_LICENCES.txt`.
3. Confirm BJNF has documented worldwide commercial use, modification, hosting and redistribution rights for every included entry.
4. Run language/script validation, Unicode NFC normalization, deduplication, native-speaker review and device tests.
5. Compute the exact SHA-256 and byte count from the final file.
6. Merge to `main` (this publishes the `manifest.json` entry) only after all checks pass.
7. Increment the integer version for any replacement. Older version folders stay for rollback.

## Legal rule

Public hosting does not grant data rights. Do not publish scraped or third-party lists merely because they are accessible online. Quarantine entries with unknown provenance. See [licenses/README.md](licenses/README.md) and the BJNF locked language/legal policy in the private app repository.

## Supported coverage

The application architecture may support all 22 Scheduled Indian Languages plus English and additional languages. A language is offered for download only when a real, legally cleared, quality-reviewed pack has been published in the manifest. Do not advertise empty or untested packs.
