"""Export a chapter's EN/HE paragraph pairs as JSON for the Word/PDF draft (tools/build_draft_docx.js).

Usage: python3 tools/draft_data.py <temp_dir> <out.json> "<Title>"
"""
import json
import re
import sys
from pathlib import Path

INLINE = re.compile(r"(\^\*\^|\*\*.+?\*\*|(?<!\*)\*(?!\s).+?(?<!\s)\*(?!\*)|\^\d+\^)")


def _runs(text):
    out = []
    for part in INLINE.split(text):
        if not part:
            continue
        if part.startswith("**"):
            out.append({"t": part[2:-2], "b": True})
        elif part.startswith("^"):                 # ^n^ or the editor's ^*^
            out.append({"t": part.strip("^"), "sup": True})
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

def cell(p):
    quote = p.startswith(">")
    lines = [re.sub(r"^>\s?", "", l) for l in p.split("\n")] if quote else p.split("\n")
    level = len(re.match(r"^(#*)", p).group(1))
    paras = []
    for l in lines:
        l = re.sub(r"^#+\s*", "", l).replace("\\.", ".").strip()
        if l:
            paras.append(runs(l))
    return {"kind": "h" if level else ("q" if quote else "p"), "level": level, "paras": paras}


def main():
    temp, out, title = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
    rows, in_notes = [], False
    for src in sorted(temp.glob("chunk[0-9][0-9][0-9][0-9].md")):
        n = src.name[5:9]
        split = lambda f: [x.strip() for x in re.split(r"\n\s*\n", f.read_text(encoding="utf-8")) if x.strip()]
        for e, h in zip(split(src), split(temp / f"output_chunk{n}.md")):
            if re.match(r"#+ .*Notes", e):
                in_notes = True
            rows.append({"en": cell(e), "he": cell(h), "notes": in_notes})
    out.write_text(json.dumps({"title": title, "rows": rows}, ensure_ascii=False), encoding="utf-8")
    print(out, len(rows))


main()
