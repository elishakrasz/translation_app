"""Step 2b, glossary: merge independent extractions, build the review page, apply the translator's decisions.

Two (or more) extractors propose terms in work/glossary/proposed_*.json. `merge` joins them by surface form, marks
where they agree, and adds the rendering from any reference glossary (another book's) for the same term. `page`
writes a review page; the translator decides each term and downloads the decisions. `apply` writes
terms/glossary.json in translate-book's v2 format, which its print-terms-for-chunk reads.
"""

import html
import json
import re
from pathlib import Path

from . import records

CATEGORIES = ("person", "place", "work", "concept")


def work_dir(project):
    return project.work("glossary")


def _surfaces(t):
    return [t["source"], *(t.get("aliases") or [])]


def _key(s):
    return re.sub(r"\s+", " ", s.strip())


def _find(index, t):
    """The merged entry a proposed term belongs to: an exact surface match, or a match differing only in case within
    the same category (Lord / LORD), never across categories (Exodus the book, exodus the event)."""
    for s in _surfaces(t):
        if _key(s) in index:
            return index[_key(s)]
    cat = t.get("category", "concept")
    for s in _surfaces(t):
        for entry in index.get(("ci", _key(s).casefold()), []):
            if cat in entry["category"].values():
                return entry
    return None


def _register(index, s, entry):
    index[_key(s)] = entry
    bucket = index.setdefault(("ci", _key(s).casefold()), [])
    if entry not in bucket:
        bucket.append(entry)


def reference_terms(project):
    """{surface key: (target, which glossary)} from the reference glossaries named in project.yaml."""
    out = {}
    for ref in project.cfg.get("reference_glossaries") or []:
        p = Path(ref).expanduser()
        if not p.exists():
            continue
        data = json.loads(p.read_text(encoding="utf-8"))
        for t in data.get("terms", []):
            for s in _surfaces(t):
                out.setdefault(_key(s), (t.get("target", ""), p.parent.parent.name or p.name))
    return out


def merge(project):
    """Join the extractions. Returns the merged entries, also written to work/glossary/merged.json."""
    files = sorted(work_dir(project).glob("proposed_*.json"))
    if not files:
        raise FileNotFoundError("no work/glossary/proposed_*.json yet")
    labels = [f.stem.removeprefix("proposed_") for f in files]
    refs = reference_terms(project)
    merged, index = [], {}
    for label, f in zip(labels, files):
        for t in json.loads(f.read_text(encoding="utf-8")).get("terms", []):
            hit = _find(index, t)
            if hit is None:
                hit = {"source": t["source"], "aliases": [], "category": {}, "targets": {}, "confidence": {},
                       "count": 0, "units": [], "notes": {}, "gender": t.get("gender", "unknown")}
                merged.append(hit)
            for s in _surfaces(t):
                if s != hit["source"] and s not in hit["aliases"]:
                    hit["aliases"].append(s)
                _register(index, s, hit)
            hit["category"][label] = t.get("category", "concept")
            hit["targets"][label] = t.get("target", "")
            hit["confidence"][label] = t.get("confidence", "medium")
            hit["count"] = max(hit["count"], int(t.get("count") or 0))
            hit["units"] = sorted(set(hit["units"]) | set(t.get("units") or []))
            if t.get("notes"):
                hit["notes"][label] = t["notes"]
    for m in merged:
        targets = {v.strip() for v in m["targets"].values() if v.strip()}
        m["found_by"] = sorted(m["targets"])
        m["agree"] = len(m["targets"]) == len(labels) and len(targets) == 1
        m["category_final"] = max(set(m["category"].values()), key=list(m["category"].values()).count)
        ref = next((refs[_key(s)] for s in _surfaces(m) if _key(s) in refs), None)
        m["reference"] = {"target": ref[0], "from": ref[1]} if ref else None
        m["proposed"] = (next(iter(targets)) if len(targets) == 1 else
                         m["targets"].get(labels[0]) or next(iter(m["targets"].values()), ""))
    merged.sort(key=_order)
    out = work_dir(project) / "merged.json"
    out.write_text(json.dumps({"extractors": labels, "terms": merged}, ensure_ascii=False, indent=1), encoding="utf-8")
    return labels, merged


def _order(m):
    """Disagreements first, then terms only one extractor found, then low confidence; within each, by frequency."""
    low = any(c == "low" for c in m["confidence"].values())
    return (m["agree"], len(m["found_by"]) == 1, not low, -m["count"], m["source"].casefold())


