"""Step 6 — report: agreement, human-look, CSV, HTML, summary, and findings for the review page.

    python -m eval.report --chapter ch02

Writes eval/report/<chapter>.csv, <chapter>.html, <chapter>-summary.md and
eval/findings/<chapter>.json (read by tools/build_review.py).
"""
import argparse
import csv
import html
import json
import re
from collections import Counter

from .config import CHAPTERS, EVAL

MAIN = ("gemini", "openai")


def _norm(s):
    return re.sub(r"\s+", " ", s or "").strip()


def interval(he, span):
    i = _norm(he).find(_norm(span))
    return (i, i + len(_norm(span))) if i >= 0 and span else None


def overlaps(a, b):
    """Spans overlap by at least 50% of the shorter one."""
    if not a or not b:
        return False
    inter = min(a[1], b[1]) - max(a[0], b[0])
    return inter > 0 and inter >= 0.5 * min(a[1] - a[0], b[1] - b[0])


def agreement(he, fa, fb):
    """Jaccard over findings: shared = matched pairs of overlapping he_spans."""
    A = [interval(he, f["he_span"]) for f in fa]
    B = [interval(he, f["he_span"]) for f in fb]
    used, shared = set(), 0
    for a in A:
        for j, b in enumerate(B):
            if j not in used and overlaps(a, b):
                used.add(j)
                shared += 1
                break
    union = len(A) + len(B) - shared
    return 1.0 if union == 0 else shared / union


def human_look(he, res):
    """res: {provider: response dict}. Returns the reasons a human should look (empty = no)."""
    why = []
    for p in MAIN:
        if p in res and any(f["severity"] == "critical" for f in res[p]["findings"]):
            why.append(f"{p}: critical")
    if all(p in res for p in MAIN):
        fa, fb = res["gemini"]["overall"].get("fidelity"), res["openai"]["overall"].get("fidelity")
        if fa is not None and fb is not None and abs(fa - fb) >= 2:
            why.append(f"fidelity {fa} vs {fb}")
        for p, q in (MAIN, MAIN[::-1]):
            for f in res[p]["findings"]:
                if f["severity"] == "major" and not any(overlaps(interval(he, f["he_span"]), interval(he, g["he_span"]))
                                                        for g in res[q]["findings"]):
                    why.append(f"{p}: major not seen by {q}")
                    break
    if "dicta" in res and any("חמור" in f.get("severity", "") for f in res["dicta"]["findings"]):
        why.append("dicta: חמורה")
    return why


def load(chapter):
    recs = {}
    for line in (EVAL / "aligned" / f"{chapter}.jsonl").read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        recs[r["id"]] = r
    results, models = {}, {}
    d = EVAL / "results" / chapter
    for f in sorted(d.glob("*.json")) if d.exists() else []:
        if f.name.startswith("_"):
            continue
        rid, prov = f.stem.rsplit(".", 1)
        out = json.loads(f.read_text(encoding="utf-8"))
        results.setdefault(rid, {})[prov] = out["response"]
        models[prov] = out.get("model")
    meta = {}
    if (d / "_run.json").exists():
        meta = json.loads((d / "_run.json").read_text(encoding="utf-8"))
    return recs, results, models, meta


def build_rows(recs, results):
    rows = []
    for rid, res in results.items():
        rec = recs.get(rid)
        if not rec:
            continue
        allf = [f for p in MAIN if p in res for f in res[p]["findings"]]
        rows.append({
            "rec": rec, "res": res,
            "critical": sum(f["severity"] == "critical" for f in allf),
            "major": sum(f["severity"] == "major" for f in allf),
            "agreement": agreement(rec["he"], res["gemini"]["findings"], res["openai"]["findings"]) if all(p in res for p in MAIN) else None,
            "look": human_look(rec["he"], res),
        })
    rows.sort(key=lambda r: (not r["look"], -r["critical"], -r["major"], r["rec"]["chunk"], r["rec"]["para"]))
    return rows


def scores(res, p):
    if p not in res:
        return ""
    o = res[p]["overall"]
    return "/".join("?" if o.get(k) is None else str(o[k]) for k in ("fidelity", "register", "terminology"))


