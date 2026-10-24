"""Build an editable glossary review page.

Usage: python3 build_glossary_review.py <glossary.json> <merge-report.json> <frequencies-glossary.json> <out.html>

Terms that the extraction agents disagreed on, and low-confidence terms, come
first; the rest follow by frequency in the book. The page saves edits as
glossary-decisions.json (browser download) for apply_glossary_review.py.
"""
import html
import json
import sys
from pathlib import Path

gloss_path, report_path, freq_path, out_path = map(Path, sys.argv[1:5])
terms = json.loads(gloss_path.read_text(encoding="utf-8"))["terms"]
freq = {t["source"]: t["frequency"] for t in json.loads(freq_path.read_text(encoding="utf-8"))["terms"]}
conflicts = {src: opts for src, opts, _ in json.loads(report_path.read_text(encoding="utf-8"))["conflicts"]}


def group(t):
    if t["source"] in conflicts:
        return 0
    if t.get("confidence") == "low":
        return 1
    return 2


terms.sort(key=lambda t: (group(t), -freq.get(t["source"], 0), t["source"].lower()))
labels = {0: "Agents disagreed", 1: "Low confidence", 2: "All other terms, most frequent first"}
rows, current = [], None
for t in terms:
    g = group(t)
    if g != current:
        current = g
        rows.append(f'<tr class="grp"><td colspan="6">{labels[g]}</td></tr>')
    alts = ""
    if t["source"] in conflicts:
        alts = "<div class='alts'>proposed: " + " / ".join(html.escape(o[0]) for o in conflicts[t["source"]]) + "</div>"
    aliases = ", ".join(t.get("aliases", []))
    rows.append(
        f'<tr data-src="{html.escape(t["source"])}" data-cat="{t.get("category", "")}">'
        f'<td dir="ltr"><strong>{html.escape(t["source"])}</strong>'
        f'{"<div class=al>" + html.escape(aliases) + "</div>" if aliases else ""}</td>'
        f'<td class="cat">{t.get("category", "")}</td><td class="num">{freq.get(t["source"], 0)}</td>'
        f'<td dir="rtl"><input class="tgt" dir="rtl" value="{html.escape(t["target"])}" data-orig="{html.escape(t["target"])}">{alts}</td>'
        f'<td dir="rtl"><input class="note" dir="auto" value="" placeholder="note for translators"></td>'
        f'<td class="n" dir="ltr">{html.escape(t.get("notes", ""))}</td></tr>'
    )

page = """<!DOCTYPE html><html lang="he"><head><meta charset="utf-8"><title>Glossary review</title>
<style>
:root { --bg:#fff; --fg:#222; --muted:#666; --line:#d6d6d6; --head:#f3f3f3; --chg:#dcfce7; }
@media (prefers-color-scheme: dark) { :root { --bg:#16181c; --fg:#e8e8e8; --muted:#9aa0a6; --line:#3a3d42; --head:#23262b; --chg:#14532d; } }
body { background:var(--bg); color:var(--fg); font-family:'Times New Roman', serif; margin:16px; }
.bar { position:sticky; top:0; background:var(--bg); padding:8px 0; border-bottom:1px solid var(--line); font-family:sans-serif; font-size:14px; display:flex; gap:10px; flex-wrap:wrap; align-items:center; z-index:2; }
input.f { padding:5px 8px; font:inherit; border:1px solid var(--line); border-radius:6px; background:var(--bg); color:var(--fg); }
button { font:inherit; padding:6px 12px; border:1px solid #1d4ed8; border-radius:6px; background:#1d4ed8; color:#fff; cursor:pointer; }
table { border-collapse:collapse; width:100%; margin-top:8px; }
td, th { border:1px solid var(--line); padding:6px 8px; vertical-align:top; font-size:16px; }
th { background:var(--head); font-family:sans-serif; font-size:13px; position:sticky; top:45px; }
tr.grp td { background:var(--head); font-family:sans-serif; font-weight:bold; font-size:14px; }
.cat, .num, .n, .al, .alts { font-family:sans-serif; font-size:12px; color:var(--muted); }
.alts { margin-top:4px; direction:rtl; }
td input.tgt, td input.note { width:100%; box-sizing:border-box; font:inherit; font-size:17px; padding:4px 6px; border:1px solid var(--line); border-radius:4px; background:var(--bg); color:var(--fg); }
td input.note { font-size:14px; }
tr.changed td { background:var(--chg); }
</style></head><body>
<div class="bar"><strong>Glossary review</strong><span>""" + str(len(terms)) + """ terms</span>
<input class="f" id="q" placeholder="filter (English or Hebrew)"><select class="f" id="cat"><option value="">all categories</option><option>person</option><option>work</option><option>place</option><option>concept</option><option>organization</option></select>
<span id="tally"></span><button id="save">Save decisions</button></div>
<table><thead><tr><th>English (aliases)</th><th>type</th><th>uses</th><th>Hebrew</th><th>note</th><th>agent notes</th></tr></thead><tbody>
""" + "".join(rows) + """</tbody></table>
<script>
const KEY = "glossary-review";
const rows = [...document.querySelectorAll("tr[data-src]")];
function edits() { return rows.map(r => ({ source: r.dataset.src, target: r.querySelector(".tgt").value.trim(),
  orig: r.querySelector(".tgt").dataset.orig, note: r.querySelector(".note").value.trim() }))
  .filter(e => e.target !== e.orig || e.note); }
function refresh() { rows.forEach(r => r.classList.toggle("changed", r.querySelector(".tgt").value.trim() !== r.querySelector(".tgt").dataset.orig || r.querySelector(".note").value.trim() !== ""));
  document.getElementById("tally").textContent = edits().length + " changed";
  try { localStorage.setItem(KEY, JSON.stringify(edits())); } catch (e) {} }
try { JSON.parse(localStorage.getItem(KEY) || "[]").forEach(e => { const r = rows.find(r => r.dataset.src === e.source);
  if (r) { r.querySelector(".tgt").value = e.target; r.querySelector(".note").value = e.note; } }); } catch (e) {}
function filter() { const q = document.getElementById("q").value.toLowerCase(), c = document.getElementById("cat").value;
  rows.forEach(r => { const text = (r.dataset.src + " " + r.querySelector(".tgt").value).toLowerCase();
    r.style.display = (!q || text.includes(q)) && (!c || r.dataset.cat === c) ? "" : "none"; }); }
document.addEventListener("input", e => { if (e.target.id === "q") filter(); else refresh(); });
document.getElementById("cat").onchange = filter;
document.getElementById("save").onclick = () => { const blob = new Blob([JSON.stringify({ edits: edits() }, null, 1)], { type: "application/json" });
  const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = "glossary-decisions.json"; a.click(); };
refresh();
</script></body></html>"""
out_path.write_text(page, encoding="utf-8")
print(out_path, len(terms), "terms")
