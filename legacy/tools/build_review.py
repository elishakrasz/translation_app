"""Build a 4-column HTML review page: English | current Hebrew | Fable | Opus.

Usage: python3 build_review.py <temp_dir> <review_dir> [title]

Reads <temp_dir>/chunkNNNN.md and output_chunkNNNN.md, and
<review_dir>/suggestions_NNNN_{fable,opus}.json. Writes <review_dir>/review.html.
The page saves decisions as review-decisions.json (browser download) for apply_review.py.
"""
import html
import json
import re
import sys
from pathlib import Path

MODELS = [("fable", "Fable 5.1"), ("opus", "Opus 5.5")]


def paras(path):
    return [p.strip() for p in re.split(r"\n\s*\n", path.read_text(encoding="utf-8")) if p.strip()]


def render(p):
    quote = p.startswith(">")
    p = re.sub(r"(?m)^>\s?", "", p)
    heading = re.match(r"^#+\s*", p)
    p = re.sub(r"^#+\s*", "", p)
    p = html.escape(p)
    p = re.sub(r"\^(\d+)\^", r"<sup>\1</sup>", p).replace("\n", "<br>")
    if heading:
        return f"<strong>{p}</strong>"
    return f'<div class="q">{p}</div>' if quote else p


def highlight(par_html, spans):
    for span in spans:
        esc = re.sub(r"\^(\d+)\^", r"<sup>\1</sup>", html.escape(span))
        par_html = par_html.replace(esc, f"<mark>{esc}</mark>", 1)
    return par_html


def options_html(it, he=""):
    """Fable's alternatives for one highlighted span (review_dir/options_fable.json)."""
    if he and (it["replaces"] not in he or any(len(o["hebrew"]) > len(it["replaces"]) and o["hebrew"] in he for o in it["options"])):
        return (f'<div class="opt done" dir="ltr">✓ <b>#{it["id"]}</b> decided — '
                f'<span dir="rtl">«{html.escape(it["replaces"])}»</span> was replaced</div>')
    rows = "".join(f'<li><b>{o["n"]}.</b> <span dir="rtl" class="oh">{html.escape(o["hebrew"])}</span>'
                   f'<div class="why" dir="ltr">{html.escape(o["reason"])}</div></li>' for o in it["options"])
    return (f'<details class="opt" open><summary dir="ltr"><b>#{it["id"]}</b> Fable options for '
            f'<span dir="rtl">«{html.escape(it["replaces"])}»</span></summary>'
            f'<div class="why" dir="ltr">“{html.escape(it.get("english", ""))}” — {html.escape(it.get("diagnosis", ""))}</div>'
            f'<ol dir="ltr">{rows}</ol></details>')


def eval_cell(ev, he=""):
    """Gemini / GPT / DictaLM findings for one paragraph (from eval/findings/<chNN>.json)."""
    if not ev:
        return '<td class="ev none">(not evaluated)</td>'
    sc = " · ".join(f'{p} ' + "/".join("?" if o.get(k) is None else str(o[k]) for k in ("fidelity", "register", "terminology"))
                   for p, o in ev["scores"].items() if o)
    if ev.get("naturalness"):
        sc += f' · dicta {ev["naturalness"]}'
    out = [f'<div class="sc" dir="ltr" title="fidelity / register / terminology">{html.escape(sc)}</div>']
    if ev["look"]:
        out.append(f'<div class="why" dir="ltr">⚑ {html.escape("; ".join(ev["look"]))}</div>')
    for f in ev["findings"]:
        if he and f["he_span"] and re.sub(r"\s+", " ", f["he_span"]) not in re.sub(r"\s+", " ", he):
            out.append(f'<div class="f done" dir="ltr">✓ {html.escape(f["category"] or f["type"])} — resolved (text changed)'
                       f'<div class="sp" dir="rtl">«{html.escape(f["he_span"])}»</div></div>')
            continue
        out.append(f'<div class="f {html.escape(f["severity"])}" dir="ltr"><b>{f["provider"]}</b> {html.escape(f["category"] or f["type"])} · {html.escape(f["severity"])}'
                   f'<div class="sp" dir="rtl">«{html.escape(f["he_span"])}»</div>{html.escape(f["note"])}</div>')
    return f'<td class="ev">{"".join(out)}</td>'


