"""Step 6, notes: a unit's footnotes in the house's style, and the book's bibliography.

`input` gathers every note: its English, its current Hebrew, and the locked quotations in it. An agent converts the
citations to the house style (houses/<house>/footnote-style.md and style rule 8) and proposes a bibliography entry for
each work cited, into work/notes/<unit>-koren.json. `page` builds the review page (English | Hebrew now | Hebrew in
house style); `write` applies the decisions downloaded from it. A note whose locked quotation would change is refused,
and the bibliography is checked for one work with two short forms.
"""

import html
import json
import re
from pathlib import Path

from . import records, sources

NOTE_RE = re.compile(r"(\d+|\\\*)\\\.\s")


def _note_blocks(path):
    out = {}
    for m in re.finditer(r"(.*?)\s*<!--id:([^>]*)-->", path.read_text(encoding="utf-8"), re.S):
        if ".n" in m.group(2):
            out[m.group(2)] = m.group(1).strip()
    return out


def gather(project, unit):
    udir = project.unit_dir(unit)
    english, hebrew, where = {}, {}, {}
    for p in sorted(udir.glob("chunk[0-9]*.md")):
        english.update(_note_blocks(p))
    for p in sorted(udir.glob("output_chunk[0-9]*.md")):
        for bid, body in _note_blocks(p).items():
            hebrew[bid], where[bid] = body, p.name
    locked = {}
    for q in records.load(project, "quotations"):
        if q.get("unit") == unit["id"]:
            locked.setdefault(q["block"], []).append({"qid": q["qid"], "text": q["text"], "locator": q["locator"]})
    return [{"id": bid, "chunk": where.get(bid), "english": english.get(bid, ""), "hebrew": hebrew.get(bid, ""),
             "locked": locked.get(bid, [])} for bid in sorted(english, key=lambda b: (b.endswith("n000"), b))]


def write_input(project, unit):
    items = gather(project, unit)
    out = project.work("notes") / f"{unit['id']}-input.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    return items, out


def locks_kept(new, locked):
    """The locked quotations a new note text no longer contains: [qid]."""
    return [q["qid"] for q in locked if sources.verify(q["text"], [new])]