def summary(labels, merged):
    agree = sum(m["agree"] for m in merged)
    single = sum(len(m["found_by"]) == 1 for m in merged)
    differ = len(merged) - agree - single
    by_cat = {c: sum(m["category_final"] == c for m in merged) for c in CATEGORIES}
    with_ref = sum(bool(m["reference"]) for m in merged)
    return {"terms": len(merged), "agree": agree, "differ": differ, "only_one": single, "by_category": by_cat,
            "in_reference": with_ref}


# ---------------------------------------------------------------------------
# Review page
# ---------------------------------------------------------------------------

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Glossary review</title>
<style>
:root { --bg:#fbfaf7; --fg:#1d1d1b; --muted:#6b6a65; --line:#e3e0d8; --agree:#e8f3ea; --differ:#fdf0e1; --one:#eef1f8; --accent:#2c5d8f; }
@media (prefers-color-scheme: dark) { :root { --bg:#1b1b1a; --fg:#ecebe6; --muted:#a3a19a; --line:#3a3936; --agree:#22332a; --differ:#3a2f22; --one:#262c38; --accent:#8fb6e0; } }
body { background:var(--bg); color:var(--fg); font:15px/1.45 -apple-system, "Segoe UI", Arial, sans-serif; margin:0 16px 80px; }
header { position:sticky; top:0; background:var(--bg); padding:12px 0 8px; border-bottom:1px solid var(--line); z-index:2; }
h1 { font-size:20px; margin:0 0 4px; } .muted { color:var(--muted); font-size:13px; }
.bar { display:flex; gap:8px; flex-wrap:wrap; align-items:center; margin-top:8px; }
button, select, input[type=search] { font:inherit; padding:5px 10px; border:1px solid var(--line); border-radius:6px; background:transparent; color:var(--fg); }
button.primary { background:var(--accent); color:#fff; border-color:var(--accent); }
table { width:100%; border-collapse:collapse; margin-top:10px; }
th, td { border-bottom:1px solid var(--line); padding:6px 8px; vertical-align:top; text-align:left; }
th { font-size:12px; text-transform:uppercase; letter-spacing:.04em; color:var(--muted); }
tr.agree { background:var(--agree); } tr.differ { background:var(--differ); } tr.one { background:var(--one); }
td.he, input.he { direction:rtl; text-align:right; font-family:"SF Hebrew","Arial Hebrew",Arial,sans-serif; font-size:16px; }
input.he, input.note { width:100%; box-sizing:border-box; padding:4px 6px; border:1px solid var(--line); border-radius:4px; background:transparent; color:var(--fg); }
.src { font-weight:600; } .alias { color:var(--muted); font-size:12px; } .notes { color:var(--muted); font-size:12px; max-width:28em; }
.pick { cursor:pointer; text-decoration:underline dotted; } .done td:first-child { box-shadow: inset 4px 0 var(--accent); }
@media (max-width: 760px) { .hide-sm { display:none; } }
</style></head><body>
<header>
<h1>Glossary review — {{TITLE}}</h1>
<div class="muted">{{SUMMARY}} · Click a proposed Hebrew form to use it. Decisions are kept in this browser until you download them.</div>
<div class="bar">
<input type="search" id="q" placeholder="Filter…">
<select id="f"><option value="">All</option><option value="differ">Extractors differ</option><option value="one">Found once</option><option value="agree">Agree</option><option value="open">Not decided yet</option></select>
<button id="acceptAgreed">Accept all agreed</button>
<span class="muted" id="count"></span>
<span style="flex:1"></span>
<button id="copy">Copy decisions</button><button class="primary" id="dl">Download decisions</button>
</div></header>
<table><thead><tr><th>English</th><th class="hide-sm">Category</th><th class="hide-sm">×</th>{{EXTRACTOR_TH}}<th>Reference</th><th style="min-width:12em">Hebrew (final)</th><th>Decision</th><th class="hide-sm">Note</th></tr></thead>
<tbody id="rows"></tbody></table>
<script>
const TERMS = {{DATA}};
const EXTRACTORS = {{EXTRACTORS}};
const KEY = "glossary-review:" + {{PROJECT_KEY}};
let state = {};
try { state = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) { state = {}; }
const save = () => { try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) {} };
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
function cls(t) { return t.agree ? "agree" : (t.found_by.length > 1 ? "differ" : "one"); }
function render() {
  const q = document.getElementById("q").value.toLowerCase(), f = document.getElementById("f").value;
  let shown = 0, done = 0;
  const rows = TERMS.map((t, i) => {
    const s = state[t.source] || {};
    if (s.decision) done++;
    const hay = (t.source + " " + t.aliases.join(" ") + " " + Object.values(t.targets).join(" ")).toLowerCase();
    if (q && !hay.includes(q)) return "";
    if (f === "open" ? s.decision : (f && cls(t) !== f)) return "";
    shown++;
    const ex = EXTRACTORS.map(e => `<td class="he"><span class="pick" data-i="${i}" data-v="${esc(t.targets[e] || "")}">${esc(t.targets[e] || "—")}</span>${t.confidence[e] === "low" ? ' <span class="muted">(low)</span>' : ""}</td>`).join("");
    const ref = t.reference ? `<span class="pick" data-i="${i}" data-v="${esc(t.reference.target)}">${esc(t.reference.target)}</span><div class="muted">${esc(t.reference.from)}</div>` : "";
    const notes = Object.entries(t.notes).map(([k, v]) => `<b>${esc(k)}:</b> ${esc(v)}`).join("<br>");
    return `<tr class="${cls(t)} ${s.decision ? "done" : ""}"><td><div class="src">${esc(t.source)}</div>` +
      (t.aliases.length ? `<div class="alias">${esc(t.aliases.join(" · "))}</div>` : "") +
      (notes ? `<div class="notes">${notes}</div>` : "") + `</td><td class="hide-sm">${esc(t.category_final)}</td><td class="hide-sm">${t.count || ""}</td>${ex}` +
      `<td class="he">${ref}</td><td><input class="he" data-i="${i}" value="${esc(s.target ?? t.proposed)}"></td>` +
      `<td><select data-i="${i}"><option value=""></option>${["accept","edit","reject"].map(d => `<option ${s.decision === d ? "selected" : ""}>${d}</option>`).join("")}</select></td>` +
      `<td class="hide-sm"><input class="note" data-i="${i}" value="${esc(s.note || "")}"></td></tr>`;
  }).join("");
  document.getElementById("rows").innerHTML = rows;
  document.getElementById("count").textContent = `${done} of ${TERMS.length} decided · ${shown} shown`;
}
function set(i, patch) { const t = TERMS[i]; state[t.source] = Object.assign({ target: t.proposed }, state[t.source] || {}, patch); save(); }
document.addEventListener("click", e => {
  const p = e.target.closest(".pick"); if (!p || !p.dataset.v) return;
  set(+p.dataset.i, { target: p.dataset.v, decision: (state[TERMS[+p.dataset.i].source] || {}).decision || "accept" }); render();
});
document.addEventListener("change", e => {
  const i = e.target.dataset.i; if (i === undefined) return;
  if (e.target.tagName === "SELECT") set(+i, { decision: e.target.value });
  else if (e.target.classList.contains("he")) set(+i, { target: e.target.value.trim(), decision: (state[TERMS[+i].source] || {}).decision || "edit" });
  else set(+i, { note: e.target.value });
  render();
});
document.getElementById("q").oninput = render; document.getElementById("f").onchange = render;
document.getElementById("acceptAgreed").onclick = () => { TERMS.forEach((t, i) => { if (t.agree && !(state[t.source] || {}).decision) set(i, { decision: "accept" }); }); render(); };
function decisions() { return JSON.stringify({ project: {{PROJECT_KEY}}, decided: new Date().toISOString(), decisions: state }, null, 1); }
document.getElementById("dl").onclick = () => { const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([decisions()], { type: "application/json" })); a.download = "glossary-decisions.json"; a.click(); };
document.getElementById("copy").onclick = async () => { try { await navigator.clipboard.writeText(decisions()); alert("Copied."); } catch (e) { prompt("Copy this:", decisions()); } };
render();
</script></body></html>
"""


def page(project):
    data = json.loads((work_dir(project) / "merged.json").read_text(encoding="utf-8"))
    labels, merged = data["extractors"], data["terms"]
    s = summary(labels, merged)
    text = (PAGE.replace("{{TITLE}}", html.escape(project.title))
            .replace("{{SUMMARY}}", html.escape(f"{s['terms']} terms: {s['agree']} agree, {s['differ']} differ, "
                                                f"{s['only_one']} found by one extractor; {s['in_reference']} also in a reference glossary"))
            .replace("{{EXTRACTOR_TH}}", "".join(f"<th>Extractor {html.escape(l.upper())}</th>" for l in labels))
            .replace("{{EXTRACTORS}}", json.dumps(labels))
            .replace("{{PROJECT_KEY}}", json.dumps(project.root.name))
            .replace("{{DATA}}", json.dumps(merged, ensure_ascii=False).replace("</", "<\\/")))
    out = project.root / "review" / "glossary" / "glossary-review.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    return out, s


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------

def apply(project, decisions_file, write=False):
    """Terms accepted or edited become terms/glossary.json (translate-book v2). Returns (terms, problems)."""
    merged = {m["source"]: m for m in json.loads((work_dir(project) / "merged.json").read_text(encoding="utf-8"))["terms"]}
    dec = json.loads(Path(decisions_file).expanduser().read_text(encoding="utf-8"))["decisions"]
    terms, problems, seen = [], [], {}
    for source, d in dec.items():
        m = merged.get(source)
        if not m:
            problems.append(f"{source!r} is not in merged.json")
            continue
        if d.get("decision") not in ("accept", "edit"):
            continue
        target = (d.get("target") or m["proposed"]).strip()
        if not target:
            problems.append(f"{source!r} accepted with no Hebrew form")
            continue
        t = {"id": source, "source": source, "target": target, "category": m["category_final"],
             "aliases": [a for a in m["aliases"] if a != source], "gender": m.get("gender", "unknown"),
             "confidence": "high", "frequency": m["count"], "evidence_refs": m["units"],
             "notes": " · ".join(filter(None, [d.get("note", ""), *m["notes"].values()]))[:500]}
        terms.append(t)
    resolved = _resolve_aliases(terms)
    for t in terms:
        for s in _surfaces(t):
            if _key(s) in seen:
                problems.append(f"{s!r} appears in two terms ({seen[_key(s)]!r} and {t['source']!r}); merge them on the page")
            seen[_key(s)] = t["source"]
    undecided = [s for s in merged if s not in dec or not dec[s].get("decision")]
    if write and not problems:
        out = project.root / "terms" / "glossary.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"version": 2, "terms": sorted(terms, key=lambda t: t["source"].casefold())},
                                  ensure_ascii=False, indent=1), encoding="utf-8")
        link_into_units(project)
        records.append(project, "decisions", [{
            "step": "glossary", "unit": "all", "question": "glossary review",
            "answer": f"{len(terms)} terms accepted or edited, {sum(1 for d in dec.values() if d.get('decision') == 'reject')} rejected, "
                      f"{len(undecided)} not decided", "note": str(Path(decisions_file).name)}], by="translator glossary apply")
    return terms, problems, undecided, resolved


def link_into_units(project):
    """translate-book reads <unit folder>/glossary.json; each unit gets a link to the one book-wide terms/glossary.json."""
    made = []
    for u in project.units:
        d = project.unit_dir(u)
        if not d.exists():
            continue
        link = d / "glossary.json"
        if link.is_symlink() or not link.exists():
            if link.is_symlink():
                link.unlink()
            link.symlink_to(Path("..") / ".." / "terms" / "glossary.json")
            made.append(u["id"])
    return made


def _resolve_aliases(terms):
    """A form that is one term's source and another's alias belongs to the term it names: drop the alias.
    ('Israelites' has its own entry, so it is no longer an alias of 'children of Israel'.) Returns what was dropped."""
    sources = {_key(t["source"]) for t in terms}
    dropped = []
    for t in terms:
        keep = [a for a in t["aliases"] if _key(a) not in sources]
        dropped += [(a, t["source"]) for a in t["aliases"] if _key(a) in sources]
        t["aliases"] = keep
    # An alias two terms share goes to the term whose source it contains, the longest one ('spiritual practices'
    # to 'spiritual practice', not to 'practice'); it stays shared only if neither source is in it.
    owners = {}
    for t in terms:
        for a in t["aliases"]:
            owners.setdefault(_key(a), []).append(t)
    for alias, ts in owners.items():
        if len(ts) < 2:
            continue
        inside = [t for t in ts if _key(t["source"]).casefold() in alias.casefold()]
        if not inside:
            continue
        owner = max(inside, key=lambda t: len(t["source"]))
        for t in ts:
            if t is not owner:
                t["aliases"] = [a for a in t["aliases"] if _key(a) != alias]
                dropped.append((alias, t["source"]))
    return dropped