def main():
    temp_dir, review_dir = Path(sys.argv[1]), Path(sys.argv[2])
    title = sys.argv[3] if len(sys.argv) > 3 else temp_dir.name
    chunks = sorted(p.name[5:9] for p in temp_dir.glob("chunk[0-9][0-9][0-9][0-9].md"))
    body, total = [], {"error": 0, "style": 0}
    # paragraphs that hold an inserted original source (frozen, so later review edits are not mistaken for sources)
    man = temp_dir.parent / "sources" / "source-paragraphs.json"
    src_paras = set(json.loads(man.read_text(encoding="utf-8")).get(review_dir.name, [])) if man.exists() else set()
    opt_path = review_dir / "options_fable.json"
    options = {}
    if opt_path.exists():
        for it in json.loads(opt_path.read_text(encoding="utf-8"))["items"]:
            options.setdefault(f'{it["chunk"]}-{it["para"]}', []).append(it)
    ev_path = temp_dir.parent / "eval" / "findings" / f"{review_dir.name}.json"
    evals = json.loads(ev_path.read_text(encoding="utf-8")) if ev_path.exists() else None
    looks = 0
    for n in chunks:
        en = paras(temp_dir / f"chunk{n}.md")
        he = paras(temp_dir / f"output_chunk{n}.md")
        before_path = temp_dir.parent / "backups" / "before-sources" / temp_dir.name / f"output_chunk{n}.md"
        before = paras(before_path) if before_path.exists() else None
        sugg = {}
        for key, _ in MODELS:
            f = review_dir / f"suggestions_{n}_{key}.json"
            sugg[key] = json.loads(f.read_text(encoding="utf-8"))["suggestions"] if f.exists() else None
        rows = []
        for i in range(max(len(en), len(he))):
            para_no = i + 1
            cells = [f'<td dir="ltr" class="en">{render(en[i]) if i < len(en) else ""}</td>']
            spans = [s["current"] for key, _ in MODELS for s in (sugg[key] or []) if s.get("para") == para_no]
            he_cell = highlight(render(he[i]), spans) if i < len(he) else ""
            src_changed = before is not None and i < len(he) and i < len(before) and f"{n}-{para_no}" in src_paras
            if src_changed:
                he_cell = ('<div class="srclabel" dir="ltr">✦ original source inserted</div>' + he_cell +
                           '<details class="prev" dir="rtl"><summary dir="ltr">previous translation</summary>' + render(before[i]) + '</details>')
            cells.append(f'<td dir="rtl" class="he{" srcchg" if src_changed else ""}">{he_cell}</td>')
            for key, _ in MODELS:
                if sugg[key] is None:
                    cells.append('<td class="none">(no review)</td>')
                    continue
                cards = []
                for idx, s in enumerate(sugg[key]):
                    if s.get("para") != para_no:
                        continue
                    kind = s.get("type", "style")
                    sid = f"{n}-{key}-{idx}"
                    if i < len(he) and s["current"] not in he[i]:
                        cards.append(f'<div class="card gone" dir="ltr"><span class="badge">{kind}</span> no longer applies — the text has changed (applied earlier or replaced by the original source).'
                                     f'<div class="cur" dir="rtl">{html.escape(s["current"])}</div></div>')
                        continue
                    total[kind] = total.get(kind, 0) + 1
                    cards.append(
                        f'<div class="card {kind}" data-id="{sid}" data-chunk="{n}" data-model="{key}" data-idx="{idx}">'
                        f'<label><input type="checkbox" class="acc"> <span class="badge">{"error" if kind == "error" else "style"}</span> accept</label>'
                        f'<div class="cur" dir="rtl">{html.escape(s["current"])}</div>'
                        f'<textarea dir="rtl" rows="3">{html.escape(s["proposed"])}</textarea>'
                        f'<div class="why" dir="ltr">{html.escape(s.get("reason", ""))}</div></div>'
                    )
                cells.append(f'<td dir="rtl">{"".join(cards)}</td>')
            ev = evals["paragraphs"].get(f"{n}-{para_no}") if evals else None
            if evals is not None:
                cells.append(eval_cell(ev, he[i] if i < len(he) else ""))
                if ev and ev["look"]:
                    looks += 1
            opts = "".join(options_html(it, he[i] if i < len(he) else "") for it in options.get(f"{n}-{para_no}", []))
            cells.append('<td class="notecell"><textarea class="note" dir="auto" rows="2" placeholder="notes…"></textarea><div class="flags"></div>'
                         + (f'<div class="opts">{opts}</div>' if opts else "") + '</td>')
            look = bool(ev and ev["look"])
            rows.append(f'<tr class="para{" look" if look else ""}" data-chunk="{n}" data-para="{para_no}">'
                        f'<td class="num">{n}·{para_no}{"<br>⚑" if look else ""}</td>{"".join(cells)}</tr>')
        body.append(f'<tr class="chunk"><td colspan="{7 if evals else 6}">Chunk {n}</td></tr>' + "".join(rows))

    dec = review_dir.parent / "decisions" / f"{review_dir.name}.json"
    banner = ('<div class="banner">Your review decisions for this chapter have been applied. Suggestions still shown are ones you did not accept; '
              'greyed cards were applied or superseded. Highlighted and noted rows are listed in REVIEW-NOTES.md.</div>') if dec.exists() else ''
    page = TEMPLATE.replace("$BANNER$", banner).replace("$TITLE$", html.escape(title)).replace("$ROWS$", "".join(body)) \
        .replace("$COUNTS$", f'{total["error"]} error and {total["style"]} style suggestions') \
        .replace("$KEY$", json.dumps(str(review_dir.resolve()))).replace("$CHAPTER$", json.dumps(review_dir.name)) \
        .replace("$EVCOL$", '<col style="width:16%">' if evals else "") \
        .replace("$EVTH$", "<th>Evaluators<br><small>" + html.escape(" · ".join(f"{k}: {v}" for k, v in evals["models"].items())) + "</small></th>" if evals else "") \
        .replace("$EVBTN$", f'<button id="onlylook">Show only ⚑ needs a look ({looks})</button>' if evals else "")
    out = review_dir / "review.html"
    out.write_text(page, encoding="utf-8")
    print(out, total)


