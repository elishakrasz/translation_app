"""Apply accepted review suggestions to the translated chunks.

Usage: python3 apply_review.py <temp_dir> <review_dir> <decisions.json>

For each accepted suggestion, replaces its `current` span (or, if the reviewer's
text was edited in the page, uses the edited text) inside the given paragraph of
output_chunkNNNN.md. Reports suggestions that could not be applied, e.g. because
an overlapping suggestion was applied first. Keeps a backup of each changed file.
"""
import json
import re
import shutil
import sys
from pathlib import Path

temp_dir, review_dir, decisions_path = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
decisions = [d for d in json.loads(decisions_path.read_text(encoding="utf-8"))["decisions"] if d["accepted"]]

by_chunk = {}
for d in decisions:
    by_chunk.setdefault(d["chunk"], []).append(d)

applied, failed = 0, []
for chunk, items in sorted(by_chunk.items()):
    out = temp_dir / f"output_chunk{chunk}.md"
    text = out.read_text(encoding="utf-8")
    blocks = re.split(r"(\n\s*\n)", text)  # keep separators
    para_idx = [i for i, b in enumerate(blocks) if b.strip() and not re.fullmatch(r"\n\s*\n", b)]
    for d in items:
        s = json.loads((review_dir / f"suggestions_{chunk}_{d['model']}.json").read_text(encoding="utf-8"))["suggestions"][d["idx"]]
        p = s["para"] - 1
        if p >= len(para_idx):
            failed.append((chunk, d["model"], s["para"], "paragraph out of range", s["current"]))
            continue
        block = blocks[para_idx[p]]
        if block.count(s["current"]) != 1:
            failed.append((chunk, d["model"], s["para"], "text not found (overlap?)", s["current"]))
            continue
        blocks[para_idx[p]] = block.replace(s["current"], d["text"], 1)
        applied += 1
    new = "".join(blocks)
    if new != text:
        shutil.copy2(out, out.with_suffix(".md.before-review"))
        out.write_text(new, encoding="utf-8")

print(f"applied {applied} of {len(decisions)} accepted suggestions")
for f in failed:
    print("NOT APPLIED:", f)


# ---- notes and highlights → REVIEW-NOTES.md (for the editor) ----
data = json.loads(decisions_path.read_text(encoding="utf-8"))
notes, flags = data.get("notes", []), data.get("flags", [])
if notes or flags:
    def para_text(chunk, n, lang):
        f = temp_dir / (f"output_chunk{chunk}.md" if lang == "he" else f"chunk{chunk}.md")
        ps = [p.strip() for p in re.split(r"\n\s*\n", f.read_text(encoding="utf-8")) if p.strip()]
        return ps[n - 1] if 0 < n <= len(ps) else ""
    by_row = {}
    for n in notes:
        by_row.setdefault((n["chunk"], n["para"]), {"notes": [], "flags": []})["notes"].append(n["text"])
    for f in flags:
        by_row.setdefault((f["chunk"], f["para"]), {"notes": [], "flags": []})["flags"].append(f)
    out = [f"# Review notes and highlights\n\n{len(notes)} notes, {len(flags)} highlighted passages.\n"]
    for (chunk, para) in sorted(by_row, key=lambda k: (k[0], k[1])):
        row = by_row[(chunk, para)]
        out.append(f"## Chunk {chunk}, paragraph {para}\n")
        for f in row["flags"]:
            out.append(f"- **Highlighted ({'Hebrew' if f['col'] == 'he' else 'English'}):** {f['text']}")
        for t in row["notes"]:
            out.append(f"- **Note:** {t}")
        out.append(f"\n> EN: {para_text(chunk, para, 'en')[:600]}\n>\n> HE: {para_text(chunk, para, 'he')[:600]}\n")
    (review_dir / "REVIEW-NOTES.md").write_text("\n".join(out), encoding="utf-8")
    print(f"wrote {review_dir / 'REVIEW-NOTES.md'} ({len(notes)} notes, {len(flags)} highlights)")
