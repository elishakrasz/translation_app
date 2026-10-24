"""Apply glossary-decisions.json (saved from glossary-review.html) to a glossary.

Usage: python3 apply_glossary_review.py <glossary.json> <glossary-decisions.json>
Updates each edited term's Hebrew target and appends the note; marks it high confidence.
"""
import json
import shutil
import sys
from pathlib import Path

gloss_path, decisions_path = Path(sys.argv[1]), Path(sys.argv[2])
gloss = json.loads(gloss_path.read_text(encoding="utf-8"))
by_source = {t["source"]: t for t in gloss["terms"]}
changed, unknown = 0, []
for e in json.loads(decisions_path.read_text(encoding="utf-8"))["edits"]:
    t = by_source.get(e["source"])
    if t is None:
        unknown.append(e["source"])
        continue
    if e["target"]:
        t["target"] = e["target"]
    if e.get("note"):
        t["notes"] = (e["note"] + (" | " + t["notes"] if t.get("notes") else ""))[:500]
    t["confidence"] = "high"
    changed += 1
shutil.copy2(gloss_path, gloss_path.with_suffix(".json.bak"))
gloss_path.write_text(json.dumps(gloss, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"updated {changed} terms" + (f"; not found: {unknown}" if unknown else ""))
