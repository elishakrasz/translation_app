"""Side-by-side page for a stage-5 pilot: English | before | after (word-level diff) | pass log | your notes.

Usage: python3 tools/build_pilot_review.py <chNN> "<Title>" [input.json] [out-name]
Reads work/<chNN>/pilot/pilot-output.json (and pilot-eval.json if the independent
fidelity check has run); writes review/<chNN>/pilot-review.html.
"""
import os
import difflib
import html
import json
import re
import sys
from pathlib import Path

ROOT = (Path(os.environ["TRANSLATOR_PROJECT"]).expanduser().resolve() if os.environ.get("TRANSLATOR_PROJECT")
        else sys.exit("Set TRANSLATOR_PROJECT to the book folder, e.g. TRANSLATOR_PROJECT=~/the_translator"))
PROV = {"openai": "GPT", "gemini": "Gemini"}


def fmt(t):
    t = html.escape(t)
    t = re.sub(r"\^(\d+)\^", r'<sup class="fn">\1</sup>', t)
    lines = [re.sub(r"^&gt;\s?", "", l) for l in t.split("\n")]
    quote = t.lstrip().startswith("&gt;")
    body = "<br>".join(re.sub(r"^#+\s*", "", l) for l in lines if l.strip())
    if re.match(r"^#+\s", t):
        return f"<strong>{body}</strong>"
    return f'<div class="q">{body}</div>' if quote else body


def diff_html(a, b):
    """b with insertions marked <ins> and deletions from a marked <del>, token-wise."""
    ta, tb = a.split(), b.split()
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, ta, tb, autojunk=False).get_opcodes():
        if op == "equal":
            out.append(html.escape(" ".join(tb[j1:j2])))
        else:
            if i2 > i1:
                out.append(f'<del>{html.escape(" ".join(ta[i1:i2]))}</del>')
            if j2 > j1:
                out.append(f'<ins>{html.escape(" ".join(tb[j1:j2]))}</ins>')
    s = " ".join(out)
    s = re.sub(r"\^(\d+)\^", r'<sup class="fn">\1</sup>', s)
    return re.sub(r"(?m)^(?:&gt;|>)\s?", "", s).replace("\n", "<br>")


def main():
    ch, title = sys.argv[1], sys.argv[2]
    w = ROOT / "work" / ch / "pilot"
    src = Path(sys.argv[3]) if len(sys.argv) > 3 else w / "pilot-output.json"
    out_name = sys.argv[4] if len(sys.argv) > 4 else "pilot-review.html"
    data = json.loads(src.read_text(encoding="utf-8"))
    ev = json.loads((w / "pilot-eval.json").read_text(encoding="utf-8")) if (w / "pilot-eval.json").exists() else {"models": {}, "rows": {}}
    rows, nchg = [], 0
    for k, r in enumerate(data["rows"]):
        changed = r.get("changed") or r["he_input"] != r["he_final"]
        nchg += changed
        log = "".join(f'<div class="p"><b>Pass {p}</b><ul>{"".join(f"<li>{html.escape(x)}</li>" for x in items)}</ul></div>'
                      for p, items in sorted((r.get("log") or {}).items()) if items)
        evs = ev["rows"].get(r["id"], {})
        cards = ""
        for p, v in evs.items():
            if "overall" in v:
                o = v["overall"]
                cards += f'<div class="sc">{PROV.get(p, p)} {o.get("fidelity", "?")}/{o.get("register", "?")}/{o.get("terminology", "?")}</div>'
            for f in v.get("findings", []):
                cards += (f'<div class="f {html.escape(f.get("severity", ""))}"><b>{PROV.get(p, p)}</b> · {html.escape(f.get("category", ""))} · {html.escape(f.get("severity", ""))}'
                          f'<div class="sp" dir="rtl">«{html.escape(f.get("he_span", ""))}»</div>{html.escape(f.get("note", ""))}</div>')
        rows.append(
            f'<tr class="row{" chg" if changed else " same"}" data-k="{k}"><td class="num">{html.escape(r["id"])}</td>'
            f'<td dir="ltr" class="en">{fmt(r["en"])}</td>'
            f'<td dir="rtl" class="he">{fmt(r["he_input"])}</td>'
            f'<td dir="rtl" class="he">{diff_html(r["he_input"], r["he_final"]) if changed else fmt(r["he_final"])}</td>'
            f'<td class="log">{log or "<span class=none>unchanged</span>"}{cards}</td>'
            f'<td class="mine"><textarea dir="auto" rows="3" placeholder="keep / revert / your wording…"></textarea></td></tr>')
    models = ", ".join(f"{PROV.get(p, p)} = {m}" for p, m in ev.get("models", {}).items())
    page = (TEMPLATE.replace("$TITLE$", html.escape(title)).replace("$ROWS$", "".join(rows)).replace("$CH$", ch)
            .replace("$N$", f"{nchg} of {len(rows)} paragraphs changed").replace("$MODELS$", html.escape(models) if models else "not yet run")
            .replace("$KEY$", json.dumps(f"pilot-review:{ch}:{out_name}")))
    out = ROOT / "review" / ch / out_name
    out.write_text(page, encoding="utf-8")
    print(out, len(rows), "rows,", nchg, "changed")


