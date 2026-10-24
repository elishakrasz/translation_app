"""Merge the Fable and Opus fidelity findings into one review page per chapter, plus a summary.

Usage: python3 tools/build_fidelity_report.py [chNN ...]     (default: every chapter with a bundle)
Reads work/fidelity/chNN-bundle.md and chNN-{fable,opus}[-body|-notes].json; writes
work/fidelity/chNN-fidelity.html and work/fidelity/SUMMARY.md. Items flagged by both reviewers come first.
"""
import os
import html
import json
import re
import sys
from pathlib import Path

ROOT = (Path(os.environ["TRANSLATOR_PROJECT"]).expanduser().resolve() if os.environ.get("TRANSLATOR_PROJECT")
        else sys.exit("Set TRANSLATOR_PROJECT to the book folder, e.g. TRANSLATOR_PROJECT=~/the_translator"))
F = ROOT / "work" / "fidelity"
SEV = {"critical": 0, "major": 1, "minor": 2}
MODELS = ("fable", "opus")


def bundle_items(ch):
    text = (F / f"{ch}-bundle.md").read_text(encoding="utf-8")
    items = {}
    for m in re.finditer(r"^## (\S+)(.*?)\n\nEN: (.*?)\n\nHE: (.*?)(?=\n\n## |\Z)", text, re.S | re.M):
        items[m.group(1)] = {"meta": m.group(2).strip(" ·"), "en": m.group(3).strip(), "he": m.group(4).strip()}
    return items


def load(ch, model):
    out = {}
    for p in sorted(F.glob(f"{ch}-{model}*.json")):
        for it in json.loads(p.read_text(encoding="utf-8")).get("items", []):
            out[it["id"]] = it
    return out


def mark(he, spans):
    s = html.escape(he)
    for sp in sorted({x for x in spans if x}, key=len, reverse=True):
        e = html.escape(sp)
        if e in s:
            s = s.replace(e, f"<mark>{e}</mark>", 1)
    return s


def cell(it):
    if not it:
        return '<span class="na">—</span>'
    if it.get("verdict") == "source-quote" and not it.get("findings"):
        return '<span class="src">original source</span>'
    if not it.get("findings"):
        return '<span class="ok">ok</span>'
    rows = []
    for f in sorted(it["findings"], key=lambda f: SEV.get(f.get("severity"), 3)):
        rows.append(f'<div class="f {f.get("severity", "")}"><b>{html.escape(f.get("severity", ""))}</b> · '
                    f'{html.escape(f.get("category", ""))}<br><span dir="rtl">«{html.escape(f.get("he_span", ""))}»</span>'
                    + (f'<br><i>“{html.escape(f.get("en_span", ""))}”</i>' if f.get("en_span") else "")
                    + f'<br>{html.escape(f.get("note", ""))}</div>')
    return "".join(rows)


def worst(it):
    return min((SEV.get(f.get("severity"), 3) for f in (it or {}).get("findings", [])), default=9)


