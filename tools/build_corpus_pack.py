#!/usr/bin/env python3
"""
Builds BJNF word packs (one word per line, most common first) from the AI4Bharat IndicCorp v2 corpus.

Legal design (see licenses/<code>/SOURCES_AND_LICENCES.txt written by this script):
  * IndicCorp v2 is released by AI4Bharat (IIT Madras) under CC0 1.0 (public domain dedication).
  * The underlying sentences come from public web pages whose own copyright may belong to their publishers.
    This script therefore keeps ONLY single words and how often they occur (facts, not expression).
    No sentence, phrase, paragraph or document text is written anywhere - not to the pack, not to the logs,
    not to the review files.

Usage (normally run by .github/workflows/build-packs.yml, because it needs internet):
  python tools/build_corpus_pack.py --lang te --top 100000 --version 1 --max-gb 5
  python tools/build_corpus_pack.py --finalize          # rewrites checksums/SHA256SUMS.txt

Output layout (the BJNF app V1.3.1+ contract, read by LanguagePackPolicy.kt):
  manifest.json                                  {"schema": 1, "packs": [...]}
  packs/<code>/<version>/<code>.txt.gz           gzip word list, deterministic bytes
  licenses/<code>/SOURCES_AND_LICENCES.txt       source, licence, exact revision, what was changed
  review/<code>/                                 top words + random sample with counts, for native-speaker review
  checksums/SHA256SUMS.txt                       SHA-256 of every published file
"""
import argparse, datetime, gzip, hashlib, json, os, random, re, sys, unicodedata, urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATASET = "ai4bharat/IndicCorpV2"
HF_API = f"https://huggingface.co/api/datasets/{DATASET}"
OBJECTSTORE = "https://objectstore.e2enetworks.net/ai4b-public-nlu-nlg/indic-corp-frozen-for-the-paper-oct-2022/{code}.txt"

LANGS = {
    # Telugu block without digits (0C66-0C6F) and fraction signs (0C78-0C7F), plus ZWNJ/ZWJ.
    "te": {"name": "Telugu", "chars": "\u0C00-\u0C65\u0C70-\u0C77\u200C\u200D", "virama": "\u0C4D"},
    # Devanagari without danda (0964-0965), digits (0966-096F) and abbreviation sign (0970), plus ZWNJ/ZWJ.
    "hi": {"name": "Hindi", "chars": "\u0900-\u0963\u0971-\u097F\u200C\u200D", "virama": "\u094D"},
    "en": {"name": "English", "chars": None},
}
EN_TOKEN = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")
EN_SINGLE_OK = {"a", "i"}
MAX_WORD_LEN = 40          # same limit as the app (DictionaryImport.MAX_WORD_LENGTH)
MIN_PACK_WORDS = 1000     # fewer than this means the source is broken
PRUNE_AT = 6_000_000       # distinct words kept in memory before rare ones are pruned


def log(*a):
    print(*a, flush=True)


def http_json(url, token=None):
    req = urllib.request.Request(url, headers={"User-Agent": "BJNF-pack-builder"})
    if token:
        req.add_header("Authorization", "Bearer " + token)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def resolve_sources(code, token):
    """Returns (list of (url, label)), provenance dict. Hugging Face first (pinned to a commit), then the frozen object store."""
    prov = {"dataset": DATASET}
    try:
        info = http_json(HF_API, token)
        sha = info.get("sha")
        prov.update({"hf_revision": sha, "hf_last_modified": info.get("lastModified"),
                     "hf_card_license": (info.get("cardData") or {}).get("license"), "hf_gated": info.get("gated")})
        tree = http_json(f"{HF_API}/tree/{sha}/data", token)
        pat = re.compile(rf"^data/{code}(?:[-_][^/]*)?\.txt$")
        files = sorted(e["path"] for e in tree if e.get("type") == "file" and pat.match(e["path"]))
        if files:
            prov["files"] = files
            prov["url_base"] = f"https://huggingface.co/datasets/{DATASET}/resolve/{sha}/"
            return [(prov["url_base"] + f, f) for f in files], prov
        log(f"  Hugging Face has no data/{code}*.txt file; trying the frozen object store")
    except Exception as e:
        log("  Hugging Face listing failed:", e)
    url = OBJECTSTORE.format(code=code)
    prov.update({"files": [url], "url_base": "", "hf_revision": None, "note": "AI4Bharat frozen IndicCorp v2 release (Oct 2022) object store"})
    return [(url, url)], prov


