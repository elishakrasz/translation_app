"""Write the stage-5 (style passes) input files for a chapter.

Usage: python3 tools/build_style_input.py <chNN> <temp_dir> [max_rows_per_part]

Rows = body paragraphs of output_chunkNNNN.md up to the notes heading, 1:1 with the
English. quotation = English paragraph is a block quote; original_source = paragraph
listed in sources/source-paragraphs.json (an inserted original); heading = Markdown
heading. Each row carries its footnote markers and the English + current Hebrew of
those notes. Parts are cut at chunk boundaries (default ≤ 60 rows) and written to
work/<chNN>/pilot/full-partN-input.json.
"""
import os
import json
import re
import sys
from pathlib import Path

ROOT = (Path(os.environ["TRANSLATOR_PROJECT"]).expanduser().resolve() if os.environ.get("TRANSLATOR_PROJECT")
        else sys.exit("Set TRANSLATOR_PROJECT to the book folder, e.g. TRANSLATOR_PROJECT=~/the_translator"))
ch, temp = sys.argv[1], ROOT / sys.argv[2]
cap = int(sys.argv[3]) if len(sys.argv) > 3 else 60
paras = lambda p: [x.strip() for x in re.split(r"\n\s*\n", p.read_text(encoding="utf-8")) if x.strip()]
NOTES_H = re.compile(r"#+\s*(Notes|הערות)\s*$")
src = set(json.loads((ROOT / "sources" / "source-paragraphs.json").read_text(encoding="utf-8")).get(ch, []))

body, notes_en, notes_he, in_notes = [], {}, {}, False
for f in sorted(temp.glob("chunk[0-9][0-9][0-9][0-9].md")):
    n = f.name[5:9]
    E, H = paras(f), paras(temp / f"output_{f.name}")
    assert len(E) == len(H), (n, len(E), len(H))
    chunk_rows = []
    for i, (e, h) in enumerate(zip(E, H), 1):
        if NOTES_H.match(e) or NOTES_H.match(h):
            in_notes = True
            continue
        if in_notes:
            for txt, store in ((e, notes_en), (h, notes_he)):
                m = re.match(r"(\d+)\\?\.\s*(.*)", txt, re.S)
                if m:
                    store[int(m.group(1))] = m.group(2).strip()
            continue
        chunk_rows.append({"id": f"{n}·{i}", "en": e, "he": h,
                           "quotation": e.lstrip().startswith(">"),
                           "original_source": f"{n}-{i}" in src,
                           "heading": bool(re.match(r"#+\s", e)),
                           "markers": [int(x) for x in re.findall(r"\^(\d+)\^", e)]})
    if chunk_rows:
        body.append(chunk_rows)

for rows in body:
    for r in rows:
        r["notes"] = {str(m): {"en": notes_en.get(m, ""), "he_current": notes_he.get(m, "")} for m in r["markers"]}

parts, cur = [], []
for rows in body:
    if cur and len(cur) + len(rows) > cap:
        parts.append(cur)
        cur = []
    cur += rows
if cur:
    parts.append(cur)
out = ROOT / "work" / ch / "pilot"
out.mkdir(parents=True, exist_ok=True)
for k, rows in enumerate(parts, 1):
    (out / f"full-part{k}-input.json").write_text(json.dumps(
        {"chapter": ch, "part": k, "range": f"{rows[0]['id']}–{rows[-1]['id']}", "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{ch} part {k}: {rows[0]['id']}–{rows[-1]['id']}, {len(rows)} rows, "
          f"{sum(r['quotation'] for r in rows)} quotation, {sum(r['original_source'] for r in rows)} source, "
          f"{sum(not (r['quotation'] or r['original_source'] or r['heading']) for r in rows)} prose")
