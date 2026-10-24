"""proof-report.md: what a person should look at after proofreading."""

from datetime import datetime
from pathlib import Path

from . import checks, textfmt as tf

MAX_CHANGES_SHOWN = 60


def _md(s):
    return (s or "").replace("|", "\\|").replace("\n", " ")


def write_report(out_dir, ocr, proof, cost_fn=None):
    out_dir = Path(out_dir)
    pages = sorted(ocr)
    done = [proof[n] for n in pages if n in proof]
    ok = [r for r in done if r["status"] == "ok"]
    kept = [r for r in done if r["status"] != "ok"]
    missing = [n for n in pages if n not in proof]
    flagged = [r for r in done if r["warnings"]]
    doubtful = [(r["page"], r["doubtful"]) for r in done if r.get("doubtful")]

    seq = [(r["page"], tf.refs(tf.split_body_notes(r["text"])[0])) for r in ok]
    seq_warnings = checks.footnote_sequence(seq)

    models = sorted({r["model"] for r in done})
    cost = None
    if cost_fn and done:
        parts = []
        for r in done:
            c = cost_fn(r["model"], r["usage"])
            if c is None:
                parts = None
                break
            parts.append(c)
        cost = sum(parts) if parts is not None else None

    L = [f"# Proofreading report — {out_dir.name}", "",
         f"Written {datetime.now():%Y-%m-%d %H:%M}. Model: {', '.join(models) or '—'}.", "",
         "| Pages | Proofread | OCR kept | Not yet done | To review | Doubtful readings | Cost |",
         "| --- | --- | --- | --- | --- | --- | --- |",
         f"| {len(pages)} | {len(ok)} | {len(kept)} | {len(missing)} | {len(flagged)} | "
         f"{sum(len(d) for _, d in doubtful)} | {'unknown' if cost is None else f'${cost:.2f}'} |", ""]

    if kept or missing:
        L += ["## Not proofread", ""]
        for r in kept:
            L.append(f"- Page {r['page']}: OCR text kept — {r.get('reason', '')}. Run again with `--repair`.")
        if missing:
            L.append(f"- Not yet done: {missing[:50]}{' …' if len(missing) > 50 else ''}")
        L.append("")

    L += ["## Footnote numbering across pages", ""]
    L += [f"- {w}" for w in seq_warnings] or ["No jumps found."]
    L.append("")

    L += ["## Pages to review", ""]
    if flagged:
        L += ["| Page | Printed | Status | Changed | Warnings |", "| --- | --- | --- | --- | --- |"]
        for r in flagged:
            L.append(f"| {r['page']} | {r.get('printed_page') or ''} | {r['status']} | "
                     f"{r.get('change_rate', 0):.0%} | {_md('; '.join(r['warnings']))} |")
    else:
        L.append("None.")
    L.append("")

    if doubtful:
        L += ["## Doubtful readings", "", "Marked `{?…}` in the text: the proofreader was not sure "
              "and kept the OCR reading. Check each against the scan.", ""]
        for n, d in doubtful:
            L.append(f"- Page {n}: {', '.join(d)}")
        L.append("")

    L += ["## Changes on flagged pages", ""]
    for r in flagged:
        if not r.get("changes"):
            continue
        head = f"### Page {r['page']}" + (f" (p. {r['printed_page']})" if r.get("printed_page") else "")
        L += [head, "", "| OCR | Proofread |", "| --- | --- |"]
        for op, old, new in r["changes"][:MAX_CHANGES_SHOWN]:
            L.append(f"| {_md(old) or '—'} | {_md(new) or '—'} |")
        if len(r["changes"]) > MAX_CHANGES_SHOWN:
            L.append(f"| … {len(r['changes']) - MAX_CHANGES_SHOWN} more in proof.jsonl | |")
        L.append("")

    path = out_dir / "proof-report.md"
    path.write_text("\n".join(L), encoding="utf-8")
    return path
