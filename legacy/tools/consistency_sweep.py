"""Whole-book consistency sweep (report only; changes nothing).

Usage: python3 tools/consistency_sweep.py [review/consistency-report.md]

Over the Hebrew of chapters 1–12 (body and notes, paragraph-aligned with the English):
1. Spelling / form variants of names, titles and words that should be uniform.
2. Required glossary terms: where the English term occurs but the fixed Hebrew
   rendering does not appear in the aligned paragraph (verified original sources skipped).
3. Divine names in Rosen's own prose (source paragraphs skipped): ה', אלוקים, הקב"ה,
   and any forbidden form anywhere outside verified originals.
"""
import os
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = (Path(os.environ["TRANSLATOR_PROJECT"]).expanduser().resolve() if os.environ.get("TRANSLATOR_PROJECT")
        else sys.exit("Set TRANSLATOR_PROJECT to the book folder, e.g. TRANSLATOR_PROJECT=~/the_translator"))
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "review" / "consistency-report.md"
TEMPS = sorted(p for p in ROOT.glob("ch[01][0-9]-*_temp") if p.name[:2] == "ch" and 1 <= int(p.name[2:4]) <= 12)
NIQ = re.compile("[\u0591-\u05BD\u05BF-\u05C7]")   # vowel points and cantillation, keeping the maqaf (U+05BE)
paras = lambda p: [x.strip() for x in re.split(r"\n\s*\n", p.read_text(encoding="utf-8")) if x.strip()]
src = json.loads((ROOT / "sources" / "source-paragraphs.json").read_text(encoding="utf-8"))

rows = []   # (ch, id, en, he, is_source, is_note)
for t in TEMPS:
    ch = t.name[:4]
    in_notes = False
    for f in sorted(t.glob("chunk[0-9][0-9][0-9][0-9].md")):
        n = f.name[5:9]
        for i, (e, h) in enumerate(zip(paras(f), paras(t / f"output_{f.name}")), 1):
            if re.match(r"#+\s*(Notes|הערות)\s*$", e) or re.match(r"#+\s*(Notes|הערות)\s*$", h):
                in_notes = True
                continue
            rows.append((ch, f"{n}·{i}", e, NIQ.sub("", h), f"{n}-{i}" in src.get(ch, []), in_notes))

out = ["# Whole-book consistency sweep — chapters 1–12", "",
       "Report only: nothing in the translation was changed. Counts are per chapter (body + notes); verified original-source paragraphs are excluded from the divine-name and glossary checks.", ""]

# 1. variants
VARIANTS = [
    ("Przysucha", ["פשיסחא", "פשיסחה", "פרשיסחא"]),
    ("Ramatayim Zofim", ["רמתים צופים", "רמתיים צופים"]),
    ("Ohel Torah / Ohel Yitzhak", ["אהל תורה", "אוהל תורה", "אהל יצחק", "אוהל יצחק"]),
    ("Keter Yehudi", ["כתר יהודי", "כתר היהודי"]),
    ("Zelechów / Zaklików", ["זעליחוב", "ז'עליחוב", "זאקליקוב"]),
    ("Kotzker (Yiddish form)", ["הקוצקער", "הרבי מקוצק"]),
    ("Izbica (Yiddish form)", ["האיזביצער", "הרבי מאיזביצא"]),
    ("Menahem Mendel", ["הרבי מנחם מנדל מקוצק", "ר' מנחם מנדל מקוצק", "ר' מנחם מנדל"]),
    ("Rebbe of Apta", ["ר' מאיר מאפטא", "הרבי מאפטא", "הרב מאפטא"]),
    ("Hiddushei ha-Rim (person)", ["בעל חידושי הרי\"ם", "החידושי הרי\"ם"]),
    ("theology", ["תאולוגיה", "תיאולוגיה", "תאולוגי", "תיאולוגי"]),
    ("theocentric", ["תאוצנטרי", "תיאוצנטרי"]),
    ("truthfulness", ["אמתיות", "אמיתיות"]),
    ("Faierstein", ["פאירשטיין", "פיירשטיין"]),
    ("Zaddikism / belief in zaddikim", ["אמונת הצדיקים", "אמונת צדיקים"]),
    ("groundedness / earthiness", ["קרקעיות", "ארציות"]),
]
out += ["## 1. Spelling and form variants", "", "| Item | Form | " + " | ".join(f"{i:02d}" for i in range(1, 13)) + " | total |", "|---|---|" + "---|" * 13]
by_ch = defaultdict(str)
for ch, _, _, he, _, _ in rows:
    by_ch[ch] += "\n" + he
