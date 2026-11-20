#!/usr/bin/env python3
"""
Second, independent check for Telugu and Hindi words: counts how often each word appears in the
Wikipedia article dump of that language (te.wikipedia.org / hi.wikipedia.org).

Wikipedia is used ONLY as a yes/no check that a word is used by a second, independent community of writers.
No Wikipedia text is published or shipped: the output file stays in work/ and is not part of any pack.

  python tools/wiki_counts.py --lang te hi
writes work/<code>/wiki_counts.tsv.gz  (word TAB count, words seen at least twice) and work/<code>/wiki_stats.json
"""
import argparse, bz2, gzip, json, sys, unicodedata, urllib.request
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_corpus_pack as b  # same tokenizer and cleaning as the packs

DUMP = "https://dumps.wikimedia.org/{w}wiki/latest/{w}wiki-latest-pages-articles.xml.bz2"


def count(code):
    url = DUMP.format(w=code)
    b.log(f"== wikipedia {code}: {url}")
    tok = b.make_tokenizer(code)
    counts = Counter()
    dec = bz2.BZ2Decompressor()
    buf = b""
    read = 0
    req = urllib.request.Request(url, headers={"User-Agent": "BJNF-pack-builder (dictionary QA; contact via GitHub BJNFDIGITAL2026)"})
    with urllib.request.urlopen(req, timeout=120) as r:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            read += len(chunk)
            data = dec.decompress(chunk)
            if dec.eof:
                rest = dec.unused_data
                dec = bz2.BZ2Decompressor()
                data += dec.decompress(rest) if rest else b""
            buf += data
            lines = buf.split(b"\n")
            buf = lines.pop()
            for raw in lines:
                line = unicodedata.normalize("NFC", raw.decode("utf-8", "ignore"))
                for w in tok(line):
                    counts[w] += 1
            if read % (100 << 20) < (1 << 20):
                b.log(f"   {read / 1e6:.0f} MB compressed read, {len(counts):,} distinct words")
    rows = [(w, c) for w, c in counts.items() if c >= 2 and b.good_word(w)]
    rows.sort(key=lambda x: (-x[1], x[0]))
    d = b.ROOT / "work" / code
    d.mkdir(parents=True, exist_ok=True)
    (d / "wiki_counts.tsv.gz").write_bytes(gzip.compress("".join(f"{w}\t{c}\n" for w, c in rows).encode("utf-8"), 9, mtime=0))
    (d / "wiki_stats.json").write_text(json.dumps({"url": url, "compressed_bytes": read, "distinct_kept": len(rows)}, indent=2) + "\n", encoding="utf-8")
    b.log(f"  {code}: {len(rows):,} words seen at least twice")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", nargs="+", required=True)
    for code in ap.parse_args().lang:
        count(code)


if __name__ == "__main__":
    main()
