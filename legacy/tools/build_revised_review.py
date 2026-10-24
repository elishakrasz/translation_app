"""Side-by-side review page for a translator's revised chapter.

Usage: python3 tools/build_revised_review.py <chNN> "<Title>"
Reads work/<chNN>/revised-aligned.json (alignment, restored footnote markers, Fable's
check), work/<chNN>/revised-eval.json (GPT / Gemini findings, optional),
work/<chNN>/revised-input.json (English notes) and review/<chNN>/notes_koren.json
(Koren-style Hebrew notes). Writes review/<chNN>/revised-review.html.
"""
import os
import html
import json
import re
import sys
from pathlib import Path

ROOT = (Path(os.environ["TRANSLATOR_PROJECT"]).expanduser().resolve() if os.environ.get("TRANSLATOR_PROJECT")
        else sys.exit("Set TRANSLATOR_PROJECT to the book folder, e.g. TRANSLATOR_PROJECT=~/the_translator"))


def fmt(t, rtl):
    t = html.escape(t)
    t = re.sub(r"\^(\d+)\^", r'<sup class="fn" data-n="\1">\1</sup>', t)
    t = re.sub(r"(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)", r"<i>\1</i>", t)
    lines = [re.sub(r"^&gt;\s?", "", l) for l in t.split("\n")]
    quote = t.lstrip().startswith("&gt;")
    head = re.match(r"^(#+)\s*", lines[0]) if lines else None
    body = "<br>".join(re.sub(r"^#+\s*", "", l) for l in lines if l.strip())
    if head:
        return f"<strong>{body}</strong>"
    return f'<div class="q">{body}</div>' if quote else body


def mark(he_html, spans):
    for s in sorted({s for s in spans if s}, key=len, reverse=True):
        e = html.escape(s)
        if e in he_html:
            he_html = he_html.replace(e, f"<mark>{e}</mark>", 1)
    return he_html


