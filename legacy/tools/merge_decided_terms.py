"""Merge the author's decided terms (eval/decided-terms.md) into the book glossary.

Usage: python3 tools/merge_decided_terms.py [--glossary glossary/glossary-book.json]

Each decided term overrides the matching glossary entry's Hebrew target (matched by
source or alias); unmatched terms are added. The previous target is kept in the
entry's notes and in the printed report, so tools/conform_terms.py can later bring
the translation into line. The translation files are not touched.
"""
import os, sys
import argparse
import json
import shutil
from pathlib import Path

ROOT = (Path(os.environ["TRANSLATOR_PROJECT"]).expanduser().resolve() if os.environ.get("TRANSLATOR_PROJECT")
        else sys.exit("Set TRANSLATOR_PROJECT to the book folder, e.g. TRANSLATOR_PROJECT=~/the_translator"))

# decided-terms.md row → glossary sources/aliases it governs, and the fixed target
DECIDED = [
    (["Przysucha", "Pshiskha"], "פשיסחא"),
    (["Yehudi"], "היהודי"),
    (["R. Bunim"], "ר' בונים"),
    (["Seer"], "החוזה"),
    (["Kotzker"], "הרבי מקוצק"),
    (["Menahem Mendel of Kotzk"], "הרבי מקוצק"),
    (["Zaddikism"], "אמונת הצדיקים"),
    (["authenticity"], "אותנטיות"),
    (["truthfulness"], "אמתיות"),
    (["ulterior motive"], "פנייה"),
    (["passion"], "להט"),
    (["purity of motive"], "טוהר המניע"),
    (["routine"], "שגרה"),
    (["externals"], "חיצוניות"),
    (["inner life force"], "חיוּת פנימית"),
    (["groundedness"], "קרקעיות"),
    (["vicarious redemption"], "גאולה בשליחות"),
    (["moreh derekh"], "מורה דרך"),
    (["dynasty"], "שושלת"),
    (["dynastic succession"], "ירושה תורשתית"),
    (["routinization of charisma"], "רוטיניזציית הכריזמה"),
    (["ba'al davar"], "בעל דבר"),
    (["homo religiosus"], "האדם הדתי"),
    (["devekut"], "דבקות"),
    (["Torat ha-Adam"], "תורת האדם"),
    (["frumkeit"], "\"פרומקייט\" (אדיקות)"),
    (["reshimu"], "רְשימוּ"),
    (["ayin", "nothingness"], "אַיִן"),
    (["self-doubt"], "ספק עצמי"),
    (["greatness"], "אדם גדול"),
    (["excommunicate", "ban"], "להחרים"),
    (["internalize"], "להפנים"),
    (["Hashavah le-Tovah"], "חשבה לטובה"),
    (["Or la-Shamayim"], "אור לשמים"),
]
NOTES = {
    "Seer": "Decided: החוזה (מלובלין) — add מלובלין where the English does.",
    "greatness": "Decided: of a person = אדם גדול; never bare גדולה or גדלות.",
    "excommunicate": "Decided: להחרים, not לנדות.",
    "Hiddushei Ha-Rim": "Decided: the person = בעל חידושי הרי\"ם; the book = חידושי הרי\"ם.",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--glossary", default=str(ROOT / "glossary" / "glossary-book.json"))
    args = ap.parse_args()
    path = Path(args.glossary)
    gloss = json.loads(path.read_text(encoding="utf-8"))
    index = {}
    for t in gloss["terms"]:
        for s in [t["source"]] + t.get("aliases", []):
            index.setdefault(s.lower(), t)
    changes, added = [], []
    for sources, target in DECIDED:
        term = next((index[s.lower()] for s in sources if s.lower() in index), None)
        if term is None:
            src = sources[0]
            term = dict(id=src, source=src, target=target, category="concept", aliases=sources[1:],
                        gender="unknown", confidence="high", frequency=0, evidence_refs=[], notes="")
            gloss["terms"].append(term)
            for s in sources:
                index[s.lower()] = term
            added.append((src, target))
        elif term["target"] != target:
            changes.append((term["source"], term["target"], target))
            term["notes"] = (f"Decided (author): {target}; previously {term['target']} | " + term.get("notes", ""))[:500]
            term["target"] = target
        term["confidence"] = "high"
        if term["source"] in NOTES and NOTES[term["source"]] not in term.get("notes", ""):
            term["notes"] = (NOTES[term["source"]] + " | " + term.get("notes", ""))[:500]
    for src, note in NOTES.items():
        if src in {t["source"] for t in gloss["terms"]}:
            t = next(t for t in gloss["terms"] if t["source"] == src)
            if note not in t.get("notes", ""):
                t["notes"] = (note + " | " + t.get("notes", ""))[:500]
    shutil.copy2(path, path.with_suffix(".json.before-decided"))
    path.write_text(json.dumps(gloss, ensure_ascii=False, indent=2), encoding="utf-8")
    (ROOT / "eval" / "term-changes.json").write_text(
        json.dumps([{"source": s, "old": o, "new": n} for s, o, n in changes], ensure_ascii=False, indent=1),
        encoding="utf-8")
    print(f"changed {len(changes)} targets, added {len(added)} terms → {path}")
    for s, o, n in changes:
        print(f"  {s}: {o} → {n}")
    for s, n in added:
        print(f"  + {s}: {n}")


main()
