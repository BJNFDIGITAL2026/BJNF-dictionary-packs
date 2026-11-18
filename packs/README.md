# Runtime language packs

Current BJNF V1.2.6 client reads:

- `packs.txt` in this directory — UTF-8 tab-separated pack manifest
- `<language-code>.txt` in this same directory — UTF-8 words, one per line

The current app does not parse JSON manifests or nested versioned paths. The version integer is carried in each manifest row. Keep previous released files separately under `archive/<code>/<version>/` for traceability. Do not publish an empty placeholder wordlist.

Manifest row format:
`<code><TAB><version><TAB><sha256><TAB><word-count><TAB><byte-count>`

Only list packs with complete BJNF legal clearance, provenance, native-speaker review and QA approval.