for label, forms in VARIANTS:
    for form in forms:
        counts = [len(re.findall(r"(?<![א-ת])[ובלמהכש]?" + re.escape(form), by_ch[f"ch{i:02d}"])) for i in range(1, 13)]
        if sum(counts):
            out.append(f"| {label} | {form} | " + " | ".join(str(c) if c else "·" for c in counts) + f" | {sum(counts)} |")
out.append("")

# 2. glossary required terms
gl = json.loads((ROOT / "glossary" / "glossary-book.json").read_text(encoding="utf-8"))["terms"]
req = [t for t in gl if t.get("rule") == "required" and t.get("target") and len(t["source"]) > 3]
misses = []
for t in req:
    names = [t["source"]] + [a for a in t.get("aliases", []) if len(a) > 3]
    pat = re.compile(r"(?<![\w-])(" + "|".join(re.escape(n) for n in names) + r")(?![\w-])", re.I)
    target = NIQ.sub("", t["target"]).strip('"').split(" / ")[0].split(" (")[0]
    if len(target) < 2:
        continue
    tw = target.split()[-1] if len(target.split()) > 1 else target
    tw = re.sub(r"(ים|ות|ה|ת|י)$", "", tw) if len(tw) > 4 else tw   # stem: match inflected forms
    hits, miss = 0, []
    for ch, rid, en, he, is_src, is_note in rows:
        if is_src or not pat.search(en):
            continue
        hits += 1
        if target not in he and tw not in he:
            miss.append(f"{ch} {rid}")
    if hits >= 3 and len(miss) / hits >= 0.3:
        misses.append((len(miss), hits, t["source"], t["target"], miss[:8]))
misses.sort(key=lambda m: (-m[0] / m[1], -m[0]))
out += ["## 2. Required glossary terms not rendered as fixed", "",
        "Paragraphs where the English term (or an alias) occurs but the fixed Hebrew does not appear. Many are legitimate (inflection, a pronoun, an admitted context rendering); the list is for review.", "",
        "| English | Fixed Hebrew | missing / occurrences | examples |", "|---|---|---|---|"]
for m, h, s, tg, ex in misses[:60]:
    out.append(f"| {s} | {tg} | {m}/{h} | {', '.join(ex)} |")
out.append("")

# 3. divine names
FORBID = re.compile(r"אלוהים|אלוהות|אלוהי|(?<![א-ת])האל(?![א-ת])")
out += ["## 3. Divine names in Rosen's prose (source paragraphs excluded)", "",
        "| Chapter | ה' | א־לוהים / א־לוהות / א־לוהי | הקב\"ה | forbidden forms |", "|---|---|---|---|---|"]
bad = []
for i in range(1, 13):
    ch = f"ch{i:02d}"
    txt = "\n".join(he for c, _, _, he, is_src, _ in rows if c == ch and not is_src)
    h = len(re.findall(r"(?<![א-ת])[ולבמהכש]?ה'(?![א-ת])", txt))
    e = len(re.findall("א\u05BEלוה|אלוק", txt))
    k = len(re.findall(r"הקב\"ה|הקדוש ברוך הוא", txt))
    f_ = [(rid, FORBID.search(he).group(0)) for c, rid, _, he, is_src, _ in rows if c == ch and not is_src and FORBID.search(he)]
    bad += [(ch,) + x for x in f_]
    out.append(f"| {i} | {h} | {e} | {k} | {len(f_)} |")
out.append("")
if bad:
    out += ["Forbidden forms outside verified originals:", ""] + [f"- {c} {rid}: {w}" for c, rid, w in bad[:40]] + [""]

OUT.write_text("\n".join(out) + "\n", encoding="utf-8")
print(OUT, f"{len(rows)} paragraphs; {len(misses)} glossary terms flagged; {len(bad)} forbidden-form hits")
