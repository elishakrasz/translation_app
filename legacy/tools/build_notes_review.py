"""Review page for the Koren-style footnotes of one chapter.

Usage: python3 tools/build_notes_review.py <chNN>
Reads review/<chNN>/notes_input.json and review/<chNN>/notes_koren.json; writes
review/<chNN>/notes-review.html. Each note: English | Hebrew now | Koren style
(editable, accept tick) | what changed / to verify | your note. Below, the
bibliography entries (editable). Save → notes-decisions-<chNN>.json, applied by
tools/apply_notes_review.py.
"""
import os
import html
import json
import re
import sys
from pathlib import Path

ROOT = (Path(os.environ["TRANSLATOR_PROJECT"]).expanduser().resolve() if os.environ.get("TRANSLATOR_PROJECT")
        else sys.exit("Set TRANSLATOR_PROJECT to the book folder, e.g. TRANSLATOR_PROJECT=~/the_translator"))


def show(t):
    t = html.escape(t)
    return re.sub(r"(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)", r"<i>\1</i>", t)


def main():
    ch = sys.argv[1]
    d = ROOT / "review" / ch
    inp = {x["n"]: x for x in json.loads((d / "notes_input.json").read_text(encoding="utf-8"))}
    kor = json.loads((d / "notes_koren.json").read_text(encoding="utf-8"))
    rows = []
    for x in kor["notes"]:
        n = x["n"]; i = inp.get(n, {})
        flag = ' class="vf"' if x.get("verify") else ""
        rows.append(f'''<tr data-n="{n}"><td class="num">{n}</td>
<td dir="ltr" class="en">{show(i.get("en", ""))}</td>
<td dir="rtl" class="he">{show(i.get("he", ""))}</td>
<td dir="rtl" class="ko"><label dir="ltr"><input type="checkbox" class="acc" checked> accept</label><textarea dir="rtl" rows="3">{html.escape(x["koren"])}</textarea><div class="pv">{show(x["koren"])}</div></td>
<td class="meta" dir="ltr">{html.escape(x.get("changes", ""))}{f'<div{flag}>⚠ {html.escape(x["verify"])}</div>' if x.get("verify") else ""}
<textarea class="note" dir="auto" rows="2" placeholder="your note…"></textarea></td></tr>''')
    bib = []
    for j, b in enumerate(kor.get("bibliography", [])):
        v = b.get("verify")
        bib.append(f'''<tr data-b="{j}"{' class="vrow"' if v else ""}><td dir="auto" class="short">{show(b["short"])}</td>
<td><textarea dir="{"ltr" if b.get("lang") not in ("he", "yi") else "rtl"}" rows="2">{html.escape(b["full"])}</textarea></td>
<td class="meta">{html.escape(b.get("type", ""))} · {html.escape(b.get("lang", ""))} · nn. {", ".join(map(str, b.get("source_notes", [])))}{f'<div class="vf">⚠ {html.escape(b.get("why", "") or "verify")}</div>' if v else ""}</td></tr>''')
    page = TEMPLATE.replace("$CH$", ch).replace("$ROWS$", "".join(rows)).replace("$BIB$", "".join(bib)) \
        .replace("$KEY$", json.dumps("notes-review:" + ch)).replace("$N$", str(len(rows))).replace("$NB$", str(len(bib)))
    (d / "notes-review.html").write_text(page, encoding="utf-8")
    print(d / "notes-review.html", len(rows), "notes,", len(bib), "bibliography entries")


