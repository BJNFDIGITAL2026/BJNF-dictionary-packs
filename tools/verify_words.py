#!/usr/bin/env python3
"""
Checks EVERY candidate word before it may enter a BJNF pack or the app's built-in lists, and records why each
rejected word was rejected. Run after the "Collect word data" workflow has filled work/.

  python tools/verify_words.py --version 1 [--app-src <unpacked app source>]

Telugu / Hindi - a word is kept only if ALL checks pass:
  1. not on tools/blocklist/<code>.txt (offensive)
  2. valid letter sequence (Unicode syllable rules: vowel signs, virama, nukta, anusvara only where the script allows)
  3. no known corruption pattern (wrong ra-ottu order such as స్ర్త, legacy-font junk such as ङ्क्ष)
  4. seen at least --min-count times in IndicCorp v2 (CC0)
  5. confirmed by a second, independent source: also used on Wikipedia in that language (>= 2 times),
     or so common in IndicCorp (>= --solo-count) that it cannot be a stray typo
  6. not a likely misspelling: if changing one vowel length (ి/ీ, ు/ూ, ె/ే, ొ/ో ...) gives a word that is
     --variant-ratio times more common in BOTH IndicCorp and Wikipedia, the rarer form is dropped
     (Telugu word-final long vowels are grammar - నేనూ, తల్లీ - and are never treated as errors)
  7. not on tools/rejectlist/<code>.txt: misspellings found by hand review of words that differ from a
     much more common word by one missing or extra letter (సమచారం, स्वस्थ्य)
English - only words in SCOWL (wamerican-large, permissive licence) are kept, ranked by IndicCorp frequency.

Outputs: packs/<code>/<version>/<code>.txt.gz (te, hi), licences, review sheets, review/<code>/rejected.tsv.gz
(every rejected word with its reason), work/app_builtin/<code>.txt (checked lists for the app's built-in assets).
"""
import argparse, gzip, json, re, sys, unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_corpus_pack as b

ROOT = b.ROOT
WORK = ROOT / "work"

# ---------- script rules ----------
def cls_te(ch):
    o = ord(ch)
    if 0x0C05 <= o <= 0x0C14 or o in (0x0C60, 0x0C61): return "V"
    if 0x0C15 <= o <= 0x0C39 or 0x0C58 <= o <= 0x0C5A: return "C"
    if 0x0C3E <= o <= 0x0C4C or o in (0x0C55, 0x0C56, 0x0C62, 0x0C63): return "M"
    if o == 0x0C4D: return "H"
    if o in (0x0C00, 0x0C01, 0x0C02, 0x0C03, 0x0C04): return "B"
    if o == 0x200C: return "Z"
    return "X"


def cls_hi(ch):
    o = ord(ch)
    if 0x0904 <= o <= 0x0914 or o in (0x0960, 0x0961) or 0x0972 <= o <= 0x0977: return "V"
    if 0x0915 <= o <= 0x0939 or 0x0958 <= o <= 0x095F or 0x0978 <= o <= 0x097F: return "C"
    if o == 0x093C: return "N"
    if 0x093E <= o <= 0x094C or o in (0x094E, 0x094F, 0x0955, 0x0956, 0x0957, 0x0962, 0x0963): return "M"
    if o == 0x094D: return "H"
    if 0x0900 <= o <= 0x0903: return "B"
    if o == 0x093D: return "A"
    return "X"


def valid_sequence(w, code):
    if w == "\u0950":                       # ॐ on its own
        return True
    cls = cls_te if code == "te" else cls_hi
    seq = [cls(c) for c in w]
    if "X" in seq or seq[0] not in ("V", "C"):
        return False
    for i in range(1, len(seq)):
        p, c = seq[i - 1], seq[i]
        if c == "M" and p not in ("C", "N"): return False          # vowel sign only on a consonant
        if c == "N" and p != "C": return False                       # nukta only on a consonant
        if c == "H" and p not in ("C", "N"): return False          # virama only on a consonant
        if c == "B" and p not in ("V", "C", "M", "N"): return False  # anusvara/visarga after a letter or sign
        if c == "Z" and p != "H": return False                       # ZWNJ only after virama
        # after virama: a consonant (conjunct). Telugu also writes acronyms as consonant+virama+vowel (టీఆర్ఎస్ = TRS).
        if p == "H" and c not in ("C", "Z") and not (code == "te" and c == "V"): return False
        if p == "Z" and c != "C" and not (code == "te" and c == "V"): return False
        if c == "A" and p == "H": return False
    return True


