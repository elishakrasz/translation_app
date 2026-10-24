"""Write the Koren-style notes (review/<chNN>/notes_koren.json) into a chapter's notes section,
appending an inline [לבדיקה: …] flag wherever the conversion marked something to verify.

Usage: python3 tools/write_koren_notes.py <chNN> <temp_dir>
Backups go to backups/before-koren-notes-<chNN>/. Also merges the chapter's bibliography
entries into sources/style/bibliography.json.
"""
import os
import json, re, shutil, sys
from pathlib import Path
ROOT = (Path(os.environ["TRANSLATOR_PROJECT"]).expanduser().resolve() if os.environ.get("TRANSLATOR_PROJECT")
        else sys.exit("Set TRANSLATOR_PROJECT to the book folder, e.g. TRANSLATOR_PROJECT=~/the_translator"))
ch, temp = sys.argv[1], ROOT / sys.argv[2]
kor = json.loads((ROOT / "review" / ch / "notes_koren.json").read_text(encoding="utf-8"))
notes = {}
for x in kor["notes"]:
    t = x["koren"].strip()
    if x.get("verify"):
        v = re.sub(r"\s+", " ", x["verify"]).strip()
        t = t + f" [לבדיקה: {v}]"
    notes[int(x["n"])] = t
bk = ROOT / "backups" / f"before-koren-notes-{ch}"; bk.mkdir(parents=True, exist_ok=True)
done = set()
for f in sorted(temp.glob("output_chunk[0-9]*.md")):
    text = f.read_text(encoding="utf-8")
    m = re.search(r"(?m)^#+\s*(?:הערות|Notes)\s*$", text)
    in_notes = bool(m) or bool(done)          # chunks after the heading hold continued notes
    if not in_notes:
        continue
    head, body = (text[:m.end()], text[m.end():]) if m else ("", text)
    def sub(mm):
        n = int(mm.group(1))
        if n in notes and n not in done:
            done.add(n); return f"{n}\\. {notes[n]}"
        return mm.group(0)
    new = re.sub(r"(?m)^(\d+)\\?\.\s.+$", sub, body)
    if new != body:
        shutil.copy2(f, bk / f.name); f.write_text(head + new, encoding="utf-8")
missing = sorted(set(notes) - done)
bpath = ROOT / "sources" / "style" / "bibliography.json"
book = json.loads(bpath.read_text(encoding="utf-8")) if bpath.exists() else {"entries": []}
by_short = {e["short"]: e for e in book["entries"]}
for b in kor.get("bibliography", []):
    tag = [f"{ch}:{n}" for n in b.get("source_notes", [])]
    if b["short"] in by_short:
        e = by_short[b["short"]]; e["chapters_notes"] = sorted(set(e.get("chapters_notes", [])) | set(tag))
        if b["full"] != e["full"] and b["full"] not in e.get("variants", []):
            e.setdefault("variants", []).append(b["full"])
    else:
        e = dict(b); e["chapters_notes"] = tag; e.pop("source_notes", None); book["entries"].append(e); by_short[b["short"]] = e
book["entries"].sort(key=lambda e: e["short"])
bpath.write_text(json.dumps(book, ensure_ascii=False, indent=1), encoding="utf-8")
flagged = sum(1 for x in kor["notes"] if x.get("verify"))
print(f"{ch}: {len(done)} notes written ({flagged} with [לבדיקה] flags), missing {missing}; bibliography now {len(book['entries'])} entries ({sum(1 for e in book['entries'] if e.get('variants'))} with variant entries to merge)")
