"""Step 8, review: two reviewers read the translation against the English and report findings; the translator decides.

`pairs` writes the unit as numbered English/Hebrew pairs by block ID, locked quotations marked. Each reviewer (a model
named in project.yaml `reviewers`) writes findings to work/review/<unit>-<reviewer>.json, never a rewrite. `page`
validates the findings (every Hebrew span must be an exact substring of its block), pairs up the ones both reviewers
flagged, and builds the review page. `apply` makes only the accepted changes, refuses any that would break a locked
quotation, and records every finding with its decision in records/findings.jsonl (the acceptance statistics).
"""

import html
import json
import re
from pathlib import Path

from . import records, sources

BLOCK_RE = re.compile(r"(.*?)\s*<!--id:([^>]*)-->", re.S)
CATEGORIES = ["meaning-shift", "omission", "addition", "attribution", "modality", "number-negation", "register",
              "calque", "gloss", "terminology", "style-rule", "typo", "other"]


def _blocks(path):
    return [(m.group(2), m.group(1).strip()) for m in BLOCK_RE.finditer(path.read_text(encoding="utf-8"))]


def gather(project, unit):
    udir = project.unit_dir(unit)
    en = {b: t for p in sorted(udir.glob("chunk[0-9]*.md")) for b, t in _blocks(p)}
    he, where = {}, {}
    for p in sorted(udir.glob("output_chunk[0-9]*.md")):
        for b, t in _blocks(p):
            he[b], where[b] = t, p.name
    locked = {}
    for q in records.load(project, "quotations"):
        if q.get("unit") == unit["id"]:
            locked.setdefault(q["block"], []).append(q)
    return [{"id": b, "chunk": where.get(b), "english": en[b], "hebrew": he.get(b, ""),
             "locked": [{"qid": q["qid"], "text": q["text"], "locator": q["locator"]} for q in locked.get(b, [])]}
            for b in en]


def write_pairs(project, unit, step="review"):
    items = gather(project, unit)
    d = project.work(step)
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{unit['id']}-pairs.json").write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    lines = [f"# {unit['id']} — {unit.get('title', '')}: English / Hebrew pairs for review", ""]
    for it in items:
        lines += [f"## {it['id']}", "", "EN: " + it["english"], "", "HE: " + it["hebrew"]]
        for q in it["locked"]:
            lines.append(f"LOCKED ({q['qid']}, {q['locator']}) — do not review these words: {q['text']}")
        lines.append("")
    md = d / f"{unit['id']}-pairs.md"
    md.write_text("\n".join(lines), encoding="utf-8")
    return items, md


# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------

