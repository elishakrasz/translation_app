"""Write the accepted stage-5 text (work/<chNN>/pilot/full-output.json) into the chapter files.

Usage: python3 tools/apply_style_passes.py <chNN> <temp_dir>
Each row's he_final replaces the paragraph(s) named by its id(s); heading rows are
left as the chapter has them; working labels are never written. Backups go to
backups/before-style-<chNN>-<date>/. Paragraph counts and footnote markers are checked.
"""
import os
import json, re, shutil, sys
from datetime import date
from pathlib import Path

ROOT = (Path(os.environ["TRANSLATOR_PROJECT"]).expanduser().resolve() if os.environ.get("TRANSLATOR_PROJECT")
        else sys.exit("Set TRANSLATOR_PROJECT to the book folder, e.g. TRANSLATOR_PROJECT=~/the_translator"))
ch, temp = sys.argv[1], ROOT / sys.argv[2]
rows = json.loads((ROOT / "work" / ch / "pilot" / "full-output.json").read_text(encoding="utf-8"))["rows"]
bk = ROOT / "backups" / f"before-style-{ch}-{date.today().isoformat()}"
bk.mkdir(parents=True, exist_ok=True)
files = {}
def load(n):
    if n not in files:
        f = temp / f"output_chunk{n}.md"
        shutil.copy2(f, bk / f.name)
        blocks = re.split(r"(\n\s*\n)", f.read_text(encoding="utf-8"))
        idx = [k for k, b in enumerate(blocks) if b.strip() and not re.fullmatch(r"\n\s*\n", b)]
        files[n] = (f, blocks, idx)
    return files[n]
written, skipped = 0, []
for r in rows:
    ids = r["id"].split("·") if r["id"].count("·") == 1 else None
    id_list = [r["id"]] if ids else re.findall(r"\d{4}·\d+", r["id"])
    if r["en"].lstrip().startswith("#"):
        skipped.append(r["id"]); continue
    paras = [p.strip() for p in re.split(r"\n\s*\n", r["he_final"]) if p.strip()]
    if len(paras) != len(id_list):
        if len(id_list) == 1 and r["en"].lstrip().startswith(">"):
            # block quotation that lost its > form in an export: one paragraph, lines joined with a blank quote line
            paras = ["\n>\n".join("> " + re.sub(r"^>\s?", "", q).replace("\n", "\n> ") for q in paras)]
        elif len(id_list) == 1:
            paras = [r["he_final"].strip()]
        else:
            sys.exit(f"row {r['id']}: {len(paras)} paragraphs for {len(id_list)} ids")
    for cid, text in zip(id_list, paras):
        n, i = cid.split("·"); f, blocks, idx = load(n)
        blocks[idx[int(i) - 1]] = text; written += 1
for n, (f, blocks, idx) in files.items():
    f.write_text("".join(blocks), encoding="utf-8")
print(f"{written} paragraphs written in {len(files)} chunk files; headings left as in chapter: {skipped}; backup {bk.relative_to(ROOT)}")
