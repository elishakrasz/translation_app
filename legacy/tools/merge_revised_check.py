"""Merge a revised chapter's skeleton + Fable check into work/<chNN>/revised-aligned.json (for build_revised_review.py).

Usage: python3 tools/merge_revised_check.py <chNN>
"""
import os
import json, sys
from pathlib import Path
ROOT = (Path(os.environ["TRANSLATOR_PROJECT"]).expanduser().resolve() if os.environ.get("TRANSLATOR_PROJECT")
        else sys.exit("Set TRANSLATOR_PROJECT to the book folder, e.g. TRANSLATOR_PROJECT=~/the_translator"))
ch = sys.argv[1]; w = ROOT / "work" / ch
sk = json.loads((w / "revised-skeleton.json").read_text(encoding="utf-8"))
chk = json.loads((w / "revised-check.json").read_text(encoding="utf-8")) if (w / "revised-check.json").exists() else {"rows": [], "summary": ""}
by_k = {r["k"]: r for r in chk["rows"]}
rows = []
for k, r in enumerate(sk["rows"]):
    c = by_k.get(k, {}) if r.get("changed") else {}
    rows.append({"en_ids": r["en_ids"], "en": r["en"], "revised": r["revised"], "he": r["he"], "markers": r["markers"],
                 "revision_note": c.get("revision_note", r.get("note") or ("unchanged" if not r.get("changed") else "")), "issues": c.get("issues", [])})
notes_in = json.loads((ROOT / "review" / ch / "notes_input.json").read_text(encoding="utf-8"))
(w / "revised-input.json").write_text(json.dumps({"notes": [{"n": x["n"], "en": x["en"]} for x in notes_in]}, ensure_ascii=False, indent=1), encoding="utf-8")
out = {"rows": rows, "orphan_notes": [], "summary": chk.get("summary", ""), "editor_notes": sk.get("editor_notes", [])}
(w / "revised-aligned.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print(w / "revised-aligned.json", len(rows), "rows,", sum(len(r["issues"]) for r in rows), "Fable issues,", len(out["editor_notes"]), "editor notes")