def stream_lines(url, token, byte_budget):
    """Yields decoded lines from url until byte_budget bytes have been read. Text is only held one line at a time."""
    req = urllib.request.Request(url, headers={"User-Agent": "BJNF-pack-builder"})
    if token and "huggingface.co" in url:
        req.add_header("Authorization", "Bearer " + token)
    read = 0
    with urllib.request.urlopen(req, timeout=120) as r:
        for raw in r:
            read += len(raw)
            yield raw.decode("utf-8", "ignore"), len(raw)
            if read >= byte_budget:
                return


def make_tokenizer(code):
    if code == "en":
        def tok(line):
            for m in EN_TOKEN.findall(line):
                w = m.lower()
                if len(w) == 1 and w not in EN_SINGLE_OK:
                    continue
                yield w
        return tok
    rx = re.compile(f"[{LANGS[code]['chars']}]+")
    virama = LANGS[code]["virama"]

    def tok(line):
        for m in rx.findall(line):
            w = clean_joiners(m, virama, code)
            if w and unicodedata.category(w[0]) == "Lo":
                yield w
    return tok


def clean_joiners(w, virama, code):
    """News sites often put ZWNJ/ZWJ inside words by mistake (e.g. ma<ZWNJ>rovaipu). In Telugu a ZWNJ is only
    meaningful right after a virama (lak<virama><ZWNJ>daun), so all others are removed and the counts merge.
    Hindi typing never needs them, so they are always removed there."""
    if code == "te":
        out = []
        for i, ch in enumerate(w):
            if ch == "\u200D" or (ch == "\u200C" and (i == 0 or w[i - 1] != virama)):
                continue
            out.append(ch)
        w = "".join(out)
    else:
        w = w.replace("\u200C", "").replace("\u200D", "")
    return w.strip("\u200C\u200D")


def load_blocklist(code):
    """tools/blocklist/<code>.txt: one entry per line. 'word' blocks that exact word, 'word*' blocks every word
    starting with it. Offensive words must never be offered as suggestions. Native reviewers extend this list."""
    exact, prefixes = set(), []
    p = ROOT / "tools" / "blocklist" / f"{code}.txt"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = unicodedata.normalize("NFC", line.split("#", 1)[0].strip())
            if not line:
                continue
            if line.endswith("*"):
                prefixes.append(line[:-1])
            else:
                exact.add(line)
    return exact, tuple(prefixes)


def blocked(w, bl):
    exact, prefixes = bl
    return w in exact or bool(prefixes and w.startswith(prefixes))


def good_word(w):
    if not (1 <= len(w) <= MAX_WORD_LEN):
        return False
    if re.search(r"(.)\1\1\1", w):           # "aaaa", "హహహహ" style noise
        return False
    return True


def count_words(code, sources, token, max_bytes):
    tok = make_tokenizer(code)
    counts = Counter()
    floor = 2
    total_bytes = lines = tokens = 0
    for url, label in sources:
        if total_bytes >= max_bytes:
            break
        log(f"  reading {label}")
        for line, n in stream_lines(url, token, max_bytes - total_bytes):
            total_bytes += n
            lines += 1
            line = unicodedata.normalize("NFC", line)
            for w in tok(line):
                counts[w] += 1
                tokens += 1
            if len(counts) > PRUNE_AT:
                before = len(counts)
                counts = Counter({w: c for w, c in counts.items() if c >= floor})
                log(f"    pruned rare words below {floor}: {before} -> {len(counts)}")
                floor *= 2
            if lines % 2_000_000 == 0:
                log(f"    {lines:,} lines, {total_bytes / 1e9:.2f} GB, {len(counts):,} distinct words")
    return counts, {"bytes_read": total_bytes, "lines_read": lines, "tokens": tokens, "prune_floor_reached": floor}