def main():
    ch, title = sys.argv[1], sys.argv[2]
    w = ROOT / "work" / ch
    al = json.loads((w / "revised-aligned.json").read_text(encoding="utf-8"))
    ev_path = w / "revised-eval.json"
    ev = json.loads(ev_path.read_text(encoding="utf-8")) if ev_path.exists() else {"models": {}, "rows": {}}
    inp = json.loads((w / "revised-input.json").read_text(encoding="utf-8"))
    en_notes = {x["n"]: x["en"] for x in inp["notes"]}
    kp = ROOT / "review" / ch / "notes_koren.json"
    if kp.exists():
        kor = {x["n"]: x["koren"] for x in json.loads(kp.read_text(encoding="utf-8"))["notes"]}
    else:   # Koren conversion not done yet: show the current Hebrew notes
        kor = {x["n"]: x["he"] + " (current form)" for x in json.loads((ROOT / "review" / ch / "notes_input.json").read_text(encoding="utf-8"))}
    rows, counts = [], {"critical": 0, "major": 0, "minor": 0}
    for k, r in enumerate(al["rows"]):
        found = [dict(f, src="Fable") for f in r.get("issues", [])]
        for prov, resp in ev["rows"].get(str(k), {}).items():
            if "error" in resp:
                continue
            for f in resp.get("findings", []):
                found.append({"type": f.get("category"), "severity": f.get("severity"), "he_span": f.get("he_span", ""),
                              "en_span": f.get("en_span", ""), "note": f.get("note", ""), "src": {"openai": "GPT", "gemini": "Gemini"}.get(prov, prov)})
        for f in found:
            counts[f.get("severity", "minor")] = counts.get(f.get("severity", "minor"), 0) + 1
        scores = " · ".join(f'{ {"openai": "GPT", "gemini": "Gemini"}.get(p, p)} {v["overall"].get("fidelity", "?")}/{v["overall"].get("register", "?")}/{v["overall"].get("terminology", "?")}'
                            for p, v in ev["rows"].get(str(k), {}).items() if "overall" in v)
        sev_order = {"critical": 0, "major": 1, "minor": 2}
        cards = "".join(
            f'<div class="f {html.escape(f.get("severity", ""))}"><b>{f["src"]}</b> · {html.escape(str(f.get("type", "")))} · {html.escape(f.get("severity", ""))}'
            + (f'<div class="sp" dir="rtl">«{html.escape(f["he_span"])}»</div>' if f.get("he_span") else "")
            + (f'<div class="en_sp">“{html.escape(f["en_span"])}”</div>' if f.get("en_span") else "")
            + f'<div>{html.escape(f.get("note", ""))}</div></div>' for f in sorted(found, key=lambda f: sev_order.get(f.get("severity"), 3)))
        notes = "".join(f'<div class="note-pair"><div dir="ltr" class="ne"><sup>{n}</sup> {fmt(en_notes.get(n, ""), False)}</div>'
                        f'<div dir="rtl" class="nh"><sup>{n}</sup> {fmt(kor.get(n, ""), True)}</div></div>' for n in r.get("markers", []))
        worst = min((sev_order.get(f.get("severity"), 3) for f in found), default=3)
        rows.append(
            f'<tr class="row{" has" if found else ""}{" major" if worst <= 1 else ""}{" unch" if r.get("revision_note") == "unchanged" else ""}" data-k="{k}">'
            f'<td class="num">{"·".join(r["en_ids"]) or "—"}<br><span class="rv">rev {",".join(map(str, r["revised"]))}</span></td>'
            f'<td dir="ltr" class="en">{fmt(r["en"], False) if r["en"] else "<i>(no English — translator’s working title)</i>"}</td>'
            f'<td dir="rtl" class="he">{mark(fmt(r["he"], True), [f.get("he_span", "") for f in found])}'
            f'<div class="rn" dir="ltr">{html.escape(r.get("revision_note", ""))}</div></td>'
            f'<td class="find">{f"<div class=sc>{html.escape(scores)}</div>" if scores else ""}{cards or "<span class=none>no findings</span>"}</td>'
            f'<td class="mine"><textarea dir="auto" rows="3" placeholder="your note / decision…"></textarea></td></tr>'
            + (f'<tr class="notes-row" data-k="{k}"><td></td><td colspan="2">{notes}</td><td colspan="2"></td></tr>' if notes else ""))
    models = ", ".join(f'{ {"openai": "GPT", "gemini": "Gemini"}.get(p, p)} = {m}' for p, m in ev.get("models", {}).items()) or "pending"
    eds = "".join(f"<li dir='rtl'>{html.escape(e['text'])}</li>" for e in al.get("editor_notes", []))
    orphans = "".join(f"<li>n. {o['n']}: {html.escape(o['reason'])}</li>" for o in al.get("orphan_notes", []))
    page = (TEMPLATE.replace("$TITLE$", html.escape(title)).replace("$ROWS$", "".join(rows))
            .replace("$SUMMARY$", html.escape(al.get("summary", ""))).replace("$MODELS$", html.escape(models))
            .replace("$COUNTS$", f'{counts["critical"]} critical · {counts["major"]} major · {counts["minor"]} minor')
            .replace("$ORPH$", f"<ul>{orphans}</ul>" if orphans else "none — all footnotes restored")
            .replace("$KEY$", json.dumps(f"revised-review:{ch}")).replace("$CH$", ch)
            .replace("$EDITOR$", f"<br><b>Editor's notes inserted in the revision</b> (not typeset; kept here for decision):<ul>{eds}</ul>" if eds else ""))
    out = ROOT / "review" / ch / "revised-review.html"
    out.write_text(page, encoding="utf-8")
    print(out, len(al["rows"]), "rows;", counts)