TEMPLATE = """<!DOCTYPE html><html lang="he"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Notes Review $CH$</title><style>
:root{--bg:#fff;--fg:#1d1d1f;--muted:#666;--line:#ddd;--head:#f3f3f3;--ok:#16a34a;--warn:#b45309;--accent:#1d4ed8}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#16181c;--fg:#e8e8e8;--muted:#9aa0a6;--line:#3a3d42;--head:#23262b;--warn:#fbbf24;--accent:#8ab4ff}}
body{background:var(--bg);color:var(--fg);font-family:sans-serif;margin:0;padding:0 16px 48px}
.bar{position:sticky;top:0;z-index:2;background:var(--bg);padding:10px 0;border-bottom:1px solid var(--line);display:flex;gap:10px;align-items:center;flex-wrap:wrap;font-size:13px}
h1{font-size:18px;margin:0 8px 0 0} h2{font-size:16px;margin-top:28px}
button{font:inherit;font-size:13px;padding:5px 10px;border:1px solid var(--line);border-radius:6px;background:var(--head);color:var(--fg);cursor:pointer} button.primary{background:var(--accent);color:#fff;border-color:var(--accent)}
.help{color:var(--muted);font-size:12px;max-width:1100px}
table{border-collapse:collapse;width:100%;table-layout:fixed} th,td{border:1px solid var(--line);padding:6px 8px;vertical-align:top;font-size:13px} th{background:var(--head);text-align:left}
td.num{width:34px;color:var(--muted)} td.en{color:var(--muted);font-family:'Times New Roman',serif;font-size:14px}
td.he,td.ko{font-family:'Times New Roman',serif;font-size:16px;text-align:right} td.ko .pv{margin-top:4px;color:var(--muted);font-size:14px}
textarea{width:100%;box-sizing:border-box;font:inherit;font-size:15px;color:var(--fg);background:var(--bg);border:1px solid var(--line);border-radius:4px}
td.meta{font-size:12px;color:var(--muted)} .vf{color:var(--warn);font-weight:bold;margin-top:4px} tr.vrow td{background:color-mix(in srgb,var(--warn) 8%,transparent)}
tr.rej td.ko{opacity:.45} td.short{font-family:'Times New Roman',serif;font-size:15px;width:24%}
label{font-size:12px;display:block;text-align:left}
@media(max-width:800px){td.en{display:none}}
</style></head><body>
<div class="bar"><h1>Footnotes — Koren style · $CH$</h1><span id="tally"></span>
<button id="onlyv">Show only items to verify</button><button class="primary" id="save">Save decisions</button><span id="st" class="help"></span></div>
<p class="help">Each note is proposed in the Koren/Maggid house style (sources/style/footnote-style.md). All are ticked <b>accept</b>; untick to keep the current Hebrew, or edit the proposal in place. ⚠ marks a detail to check (a Hebrew title not certain, a missing year…). The bibliography entries below will form the book's רשימת קיצורים ביבליוגרפיים; edit them freely. $N$ notes · $NB$ bibliography entries.</p>
<table><colgroup><col style="width:34px"><col style="width:24%"><col style="width:22%"><col style="width:28%"><col></colgroup>
<tr><th>#</th><th>English</th><th>Hebrew now</th><th>Koren style (proposed)</th><th>Changes · verify · your note</th></tr>$ROWS$</table>
<h2>Bibliography entries (רשימת קיצורים ביבליוגרפיים)</h2>
<table><tr><th>Short form (as in the notes)</th><th>Full entry</th><th>Type · notes · verify</th></tr>$BIB$</table>
<script>
const KEY=$KEY$; let st={}; try{st=JSON.parse(localStorage.getItem(KEY))||{}}catch(e){}
const rows=[...document.querySelectorAll("tr[data-n]")], brows=[...document.querySelectorAll("tr[data-b]")];
rows.forEach(r=>{const s=(st.notes||{})[r.dataset.n]; if(s){r.querySelector(".acc").checked=s.accepted; r.querySelector("td.ko textarea").value=s.text; r.querySelector("textarea.note").value=s.note||"";}});
brows.forEach(r=>{const s=(st.bib||{})[r.dataset.b]; if(s!==undefined) r.querySelector("textarea").value=s;});
function collect(){const notes={},bib={};rows.forEach(r=>{notes[r.dataset.n]={accepted:r.querySelector(".acc").checked,text:r.querySelector("td.ko textarea").value,note:r.querySelector("textarea.note").value}; r.classList.toggle("rej",!notes[r.dataset.n].accepted);});
 brows.forEach(r=>bib[r.dataset.b]=r.querySelector("textarea").value); return {notes,bib};}
function refresh(){st=collect(); try{localStorage.setItem(KEY,JSON.stringify(st))}catch(e){} const a=Object.values(st.notes).filter(x=>x.accepted).length; tally.textContent=a+" of "+rows.length+" accepted";}
document.addEventListener("input",refresh); refresh();
onlyv.onclick=()=>{const on=onlyv.dataset.on!=="1"; onlyv.dataset.on=on?"1":"0"; onlyv.textContent=on?"Show all":"Show only items to verify";
 [...rows,...brows].forEach(r=>r.style.display=(!on||r.querySelector(".vf"))?"":"none");};
save.onclick=()=>{refresh(); const data={chapter:"$CH$",saved:new Date().toISOString(),notes:Object.entries(st.notes).map(([n,v])=>({n:+n,...v})),bibliography:Object.entries(st.bib).map(([i,full])=>({i:+i,full}))};
 const json=JSON.stringify(data,null,1);
 try{const a=document.createElement("a");a.href=URL.createObjectURL(new Blob([json],{type:"application/json"}));a.download="notes-decisions-$CH$.json";document.body.appendChild(a);a.click();a.remove();st_.textContent="saved notes-decisions-$CH$.json · "+new Date().toLocaleTimeString();}
 catch(e){prompt("Copy and send to Claude:",json);}};
const st_=document.getElementById("st");
</script></body></html>"""

main()