TEMPLATE = """<!DOCTYPE html>
<html lang="he"><head><meta charset="utf-8"><title>Review — $TITLE$</title>
<style>
:root { --bg:#fff; --fg:#222; --muted:#666; --line:#d6d6d6; --head:#f3f3f3; --err:#b42318; --errbg:#fdecea; --sty:#1d4ed8; --stybg:#eef2ff; --mark:#fff3b0; --flag:#ffd9ec; --flagline:#c2185b; }
@media (prefers-color-scheme: dark) { :root { --bg:#16181c; --fg:#e8e8e8; --muted:#9aa0a6; --line:#3a3d42; --head:#23262b; --err:#ff8a80; --errbg:#3a1f1d; --sty:#9db4ff; --stybg:#1f2640; --mark:#5c4d00; --flag:#4a1d33; --flagline:#f06292; } }
body { background:var(--bg); color:var(--fg); font-family:'Times New Roman', serif; margin:16px; }
.bar { position:sticky; top:0; z-index:2; background:var(--bg); padding:8px 0; border-bottom:1px solid var(--line); font-family:sans-serif; font-size:14px; display:flex; gap:12px; align-items:center; flex-wrap:wrap; }
button { font:inherit; padding:6px 12px; border:1px solid var(--line); border-radius:6px; background:var(--head); color:var(--fg); cursor:pointer; }
button.primary { background:#1d4ed8; color:#fff; border-color:#1d4ed8; }
table { border-collapse:collapse; width:100%; table-layout:fixed; margin-top:8px; }
th, td { border:1px solid var(--line); padding:8px 10px; vertical-align:top; font-size:17px; line-height:1.6; }
th { background:var(--head); position:sticky; top:49px; z-index:1; font-family:sans-serif; font-size:14px; }
td.num { width:52px; font-family:sans-serif; font-size:12px; color:var(--muted); }
td.en { font-size:14px; color:var(--muted); }
td[dir=rtl] { text-align:right; }
td.none { color:var(--muted); font-family:sans-serif; font-size:13px; }
tr.chunk td { background:var(--head); font-family:sans-serif; font-weight:bold; font-size:14px; }
.q { border-inline-start:3px solid var(--line); padding-inline-start:8px; }
mark { background:var(--mark); color:inherit; }
.card { border:1px solid var(--line); border-radius:6px; padding:6px 8px; margin-bottom:8px; }
.card.error { border-color:var(--err); background:var(--errbg); }
.card.style { background:var(--stybg); }
.card label { font-family:sans-serif; font-size:13px; display:block; direction:ltr; text-align:left; }
.badge { font-weight:bold; text-transform:uppercase; font-size:11px; }
.card.error .badge { color:var(--err); } .card.style .badge { color:var(--sty); }
.cur { text-decoration:line-through; color:var(--muted); font-size:15px; margin:4px 0; }
textarea { width:100%; box-sizing:border-box; font:inherit; font-size:16px; background:var(--bg); color:var(--fg); border:1px solid var(--line); border-radius:4px; }
.why { font-family:sans-serif; font-size:12px; color:var(--muted); text-align:left; }
.card.accepted { outline:2px solid #16a34a; }
td.notecell { width:17%; background:var(--head); }
textarea.note { width:100%; box-sizing:border-box; font:inherit; font-size:15px; background:var(--bg); color:var(--fg); border:1px solid var(--line); border-radius:4px; }
mark.flag { background:var(--flag); color:inherit; border-bottom:2px solid var(--flagline); cursor:pointer; }
td.flag-whole { box-shadow: inset 4px 0 0 var(--flagline); }
tr.has-flag td.num { background:var(--flag); font-weight:bold; }
.flags .chip { display:block; font-size:13px; margin-top:4px; padding:3px 6px; border-radius:4px; background:var(--flag); border-inline-start:3px solid var(--flagline); }
.flags .chip button { border:none; background:none; color:var(--muted); cursor:pointer; padding:0 4px; font-size:14px; float:inline-end; }
body.only-flagged tr.para:not(.has-flag) { display:none; }
.help { font-size:12px; color:var(--muted); }
.banner { font-family:sans-serif; font-size:14px; margin:8px 0; padding:8px 12px; border-radius:6px; background:#ecfdf5; color:#065f46; border:1px solid #a7f3d0; }
@media (prefers-color-scheme: dark) { .banner { background:#052e2b; color:#a7f3d0; border-color:#065f46; } }
td.srcchg { box-shadow: inset -4px 0 0 #0f766e; }
.srclabel { font-family:sans-serif; font-size:12px; color:#0f766e; font-weight:bold; text-align:left; margin-bottom:4px; }
details.prev { margin-top:6px; font-size:15px; color:var(--muted); }
details.prev summary { font-family:sans-serif; font-size:12px; cursor:pointer; text-align:left; }
td.ev { font-family:sans-serif; font-size:12px; }
td.ev .sc { color:var(--muted); margin-bottom:4px; }
td.ev .why { color:var(--err); font-weight:bold; text-align:left; }
td.ev .f { border-inline-start:3px solid var(--line); padding:2px 6px; margin-bottom:4px; }
td.ev .f.done { opacity:.5; text-decoration:line-through; border-style:dashed; }
td.ev .f.critical { border-color:var(--err); } td.ev .f.major { border-color:#d97706; }
td.ev .f .sp { font-family:'Times New Roman', serif; font-size:15px; }
tr.look td.num { color:var(--err); font-weight:bold; }
body.only-look tr.para:not(.look) { display:none; }
.opts details.opt { font-family:sans-serif; font-size:12px; margin-top:6px; padding:4px 6px; border:1px solid var(--line); border-radius:6px; background:var(--bg); }
.opts .opt.done { font-family:sans-serif; font-size:12px; color:var(--muted); margin-top:4px; }
.opts summary { cursor:pointer; }
.opts ol { margin:4px 0; padding-inline-start:0; list-style:none; }
.opts li { margin-bottom:5px; }
.opts .oh { font-family:'Times New Roman', serif; font-size:16px; }
.card.gone { opacity:.55; font-family:sans-serif; font-size:12px; background:none; border-style:dashed; }
</style></head><body>
<div class="bar"><strong>$TITLE$</strong><span>$COUNTS$</span><span id="tally"></span><span id="flagtally"></span>
<button id="flagbtn" title="Select text in the English or Hebrew column, then click (or press ⌥H)">Highlight selection</button><button id="onlyflag">Show only highlighted/noted</button>$EVBTN$<button id="allerr">Accept all errors</button><button id="none">Clear all</button>
<button class="primary" id="save">Save decisions</button><button id="copyjson" title="If Save does not download a file (e.g. inside an editor preview)">Show / copy decisions</button><span id="savestatus" class="help"></span></div>
<div id="jsonbox" hidden><span class="help">Select all and copy, then paste it to Claude or save it as a .json file.</span><textarea dir="ltr" rows="8"></textarea></div>
$BANNER$
<table><colgroup><col style="width:52px"><col><col><col><col>$EVCOL$<col style="width:17%"></colgroup>
<thead><tr><th>#</th><th>English</th><th>נוכחי</th><th>Fable 5.1</th><th>Opus 5.5</th>$EVTH$<th>Notes / for review</th></tr></thead>
<tbody>$ROWS$</tbody></table>
<script>
const KEY = "review:" + $KEY$, CHAPTER = $CHAPTER$;
const cards = [...document.querySelectorAll(".card:not(.gone)")];
function state() { return cards.map(c => ({ chunk: c.dataset.chunk, model: c.dataset.model, idx: +c.dataset.idx,
  accepted: c.querySelector(".acc").checked, text: c.querySelector("textarea").value })); }
function refresh() { cards.forEach(c => c.classList.toggle("accepted", c.querySelector(".acc").checked));
  const n = cards.filter(c => c.querySelector(".acc").checked).length; document.getElementById("tally").textContent = n + " accepted";
  try { localStorage.setItem(KEY, JSON.stringify(state())); } catch (e) {} }
try { const saved = JSON.parse(localStorage.getItem(KEY) || "[]"); saved.forEach(s => { const c = cards.find(c => c.dataset.chunk === s.chunk && c.dataset.model === s.model && +c.dataset.idx === s.idx);
  if (c) { c.querySelector(".acc").checked = s.accepted; c.querySelector("textarea").value = s.text; } }); } catch (e) {}
document.addEventListener("input", refresh);
document.getElementById("allerr").onclick = () => { cards.filter(c => c.classList.contains("error")).forEach(c => c.querySelector(".acc").checked = true); refresh(); };
document.getElementById("none").onclick = () => { cards.forEach(c => c.querySelector(".acc").checked = false); refresh(); };
document.getElementById("save").onclick = () => {
  let json;
  try { json = JSON.stringify({ chapter: CHAPTER, decisions: state(), notes: noteList(), flags: flags }, null, 1); }
  catch (e) { alert("Could not collect the decisions: " + e); return; }
  try {
    const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([json], { type: "application/json" }));
    a.download = "review-decisions-" + CHAPTER + ".json"; document.body.appendChild(a); a.click(); a.remove();
    document.getElementById("savestatus").textContent = "saved review-decisions-" + CHAPTER + ".json to Downloads · " + new Date().toLocaleTimeString();
  } catch (e) { showJson(json); }
};
document.getElementById("copyjson").onclick = () => { try { showJson(JSON.stringify({ chapter: CHAPTER, decisions: state(), notes: noteList(), flags: flags }, null, 1)); } catch (e) { alert(e); } };
function showJson(json) {
  const box = document.getElementById("jsonbox"); box.hidden = false; const ta = box.querySelector("textarea"); ta.value = json; ta.select();
  try { navigator.clipboard.writeText(json).then(() => box.querySelector("span").textContent = "Copied to the clipboard — paste it to Claude, or save it as a .json file."); } catch (e) {}
}
refresh();

/* ---- notes and highlights (stored separately from the accept/reject state) ---- */
const NKEY = KEY + ":notes", FKEY = KEY + ":flags";
function load(k, d) { try { return JSON.parse(localStorage.getItem(k)) || d; } catch (e) { return d; } }
function store(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} }
let notes = load(NKEY, {}), flags = load(FKEY, []);
if (typeof notes !== "object" || Array.isArray(notes)) notes = {};
if (!Array.isArray(flags)) flags = [];
const prow = [...document.querySelectorAll("tr.para")];
const rowKey = tr => tr.dataset.chunk + "-" + tr.dataset.para;
function noteList() { return Object.entries(notes).map(([k, text]) => { const [chunk, para] = k.split("-"); return { chunk, para: +para, text }; }); }
function unwrap(td) { td.querySelectorAll("mark.flag").forEach(m => m.replaceWith(...m.childNodes)); td.normalize(); td.classList.remove("flag-whole"); }
function wrapText(td, text, id) {
  const walker = document.createTreeWalker(td, NodeFilter.SHOW_TEXT);
  let node;
  while ((node = walker.nextNode())) {
    const i = node.nodeValue.indexOf(text);
    if (i < 0) continue;
    const r = document.createRange(); r.setStart(node, i); r.setEnd(node, i + text.length);
    const m = document.createElement("mark"); m.className = "flag"; m.dataset.flag = id; m.title = "Highlighted for review — click to remove";
    r.surroundContents(m); return true;
  }
  return false;
}
function paint(tr) {
  const en = tr.querySelector("td.en"), he = tr.querySelector("td.he");
  [en, he].forEach(td => td && unwrap(td));
  const mine = flags.filter(f => f.chunk === tr.dataset.chunk && f.para === +tr.dataset.para);
  mine.forEach(f => { const td = f.col === "he" ? he : en; if (td && !wrapText(td, f.text, f.id)) td.classList.add("flag-whole"); });
  const box = tr.querySelector(".flags"); box.innerHTML = "";
  mine.forEach(f => {
    const c = document.createElement("span"); c.className = "chip"; c.dir = "auto";
    c.textContent = (f.col === "he" ? "HE: " : "EN: ") + (f.text.length > 60 ? f.text.slice(0, 60) + "…" : f.text);
    const b = document.createElement("button"); b.textContent = "×"; b.title = "Remove highlight"; b.onclick = () => removeFlag(f.id);
    c.prepend(b); box.appendChild(c);
  });
  tr.classList.toggle("has-flag", mine.length > 0 || !!notes[rowKey(tr)]);
}
function removeFlag(id) { const f = flags.find(x => x.id === id); flags = flags.filter(x => x.id !== id); store(FKEY, flags);
  const tr = prow.find(t => f && t.dataset.chunk === f.chunk && +t.dataset.para === f.para); if (tr) paint(tr); tallyFlags(); }
function tallyFlags() { document.getElementById("flagtally").textContent =
  flags.length + " highlighted · " + Object.keys(notes).length + " notes"; }
function flagSelection() {
  const sel = window.getSelection();
  if (!sel.rangeCount || sel.isCollapsed) { alert("First select some text in the English or Hebrew column."); return; }
  const text = sel.toString().replace(/\\s+/g, " ").trim();
  const n = sel.anchorNode, el = n.nodeType === 1 ? n : n.parentElement, td = el && el.closest("td.en, td.he");
  if (!td || !text) { alert("Highlights work in the English and Hebrew columns."); return; }
  const tr = td.closest("tr.para");
  flags.push({ id: Date.now().toString(36) + Math.random().toString(36).slice(2, 6), chunk: tr.dataset.chunk,
               para: +tr.dataset.para, col: td.classList.contains("he") ? "he" : "en", text });
  store(FKEY, flags); sel.removeAllRanges(); paint(tr); tallyFlags();
  tr.querySelector("textarea.note").focus();
}
prow.forEach(tr => {
  const ta = tr.querySelector("textarea.note"), k = rowKey(tr);
  ta.value = notes[k] || "";
  ta.addEventListener("input", () => { if (ta.value.trim()) notes[k] = ta.value; else delete notes[k]; store(NKEY, notes); paint(tr); tallyFlags(); });
  paint(tr);
});
document.addEventListener("click", e => { const m = e.target.closest("mark.flag"); if (m && confirm("Remove this highlight?")) removeFlag(m.dataset.flag); });
const fb = document.getElementById("flagbtn");
fb.addEventListener("mousedown", e => e.preventDefault());
fb.onclick = flagSelection;
document.addEventListener("keydown", e => { if (e.altKey && e.code === "KeyH") { e.preventDefault(); flagSelection(); } });
document.getElementById("onlyflag").onclick = e => { const on = document.body.classList.toggle("only-flagged");
  e.target.textContent = on ? "Show all rows" : "Show only highlighted/noted"; };
const lb = document.getElementById("onlylook");
if (lb) { const label = lb.textContent; lb.onclick = () => { const on = document.body.classList.toggle("only-look");
  lb.textContent = on ? "Show all rows" : label; }; }
tallyFlags();
</script></body></html>"""

main()