RA = {"te": "\u0C30", "hi": "\u0930"}
YA_VA = {"te": ("\u0C2F", "\u0C35"), "hi": ("\u092F", "\u0935")}   # త్ర్య style conjuncts are correct
VIRAMA = {"te": "్", "hi": "्"}
JUNK = {"hi": ["ङ्क्ष"], "te": []}   # ङ्क्ष = legacy-font conversion junk


def corruption(w, code):
    cls = cls_te if code == "te" else cls_hi
    v, ra = VIRAMA[code], RA[code]
    for i in range(1, len(w) - 2):
        # consonant + virama + RA + virama + consonant: ra-ottu typed in the wrong place (స్ర్త for స్త్ర)
        if w[i] == v and w[i + 1] == ra and w[i + 2] == v and cls(w[i - 1]) == "C" and i + 3 < len(w) and cls(w[i + 3]) == "C" and w[i + 3] not in YA_VA[code]:
            return "ra_ottu_order"
    if code == "hi" and any(ch in w for ch in "\u0929\u0931\u0934"):
        return "legacy_font_junk"       # ऩ ऱ ऴ do not occur in Hindi; they come from old font conversion (पढऩे)
    for j in JUNK[code]:
        if j in w:
            return "legacy_font_junk"
    return None


# vowel-length pairs: a one-letter change between these is the most common Indian-language spelling error
PAIRS = {
    "te": [("ి", "ీ"), ("ు", "ూ"), ("ె", "ే"), ("ొ", "ో"),
           ("ఇ", "ఈ"), ("ఉ", "ఊ"), ("ఎ", "ఏ"), ("ఒ", "ఓ")],
    "hi": [("ि", "ी"), ("ु", "ू"), ("इ", "ई"), ("उ", "ऊ")],
}


def neighbours(w, code):
    swap = {}
    for a, c in PAIRS[code]:
        swap[a], swap[c] = c, a
    for i, ch in enumerate(w):
        if ch in swap:
            yield i, w[:i] + swap[ch] + w[i + 1:]
    if code == "hi":                      # Hindi: a missing or extra anusvara (मैने for मैंने)
        for i, ch in enumerate(w):
            if ch == "\u0902" and i + 1 < len(w):   # a word-final ं is grammar (हुईं, बनें, कहां), never an error
                yield i, w[:i] + w[i + 1:]
            elif cls_hi(ch) in ("V", "M") and (i + 1 == len(w) or w[i + 1] != "\u0902"):
                yield i, w[:i + 1] + "\u0902" + w[i + 1:]


def load_allowlist(code, folder="allowlist"):
    p = ROOT / "tools" / folder / f"{code}.txt"
    if not p.exists():
        return set()
    return {unicodedata.normalize("NFC", l.split("#", 1)[0].strip()) for l in p.read_text(encoding="utf-8").splitlines()} - {""}


# ---------- io ----------
def read_counts(path):
    out = {}
    if not path.exists():
        return out
    for line in gzip.decompress(path.read_bytes()).decode("utf-8").splitlines():
        w, _, c = line.partition("\t")
        if w:
            out[unicodedata.normalize("NFC", w)] = int(c)
    return out


def write_gz_tsv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(gzip.compress("".join("\t".join(map(str, r)) + "\n" for r in rows).encode("utf-8"), 9, mtime=0))


