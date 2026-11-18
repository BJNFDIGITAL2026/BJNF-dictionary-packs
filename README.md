# BJNF Dictionary Packs

Public distribution repository for BJNF AI Keyboard language packs.

## Repository layout

- `manifest.json` — versioned list of available language packs
- `packs/<language-code>/<version>/` — downloadable pack files
- `licenses/<language-code>/` — license and attribution records for each pack
- `checksums/SHA256SUMS.txt` — SHA-256 checksums for published files

## Upload rules

1. Upload only language data that BJNF is authorized to redistribute.
2. Include the original license and required attribution for every source.
3. Do not mix assets with different licenses without documenting each one.
4. Update `manifest.json` with the exact filename, version, size and SHA-256 checksum.
5. Test the pack before publishing it for app downloads.

## Important

Public hosting does not itself grant redistribution rights. Each pack must pass its own license review before release.
