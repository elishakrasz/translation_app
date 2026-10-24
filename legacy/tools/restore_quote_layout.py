"""After apply_style_passes: restore the > layout of locked quotation/source rows that an export flattened.
Usage: python3 tools/restore_quote_layout.py <chNN> <temp_dir> <backup_dir>"""
import os
import json, re, sys
from pathlib import Path
ROOT = (Path(os.environ["TRANSLATOR_PROJECT"]).expanduser().resolve() if os.environ.get("TRANSLATOR_PROJECT")
        else sys.exit("Set TRANSLATOR_PROJECT to the book folder, e.g. TRANSLATOR_PROJECT=~/the_translator"))
ch, T, bk = sys.argv[1], ROOT / sys.argv[2], ROOT / sys.argv[3]
locked = {r["id"]: r for p in (ROOT / "work" / ch / "pilot").glob("full-part*-input.json") for r in json.loads(p.read_text(encoding="utf-8"))["rows"]}
norm = lambda s: re.sub(r"[\s>]+", "", s)
restored = []
for f in sorted(T.glob("output_chunk[0-9]*.md")):
    if not (bk / f.name).exists():
        continue
    n = f.name[12:16]
    blocks = re.split(r"(\n\s*\n)", f.read_text(encoding="utf-8")); idx = [k for k, b in enumerate(blocks) if b.strip() and not re.fullmatch(r"\n\s*\n", b)]
    old = [p.strip() for p in re.split(r"\n\s*\n", (bk / f.name).read_text(encoding="utf-8")) if p.strip()]
    changed = False
    for i, k in enumerate(idx, 1):
        r = locked.get(f"{n}·{i}")
        if r and (r["quotation"] or r["original_source"]) and i <= len(old) and blocks[k].strip() != old[i - 1] and norm(blocks[k]) == norm(old[i - 1]):
            blocks[k] = old[i - 1]; changed = True; restored.append(f"{n}·{i}")
    if changed:
        f.write_text("".join(blocks), encoding="utf-8")
print("quote layout restored in:", restored or "none")