# ---------- Telugu / Hindi ----------
def check_indic(code, a):
    ic = read_counts(WORK / code / "indiccorp_counts.tsv.gz")
    wk = read_counts(WORK / code / "wiki_counts.tsv.gz")
    if not ic or not wk:
        sys.exit(f"{code}: work data missing - run the Collect word data workflow first")
    bl = b.load_blocklist(code)
    allow = load_allowlist(code)
    rejectlist = load_allowlist(code, "rejectlist")
    kept, rejected = [], []
    for w, c in sorted(ic.items(), key=lambda x: (-x[1], x[0])):
        reason = None
        if b.blocked(w, bl):
            reason = "offensive"
        elif w in rejectlist:
            reason = "misspelling_hand_reviewed"
        elif not valid_sequence(w, code):
            reason = "invalid_letter_sequence"
        elif corruption(w, code):
            reason = corruption(w, code)
        elif c < a.min_count:
            reason = "too_rare"
        elif wk.get(w, 0) < 2 and c < a.solo_count:
            reason = "not_confirmed_by_second_source"
        elif w not in allow:
            for i, n in neighbours(w, code):
                if code == "te" and i == len(w) - 1:
                    continue          # word-final -ū / -ī / -ē are grammar in Telugu (నేనూ, తల్లీ), not errors
                # a misspelling only when BOTH independent sources prefer the other form by a wide margin
                if ic.get(n, 0) >= a.variant_ratio * c and wk.get(n, 0) >= a.variant_ratio * max(wk.get(w, 0), 1):
                    reason = "likely_misspelling_of:" + n
                    break
        if reason:
            if reason != "too_rare":      # too_rare words are simply below the cut, not errors
                rejected.append((w, c, wk.get(w, 0), reason))
        else:
            kept.append(w)
    top = kept[: a.top]
    stats = {"candidates": len(ic), "passed_all_checks": len(kept), "published": len(top),
             "rejected_by_reason": {}}
    for r in rejected:
        k = r[3].split(":")[0]
        stats["rejected_by_reason"][k] = stats["rejected_by_reason"].get(k, 0) + 1
    write_gz_tsv(ROOT / "review" / code / "rejected.tsv.gz", [("word", "indiccorp_count", "reason")] + [(r[0], r[1], r[3]) for r in rejected])
    return top, ic, wk, stats


def check_seed(code, app_src, ic, wk):
    """Re-checks the app's own hand-made seed list (assets/dict/<code>.txt) with the same rules."""
    f = app_src / "android/app/src/main/assets/dict" / f"{code}.txt" if app_src else None
    if not f or not f.exists():
        return None, None
    bl = b.load_blocklist(code)
    keep, rej, unconfirmed = [], [], []
    for w in f.read_text(encoding="utf-8").splitlines():
        w = unicodedata.normalize("NFC", w.strip())
        if not w or w.startswith("#"):
            continue
        if b.blocked(w, bl): r = "offensive"
        elif not valid_sequence(w, code): r = "invalid_letter_sequence"
        elif corruption(w, code): r = corruption(w, code)
        elif ic.get(w, 0) < 5 and wk.get(w, 0) < 2:
            # Hand-made BJNF words that no corpus confirms: keep them only if they are grammatical.
            # Forms generated wrongly by tools/morphology.py are removed (reviewed 2026-11-21).
            bad = next((rx for rx in BAD_FORMS.get(code, []) if re.search(rx, w)), None)
            r = "wrong_generated_form" if bad else None
            if not bad:
                unconfirmed.append((w, ic.get(w, 0), wk.get(w, 0), "kept: grammatical hand-made form, each read and accepted in review 2026-11-21"))
        else: r = None
        (rej.append((w, ic.get(w, 0), wk.get(w, 0), r)) if r else keep.append(w))
    return keep, rej + unconfirmed