def pack_bytes(words):
    data = ("\n".join(words) + "\n").encode("utf-8")
    return gzip.compress(data, compresslevel=9, mtime=0)


def sha256(b):
    return hashlib.sha256(b).hexdigest()


def write_licence(code, prov, stats, n_words, min_count):
    name = LANGS[code]["name"]
    today = datetime.date.today().isoformat()
    files = "\n".join("    " + f for f in prov.get("files", []))
    text = f"""BJNF AI Keyboard - {name} word pack ({code}) - sources and licences
Generated: {today}

SOURCE
  Name:      IndicCorp v2 (AI4Bharat, IIT Madras)
  Dataset:   https://huggingface.co/datasets/{DATASET}
  Project:   https://github.com/AI4Bharat/IndicBERT/tree/main#indiccorp-v2
  Revision:  {prov.get('hf_revision') or prov.get('note', 'n/a')}
  Files read:
{files}
  Bytes read: {stats['bytes_read']:,}  Lines read: {stats['lines_read']:,}

LICENCE
  The dataset card states: all datasets created as part of this work are released under CC-0
  (Creative Commons CC0 1.0 Universal, public domain dedication):
  https://creativecommons.org/publicdomain/zero/1.0/
  (The Hugging Face card has no separate licence field; the CC-0 statement is in its License section.)
  CC0 permits commercial use, modification and redistribution without conditions.

WHAT BJNF TOOK AND WHAT IT CHANGED
  * Only single words and their occurrence counts were extracted. No sentence, phrase or document text
    from the corpus is stored, published or shipped. (The corpus text was collected from public web pages;
    their wording may be owned by the original publishers, so BJNF keeps only words, which are facts.)
  * Unicode NFC normalisation; only words written fully in the {name} script were kept
    (no digits, no punctuation, no mixed scripts); stray zero-width joiners removed; length 1-{MAX_WORD_LEN};
    obvious repeated-letter noise removed; offensive words removed (tools/blocklist/{code}.txt).
  * Kept words seen at least {min_count} times; ranked most frequent first; the top {n_words:,} words published.
  * English words were lower-cased.

ATTRIBUTION (courtesy - not required by CC0)
  Doddapaneni et al., "Towards Leaving No Indic Language Behind: Building Monolingual Corpora,
  Benchmark and Models for Indic Languages", ACL 2023.

STATUS
  Source licence: verified (CC0).  Native-speaker review: see review/{code}/ - pending until signed off.
"""
    p = ROOT / "licenses" / code / "SOURCES_AND_LICENCES.txt"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def write_review(code, ranked, counts):
    d = ROOT / "review" / code
    d.mkdir(parents=True, exist_ok=True)
    (d / "top_500.tsv").write_text("".join(f"{i+1}\t{w}\t{counts[w]}\n" for i, w in enumerate(ranked[:500])), encoding="utf-8")
    rnd = random.Random(20261121)
    sample = sorted(rnd.sample(range(len(ranked)), min(300, len(ranked))))
    (d / "random_300.tsv").write_text("".join(f"{i+1}\t{ranked[i]}\t{counts[ranked[i]]}\n" for i in sample), encoding="utf-8")
    (d / "tail_200.tsv").write_text("".join(f"{len(ranked)-200+i+1}\t{w}\t{counts[w]}\n" for i, w in enumerate(ranked[-200:])), encoding="utf-8")
    (d / "README.md").write_text(
        f"# {LANGS[code]['name']} review sheet\n\n"
        "Rank, word, number of times seen in the corpus. A native speaker should mark wrong spellings, "
        "offensive words and personal names here before the pack is merged to `main`.\n\n"
        "- `top_500.tsv` - most common words\n- `random_300.tsv` - random sample across the whole list\n"
        "- `tail_200.tsv` - the rarest words that still made the cut (most likely to contain errors)\n",
        encoding="utf-8")


