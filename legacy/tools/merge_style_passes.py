"""Merge the stage-5 part outputs of a chapter into one file for the review page.

Usage: python3 tools/merge_style_passes.py <chNN>
Reads work/<chNN>/pilot/full-part*-output.json (pilot rows already carried inside part 1),
checks ids against work/<chNN>/revised-aligned.json, locked rows and footnote markers,
and writes work/<chNN>/pilot/full-output.json (same schema as pilot-output.json).
"""
import os
import json, re, sys
from collections import Counter
from pathlib import Path

ROOT = (Path(os.environ["TRANSLATOR_PROJECT"]).expanduser().resolve() if os.environ.get("TRANSLATOR_PROJECT")
        else sys.exit("Set TRANSLATOR_PROJECT to the book folder, e.g. TRANSLATOR_PROJECT=~/the_translator"))
ch = sys.argv[1]; w = ROOT / "work" / ch / "pilot"
inputs = sorted(w.glob("full-part*-input.json"), key=lambda p: int(re.search(r"part(\d+)", p.name).group(1)))
expected = [r["id"] for p in inputs for r in json.loads(p.read_text(encoding="utf-8"))["rows"]]
rows, parts = [], sorted(w.glob("full-part*-output.json"), key=lambda p: int(re.search(r"part(\d+)", p.name).group(1)))
for p in parts:
    rows += json.loads(p.read_text(encoding="utf-8"))["rows"]
ids = [r["id"] for r in rows]
problems = []
if ids != expected:
    missing = [i for i in expected if i not in ids]; extra = [i for i in ids if i not in expected]
    problems.append(f"id mismatch: missing {missing[:10]}{'…' if len(missing) > 10 else ''}, extra {extra[:10]}, order {'ok' if [i for i in ids if i in expected] == [i for i in expected if i in ids] else 'differs'}")
locked = {r["id"]: r for p in sorted(w.glob("full-part*-input.json")) for r in json.loads(p.read_text(encoding="utf-8"))["rows"]}
for r in rows:
    src = locked.get(r["id"])
    if not src:
        continue
    if (src["quotation"] or src["original_source"] or src["heading"]) and r["he_final"] != src["he"]:
        problems.append(f"locked row changed: {r['id']}")
    ma, mb = Counter(re.findall(r"\^(\d+)\^", src["he"])), Counter(re.findall(r"\^(\d+)\^", r["he_final"]))
    if ma != mb:
        problems.append(f"markers differ in {r['id']}: {sorted(ma)} vs {sorted(mb)}")
    for m in re.finditer(r"\^\d+\^", r["he_final"]):
        if m.start() and r["he_final"][m.start() - 1] not in ".,;:!?\"'”)»]—–" and not re.match(r"[א-ת]", r["he_final"][m.start() - 1]):
            pass
out = {"chapter": ch, "parts": [p.name for p in parts], "rows": rows}
(w / "full-output.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
changed = sum(1 for r in rows if r.get("changed") or r["he_input"] != r["he_final"])
print(f"{len(parts)} parts, {len(rows)} rows ({len(expected)} expected), {changed} changed → {w / 'full-output.json'}")
for p in problems:
    print("PROBLEM:", p)
sys.exit(1 if problems else 0)
