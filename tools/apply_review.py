#!/usr/bin/env python3
"""
Native-expert review loop.

1. Make the sheets (done for each pack build):
     python tools/apply_review.py --make-sheets
   writes review/<code>/expert_review.tsv with the words most worth a human look:
   the 500 most common, 300 random, the 200 rarest, every allow-listed word, and the app's hand-made
   words that no corpus confirms.

2. The expert fills the "decision" column (ok / wrong / offensive) and, for wrong words, "correct_spelling".
   Open the .tsv in Excel / Google Sheets / LibreOffice, keep it as tab-separated text.

3. Apply the decisions, then rebuild with a higher version:
     python tools/apply_review.py --apply te
     python tools/verify_words.py --version 2 --app-src <unpacked app source>
   wrong      -> tools/rejectlist/<code>.txt (with the correct spelling as a note)
   offensive  -> tools/blocklist/<code>.txt
   ok         -> if it was on the allow-list it stays; nothing else changes
   The reviewer's name and the date are written next to every entry.
"""
import argparse, datetime, gzip, random, sys, unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COLS = ["rank", "word", "why_in_sheet", "decision", "correct_spelling", "note"]


def pack_words(code):
    import json
    m = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    p = next(p for p in m["packs"] if p["code"] == code)
    return gzip.decompress((ROOT / p["path"]).read_bytes()).decode("utf-8").splitlines()


def list_file(folder, code):
    p = ROOT / "tools" / folder / f"{code}.txt"
    if not p.exists():
        return []
    return [unicodedata.normalize("NFC", l.split("#", 1)[0].strip()) for l in p.read_text(encoding="utf-8").splitlines() if l.split("#", 1)[0].strip()]


def make_sheets():
    for code in ("te", "hi"):
        words = pack_words(code)
        rank = {w: i + 1 for i, w in enumerate(words)}
        rows, seen = [], set()

        def add(w, why):
            if w and w not in seen:
                seen.add(w)
                rows.append([str(rank.get(w, "")), w, why, "", "", ""])
        for w in words[:500]:
            add(w, "top 500")
        rnd = random.Random(20261121)
        for i in sorted(rnd.sample(range(len(words)), 300)):
            add(words[i], "random sample")
        for w in words[-200:]:
            add(w, "rarest 200")
        for w in list_file("allowlist", code):
            add(w, "allow-list (kept although a similar word is more common)")
        chk = ROOT / "review" / code / "builtin_check.tsv.gz"
        if chk.exists():
            for line in gzip.decompress(chk.read_bytes()).decode("utf-8").splitlines()[1:]:
                parts = line.split("\t")
                if parts[-1].startswith("kept"):
                    add(parts[0], "app built-in word not found in any corpus")
        out = ROOT / "review" / code / "expert_review.tsv"
        out.write_text("\t".join(COLS) + "\n" + "".join("\t".join(r) + "\n" for r in rows), encoding="utf-8")
        print(f"{code}: {len(rows)} words -> {out.relative_to(ROOT)}")


def apply(code, reviewer):
    sheet = ROOT / "review" / code / "expert_review.tsv"
    lines = sheet.read_text(encoding="utf-8").splitlines()
    head = lines[0].split("\t")
    idx = {c: head.index(c) for c in COLS}
    today = datetime.date.today().isoformat()
    wrong, offensive, ok = [], [], 0
    for line in lines[1:]:
        f = line.split("\t") + [""] * len(COLS)
        w = unicodedata.normalize("NFC", f[idx["word"]].strip())
        d = f[idx["decision"]].strip().lower()
        if d == "wrong":
            wrong.append(f"{w}\t# -> {f[idx['correct_spelling']].strip()} (review: {reviewer}, {today})")
        elif d == "offensive":
            offensive.append(f"{w}\t# review: {reviewer}, {today}")
        elif d == "ok":
            ok += 1
    for folder, new in (("rejectlist", wrong), ("blocklist", offensive)):
        if new:
            p = ROOT / "tools" / folder / f"{code}.txt"
            p.parent.mkdir(parents=True, exist_ok=True)
            old = p.read_text(encoding="utf-8") if p.exists() else ""
            p.write_text(old.rstrip("\n") + "\n" + "\n".join(new) + "\n", encoding="utf-8")
    print(f"{code}: {ok} ok, {len(wrong)} wrong -> rejectlist, {len(offensive)} offensive -> blocklist")
    print("Now rebuild with a higher version: python tools/verify_words.py --version <n+1> --app-src <app source>")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--make-sheets", action="store_true")
    ap.add_argument("--apply", metavar="CODE")
    ap.add_argument("--reviewer", default="native reviewer")
    a = ap.parse_args()
    if a.make_sheets:
        make_sheets()
    if a.apply:
        apply(a.apply, a.reviewer)
    if not (a.make_sheets or a.apply):
        ap.print_help()


if __name__ == "__main__":
    sys.exit(main())