def update_manifest(entry):
    mpath = ROOT / "manifest.json"
    m = json.loads(mpath.read_text(encoding="utf-8")) if mpath.exists() else {}
    m.pop("schema_version", None)
    m = {"schema": 1, **{k: v for k, v in m.items() if k != "schema"}}
    packs = {p["code"]: p for p in m.get("packs", [])}
    packs[entry["code"]] = entry
    m["packs"] = sorted(packs.values(), key=lambda e: e["code"])
    m["repository"] = "BJNFDIGITAL2026/BJNF-dictionary-packs"
    m["updated_at"] = datetime.date.today().isoformat()
    mpath.write_text(json.dumps(m, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def finalize():
    sums = []
    for p in sorted(ROOT.rglob("*")):
        rel = p.relative_to(ROOT).as_posix()
        if p.is_file() and (rel == "manifest.json" or rel.startswith("packs/") or rel.startswith("licenses/")) and p.name != "README.md":
            sums.append(f"{sha256(p.read_bytes())}  {rel}")
    (ROOT / "checksums").mkdir(exist_ok=True)
    (ROOT / "checksums" / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n", encoding="utf-8")
    log(f"checksums: {len(sums)} files")


def build(code, top, version, max_gb, min_count, token):
    log(f"== {code} ({LANGS[code]['name']})")
    sources, prov = resolve_sources(code, token)
    counts, stats = count_words(code, sources, token, int(max_gb * 1e9))
    bl = load_blocklist(code)
    ranked, n_blocked = [], 0
    for w, c in sorted(counts.items(), key=lambda x: (-x[1], x[0])):
        if c < min_count or len(ranked) >= top:
            break
        if not good_word(w):
            continue
        if blocked(w, bl):
            n_blocked += 1
            continue
        ranked.append(w)
    stats["blocked_offensive"] = n_blocked
    if len(ranked) < MIN_PACK_WORDS:
        sys.exit(f"{code}: only {len(ranked)} words - something is wrong with the source, nothing written")
    blob = pack_bytes(ranked)
    rel = f"packs/{code}/{version}/{code}.txt.gz"
    target = ROOT / rel
    if target.exists() and target.read_bytes() != blob:
        sys.exit(f"{rel} already exists with different content. Use a higher --version.")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(blob)
    write_licence(code, prov, stats, len(ranked), min_count)
    write_review(code, ranked, counts)
    update_manifest({
        "code": code, "version": version, "path": rel, "sha256": sha256(blob), "bytes": len(blob), "words": len(ranked),
        "license_file": f"licenses/{code}/SOURCES_AND_LICENCES.txt",
        "source": "IndicCorp v2 (AI4Bharat) - CC0-1.0 - words and counts only",
        "licence_review": "source licence verified CC0; native-speaker review pending",
    })
    stats.update({"code": code, "words": len(ranked), "gz_bytes": len(blob), "min_count": min_count,
                  "lowest_kept_count": counts[ranked[-1]], "provenance": prov})
    (ROOT / "review" / code / "build_stats.json").write_text(json.dumps(stats, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    log(f"  {code}: {len(ranked):,} words, {len(blob)/1024:.0f} KB gz, lowest kept count {counts[ranked[-1]]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", nargs="*", default=[])
    ap.add_argument("--top", type=int, default=100000)
    ap.add_argument("--top-en", type=int, default=50000, help="English already ships ~107k words in the app")
    ap.add_argument("--version", type=int, default=1)
    ap.add_argument("--max-gb", type=float, default=5.0, help="corpus bytes to read per language")
    ap.add_argument("--min-count", type=int, default=20)
    ap.add_argument("--finalize", action="store_true")
    a = ap.parse_args()
    token = os.environ.get("HF_TOKEN") or None
    for code in a.lang:
        if code not in LANGS:
            sys.exit(f"unknown language {code}")
        build(code, a.top_en if code == "en" else a.top, a.version, a.max_gb, a.min_count, token)
    if a.finalize or a.lang:
        finalize()


if __name__ == "__main__":
    main()
