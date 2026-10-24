"""Editable glossary page built from the current book glossary.

Usage: python3 tools/build_glossary_page.py [glossary/glossary-book.json] [glossary/glossary.html]

Shows every term with its Hebrew rendering, rule (required / preferred / flexible),
category, aliases and notes, plus how often the English occurs in chapters 1–6 and
in chapters 7–12, and how often the Hebrew rendering appears in the translation.
Proposals for chapters 7–12 (glossary/part2-proposals-*.json) are shown as their own
rows, to be accepted, rejected or left pending. Edits, new terms, deletions and
proposal decisions are kept in the browser and saved as glossary-edits.json for
tools/apply_glossary_edits.py.
"""
import os
import html
import json
import re
import sys
from pathlib import Path

ROOT = (Path(os.environ["TRANSLATOR_PROJECT"]).expanduser().resolve() if os.environ.get("TRANSLATOR_PROJECT")
        else sys.exit("Set TRANSLATOR_PROJECT to the book folder, e.g. TRANSLATOR_PROJECT=~/the_translator"))
TEMPS = ["ch01-introduction_temp", "ch02-holy-rebellion_temp", "ch03-biographical-sketch_temp",
         "ch04-torah-and-theology_temp", "ch05-zaddik-and-leadership_temp", "ch06-quest-for-truth_temp"]
PART2 = sorted((ROOT / "books" / "chapters").glob("ch[01][0-9]-*.md"))
PART2 = [p for p in PART2 if 7 <= int(p.name[2:4]) <= 12]
NIQQUD = re.compile(r"[֑-ׇ]")


def decided_sources():
    """English terms of the author's decided list (eval/decided-terms.md), lower-cased."""
    out = set()
    for line in (ROOT / "eval" / "decided-terms.md").read_text(encoding="utf-8").splitlines():
        m = re.match(r"\|\s*([^|]+?)\s*\|\s*[^|]+\|", line)
        if m and not m.group(1).startswith(("English", "---")):
            for part in re.split(r"\s*/\s*|\s*\(", m.group(1)):
                out.add(part.strip(" )").removeprefix("the ").removeprefix("to ").lower())
    return out


