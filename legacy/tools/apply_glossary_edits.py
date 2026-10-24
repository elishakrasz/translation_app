"""Apply glossary-edits.json (saved from glossary/glossary.html) to the book glossary.

Usage: python3 tools/apply_glossary_edits.py <glossary-edits.json> [glossary/glossary-book.json]

Edited fields replace the term's values (aliases are comma-separated on the page);
new terms are added; deleted terms are removed; accepted chapter 7–12 proposals are
added (and every proposal decision is logged in glossary/part2-decisions.json). A backup is kept and a short
report lists every change, including Hebrew renderings that changed (which may
call for a conformance pass over the translation).
"""
import os
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = (Path(os.environ["TRANSLATOR_PROJECT"]).expanduser().resolve() if os.environ.get("TRANSLATOR_PROJECT")
        else sys.exit("Set TRANSLATOR_PROJECT to the book folder, e.g. TRANSLATOR_PROJECT=~/the_translator"))
edits_path = Path(sys.argv[1])
gpath = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "glossary" / "glossary-book.json"
data = json.loads(edits_path.read_text(encoding="utf-8"))
gloss = json.loads(gpath.read_text(encoding="utf-8"))
by_src = {t["source"]: t for t in gloss["terms"]}
report, retargeted = [], []


def norm(field, value):
    if field == "aliases":
        return [a.strip() for a in value.split(",") if a.strip()]
    return value.strip() if isinstance(value, str) else value


for e in data.get("edits", []):
    t = by_src.get(e["source"])
    if not t:
        report.append(f"? unknown term: {e['source']}")
        continue
    for f in ("target", "rule", "aliases", "category", "notes"):
        if f in e:
            old, new = t.get(f), norm(f, e[f])
            if old != new:
                t[f] = new
                report.append(f"~ {t['source']}: {f} {old!r} → {new!r}")
                if f == "target" and old:
                    retargeted.append({"source": t["source"], "old": old, "new": new})
    t["confidence"] = "high"

for a in data.get("added", []):
    src = a["source"].strip()
    if not src or src in by_src:
        report.append(f"? skipped new term (empty or exists): {src}")
        continue
    t = {"id": src, "source": src, "target": a.get("target", "").strip(), "category": a.get("category", "concept") or "concept",
         "aliases": norm("aliases", a.get("aliases", "")), "gender": "unknown", "confidence": "high", "frequency": 0,
         "evidence_refs": [], "notes": a.get("notes", ""), "rule": a.get("rule", "preferred")}
    gloss["terms"].append(t)
    by_src[src] = t
    report.append(f"+ {src} → {t['target']} ({t['rule']})")

decided = []                     # chapter 7–12 proposals accepted or rejected on the page
for pr in data.get("proposals", []):
    src = pr["source"].strip()
    decided.append(pr)
    if pr.get("decision") != "accept":
        report.append(f"x rejected proposal: {src}")
        continue
    if src in by_src:
        report.append(f"? skipped proposal (already in glossary): {src}")
        continue
    t = {"id": src, "source": src, "target": pr.get("target", "").strip(), "category": pr.get("category", "concept") or "concept",
         "aliases": norm("aliases", pr.get("aliases", "")), "gender": "unknown", "confidence": "high", "frequency": 0,
         "evidence_refs": [], "notes": pr.get("notes", ""), "rule": pr.get("rule", "preferred"), "added_for": "ch07-12"}
    gloss["terms"].append(t)
    by_src[src] = t
    changed = f" (proposed {pr['proposed_target']})" if pr.get("proposed_target") else ""
    report.append(f"+ {src} → {t['target']} ({t['rule']}){changed}")

dels = set(data.get("deleted", []))
if dels:
    gloss["terms"] = [t for t in gloss["terms"] if t["source"] not in dels]
    report += [f"- {s}" for s in sorted(dels)]

stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
shutil.copy2(gpath, gpath.with_name(f"{gpath.stem}.before-edits-{stamp}.json"))
gpath.write_text(json.dumps(gloss, ensure_ascii=False, indent=2), encoding="utf-8")
if decided:                      # keep a running record of the part-2 decisions
    log = ROOT / "glossary" / "part2-decisions.json"
    old = json.loads(log.read_text(encoding="utf-8")) if log.exists() else []
    keep = {d["source"] for d in decided}
    log.write_text(json.dumps([d for d in old if d["source"] not in keep] + [dict(d, applied=stamp) for d in decided], ensure_ascii=False, indent=1), encoding="utf-8")
if retargeted:
    (ROOT / "glossary" / f"retargeted-{stamp}.json").write_text(json.dumps(retargeted, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"{len(report)} changes → {gpath}")
print("\n".join(report))
if retargeted:
    print(f"\n{len(retargeted)} Hebrew renderings changed — the translation can be brought into line with tools/conform_terms.py (list in glossary/retargeted-{stamp}.json).")