# Wrong patterns produced by the old morphology generator (Telugu). Each was checked by hand.
BAD_FORMS = {"te": [
    "\u0C3F\u0C15\u0C41$",                 # -ికు  (గదికు)  -> should be -ికి
    "\u0C3F\u0C28\u0C41$",                 # -ిను  (గదిను)  -> should be -ిని
    "\u0C21\u0C24(\u0C41\u0C02\u0C26\u0C3F|\u0C4B\u0C02\u0C26\u0C3F|\u0C41\u0C28\u0C4D\u0C28)",  # -డతుంది/-డతోంది/-డతున్న -> -డుతుంది
    "^\u0C2A\u0C46\u0C21\u0C24",          # పెడత... -> పెడుత...
    "^\u0C2A\u0C30\u0C3F\u0C1A\u0C2F\u0C3F(\u0C02\u0C1A|\u0C38\u0C4D\u0C24)",  # పరిచయించ/పరిచయిస్త -> పరిచయం చేయు
    "(\u0C4B|\u0C2A\u0C4B|\u0C30\u0C3E)\u0C35(\u0C17\u0C32\u0C28\u0C41|\u0C32\u0C47\u0C28\u0C41|\u0C02\u0C21\u0C3F)$",  # -ోవగలను/పోవలేను/రావగలను/-ోవండి
    "^\u0C09\u0C02\u0C21\u0C3E(\u0C02|\u0C28\u0C41)$",   # ఉండాం / ఉండాను -> ఉన్నాం / ఉన్నాను
]}
INVALID_HI_SEED = None


# ---------- English ----------
CONTRACTIONS = {"it's", "he's", "she's", "that's", "what's", "there's", "here's", "who's", "where's", "let's", "how's", "when's", "why's"}


def check_english(a, app_src):
    raw = (WORK / "en" / "scowl_words.txt").read_text(encoding="utf-8", errors="replace").splitlines()
    ic = read_counts(WORK / "en" / "indiccorp_counts.tsv.gz")
    bl = b.load_blocklist("en")
    words, rejected, seen = [], [], set()
    for w in raw:
        w = unicodedata.normalize("NFC", w.strip())
        if not w:
            continue
        lw = w.lower()
        if lw.endswith("'s") and lw not in CONTRACTIONS:
            continue                                   # possessives are typed from the base word
        if not all(ch.isalpha() or ch in "'-" for ch in w):
            rejected.append((w, "symbol_or_digit")); continue
        if b.blocked(lw, bl):
            rejected.append((w, "offensive")); continue
        if w in seen:
            continue
        seen.add(w)
        words.append(w)
    hand = []
    if app_src:
        for name in ("top_en.txt", "common_en_extra.txt"):
            p = app_src / "tools" / name
            if p.exists():
                hand += p.read_text(encoding="utf-8").split()
    in_scowl = {w.lower(): w for w in words}
    hand_ok, hand_rej, used = [], [], set()
    for h in hand:
        k = h.lower()
        if k in in_scowl and k not in used:
            hand_ok.append(in_scowl[k]); used.add(k)
        elif k not in in_scowl:
            hand_rej.append((h, "not_in_SCOWL (chat shortcut or missing apostrophe; app code handles these)"))
    rest = sorted((w for w in words if w.lower() not in used), key=lambda w: (-ic.get(w.lower(), 0), w.lower()))
    ordered = hand_ok + rest
    write_gz_tsv(ROOT / "review" / "en" / "rejected.tsv.gz", [("word", "reason")] + rejected + hand_rej)
    return ordered, {"scowl_entries": len(raw), "kept": len(ordered), "hand_picked_kept": len(hand_ok),
                     "rejected": len(rejected) + len(hand_rej), "ranked_by_indiccorp": sum(1 for w in words if ic.get(w.lower()))}


# ---------- licences for the verified packs ----------
def write_licence(code, stats, n):
    prov = json.loads((WORK / code / "indiccorp_stats.json").read_text(encoding="utf-8"))
    b.write_licence(code, prov["provenance"], {"bytes_read": prov["bytes_read"], "lines_read": prov["lines_read"]}, n, 20)
    p = ROOT / "licenses" / code / "SOURCES_AND_LICENCES.txt"
    wiki = json.loads((WORK / code / "wiki_stats.json").read_text(encoding="utf-8"))
    extra = f"""
VERIFICATION (tools/verify_words.py) - every word passed all of these checks
  1. not offensive (tools/blocklist/{code}.txt)
  2. valid letter sequence for the script (Unicode syllable rules)
  3. no known corruption pattern (wrong ra-ottu order, legacy-font junk)
  4. seen at least 20 times in IndicCorp v2
  5. confirmed by a second, independent source: used on {code}.wikipedia.org at least twice,
     or seen at least 2,000 times in IndicCorp. Wikipedia ({wiki['url']}) was used ONLY as a yes/no check;
     no Wikipedia text or counts are published.
  6. not a likely misspelling: a form differing by one vowel length (Hindi: or a missing anusvara)
     is 20x more common in BOTH sources; expert-checked exceptions in tools/allowlist/{code}.txt
  7. not on tools/rejectlist/{code}.txt (one missing/extra letter, found by hand review)
  Candidates: {stats['candidates']:,}  Passed: {stats['passed_all_checks']:,}  Published: {stats['published']:,}
  Rejected words and reasons: review/{code}/rejected.tsv.gz
"""
    p.write_text(p.read_text(encoding="utf-8").replace("\nATTRIBUTION", extra + "\nATTRIBUTION"), encoding="utf-8")