def mark_spans(he, findings):
    out = html.escape(he)
    for f in findings:
        e = html.escape(f["he_span"])
        if e and e in out:
            out = out.replace(e, f'<mark class="{f.get("severity", "")}">{e}</mark>', 1)
    return out


def write_csv(chapter, rows):
    with open(EVAL / "report" / f"{chapter}.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "he (first 80)", "gemini f/r/t", "openai f/r/t", "dicta naturalness", "#critical", "#major", "agreement", "human-look", "why"])
        for r in rows:
            res = r["res"]
            w.writerow([r["rec"]["id"], r["rec"]["he"][:80], scores(res, "gemini"), scores(res, "openai"),
                        res.get("dicta", {}).get("naturalness", ""), r["critical"], r["major"],
                        "" if r["agreement"] is None else f'{r["agreement"]:.2f}', "yes" if r["look"] else "", "; ".join(r["look"])])


def write_html(chapter, rows, models, meta, recs):
    sev = {p: Counter(f["severity"] for r in rows if p in r["res"] for f in r["res"][p]["findings"]) for p in ("gemini", "openai", "dicta")}
    kinds = Counter(r["kind"] for r in recs.values())
    head = (f'<p>Models: {", ".join(f"{p} = <b>{html.escape(str(m))}</b>" for p, m in models.items())}<br>'
            f'Run: {html.escape(meta.get("run_at", "?"))} · evaluated {len(rows)} · skipped as original Hebrew source {kinds.get("source-quote", 0)}'
            f' · headings {kinds.get("heading", 0)} · unaligned chunks {meta.get("unaligned", 0)}<br>'
            + " · ".join(f"{p}: " + ", ".join(f"{k} {v}" for k, v in c.items()) for p, c in sev.items() if c) + "</p>")
    body = []
    for r in rows:
        rec, res = r["rec"], r["res"]
        allf = [dict(f, _p=p) for p in ("gemini", "openai", "dicta") if p in res for f in res[p]["findings"]]
        items = "".join(
            f'<li class="{html.escape(f.get("severity", ""))}"><b>{f["_p"]}</b> · {html.escape(f.get("category", f.get("type", "")))} · '
            f'{html.escape(f.get("severity", ""))} — «{html.escape(f["he_span"])}»'
            + (f' ← <span dir="ltr">“{html.escape(f.get("en_span", ""))}”</span>' if f.get("en_span") else "")
            + f'<div class="note" dir="ltr">{html.escape(f.get("note", ""))}</div></li>' for f in allf)
        body.append(
            f'<section class="{"look" if r["look"] else ""}"><h3>{rec["id"]} '
            f'<span class="meta" dir="ltr">gemini {scores(res, "gemini") or "–"} · openai {scores(res, "openai") or "–"}'
            + (f' · dicta {res["dicta"]["naturalness"]}' if "dicta" in res else "")
            + (f' · agreement {r["agreement"]:.2f}' if r["agreement"] is not None else "")
            + (f' · <b>look: {html.escape("; ".join(r["look"]))}</b>' if r["look"] else "") + "</span></h3>"
            f'<p class="he">{mark_spans(rec["he"], allf)}</p>'
            f'<details dir="ltr"><summary>English</summary><p>{html.escape(rec["en"])}</p></details>'
            f'<ul>{items or "<li>no findings</li>"}</ul></section>')
    page = f"""<!DOCTYPE html><html lang="he" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Evaluation — {chapter}</title><style>
:root{{--bg:#fff;--fg:#222;--muted:#666;--line:#ddd;--crit:#fdecea;--maj:#fff3b0;--min:#eef2ff;--look:#b42318}}
@media (prefers-color-scheme:dark){{:root{{--bg:#16181c;--fg:#e8e8e8;--muted:#9aa0a6;--line:#3a3d42;--crit:#4a1d1d;--maj:#4a3f00;--min:#1f2640;--look:#ff8a80}}}}
body{{background:var(--bg);color:var(--fg);font-family:'Times New Roman',serif;margin:16px;max-width:980px}}
.top,.meta,summary,.note,li b{{font-family:sans-serif;font-size:13px}} .meta{{color:var(--muted);font-weight:normal}}
section{{border-top:1px solid var(--line);padding:8px 0}} section.look h3{{border-inline-start:4px solid var(--look);padding-inline-start:8px}}
.he{{font-size:18px;line-height:1.7}} mark.critical{{background:var(--crit)}} mark.major{{background:var(--maj)}} mark.minor{{background:var(--min)}}
mark{{color:inherit}} .note{{color:var(--muted)}} li{{margin-bottom:6px}} details p{{color:var(--muted);font-size:15px}}
</style></head><body><h1>Evaluation — {html.escape(CHAPTERS[chapter][1])}</h1><div class="top" dir="ltr">{head}</div>{"".join(body)}</body></html>"""
    (EVAL / "report" / f"{chapter}.html").write_text(page, encoding="utf-8")


def write_summary(chapter, rows, models):
    top = sorted(rows, key=lambda r: -sum(len(r["res"][p]["findings"]) for p in r["res"]))[:10]
    lines = [f"# Evaluation summary — {CHAPTERS[chapter][1]}", "",
             "Models: " + ", ".join(f"{p} = {m}" for p, m in models.items()), "",
             f"Paragraphs evaluated: {len(rows)}; needing a human look: {sum(1 for r in rows if r['look'])}", "",
             "## The ten most-flagged paragraphs", ""]
    for r in top:
        n = {p: len(r["res"][p]["findings"]) for p in r["res"]}
        lines.append(f"- **{r['rec']['id']}** — " + ", ".join(f"{p} {c}" for p, c in n.items())
                     + (f" — look: {'; '.join(r['look'])}" if r["look"] else "") + f"  \n  {r['rec']['he'][:120]}…")
    lines += ["", "## Finding categories per provider (watch for systematic bias)", "",
              "| category | " + " | ".join(MAIN) + " |", "|---|" + "---|" * len(MAIN)]
    cats = {p: Counter(f["category"] for r in rows if p in r["res"] for f in r["res"][p]["findings"]) for p in MAIN}
    for c in sorted(set().union(*cats.values())):
        lines.append(f"| {c} | " + " | ".join(str(cats[p][c]) for p in MAIN) + " |")
    lines += ["", "## Terminology findings", ""]
    terms = [(r["rec"]["id"], p, f) for r in rows for p in MAIN if p in r["res"] for f in r["res"][p]["findings"] if f["category"] == "terminology"]
    lines += [f"- {rid} ({p}): «{f['he_span']}» ← “{f.get('en_span', '')}” — {f['note']}" for rid, p, f in terms] or ["(none)"]
    (EVAL / "report" / f"{chapter}-summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_findings(chapter, rows, models):
    """For tools/build_review.py: keyed by "<chunk>-<para>"."""
    out = {"models": models, "paragraphs": {}}
    for r in rows:
        rec = r["rec"]
        out["paragraphs"][f'{rec["chunk"]}-{rec["para"]}'] = {
            "look": r["look"], "agreement": r["agreement"],
            "scores": {p: r["res"][p].get("overall") for p in MAIN if p in r["res"]},
            "naturalness": r["res"].get("dicta", {}).get("naturalness"),
            "findings": [dict(provider=p, **{k: f.get(k, "") for k in ("category", "type", "severity", "he_span", "en_span", "note")})
                         for p in ("gemini", "openai", "dicta") if p in r["res"] for f in r["res"][p]["findings"]]}
    (EVAL / "findings").mkdir(parents=True, exist_ok=True)
    (EVAL / "findings" / f"{chapter}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--chapter", required=True, choices=sorted(CHAPTERS))
    a = ap.parse_args(argv)
    recs, results, models, meta = load(a.chapter)
    rows = build_rows(recs, results)
    (EVAL / "report").mkdir(parents=True, exist_ok=True)
    write_csv(a.chapter, rows)
    write_html(a.chapter, rows, models, meta, recs)
    write_summary(a.chapter, rows, models)
    write_findings(a.chapter, rows, models)
    print(f"report: eval/report/{a.chapter}.html ({len(rows)} paragraphs, {sum(1 for r in rows if r['look'])} to look at)")


if __name__ == "__main__":
    main()
