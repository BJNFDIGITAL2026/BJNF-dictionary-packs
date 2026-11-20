# Runtime language packs

The BJNF app (V1.3.1 and later) reads `../manifest.json` and downloads `packs/<code>/<version>/<code>.txt.gz`
(gzip, UTF-8, one word per line, most common first). See the main README for the full contract.

`packs.txt` in this folder is the old V1.2.6 manifest format, kept only for old test builds.
Only packs with verified licence records and native-speaker review are merged to `main`.