def build(ch):
    items = bundle_items(ch)
    res = {m: load(ch, m) for m in MODELS}
    if not any(res.values()):
        return None
    rows, stats = [], {"items": len(items), "both": 0, "one": 0, "crit": 0, "major": 0, "minor": 0, "missing": {}}
    for m in MODELS:
        stats["missing"][m] = len([i for i in items if i not in res[m]])
    for iid, it in items.items():
        a, b = res["fable"].get(iid), res["opus"].get(iid)
        fa, fb = bool(a and a.get("findings")), bool(b and b.get("findings"))
        if not (fa or fb):
            continue
        both = fa and fb
        stats["both" if both else "one"] += 1
        w = min(worst(a), worst(b))
        stats[{0: "crit", 1: "major", 2: "minor"}.get(w, "minor")] += 1
        spans = [f.get("he_span", "") for x in (a, b) if x for f in x.get("findings", [])]
        rows.append((0 if both else 1, w, iid, f'<tr class="{"both" if both else "one"} w{w}"><td>{iid}<br><small>{html.escape(it["meta"])}</small>'
                     f'{"<br><b>both</b>" if both else ""}</td><td dir="ltr">{html.escape(it["en"])}</td>'
                     f'<td dir="rtl">{mark(it["he"], spans)}</td><td dir="ltr">{cell(a)}</td><td dir="ltr">{cell(b)}</td></tr>'))
    rows.sort(key=lambda r: (r[0], r[1]))
    page = f"""<!DOCTYPE html><html lang="he"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Fidelity check {ch}</title><style>
:root{{--bg:#fff;--fg:#1d1d1f;--line:#ddd;--mark:#fff3a0;--both:#fdecea;--muted:#666}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{--bg:#16181c;--fg:#e8e8e8;--line:#333;--mark:#6b5d00;--both:#3a2020;--muted:#999}}}}
body{{background:var(--bg);color:var(--fg);font-family:'Times New Roman',serif;margin:0 auto;max-width:1400px;padding:20px 16px}}
h1{{font-size:20px}} .sum{{font-family:sans-serif;font-size:13px;color:var(--muted)}}
table{{border-collapse:collapse;width:100%;table-layout:fixed}} td{{border-bottom:1px solid var(--line);vertical-align:top;padding:6px 8px;font-size:15px;line-height:1.5}}
td:nth-child(1){{width:70px;font-family:sans-serif;font-size:12px}} td:nth-child(4),td:nth-child(5){{width:22%;font-family:sans-serif;font-size:12.5px}}
td[dir=rtl]{{font-size:17px}} mark{{background:var(--mark);color:inherit}} tr.both{{background:var(--both)}}
.f{{margin-bottom:6px}} .critical b{{color:#c0392b}} .major b{{color:#d35400}} .minor b{{color:#7f8c8d}} .ok{{color:#27ae60}} .src{{color:#2980b9}} .na{{color:var(--muted)}}
label{{font-family:sans-serif;font-size:13px;margin-right:12px}}
</style></head><body>
<h1>Fidelity check — {ch} (your edited Koren file vs. Rosen's English)</h1>
<p class="sum">{stats['items']} items checked · flagged by both reviewers: {stats['both']} · by one: {stats['one']} · worst severity — critical {stats['crit']}, major {stats['major']}, minor {stats['minor']}. Rows flagged by both come first (shaded). Highlighted = the flagged Hebrew span.</p>
<p><label><input type="checkbox" id="onlyboth"> only items flagged by both</label><label><input type="checkbox" id="nominor"> hide minor-only</label></p>
<table><thead><tr><th>Item</th><th>English</th><th>Your Hebrew</th><th>Fable</th><th>Opus</th></tr></thead><tbody>
{''.join(r[3] for r in rows)}
</tbody></table><script>
const ob=document.getElementById('onlyboth'),nm=document.getElementById('nominor');
function f(){{document.querySelectorAll('tbody tr').forEach(r=>{{r.style.display=((ob.checked&&!r.classList.contains('both'))||(nm.checked&&r.classList.contains('w2')))?'none':''}})}}
ob.onchange=f;nm.onchange=f;</script></body></html>"""
    (F / f"{ch}-fidelity.html").write_text(page, encoding="utf-8")
    return stats


def main():
    chs = sys.argv[1:] or sorted(p.name[:4] for p in F.glob("ch??-bundle.md"))
    lines = ["# Fidelity check — summary", "", "| Chapter | Items | Flagged by both | By one only | Worst: critical | major | minor | Not yet reviewed (Fable / Opus) |", "|---|---|---|---|---|---|---|---|"]
    for ch in chs:
        s = build(ch)
        if s:
            lines.append(f"| {ch} | {s['items']} | {s['both']} | {s['one']} | {s['crit']} | {s['major']} | {s['minor']} | {s['missing']['fable']} / {s['missing']['opus']} |")
            print(ch, s)
    (F / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
