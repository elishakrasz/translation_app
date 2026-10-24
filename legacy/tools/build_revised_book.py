"""Book data (Koren layout) for a chapter whose opening part the translator revised.

Usage: python3 tools/build_revised_book.py <chNN> <temp_dir> <last_revised_id> <out.json> "<Title>"
Takes the revised rows from work/<chNN>/revised-aligned.json (footnote markers
restored, translator's notes applied), the current text for every paragraph after
<last_revised_id> (e.g. 0003·7), and the Koren-style notes from
review/<chNN>/notes_koren.json. Writes the JSON read by tools/build_book_docx.js,
and work/<chNN>/<chNN>-koren.md (the assembled Hebrew text, for checking).
"""
import os
import json
import re
import sys
from pathlib import Path

ROOT = (Path(os.environ["TRANSLATOR_PROJECT"]).expanduser().resolve() if os.environ.get("TRANSLATOR_PROJECT")
        else sys.exit("Set TRANSLATOR_PROJECT to the book folder, e.g. TRANSLATOR_PROJECT=~/the_translator"))
INLINE = re.compile(r"(\*\*.+?\*\*|(?<!\*)\*(?!\s).+?(?<!\s)\*(?!\*)|\^\d+\^)")


def _runs(text):
    out = []
    for part in INLINE.split(text):
        if not part:
            continue
        if part.startswith("**"):
            out.append({"t": part[2:-2], "b": True})
        elif part.startswith("^"):
            out.append({"fn": int(part.strip("^"))})
        elif part.startswith("*") and part.endswith("*") and len(part) > 2:
            out.append({"t": part[1:-1], "i": True})
        else:
            out.append({"t": part})
    return out



def runs(text):
    """Inline runs; text between == and == is the editor's highlight ("hl": True)."""
    out = []
    for k, seg in enumerate(text.split("==")):
        for r in _runs(seg):
            if k % 2:
                r["hl"] = True
            out.append(r)
    return out

def main():
    ch, temp, last_id, out, title = sys.argv[1], Path(sys.argv[2]), sys.argv[3], Path(sys.argv[4]), sys.argv[5]
    al = json.loads((ROOT / "work" / ch / "revised-aligned.json").read_text(encoding="utf-8"))
    md = []                      # assembled text as markdown, one entry per paragraph
    for r in al["rows"]:
        if not r["en_ids"]:      # translator's working title line: not typeset
            continue
        en = r["en"].lstrip()
        level = len(re.match(r"^(#*)", en).group(1))
        paras = [p.strip() for p in re.split(r"\n\s*\n", r["he"]) if p.strip()]
        if level:                # heading level follows the English, not the export; no working labels
            h = re.sub(r"^#+\s*", "", paras[0])
            h = re.sub(r"\s*\(נוסח מתוקן\)", "", re.sub(r"^פרק\s*\d+\s*:\s*", "", h)).strip()
            md.append("#" * level + " " + h)
        elif any(p.startswith(">") for p in paras):   # quotation marks present: keep each paragraph as it is
            md.extend(paras)
        elif en.startswith(">"):  # quotation / epigraph that lost its block-quote form in the export
            md.append("\n>\n".join("> " + p.replace("\n", "\n> ") for p in paras))
        else:
            md.extend(paras)
    # the rest of the chapter, current text
    started = False
    for f in sorted(temp.glob("chunk[0-9][0-9][0-9][0-9].md")):
        n = f.name[5:9]
        H = [p.strip() for p in re.split(r"\n\s*\n", (temp / f"output_{f.name}").read_text(encoding="utf-8")) if p.strip()]
        for i, h in enumerate(H, 1):
            if re.match(r"#+\s*(?:הערות|Notes)\s*$", h):
                break
            if started:
                md.append(h)
            if f"{n}·{i}" == last_id:
                started = True
        else:
            continue
        break
    notes = {x["n"]: x["koren"] for x in json.loads((ROOT / "review" / ch / "notes_koren.json").read_text(encoding="utf-8"))["notes"]}
    blocks = []
    for p in md:
        quote = p.startswith(">")
        level = len(re.match(r"^(#*)", p).group(1))
        lines = [re.sub(r"^>\s?", "", l) for l in p.split("\n")] if quote else [p.replace("\n", " ")]
        for l in lines:
            l = re.sub(r"^#+\s*", "", l).replace("\\.", ".").strip()
            if l:
                blocks.append({"kind": "h" if level else ("q" if quote else "p"), "level": level, "runs": runs(l)})
    used = sorted({r["fn"] for b in blocks for r in b["runs"] if "fn" in r})
    missing = [n for n in used if n not in notes]
    unused = sorted(set(notes) - set(used))
    out.write_text(json.dumps({"title": title, "blocks": blocks, "notes": {str(n): runs(notes[n]) for n in used if n in notes}}, ensure_ascii=False), encoding="utf-8")
    (ROOT / "work" / ch / f"{ch}-koren.md").write_text("\n\n".join(md) + "\n\n## הערות\n\n" + "\n".join(f"{n}\\. {notes[n]}" for n in sorted(notes)) + "\n", encoding="utf-8")
    print(out, len(blocks), "paragraphs,", len(used), "footnotes", f"missing {missing}" if missing else "", f"unused {unused}" if unused else "")


main()