TEMPLATE = """<!DOCTYPE html><html lang="he"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Pilot Review $CH$</title><style>
:root{--bg:#fff;--fg:#1d1d1f;--muted:#666;--line:#ddd;--head:#f3f3f3;--ins:#dcfce7;--del:#fee2e2;--accent:#1d4ed8;--q:#f6f6f4;--crit:#b42318;--maj:#d97706;--min:#1d4ed8}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#16181c;--fg:#e8e8e8;--muted:#9aa0a6;--line:#3a3d42;--head:#23262b;--ins:#14532d;--del:#5b1a1a;--accent:#8ab4ff;--q:#1f2226;--crit:#ff8a80;--maj:#fbbf24;--min:#8ab4ff}}
body{background:var(--bg);color:var(--fg);font-family:sans-serif;margin:0;padding:0 16px 48px}
.bar{position:sticky;top:0;z-index:2;background:var(--bg);padding:10px 0;border-bottom:1px solid var(--line);display:flex;gap:10px;flex-wrap:wrap;align-items:center;font-size:13px}
h1{font-size:18px;margin:0 8px 0 0} button{font:inherit;font-size:13px;padding:5px 10px;border:1px solid var(--line);border-radius:6px;background:var(--head);color:var(--fg);cursor:pointer} button.primary{background:var(--accent);color:#fff;border-color:var(--accent)}
.help{color:var(--muted);font-size:12px;max-width:1100px;margin:8px 0}
table{border-collapse:collapse;width:100%;table-layout:fixed} td,th{border:1px solid var(--line);padding:7px 9px;vertical-align:top} th{background:var(--head);font-size:13px;text-align:left;position:sticky;top:45px}
td.num{width:58px;font-size:11px;color:var(--muted)}
td.en{font-family:'Times New Roman',serif;font-size:14px;line-height:1.5;color:var(--muted)}
td.he{font-family:'Times New Roman',serif;font-size:17px;line-height:1.75;text-align:right}
.q{background:var(--q);border-inline-start:3px solid var(--line);padding:4px 8px}
sup.fn{color:var(--accent);font-weight:bold;font-size:.7em}
ins{background:var(--ins);text-decoration:none} del{background:var(--del);color:var(--muted)}
td.log{font-size:12px} .p ul{margin:2px 0 6px;padding-inline-start:16px} .none{color:var(--muted)}
.sc{color:var(--muted);margin:4px 0} .f{border-inline-start:3px solid var(--line);padding:2px 6px;margin:4px 0} .f.critical{border-color:var(--crit)} .f.major{border-color:var(--maj)} .f.minor{border-color:var(--min)} .f .sp{font-family:'Times New Roman',serif;font-size:14px}
td.mine{width:13%} textarea{width:100%;box-sizing:border-box;font:inherit;font-size:14px;color:var(--fg);background:var(--bg);border:1px solid var(--line);border-radius:4px}
body.onlychg tr.same{display:none}
</style></head><body>
<div class="bar"><h1>$TITLE$ — stage-5 pilot</h1><span>$N$</span><button id="b1">Changed only</button><button id="b2">Show all</button><button class="primary" id="save">Save notes</button><span id="st" class="help"></span></div>
<p class="help">Before = the current text (the translator's revision); After = the five passes of the draft style sheet (structure → lexicon → voice → fidelity → footnotes). Green = inserted, red = removed. The log names the rule behind each change. Independent fidelity check of the result: $MODELS$ (scores = fidelity/register/terminology). Nothing has been written into the chapter.</p>
<table><colgroup><col style="width:58px"><col style="width:22%"><col style="width:24%"><col style="width:24%"><col><col style="width:13%"></colgroup>
<tr><th>#</th><th>English</th><th>Before</th><th>After (diff)</th><th>Passes · check</th><th>Your decision</th></tr>$ROWS$</table>
<script>
const KEY=$KEY$; let st={}; try{st=JSON.parse(localStorage.getItem(KEY))||{}}catch(e){}
const tas=[...document.querySelectorAll("tr.row")].map(r=>[r.dataset.k,r.querySelector("textarea")]);
tas.forEach(([k,t])=>{t.value=st[k]||""; t.addEventListener("input",()=>{st[k]=t.value; try{localStorage.setItem(KEY,JSON.stringify(st))}catch(e){}});});
b1.onclick=()=>document.body.className="onlychg"; b2.onclick=()=>document.body.className="";
save.onclick=()=>{const notes=tas.filter(([k,t])=>t.value.trim()).map(([k,t])=>({row:+k,text:t.value}));
 const json=JSON.stringify({chapter:"$CH$",kind:"pilot-review",saved:new Date().toISOString(),notes},null,1);
 try{const a=document.createElement("a");a.href=URL.createObjectURL(new Blob([json],{type:"application/json"}));a.download="pilot-review-$CH$.json";document.body.appendChild(a);a.click();a.remove();
 document.getElementById("st").textContent="saved pilot-review-$CH$.json · "+new Date().toLocaleTimeString();}catch(e){prompt("Copy and send to Claude:",json);}};
</script></body></html>"""

main()
