"""Extract a chapter's notes (English + current Hebrew) into review/<chNN>/notes_input.json.

Usage: python3 tools/build_notes_input.py <chNN>
Notes are paragraphs starting "n\\." in the chunk files; following paragraphs that are not
a new note (and not a heading) are continuations of the same note.
"""
import os
import glob, json, re, sys
from pathlib import Path
ROOT = (Path(os.environ["TRANSLATOR_PROJECT"]).expanduser().resolve() if os.environ.get("TRANSLATOR_PROJECT")
        else sys.exit("Set TRANSLATOR_PROJECT to the book folder, e.g. TRANSLATOR_PROJECT=~/the_translator"))

def notes(files):
    out, cur = {}, None
    for f in files:
        text = open(f, encoding="utf-8").read()
        m = re.search(r"(?m)^#+\s*(?:הערות|Notes)\s*$", text)
        if not m and cur is None: continue
        body = text[m.end():] if m else text
        for p in [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]:
            n = re.match(r"^(\d+)\\?\.\s*(.*)$", p, re.S)
            if n: cur = int(n.group(1)); out[cur] = n.group(2).strip()
            elif cur is not None and not p.startswith("#"): out[cur] += "\n\n" + p
    return out

ch = sys.argv[1]; temp = glob.glob(str(ROOT / f"{ch}-*_temp"))[0]
en = notes(sorted(glob.glob(f"{temp}/chunk[0-9][0-9][0-9][0-9].md")))
he = notes(sorted(glob.glob(f"{temp}/output_chunk[0-9][0-9][0-9][0-9].md")))
rows = [{"chapter": ch, "n": str(n), "en": en.get(n, ""), "he": he.get(n, "")} for n in sorted(set(en) | set(he))]
(ROOT / "review" / ch).mkdir(parents=True, exist_ok=True)
json.dump(rows, open(ROOT / "review" / ch / "notes_input.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(ch, len(rows), "notes; missing he:", [r["n"] for r in rows if not r["he"]], "missing en:", [r["n"] for r in rows if not r["en"]])