TEMPLATE = """<!DOCTYPE html><html lang="he"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Revised Review $CH$</title><style>
:root{--bg:#fff;--fg:#1d1d1f;--muted:#666;--line:#ddd;--head:#f3f3f3;--mark:#fff1a8;--crit:#b42318;--maj:#d97706;--min:#1d4ed8;--accent:#1d4ed8;--q:#f6f6f4}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#16181c;--fg:#e8e8e8;--muted:#9aa0a6;--line:#3a3d42;--head:#23262b;--mark:#5c4d00;--crit:#ff8a80;--maj:#fbbf24;--min:#8ab4ff;--accent:#8ab4ff;--q:#1f2226}}
body{background:var(--bg);color:var(--fg);font-family:sans-serif;margin:0;padding:0 16px 48px}
.bar{position:sticky;top:0;z-index:2;background:var(--bg);padding:10px 0;border-bottom:1px solid var(--line);display:flex;gap:10px;flex-wrap:wrap;align-items:center;font-size:13px}
h1{font-size:18px;margin:0 8px 0 0} button{font:inherit;font-size:13px;padding:5px 10px;border:1px solid var(--line);border-radius:6px;background:var(--head);color:var(--fg);cursor:pointer} button.primary{background:var(--accent);color:#fff;border-color:var(--accent)}
.sum{font-size:13px;max-width:1150px;margin:10px 0;line-height:1.5} .sum b{font-weight:600} .help{color:var(--muted);font-size:12px}
table{border-collapse:collapse;width:100%;table-layout:fixed} td,th{border:1px solid var(--line);padding:7px 9px;vertical-align:top} th{background:var(--head);font-size:13px;text-align:left;position:sticky;top:45px}
td.num{width:62px;font-size:11px;color:var(--muted)} .rv{font-size:10px}
td.en{font-family:'Times New Roman',serif;font-size:15px;line-height:1.55}
td.he{font-family:'Times New Roman',serif;font-size:18px;line-height:1.75;text-align:right}
.q{background:var(--q);border-inline-start:3px solid var(--line);padding:4px 8px}
sup.fn{color:var(--accent);font-weight:bold;font-size:.7em}
mark{background:var(--mark);color:inherit}
.rn{font-family:sans-serif;font-size:11px;color:var(--muted);text-align:left;margin-top:6px}
td.find{font-size:12px} .f{border-inline-start:3px solid var(--line);padding:2px 6px;margin-bottom:6px} .f.critical{border-color:var(--crit)} .f.major{border-color:var(--maj)} .f.minor{border-color:var(--min)}
.f .sp{font-family:'Times New Roman',serif;font-size:15px} .f .en_sp{color:var(--muted);font-style:italic} .sc{color:var(--muted);margin-bottom:6px} .none{color:var(--muted)}
td.mine{width:15%} textarea{width:100%;box-sizing:border-box;font:inherit;font-size:14px;color:var(--fg);background:var(--bg);border:1px solid var(--line);border-radius:4px}
tr.notes-row td{background:var(--head);font-size:13px} .note-pair{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:3px 0}
.ne{font-family:'Times New Roman',serif;color:var(--muted)} .nh{font-family:'Times New Roman',serif;font-size:15px;text-align:right}
body.only tr.row:not(.has), body.only tr.notes-row{display:none} body.onlych tr.row.unch, body.onlych tr.notes-row{display:none} body.onlymaj tr.row:not(.major), body.onlymaj tr.notes-row{display:none}
@media(max-width:800px){td.find,td.mine{display:none} .note-pair{grid-template-columns:1fr}}
</style></head><body>
<div class="bar"><h1>$TITLE$ — revised version</h1><span>$COUNTS$</span>
<button id="b1">Rows with findings</button><button id="b2">Major / critical only</button><button id="b4">Changed paragraphs</button><button id="b3">Show all</button>
<button class="primary" id="save">Save notes</button><span id="st" class="help"></span></div>
<div class="sum"><b>Check of the revision against the English (Fable):</b> $SUMMARY$<br><b>Independent evaluators:</b> $MODELS$ — scores are fidelity/register/terminology (1–5).<br><b>Footnotes:</b> all markers restored in the revised text at the Koren position (after punctuation); the Koren-style notes are shown under each paragraph (English note left, Hebrew right). Orphaned notes: $ORPH$$EDITOR$</div>
<table><colgroup><col style="width:62px"><col style="width:30%"><col style="width:33%"><col><col style="width:14%"></colgroup>
<tr><th>#</th><th>English</th><th>Revised Hebrew</th><th>Findings</th><th>Your notes</th></tr>$ROWS$</table>
<script>
const KEY=$KEY$; let st={}; try{st=JSON.parse(localStorage.getItem(KEY))||{}}catch(e){}
const tas=[...document.querySelectorAll("tr.row")].map(r=>[r.dataset.k,r.querySelector("td.mine textarea")]);
tas.forEach(([k,t])=>{t.value=st[k]||""; t.addEventListener("input",()=>{st[k]=t.value; try{localStorage.setItem(KEY,JSON.stringify(st))}catch(e){}});});
b1.onclick=()=>{document.body.className="only"}; b2.onclick=()=>{document.body.className="onlymaj"}; b3.onclick=()=>{document.body.className=""}; b4.onclick=()=>{document.body.className="onlych"};
save.onclick=()=>{const notes=tas.filter(([k,t])=>t.value.trim()).map(([k,t])=>({row:+k,text:t.value}));
 const json=JSON.stringify({chapter:"$CH$",kind:"revised-review",saved:new Date().toISOString(),notes},null,1);
 try{const a=document.createElement("a");a.href=URL.createObjectURL(new Blob([json],{type:"application/json"}));a.download="revised-review-$CH$.json";document.body.appendChild(a);a.click();a.remove();
 document.getElementById("st").textContent="saved revised-review-$CH$.json · "+new Date().toLocaleTimeString();}catch(e){prompt("Copy and send to Claude:",json);}};
</script></body></html>"""

main()