# ---------------------------------------------------------------------------
# Review page
# ---------------------------------------------------------------------------

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Notes review</title>
<style>
:root { --bg:#fbfaf7; --fg:#1d1d1b; --muted:#6b6a65; --line:#e3e0d8; --accent:#2c5d8f; --done:#e8f3ea; --warn:#b5651d; }
@media (prefers-color-scheme: dark) { :root { --bg:#1b1b1a; --fg:#ecebe6; --muted:#a3a19a; --line:#3a3936; --accent:#8fb6e0; --done:#22332a; } }
body { background:var(--bg); color:var(--fg); font:15px/1.5 -apple-system, "Segoe UI", Arial, sans-serif; margin:0 16px 80px; }
header { position:sticky; top:0; background:var(--bg); padding:12px 0 8px; border-bottom:1px solid var(--line); z-index:2; }
h1 { font-size:20px; margin:0 0 4px; } .muted { color:var(--muted); font-size:13px; }
.bar { display:flex; gap:8px; flex-wrap:wrap; align-items:center; margin-top:8px; }
button, select { font:inherit; padding:5px 10px; border:1px solid var(--line); border-radius:6px; background:transparent; color:var(--fg); }
button.primary { background:var(--accent); color:#fff; border-color:var(--accent); }
.note { border-bottom:1px solid var(--line); padding:12px 0; display:grid; grid-template-columns: 1fr 1fr 1fr; gap:12px; }
.note.done { background:var(--done); }
.he { direction:rtl; text-align:right; font-family:"SF Hebrew","Arial Hebrew",Arial,sans-serif; font-size:16px; }
textarea { width:100%; box-sizing:border-box; min-height:7em; font:inherit; padding:6px; border:1px solid var(--line); border-radius:4px; background:transparent; color:var(--fg); }
.label { font-size:12px; text-transform:uppercase; letter-spacing:.04em; color:var(--muted); margin-bottom:4px; }
.changes { color:var(--muted); font-size:13px; } .lock { color:var(--warn); font-size:12px; }
@media (max-width: 900px) { .note { grid-template-columns: 1fr; } }
</style></head><body>
<header><h1>Notes review — {{TITLE}}, {{UNIT}}</h1>
<div class="muted">{{SUMMARY}} Edit the house-style Hebrew if needed, then choose. Decisions stay in this browser until you download them.</div>
<div class="bar"><select id="f"><option value="">All</option><option value="open">Not decided yet</option><option value="changed">Changed by the conversion</option></select>
<button id="acceptAll">Accept all undecided</button><span class="muted" id="count"></span><span style="flex:1"></span>
<button id="copy">Copy decisions</button><button class="primary" id="dl">Download decisions</button></div></header>
<div id="rows"></div>
<script>
const NOTES = {{DATA}};
const KEY = "notes-review:" + {{KEYNAME}};
let state = {}; try { state = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) {}
const save = () => { try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) {} };
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
function render() {
  const f = document.getElementById("f").value; let done = 0, shown = 0;
  document.getElementById("rows").innerHTML = NOTES.map((n, i) => {
    const s = state[n.id] || {}; if (s.decision) done++;
    if (f === "open" && s.decision) return ""; if (f === "changed" && n.hebrew === n.koren) return ""; shown++;
    return `<div class="note ${s.decision ? "done" : ""}"><div><div class="label">${esc(n.id)} — English</div>${esc(n.english)}</div>
      <div class="he"><div class="label">Hebrew now</div>${esc(n.hebrew)}</div>
      <div class="he"><div class="label">House style</div><textarea class="he" data-i="${i}">${esc(s.text ?? n.koren)}</textarea>
      ${n.changes && n.changes.length ? `<div class="changes" dir="ltr">${n.changes.map(esc).join("<br>")}</div>` : ""}
      ${n.locked && n.locked.length ? `<div class="lock" dir="ltr">Locked quotation: ${n.locked.map(q => esc(q.qid + " " + q.locator)).join(", ")} — must stay word for word</div>` : ""}
      <select data-i="${i}"><option value=""></option>${["accept","edit","reject"].map(d => `<option ${s.decision===d?"selected":""}>${d}</option>`).join("")}</select></div></div>`;
  }).join("");
  document.getElementById("count").textContent = `${done} of ${NOTES.length} decided · ${shown} shown`;
}
function set(i, patch) { const n = NOTES[i]; state[n.id] = Object.assign({}, state[n.id] || {}, patch); save(); }
document.addEventListener("change", e => { const i = e.target.dataset.i; if (i === undefined) return;
  if (e.target.tagName === "SELECT") set(+i, { decision: e.target.value });
  else set(+i, { text: e.target.value, decision: (state[NOTES[+i].id] || {}).decision || "edit" }); render(); });
document.getElementById("f").onchange = render;
document.getElementById("acceptAll").onclick = () => { NOTES.forEach((n, i) => { if (!(state[n.id] || {}).decision) set(i, { decision: "accept" }); }); render(); };
function decisions() { return JSON.stringify({ unit: {{UNITID}}, decided: new Date().toISOString(), decisions: state }, null, 1); }
document.getElementById("dl").onclick = () => { const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([decisions()], {type:"application/json"})); a.download = {{FILENAME}}; a.click(); };
document.getElementById("copy").onclick = async () => { try { await navigator.clipboard.writeText(decisions()); alert("Copied."); } catch (e) { prompt("Copy this:", decisions()); } };
render();
</script></body></html>
"""


def page(project, unit):
    conv = json.loads((project.work("notes") / f"{unit['id']}-koren.json").read_text(encoding="utf-8"))
    by_id = {c["id"]: c for c in conv["notes"]}
    data = []
    for n in gather(project, unit):
        c = by_id.get(n["id"], {})
        data.append({**n, "koren": c.get("hebrew", n["hebrew"]), "changes": c.get("changes", [])})
    changed = sum(d["koren"] != d["hebrew"] for d in data)
    text = (PAGE.replace("{{TITLE}}", html.escape(project.title)).replace("{{UNIT}}", html.escape(unit["id"]))
            .replace("{{SUMMARY}}", html.escape(f"{len(data)} notes, {changed} changed by the conversion; "
                                                f"{len(conv.get('bibliography', []))} works for the bibliography."))
            .replace("{{KEYNAME}}", json.dumps(f"{project.root.name}:{unit['id']}"))
            .replace("{{UNITID}}", json.dumps(unit["id"])).replace("{{FILENAME}}", json.dumps(f"notes-decisions-{unit['id']}.json"))
            .replace("{{DATA}}", json.dumps(data, ensure_ascii=False).replace("</", "<\\/")))
    out = project.root / "review" / "notes" / unit["id"] / "notes-review.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    return out, len(data), changed


# ---------------------------------------------------------------------------
# Applying the decisions
# ---------------------------------------------------------------------------

def bibliography_conflicts(rows):
    """One work with two short forms, or one short form for two works."""
    by_work, by_short, out = {}, {}, []
    for r in rows:
        by_work.setdefault(r["work"], set()).add(r["short_form"])
        by_short.setdefault(r["short_form"], set()).add(r["work"])
    out += [f"{w!r} has two short forms: {', '.join(sorted(s))}" for w, s in by_work.items() if len(s) > 1]
    out += [f"short form {s!r} names two works: {', '.join(sorted(w))}" for s, w in by_short.items() if len(w) > 1]
    return out


def write(project, unit, decisions_file, write=False):
    """Apply the decisions. Returns (applied, problems). Nothing is written if there are problems."""
    dec = json.loads(Path(decisions_file).expanduser().read_text(encoding="utf-8"))["decisions"]
    conv = json.loads((project.work("notes") / f"{unit['id']}-koren.json").read_text(encoding="utf-8"))
    koren = {c["id"]: c["hebrew"] for c in conv["notes"]}
    udir = project.unit_dir(unit)
    applied, problems, edits = [], [], []
    files = {}
    for n in gather(project, unit):
        d = dec.get(n["id"], {})
        if d.get("decision") not in ("accept", "edit"):
            continue
        new = (d.get("text") or koren.get(n["id"], n["hebrew"])).strip()
        if new == n["hebrew"]:
            continue
        if not NOTE_RE.match(new):
            problems.append(f"{n['id']}: the note must start with its number, as '12\\. '")
            continue
        if (lost := locks_kept(new, n["locked"])):
            problems.append(f"{n['id']}: locked quotation(s) {', '.join(lost)} would change")
            continue
        f = udir / n["chunk"]
        body = files.get(f) or f.read_text(encoding="utf-8")
        if body.count(n["hebrew"]) != 1:
            problems.append(f"{n['id']}: current text not found exactly once in {n['chunk']}")
            continue
        files[f] = body.replace(n["hebrew"], new, 1)
        applied.append(n["id"])
        edits.append({"command": "translator notes write", "unit": unit["id"], "block": n["id"],
                      "before": n["hebrew"], "after": new, "reason": "house footnote style"})
    bib = [dict(b, units=[unit["id"]]) for b in conv.get("bibliography", [])]
    existing = records.load(project, "bibliography")
    problems += bibliography_conflicts([*existing, *bib])
    if write and not problems:
        for f, body in files.items():
            f.write_text(body, encoding="utf-8")
        if edits:
            records.append(project, "edits", edits, by="translator notes write")
        known = {(b["work"], b["short_form"]) for b in existing}
        new_bib = [b for b in bib if (b["work"], b["short_form"]) not in known]
        if new_bib:
            records.append(project, "bibliography", new_bib, by="translator notes write")
    return applied, problems
