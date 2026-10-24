"""Stage-4 diagnosis (per CLAUDE_addendum.md) of a chapter's Hebrew, generated from the
evaluator findings already on disk: Fable / GPT / Gemini checks of the revised text
(work/<chNN>/revised-aligned.json, revised-eval.json) and, for chapters without a
revision, the eval findings (eval/findings/<chNN>.json) and reviewer suggestions.

Usage: python3 tools/build_diagnosis.py <chNN> "<Title>"   → reports/<chNN>-diagnosis.md
Marks passages that read as translated rather than written: calques, English word
order, cleft constructions, overuse of זה/זו, glosses not in the original, register.
"""
import os
import json, re, sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = (Path(os.environ["TRANSLATOR_PROJECT"]).expanduser().resolve() if os.environ.get("TRANSLATOR_PROJECT")
        else sys.exit("Set TRANSLATOR_PROJECT to the book folder, e.g. TRANSLATOR_PROJECT=~/the_translator"))
TEMPS = {"ch01": "ch01-introduction_temp", "ch02": "ch02-holy-rebellion_temp", "ch03": "ch03-biographical-sketch_temp",
         "ch04": "ch04-torah-and-theology_temp", "ch05": "ch05-zaddik-and-leadership_temp", "ch06": "ch06-quest-for-truth_temp"}
STYLE_CATS = {"calque", "register", "gloss", "addition", "formatting", "other"}
PROV = {"openai": "GPT", "gemini": "Gemini"}


def heuristics(he, en):
    """Mechanical markers of translated Hebrew."""
    out = []
    t = re.sub(r"\^\d+\^", "", he)
    for pat, label in [(r"\bמה ש(?:היה|הוא|היא) זה ש", "cleft: 'what it was that…'"), (r"\bזה (?:היה|הוא|היא) ש", "cleft: 'it is X that…'"),
                       (r"\bבמונחים של\b", "calque: 'in terms of'"), (r"\bבאופן ש", "calque: 'in a way that'"),
                       (r"\bמה שמעניין הוא\b", "calque: 'what is interesting is'"), (r"\bנעשה על ידי\b", "passive 'done by'"),
                       (r"\bביחס ל", "calque: 'in relation to'"), (r"\bבהקשר של\b", "calque: 'in the context of'"),
                       (r"\bהוא או היא\b", "calque: 'he or she'"), (r"\bבא במגע עם\b", "calque: 'come into contact with'"),
                       (r"\bיש (?:תופעה|נטייה|תחושה) ש", "calque: 'there is a phenomenon that…'")]:
        for m in re.finditer(pat, t):
            out.append((label, t[max(0, m.start() - 20):m.end() + 25].strip()))
    ze = len(re.findall(r"(?<![א-ת])(?:זה|זו|זאת)(?![א-ת])", t))
    words = len(t.split())
    if words > 60 and ze / words > 0.035:
        out.append(("frequent זה/זו", f"{ze} in {words} words"))
    sents_he = [s for s in re.split(r"[.!?؟]\s", t) if s.strip()]
    sents_en = [s for s in re.split(r"[.!?]\s", en) if s.strip()]
    if len(sents_he) >= 4 and len(sents_en) == len(sents_he):
        out.append(("sentence count mirrors English", f"{len(sents_he)} = {len(sents_en)}"))
    return out


def main():
    ch, title = sys.argv[1], sys.argv[2]
    w = ROOT / "work" / ch
    rows = []
    if (w / "revised-aligned.json").exists():
        al = json.loads((w / "revised-aligned.json").read_text(encoding="utf-8"))
        ev = json.loads((w / "revised-eval.json").read_text(encoding="utf-8")) if (w / "revised-eval.json").exists() else {"rows": {}}
        for k, r in enumerate(al["rows"]):
            if not r["en_ids"]:
                continue
            f = [dict(x, src="Fable") for x in r.get("issues", [])]
            for p, v in ev["rows"].get(str(k), {}).items():
                f += [dict(category=x.get("category"), type=x.get("category"), severity=x.get("severity"), he_span=x.get("he_span", ""),
                           en_span=x.get("en_span", ""), note=x.get("note", ""), src=PROV.get(p, p)) for x in v.get("findings", [])]
            rows.append({"id": "·".join(r["en_ids"]), "en": r["en"], "he": r["he"], "findings": f})
        basis = "the translator's revised text (Fable check + GPT‑5.5 + Gemini 3.1 Pro findings)"
    else:
        temp = ROOT / TEMPS[ch]
        fnd = json.loads((ROOT / "eval" / "findings" / f"{ch}.json").read_text(encoding="utf-8"))["paragraphs"] if (ROOT / "eval" / "findings" / f"{ch}.json").exists() else {}
        for src in sorted(temp.glob("chunk[0-9][0-9][0-9][0-9].md")):
            n = src.name[5:9]
            E = [p.strip() for p in re.split(r"\n\s*\n", src.read_text(encoding="utf-8")) if p.strip()]
            H = [p.strip() for p in re.split(r"\n\s*\n", (temp / f"output_{src.name}").read_text(encoding="utf-8")) if p.strip()]
            for i, (e, h) in enumerate(zip(E, H), 1):
                if re.match(r"#+\s*(Notes|הערות)", e):
                    break
                f = [dict(x, type=x.get("category") or x.get("type"), src=PROV.get(x["provider"], x["provider"])) for x in fnd.get(f"{n}-{i}", {}).get("findings", [])]
                rows.append({"id": f"{n}·{i}", "en": e, "he": h, "findings": f})
        basis = "the current text (GPT/Gemini evaluator findings where they exist, plus mechanical markers)"
    style_rows, cats, srcs = [], Counter(), Counter()
    for r in rows:
        sty = [f for f in r["findings"] if (f.get("type") or f.get("category")) in STYLE_CATS]
        heur = heuristics(r["he"], r["en"]) if not r["he"].lstrip().startswith("#") else []
        for f in sty:
            cats[f.get("type") or f.get("category")] += 1; srcs[f["src"]] += 1
        if sty or heur:
            style_rows.append((r, sty, heur))
    lines = [f"# {title} — diagnosis (stage 4)", "", f"Basis: {basis}. Only style findings are listed here (calque, register, gloss, addition); fidelity findings are on the review pages.", "",
             f"**{len(rows)} paragraphs; {len(style_rows)} with passages that read as translated.** Categories: " + ", ".join(f"{k} {v}" for k, v in cats.most_common())
             + (" · by evaluator: " + ", ".join(f"{k} {v}" for k, v in srcs.most_common()) if srcs else ""), ""]
    hcount = Counter(l for _, _, h in style_rows for l, _ in h)
    if hcount:
        lines += ["Mechanical markers across the chapter: " + ", ".join(f"{k} ×{v}" for k, v in hcount.most_common()), ""]
    for r, sty, heur in style_rows:
        lines += [f"## {r['id']}", "", "> " + re.sub(r"\s+", " ", r["en"])[:400], ""]
        for f in sty:
            lines.append(f"- **{f.get('type') or f.get('category')}** ({f['src']}, {f.get('severity','')}): «{f.get('he_span','')}»" + (f" ← “{f['en_span']}”" if f.get("en_span") else "") + f" — {f.get('note','')}")
        for l, ctx in heur:
            lines.append(f"- *{l}*: «{ctx}»")
        lines.append("")
    (ROOT / "reports").mkdir(exist_ok=True)
    out = ROOT / "reports" / f"{ch}-diagnosis.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(out, len(rows), "paragraphs,", len(style_rows), "flagged;", dict(cats))


main()
