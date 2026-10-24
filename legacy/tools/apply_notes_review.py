"""Apply notes-decisions-<chNN>.json (from review/<chNN>/notes-review.html).

Usage: python3 tools/apply_notes_review.py <chNN> <notes-decisions.json>

Accepted notes replace the note text in the chapter's notes section (output_chunk
files, with backups); rejected ones are left as they are. Bibliography entries
(with any edits) are merged into sources/style/bibliography.json, the book-wide
list that becomes the רשימת קיצורים ביבליוגרפיים. Translator notes are written to
review/<chNN>/NOTES-REVIEW.md.
"""
import os
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = (Path(os.environ["TRANSLATOR_PROJECT"]).expanduser().resolve() if os.environ.get("TRANSLATOR_PROJECT")
        else sys.exit("Set TRANSLATOR_PROJECT to the book folder, e.g. TRANSLATOR_PROJECT=~/the_translator"))
TEMPS = {"ch01": "ch01-introduction_temp", "ch02": "ch02-holy-rebellion_temp", "ch03": "ch03-biographical-sketch_temp",
         "ch04": "ch04-torah-and-theology_temp", "ch05": "ch05-zaddik-and-leadership_temp", "ch06": "ch06-quest-for-truth_temp",
         "ch07": "ch07-torat-ha-adam-human-psychology_temp", "ch08": "ch08-torat-ha-adam-psychology-of-the-soul_temp",
         "ch09": "ch09-torat-ha-adam-psychology-of-service_temp", "ch10": "ch10-prayer_temp",
         "ch11": "ch11-reaction-against-przysucha_temp", "ch12": "ch12-end-of-the-holy-rebellion_temp"}

ch, dec_path = sys.argv[1], Path(sys.argv[2])
dec = json.loads(dec_path.read_text(encoding="utf-8"))
kor = json.loads((ROOT / "review" / ch / "notes_koren.json").read_text(encoding="utf-8"))
temp = ROOT / TEMPS[ch]
bk = ROOT / "backups" / f"before-notes-{ch}"
bk.mkdir(parents=True, exist_ok=True)

accepted = {x["n"]: x["text"].strip() for x in dec["notes"] if x["accepted"]}
done, missing = set(), []
for f in sorted(temp.glob("output_chunk[0-9]*.md")):
    text = f.read_text(encoding="utf-8")
    m = re.search(r"(?m)^#+\s*(?:הערות|Notes)\s*$", text)
    head, notes = (text[:m.end()], text[m.end():]) if m else ("", text)
    def sub(mm):
        n = int(mm.group(1))
        if n in accepted and n not in done:
            done.add(n)
            return f"{n}\\. {accepted[n]}"
        return mm.group(0)
    # only lines that are note entries (a chunk with no heading may still hold continued notes)
    new_notes = re.sub(r"(?m)^(\d+)\\?\.\s.+$", sub, notes) if (m or re.match(r"\s*\d+\\?\.", notes)) else notes
    if new_notes != notes:
        if not (bk / f.name).exists():
            shutil.copy2(f, bk / f.name)
        f.write_text(head + new_notes, encoding="utf-8")
missing = sorted(set(accepted) - done)

# bibliography
edits = {b["i"]: b["full"] for b in dec.get("bibliography", [])}
bpath = ROOT / "sources" / "style" / "bibliography.json"
book = json.loads(bpath.read_text(encoding="utf-8")) if bpath.exists() else {"entries": []}
by_short = {e["short"]: e for e in book["entries"]}
for i, b in enumerate(kor.get("bibliography", [])):
    entry = dict(b, full=edits.get(i, b["full"]).strip())
    old = by_short.get(b["short"])
    if old:
        old["full"] = entry["full"]
        old["chapters_notes"] = sorted(set(old.get("chapters_notes", [])) | {f"{ch}:{n}" for n in b.get("source_notes", [])})
    else:
        entry["chapters_notes"] = [f"{ch}:{n}" for n in b.get("source_notes", [])]
        book["entries"].append(entry)
        by_short[b["short"]] = entry
book["entries"].sort(key=lambda e: e["short"])
bpath.write_text(json.dumps(book, ensure_ascii=False, indent=1), encoding="utf-8")

notes = [x for x in dec["notes"] if x.get("note", "").strip()]
if notes:
    (ROOT / "review" / ch / "NOTES-REVIEW.md").write_text(
        f"# Footnote review notes — {ch}\n\n" + "\n".join(f"- n. {x['n']}: {x['note'].strip()}" for x in notes) + "\n", encoding="utf-8")
print(f"{len(done)} notes written, {len(dec['notes']) - len(accepted)} kept as before, missing {missing}; "
      f"bibliography: {len(book['entries'])} entries in {bpath.relative_to(ROOT)}; {len(notes)} translator notes")