def load_findings(project, unit, step="review"):
    """{reviewer: [finding]} with each finding validated: an exact span in its block, not inside a locked quotation."""
    blocks = {it["id"]: it for it in gather(project, unit)}
    out, problems = {}, []
    for f in sorted(project.work(step).glob(f"{unit['id']}-findings-*.json")):
        reviewer = f.stem.split("-findings-", 1)[1]
        rows = []
        for i, x in enumerate(json.loads(f.read_text(encoding="utf-8")).get("findings", [])):
            b = blocks.get(x.get("block"))
            span = x.get("he_span", "")
            if not b or not span or b["hebrew"].count(span) < 1:
                problems.append(f"{reviewer} #{i + 1} ({x.get('block')}): the Hebrew span isn't in the block — dropped")
                continue
            if any(sources.norm(span) and sources.norm(span) in sources.norm(q["text"]) for q in b["locked"]):
                problems.append(f"{reviewer} #{i + 1} ({x['block']}): inside a locked quotation — dropped")
                continue
            rows.append({**x, "reviewer": reviewer, "key": f"{reviewer}-{i + 1}"})
        out[reviewer] = rows
    # agreement: two reviewers flag overlapping spans in the same block
    names = list(out)
    for a in range(len(names)):
        for b in range(a + 1, len(names)):
            for x in out[names[a]]:
                for y in out[names[b]]:
                    if x["block"] == y["block"] and (x["he_span"] in y["he_span"] or y["he_span"] in x["he_span"]):
                        x.setdefault("agreed_with", []).append(y["key"])
                        y.setdefault("agreed_with", []).append(x["key"])
    return out, problems


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{STEPTITLE}}</title>
<style>
:root { --bg:#fbfaf7; --fg:#1d1d1b; --muted:#6b6a65; --line:#e3e0d8; --accent:#2c5d8f; --both:#fdf0e1; --done:#e8f3ea; }
@media (prefers-color-scheme: dark) { :root { --bg:#1b1b1a; --fg:#ecebe6; --muted:#a3a19a; --line:#3a3936; --accent:#8fb6e0; --both:#3a2f22; --done:#22332a; } }
body { background:var(--bg); color:var(--fg); font:15px/1.5 -apple-system, "Segoe UI", Arial, sans-serif; margin:0 16px 80px; }
header { position:sticky; top:0; background:var(--bg); padding:12px 0 8px; border-bottom:1px solid var(--line); z-index:2; }
h1 { font-size:20px; margin:0 0 4px; } .muted { color:var(--muted); font-size:13px; }
.bar { display:flex; gap:8px; flex-wrap:wrap; align-items:center; margin-top:8px; }
button, select { font:inherit; padding:5px 10px; border:1px solid var(--line); border-radius:6px; background:transparent; color:var(--fg); }
button.primary { background:var(--accent); color:#fff; border-color:var(--accent); }
.block { border-bottom:1px solid var(--line); padding:12px 0; }
.texts { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
.he { direction:rtl; text-align:right; font-family:"SF Hebrew","Arial Hebrew",Arial,sans-serif; font-size:16px; }
mark { background:#ffe58a; color:inherit; }
.finding { margin:8px 0 0; padding:8px; border:1px solid var(--line); border-radius:6px; display:grid; grid-template-columns: 1fr 1fr auto; gap:8px; align-items:start; }
.finding.both { background:var(--both); } .finding.done { background:var(--done); }
.meta { font-size:12px; color:var(--muted); } textarea { width:100%; box-sizing:border-box; min-height:3em; font:inherit; padding:4px; border:1px solid var(--line); border-radius:4px; background:transparent; color:var(--fg); }
@media (max-width: 900px) { .texts, .finding { grid-template-columns:1fr; } }
</style></head><body>
<header><h1>{{STEPTITLE}} — {{TITLE}}, {{UNIT}}</h1>
<div class="muted">{{SUMMARY}} Findings flagged by both reviewers are shaded and come first. Edit the proposed Hebrew if needed, then decide.</div>
<div class="bar"><select id="f"><option value="">All</option><option value="both">Both reviewers</option><option value="open">Not decided yet</option></select>
<span class="muted" id="count"></span><span style="flex:1"></span>
<button id="copy">Copy decisions</button><button class="primary" id="dl">Download decisions</button></div></header>
<div id="rows"></div>
<script>
const BLOCKS = {{DATA}};
const KEY = "review:" + {{KEYNAME}};
let state = {}; try { state = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) {}
const save = () => { try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) {} };
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
function marked(he, spans) { let out = esc(he); spans.forEach(s => { const e = esc(s); if (e) out = out.split(e).join("<mark>" + e + "</mark>"); }); return out; }
function render() {
  const f = document.getElementById("f").value; let done = 0, total = 0;
  document.getElementById("rows").innerHTML = BLOCKS.map(b => {
    const fs = b.findings.filter(x => (f !== "both" || (x.agreed_with || []).length) && (f !== "open" || !(state[x.key] || {}).decision));
    b.findings.forEach(x => { total++; if ((state[x.key] || {}).decision) done++; });
    if (!fs.length) return "";
    return `<div class="block"><div class="meta">${esc(b.id)}</div><div class="texts"><div>${esc(b.english)}</div><div class="he">${marked(b.hebrew, b.findings.map(x => x.he_span))}</div></div>` +
      fs.map(x => { const s = state[x.key] || {}; return `<div class="finding ${(x.agreed_with || []).length ? "both" : ""} ${s.decision ? "done" : ""}">
        <div><div class="meta">${esc(x.reviewer)} · ${esc(x.category)} · ${esc(x.severity)}${x.checklist_rule ? " · " + esc(x.checklist_rule) : ""}${(x.agreed_with || []).length ? " · both" : ""}</div>${esc(x.reason)}</div>
        <div class="he"><div class="meta">${esc(x.he_span)} →</div><textarea class="he" data-k="${esc(x.key)}">${esc(s.text ?? x.proposed)}</textarea></div>
        <select data-k="${esc(x.key)}"><option value=""></option>${["accept","edit","reject"].map(d => `<option ${s.decision===d?"selected":""}>${d}</option>`).join("")}</select></div>`; }).join("") + "</div>";
  }).join("");
  document.getElementById("count").textContent = `${done} of ${total} findings decided`;
}
document.addEventListener("change", e => { const k = e.target.dataset.k; if (!k) return;
  state[k] = Object.assign({}, state[k] || {}, e.target.tagName === "SELECT" ? { decision: e.target.value } : { text: e.target.value, decision: (state[k] || {}).decision || "edit" });
  save(); render(); });
document.getElementById("f").onchange = render;
function decisions() { return JSON.stringify({ unit: {{UNITID}}, decided: new Date().toISOString(), decisions: state }, null, 1); }
document.getElementById("dl").onclick = () => { const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([decisions()], {type:"application/json"})); a.download = {{FILENAME}}; a.click(); };
document.getElementById("copy").onclick = async () => { try { await navigator.clipboard.writeText(decisions()); alert("Copied."); } catch (e) { prompt("Copy this:", decisions()); } };
render();
</script></body></html>
"""


def page(project, unit, step="review"):
    findings, problems = load_findings(project, unit, step)
    by_block = {}
    for rows in findings.values():
        for x in rows:
            by_block.setdefault(x["block"], []).append(x)
    data = []
    for it in gather(project, unit):
        fs = sorted(by_block.get(it["id"], []), key=lambda x: (not x.get("agreed_with"), x["reviewer"]))
        if fs:
            data.append({"id": it["id"], "english": it["english"], "hebrew": it["hebrew"], "findings": fs})
    data.sort(key=lambda b: (not any(x.get("agreed_with") for x in b["findings"]),))
    total = sum(len(v) for v in findings.values())
    both = sum(1 for v in findings.values() for x in v if x.get("agreed_with"))
    summary = (f"{total} findings from {', '.join(f'{k} ({len(v)})' for k, v in findings.items())}; "
               f"{both} flagged by both; {len(problems)} dropped (span not found or inside a locked quotation).")
    text = (PAGE.replace("{{STEPTITLE}}", "Review round" if step == "review" else "Style passes")
            .replace("{{TITLE}}", html.escape(project.title)).replace("{{UNIT}}", html.escape(unit["id"]))
            .replace("{{SUMMARY}}", html.escape(summary)).replace("{{KEYNAME}}", json.dumps(f"{project.root.name}:{step}:{unit['id']}"))
            .replace("{{UNITID}}", json.dumps(unit["id"])).replace("{{FILENAME}}", json.dumps(f"{step}-decisions-{unit['id']}.json"))
            .replace("{{DATA}}", json.dumps(data, ensure_ascii=False).replace("</", "<\\/")))
    out = project.root / "review" / step / unit["id"] / f"{step}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    return out, summary, problems


def apply(project, unit, decisions_file, write=False, step="review"):
    """Make the accepted changes. Returns (applied, problems). Nothing is written if there are problems."""
    dec = json.loads(Path(decisions_file).expanduser().read_text(encoding="utf-8"))["decisions"]
    findings, _ = load_findings(project, unit, step)
    blocks = {it["id"]: it for it in gather(project, unit)}
    udir = project.unit_dir(unit)
    files, applied, problems, edits, frows = {}, [], [], [], []
    done_spans = set()
    for rows in findings.values():
        for x in rows:
            d = dec.get(x["key"], {})
            frows.append({"step": step, "unit": unit["id"], "block": x["block"], "reviewer": x["reviewer"],
                          "category": x.get("category"), "severity": x.get("severity"), "he_span": x["he_span"],
                          "proposed": x.get("proposed", ""), "reason": x.get("reason", ""),
                          "checklist_rule": x.get("checklist_rule"), "agreed_with": x.get("agreed_with", []),
                          "decision": d.get("decision") or "undecided", "final": d.get("text")})
            if d.get("decision") not in ("accept", "edit"):
                continue
            new = d.get("text") if d.get("text") is not None else x.get("proposed", "")
            if (x["block"], x["he_span"]) in done_spans:
                continue                                    # the same span accepted from both reviewers: once
            b = blocks[x["block"]]
            f = udir / b["chunk"]
            body = files.get(f) or f.read_text(encoding="utf-8")
            current = files.get(("block", x["block"]), b["hebrew"])
            if current.count(x["he_span"]) != 1:
                problems.append(f"{x['key']} ({x['block']}): the span isn't exactly once in the block now")
                continue
            updated = current.replace(x["he_span"], new, 1)
            if (lost := [q["qid"] for q in b["locked"] if sources.verify(q["text"], [updated])]):
                problems.append(f"{x['key']} ({x['block']}): would change locked quotation(s) {', '.join(lost)}")
                continue
            files[f] = body.replace(current, updated, 1)
            files[("block", x["block"])] = updated
            done_spans.add((x["block"], x["he_span"]))
            applied.append(x["key"])
            edits.append({"command": f"translator {step} apply", "unit": unit["id"], "block": x["block"],
                          "before": x["he_span"], "after": new, "reason": f"{x['reviewer']}: {x.get('reason', '')}"[:300]})
    if write and not problems:
        for f, body in files.items():
            if not isinstance(f, tuple):
                f.write_text(body, encoding="utf-8")
        records.append(project, "findings", frows, by=f"translator {step} apply")
        if edits:
            records.append(project, "edits", edits, by=f"translator {step} apply")
    return applied, problems


def stats(project):
    """{reviewer: {category: {decision: n}}} across the book."""
    out = {}
    for f in records.load(project, "findings"):
        c = out.setdefault(f["reviewer"], {}).setdefault(f.get("category") or "?", {})
        c[f["decision"]] = c.get(f["decision"], 0) + 1
    return out