def main():
    gpath = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "glossary" / "glossary-book.json"
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "glossary" / "glossary.html"
    terms = json.loads(gpath.read_text(encoding="utf-8"))["terms"]
    en_text = "\n".join(p.read_text(encoding="utf-8") for t in TEMPS for p in sorted((ROOT / t).glob("chunk[0-9]*.md")))
    he_text = NIQQUD.sub("", "\n".join(p.read_text(encoding="utf-8") for t in TEMPS for p in sorted((ROOT / t).glob("output_chunk[0-9]*.md"))))
    en2_text = "\n".join(p.read_text(encoding="utf-8") for p in PART2)
    decided = decided_sources()
    count = lambda names, text: sum(len(re.findall(r"(?<![\w-])" + re.escape(s) + r"(?![\w-])", text)) for s in names if len(s) > 1)
    rows = []
    for t in terms:
        names = [t["source"]] + t.get("aliases", [])
        en_n = count(names, en_text)
        tgt = NIQQUD.sub("", t["target"]).strip('"')
        he_n = len(re.findall(r"(?<![א-ת])[ובלמהכש]{0,3}" + re.escape(tgt) + r"(?![א-ת])", he_text)) if tgt else 0
        is_decided = t["source"].lower().removeprefix("the ") in decided or any(a.lower() in decided for a in t.get("aliases", []))
        rule = t.get("rule") or ("required" if is_decided else "preferred")
        rows.append(dict(source=t["source"], target=t["target"], aliases=", ".join(t.get("aliases", [])), category=t.get("category", ""),
                         notes=t.get("notes", ""), rule=rule, decided=is_decided, en=en_n, en2=count(names, en2_text), he=he_n))
    rows.sort(key=lambda r: (not r["decided"], -r["en"], r["source"].lower()))
    props, conflicts = [], []
    for f in sorted((ROOT / "glossary").glob("part2-proposals.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        for x in d.get("proposals", []):
            names = [x["source"]] + list(x.get("aliases", []))
            alts = [a if isinstance(a, dict) else {"target": a} for a in x.get("alternatives", [])]
            props.append(dict(source=x["source"], target=x.get("target", ""), aliases=", ".join(x.get("aliases", [])),
                              category=x.get("category", ""), rule=x.get("rule", "preferred"), notes=x.get("why", ""),
                              alts=[{"target": a.get("target") or a.get("hebrew", ""), "why": a.get("why") or a.get("reason", "")} for a in alts],
                              example=x.get("example", ""), freq=x.get("frequency", {}), verify=bool(x.get("verify")),
                              en2=count(names, en2_text), en=count(names, en_text), file=f.stem))
        conflicts += [dict(c, file=f.stem) for c in d.get("sense_conflicts", [])]
        conflicts += [dict(source=c.get("source"), existing_target="(open question)", new_sense=c.get("evidence", ""),
                           proposed_handling=c.get("proposed", ""), example="", file=f.stem) for c in d.get("open_questions_resolved", [])]
    seen, uniq = set(), []                       # the two halves may propose the same term
    for x in props:
        k = x["source"].lower()
        if k in seen:
            continue
        seen.add(k)
        uniq.append(x)
    props = uniq
    cats = sorted({r["category"] for r in rows + props if r["category"]})
    page = TEMPLATE.replace("$DATA$", json.dumps(rows, ensure_ascii=False).replace("</", "<\\/")) \
        .replace("$PROPS$", json.dumps(props, ensure_ascii=False).replace("</", "<\\/")) \
        .replace("$CONFLICTS$", json.dumps(conflicts, ensure_ascii=False).replace("</", "<\\/")) \
        .replace("$CATS$", "".join(f"<option>{html.escape(c)}</option>" for c in cats)).replace("$N$", str(len(rows)))
    out.write_text(page, encoding="utf-8")
    print(out, len(rows), "terms,", len(props), "proposals for ch. 7–12,", len(conflicts), "sense conflicts / open questions")


TEMPLATE = r"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Book Glossary</title><style>
:root{--bg:#fff;--fg:#1d1d1f;--muted:#666;--line:#ddd;--head:#f3f3f3;--edit:#fff7d6;--new:#e8f5e9;--del:#fdecea;--accent:#1d4ed8;--prop:#f3eefe}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#16181c;--fg:#e8e8e8;--muted:#9aa0a6;--line:#3a3d42;--head:#23262b;--edit:#3d3410;--new:#123018;--del:#3a1f1d;--accent:#8ab4ff;--prop:#261d3a}}
body{background:var(--bg);color:var(--fg);font-family:sans-serif;margin:0;padding:0 16px 48px}
.bar{position:sticky;top:0;z-index:2;background:var(--bg);padding:10px 0;border-bottom:1px solid var(--line);display:flex;gap:8px;flex-wrap:wrap;align-items:center;font-size:13px}
h1{font-size:19px;margin:0 12px 0 0} input,select,textarea,button{font:inherit;font-size:13px;color:var(--fg);background:var(--bg);border:1px solid var(--line);border-radius:5px;padding:4px 6px}
button{cursor:pointer;background:var(--head)} button.primary{background:var(--accent);color:#fff;border-color:var(--accent)}
#q{width:220px} .help{color:var(--muted);font-size:12px;margin:8px 0;max-width:1000px}
table{border-collapse:collapse;width:100%;table-layout:fixed} th,td{border-bottom:1px solid var(--line);padding:4px 6px;vertical-align:top;font-size:13px}
th{background:var(--head);text-align:left;position:sticky;top:49px;z-index:1}
td input.he,td textarea.he{font-family:'Times New Roman',serif;font-size:17px;direction:rtl;text-align:right;width:100%;box-sizing:border-box}
td input,td textarea,td select{width:100%;box-sizing:border-box} td textarea{resize:vertical;min-height:28px}
td.num{text-align:right;color:var(--muted);font-variant-numeric:tabular-nums} td.src{font-weight:600}
tr.edited td{background:var(--edit)} tr.added td{background:var(--new)} tr.deleted td{background:var(--del);opacity:.6} tr.deleted td.src{text-decoration:line-through}
.badge{display:inline-block;font-size:10px;font-weight:bold;padding:1px 5px;border-radius:8px;background:var(--head);color:var(--muted);margin-left:4px}
.badge.dec{background:#1d4ed8;color:#fff} .badge.new{background:#7c3aed;color:#fff} .badge.ver{background:#d97706;color:#fff} .warn{color:#b42318;font-weight:bold}
tr.prop td{background:var(--prop)} tr.prop.acc td{background:var(--new)} tr.prop.rej td{opacity:.45}
.alts{margin-top:3px} .alt{display:inline-block;font-family:'Times New Roman',serif;font-size:15px;direction:rtl;border:1px dashed var(--line);border-radius:5px;padding:0 5px;margin:2px 3px 0 0;cursor:pointer}
.alt:hover{border-color:var(--accent)} .ex{color:var(--muted);font-size:12px;margin-top:3px;font-style:italic}
select.dec-acc{border-color:#15803d;color:#15803d;font-weight:bold} select.dec-rej{border-color:#b42318;color:#b42318}
details.conf{margin:6px 0;font-size:13px;max-width:1200px} details.conf li{margin:4px 0} details.conf .he{font-family:'Times New Roman',serif;font-size:15px}
@media(max-width:800px){th:nth-child(4),td:nth-child(4),th:nth-child(6),td:nth-child(6){display:none}}
</style></head><body>
<div class="bar"><h1>Book glossary</h1>
<input id="q" type="search" placeholder="Search English or Hebrew…">
<select id="fcat"><option value="">all categories</option>$CATS$</select>
<select id="frule"><option value="">any rule</option><option>required</option><option>preferred</option><option>flexible</option></select>
<select id="fshow"><option value="">all terms</option><option value="decided">author's decided terms</option><option value="changed">my changes only</option><option value="mismatch">Hebrew used less than English</option><option value="prop">proposed for ch. 7–12</option><option value="pending">proposals still pending</option><option value="used2">existing terms used in ch. 7–12</option></select>
<button id="add">+ New term</button><span id="cnt"></span><span id="chg" class="help"></span>
<button class="primary" id="save">Save changes</button><button id="reset" title="Discard all unsaved changes on this page">Discard changes</button></div>
<p class="help">Edit the Hebrew, the rule or the notes directly; changed rows turn yellow. <b>Rule</b>: <i>required</i> = must always be used (checked by the evaluators); <i>preferred</i> = the default, but context may justify another rendering; <i>flexible</i> = a suggestion only. <b>EN</b> = times the English term (or an alias) occurs in chapters 1–6; <b>7–12</b> = in chapters 7–12; <b>HE</b> = times the Hebrew rendering occurs in the translation (with prefixes) — a large gap may mean inconsistent renderings or legitimate variation. Edits stay in this browser until you press <b>Save changes</b>, which downloads <code>glossary-edits.json</code>. $N$ terms. <b>Proposals for chapters 7–12</b> (purple rows, filter “proposed for ch. 7–12”): set <i>accept</i> or <i>reject</i>; edit the Hebrew first if needed, or click an alternative to use it. Only accepted proposals enter the glossary; pending ones stay open. <span class="badge ver">verify</span> = standard Hebrew form not certain.</p>
<details class="conf" id="conf"><summary></summary><ul id="confl"></ul></details>
<table><colgroup><col style="width:17%"><col style="width:19%"><col style="width:9%"><col style="width:11%"><col style="width:7%"><col><col style="width:4%"><col style="width:4%"><col style="width:4%"><col style="width:3%"></colgroup>
<thead><tr><th>English</th><th>Hebrew</th><th>Rule</th><th>Aliases</th><th>Category</th><th>Notes</th><th>EN</th><th>7–12</th><th>HE</th><th></th></tr></thead><tbody id="tb"></tbody></table>
<script>
const BASE = $DATA$;
const PROPS = $PROPS$;
const CONFLICTS = $CONFLICTS$;
const KEY = "glossary-edits-v1";
let st; try { st = JSON.parse(localStorage.getItem(KEY)) || {}; } catch (e) { st = {}; }
st.edits = st.edits || {}; st.added = st.added || []; st.deleted = st.deleted || []; st.props = st.props || {};
const store = () => { try { localStorage.setItem(KEY, JSON.stringify(st)); } catch (e) {} };
const FIELDS = ["target", "rule", "aliases", "category", "notes"];
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
function cur(r) { return Object.assign({}, r, st.edits[r.source] || {}); }
function changed(r) { const e = st.edits[r.source]; return e && FIELDS.some(f => f in e && e[f] !== r[f]); }
function rowHtml(r, kind) {
  const c = kind === "added" ? r : cur(r);
  const cls = kind === "added" ? "added" : st.deleted.includes(r.source) ? "deleted" : changed(r) ? "edited" : "";
  const gap = r.en > 2 && r.he < r.en / 2 ? ' class="num warn" title="Hebrew rendering appears much less often than the English term"' : ' class="num"';
  const src = kind === "added" ? `<input data-f="source" value="${esc(c.source)}" placeholder="English term">` : esc(r.source) + (r.decided ? '<span class="badge dec">decided</span>' : "");
  return `<tr class="${cls}" data-src="${esc(kind === "added" ? r._id : r.source)}" data-kind="${kind || "base"}">
    <td class="src">${src}</td>
    <td><input class="he" data-f="target" value="${esc(c.target)}"></td>
    <td><select data-f="rule">${["required","preferred","flexible"].map(o => `<option${o === c.rule ? " selected" : ""}>${o}</option>`).join("")}</select></td>
    <td><input data-f="aliases" value="${esc(c.aliases)}"></td>
    <td><input data-f="category" value="${esc(c.category)}"></td>
    <td><textarea data-f="notes" rows="1" dir="auto">${esc(c.notes)}</textarea></td>
    <td${gap}>${kind === "added" ? "" : r.en}</td><td class="num">${kind === "added" ? "" : r.he}</td>
    <td><button class="del" title="${kind === "added" ? "Remove this new term" : "Mark for deletion / undo"}">${st.deleted.includes(r.source) ? "↺" : "×"}</button></td></tr>`;
}
function pcur(p) { return Object.assign({ decision: "pending" }, p, st.props[p.source] || {}); }
function propHtml(p) {
  const c = pcur(p), d = c.decision;
  const fq = Object.entries(p.freq || {}).map(([k, v]) => k.replace("ch", "") + ":" + v).join(" ");
  return `<tr class="prop${d === "accept" ? " acc" : d === "reject" ? " rej" : ""}" data-src="${esc(p.source)}" data-kind="prop">
    <td class="src">${esc(p.source)}<span class="badge new">new 7–12</span>${p.verify ? '<span class="badge ver">verify</span>' : ""}
      <div><select data-f="decision" class="${d === "accept" ? "dec-acc" : d === "reject" ? "dec-rej" : ""}">${["pending","accept","reject"].map(o => `<option${o === d ? " selected" : ""}>${o}</option>`).join("")}</select></div></td>
    <td><input class="he" data-f="target" value="${esc(c.target)}">
      ${p.alts.length ? `<div class="alts">${p.alts.map(a => `<span class="alt" title="${esc(a.why)}" data-t="${esc(a.target)}">${esc(a.target)}</span>`).join("")}</div>` : ""}
      ${c.target !== p.target ? `<div class="alts"><span class="alt" title="proposed rendering" data-t="${esc(p.target)}">↺ ${esc(p.target)}</span></div>` : ""}</td>
    <td><select data-f="rule">${["required","preferred","flexible"].map(o => `<option${o === c.rule ? " selected" : ""}>${o}</option>`).join("")}</select></td>
    <td><input data-f="aliases" value="${esc(c.aliases)}"></td>
    <td><input data-f="category" value="${esc(c.category)}"></td>
    <td><textarea data-f="notes" rows="2" dir="auto">${esc(c.notes)}</textarea>${p.example ? `<div class="ex">${esc(p.example)}</div>` : ""}</td>
    <td class="num">${p.en || ""}</td><td class="num" title="${esc(fq)}">${p.en2}</td><td class="num"></td><td></td></tr>`;
}
function render() {
  const q = document.getElementById("q").value.trim().toLowerCase(), fc = fcat.value, fr = frule.value, fs = fshow.value;
  const ok = (r, kind) => { const c = kind === "added" ? r : cur(r);
    if (q && !(String(c.source).toLowerCase().includes(q) || String(c.target).includes(q) || String(c.aliases).toLowerCase().includes(q) || String(c.notes).toLowerCase().includes(q))) return false;
    if (fc && c.category !== fc) return false; if (fr && c.rule !== fr) return false;
    if (fs === "decided" && !r.decided) return false;
    if (fs === "changed" && !(kind === "added" || changed(r) || st.deleted.includes(r.source))) return false;
    if (fs === "mismatch" && !(r.en > 2 && r.he < r.en / 2)) return false;
    if (fs === "prop" || fs === "pending") return false;
    if (fs === "used2" && !(r.en2 > 0)) return false;
    return true; };
  const okp = p => { const c = pcur(p);
    if (fs && fs !== "prop" && fs !== "pending" && !(fs === "changed" && c.decision !== "pending")) return false;
    if (fs === "pending" && c.decision !== "pending") return false;
    if (q && !(c.source.toLowerCase().includes(q) || c.target.includes(q) || c.aliases.toLowerCase().includes(q) || c.notes.toLowerCase().includes(q))) return false;
    if (fc && c.category !== fc) return false; if (fr && c.rule !== fr) return false; return true; };
  const props = PROPS.filter(okp);
  const added = st.added.filter(r => ok(r, "added")), base = BASE.filter(r => ok(r));
  if (fs === "used2") base.sort((a, b) => b.en2 - a.en2);
  tb.innerHTML = added.map(r => rowHtml(r, "added")).join("") + props.map(propHtml).join("") + base.slice(0, 1500).map(r => rowHtml(r)).join("");
  cnt.textContent = (added.length + props.length + base.length) + " shown";
  status();
}
function status() {
  const n = Object.keys(st.edits).filter(s => { const r = BASE.find(b => b.source === s); return r && changed(r); }).length;
  const pd = PROPS.map(pcur), acc = pd.filter(p => p.decision === "accept").length, rej = pd.filter(p => p.decision === "reject").length;
  chg.textContent = `${n} edited · ${st.added.length} new · ${st.deleted.length} to delete · proposals: ${acc} accepted, ${rej} rejected, ${PROPS.length - acc - rej} pending`;
}
tb.addEventListener("input", e => {
  const el = e.target, f = el.dataset.f; if (!f) return; const tr = el.closest("tr"), src = tr.dataset.src;
  if (tr.dataset.kind === "prop") { st.props[src] = st.props[src] || {}; st.props[src][f] = el.value;
    if (f === "target" && !st.props[src].decision) st.props[src].decision = "pending";
    store(); if (f === "decision") render(); else status(); return; }
  if (tr.dataset.kind === "added") { const r = st.added.find(a => a._id === src); r[f] = el.value; }
  else { const r = BASE.find(b => b.source === src); st.edits[src] = st.edits[src] || {}; st.edits[src][f] = el.value;
         tr.className = st.deleted.includes(src) ? "deleted" : changed(r) ? "edited" : ""; }
  store(); status();
});
tb.addEventListener("change", e => tb.dispatchEvent(new Event("input", { bubbles: true })) || null);
tb.addEventListener("click", e => {
  if (e.target.classList.contains("alt")) { const src = e.target.closest("tr").dataset.src;
    st.props[src] = st.props[src] || {}; st.props[src].target = e.target.dataset.t; store(); render(); return; }
  if (!e.target.classList.contains("del")) return; const tr = e.target.closest("tr"), src = tr.dataset.src;
  if (tr.dataset.kind === "added") st.added = st.added.filter(a => a._id !== src);
  else st.deleted = st.deleted.includes(src) ? st.deleted.filter(s => s !== src) : [...st.deleted, src];
  store(); render();
});
add.onclick = () => { const id = "new-" + Date.now(); st.added.unshift({ _id: id, source: "", target: "", rule: "preferred", aliases: "", category: "concept", notes: "" });
  store(); fshow.value = ""; document.getElementById("q").value = ""; render(); tb.querySelector('tr[data-kind="added"] input').focus(); };
[document.getElementById("q"), fcat, frule, fshow].forEach(el => el.addEventListener("input", render));
save.onclick = () => {
  const edits = Object.entries(st.edits).map(([source, e]) => { const r = BASE.find(b => b.source === source); if (!r) return null;
    const d = {}; FIELDS.forEach(f => { if (f in e && e[f] !== r[f]) d[f] = e[f]; }); return Object.keys(d).length ? { source, ...d } : null; }).filter(Boolean);
  const added = st.added.filter(a => a.source.trim()).map(({ _id, ...r }) => r);
  const proposals = PROPS.map(pcur).filter(p => p.decision !== "pending").map(p => ({ source: p.source, decision: p.decision, target: p.target,
    rule: p.rule, aliases: p.aliases, category: p.category, notes: p.notes, proposed_target: p.target === PROPS.find(x => x.source === p.source).target ? undefined : PROPS.find(x => x.source === p.source).target }));
  const data = { saved: new Date().toISOString(), edits, added, deleted: st.deleted, proposals };
  try { const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([JSON.stringify(data, null, 1)], { type: "application/json" }));
        a.download = "glossary-edits.json"; document.body.appendChild(a); a.click(); a.remove();
        chg.textContent = `saved glossary-edits.json (${edits.length} edited, ${added.length} new, ${st.deleted.length} deleted, ${proposals.length} proposals decided) · ${new Date().toLocaleTimeString()}`; }
  catch (e) { prompt("Copy this and send it to Claude:", JSON.stringify(data)); }
};
reset.onclick = () => { if (confirm("Discard all unsaved changes on this page?")) { st = { edits: {}, added: [], deleted: [], props: {} }; store(); render(); } };
conf.querySelector("summary").textContent = `Sense conflicts and open questions for chapters 7–12 (${CONFLICTS.length}) — existing renderings that may not fit the new chapters`;
confl.innerHTML = CONFLICTS.map(c => `<li><b>${esc(c.source)}</b> — now <span class="he" dir="rtl">${esc(c.existing_target)}</span>. ${esc(c.new_sense)} <i>Proposed:</i> <span dir="auto">${esc(c.proposed_handling)}</span>${c.example ? ` <span class="ex">${esc(c.example)}</span>` : ""}</li>`).join("");
if (!CONFLICTS.length) conf.style.display = "none";
render();
</script></body></html>"""

main()