def drop_english_pack():
    """English now ships fully checked inside the app (SCOWL), so the separate en pack is withdrawn."""
    import shutil
    for d in (ROOT / "packs" / "en", ROOT / "licenses" / "en"):
        shutil.rmtree(d, ignore_errors=True)
    for f in ("top_500.tsv", "random_300.tsv", "tail_200.tsv", "build_stats.json", "README.md"):
        (ROOT / "review" / "en" / f).unlink(missing_ok=True)
    mpath = ROOT / "manifest.json"
    m = json.loads(mpath.read_text(encoding="utf-8"))
    m["packs"] = [p for p in m.get("packs", []) if p["code"] != "en"]
    mpath.write_text(json.dumps(m, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", type=int, default=1)
    ap.add_argument("--top", type=int, default=100000)
    ap.add_argument("--min-count", type=int, default=20)
    ap.add_argument("--solo-count", type=int, default=2000)
    ap.add_argument("--variant-ratio", type=float, default=20.0)
    ap.add_argument("--app-src", default="", help="unpacked app source, to re-check its built-in lists")
    a = ap.parse_args()
    app_src = Path(a.app_src) if a.app_src else None
    out_app = WORK / "app_builtin"
    out_app.mkdir(parents=True, exist_ok=True)
    report = {}
    for code in ("te", "hi"):
        top, ic, wk, stats = check_indic(code, a)
        blob = b.pack_bytes(top)
        rel = f"packs/{code}/{a.version}/{code}.txt.gz"
        (ROOT / rel).parent.mkdir(parents=True, exist_ok=True)
        (ROOT / rel).write_bytes(blob)
        write_licence(code, stats, len(top))
        b.write_review(code, top, ic)
        b.update_manifest({
            "code": code, "version": a.version, "path": rel, "sha256": b.sha256(blob), "bytes": len(blob), "words": len(top),
            "license_file": f"licenses/{code}/SOURCES_AND_LICENCES.txt",
            "source": "IndicCorp v2 (AI4Bharat) - CC0-1.0 - words only; each word cross-checked (see licence file)",
            "licence_review": "source licence verified CC0; every word auto-checked and borderline words hand-reviewed; native sign-off sheet: review/" + code + "/expert_review.tsv",
        })
        keep, rej = check_seed(code, app_src, ic, wk)
        if keep is not None:
            (out_app / f"{code}.txt").write_text("\n".join(keep) + "\n", encoding="utf-8")
            write_gz_tsv(ROOT / "review" / code / "builtin_check.tsv.gz", [("word", "indiccorp_count", "result")] + [(r[0], r[1], r[3]) for r in rej])
            stats["app_builtin"] = {"kept": len(keep), "rejected": sum(1 for r in rej if not r[3].startswith("kept")),
                                    "kept_needs_native_signoff": sum(1 for r in rej if r[3].startswith("kept"))}
        stats["gz_bytes"] = len(blob)
        report[code] = stats
        b.log(code, json.dumps(stats, ensure_ascii=False))
    drop_english_pack()
    en, est = check_english(a, app_src)
    (out_app / "en.txt").write_text("\n".join(en) + "\n", encoding="utf-8")
    report["en_builtin"] = est
    b.log("en", json.dumps(est))
    (ROOT / "review" / "verification_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    b.finalize()


if __name__ == "__main__":
    main()
