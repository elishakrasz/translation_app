"""translator check: every check on a project's text, like a test suite (section 9 of the design).

Errors stop a gate; warnings and counts are for reading. Implemented: structure (block IDs and ^n^ markers against the
English), the quotation lock (every recorded quotation still word for word in its block), the forbidden forms of the
style checklist in the translator's prose, the bibliography (one work, one short form), and the open flags.
"""

import re

import yaml

from . import notes, records, sources

BLOCK_RE = re.compile(r"(.*?)\s*<!--id:([^>]*)-->", re.S)
REF_RE = re.compile(r"\^(\d+|\*)\^")
FLAG_RE = re.compile(r"\[לבדיקה[^\]]*\]")


def blocks(path):
    return [(m.group(2), m.group(1)) for m in BLOCK_RE.finditer(path.read_text(encoding="utf-8"))]


def prose(text):
    """The translator's own words: block quotes, quotations in "…", flags and verses removed."""
    text = "\n".join(l for l in text.splitlines() if not l.lstrip().startswith(">"))
    text = re.sub(r'"[^"\n]{0,1500}"', " ", text)
    return FLAG_RE.sub(" ", text)


def check_unit(project, unit, forbid):
    udir = project.unit_dir(unit)
    out = []                                              # (level, check, block, message)
    outputs = sorted(udir.glob("output_chunk[0-9]*.md"))
    if not outputs:
        return out
    for o in outputs:
        src = udir / o.name.removeprefix("output_")
        s_blocks, t_blocks = blocks(src), blocks(o)
        if [b for b, _ in s_blocks] != [b for b, _ in t_blocks]:
            out.append(("error", "structure", o.name, "block IDs differ from the English (missing, added or out of order)"))
        tmap = dict(t_blocks)
        for bid, en in s_blocks:
            if bid in tmap and REF_RE.findall(en) != REF_RE.findall(tmap[bid]):
                out.append(("error", "structure", bid, f"footnote markers {REF_RE.findall(en)} → {REF_RE.findall(tmap[bid])}"))
    text_of = {bid: body for o in outputs for bid, body in blocks(o)}
    for q in records.load(project, "quotations"):
        if q.get("unit") != unit["id"]:
            continue
        body = text_of.get(q["block"])
        if body is None:
            out.append(("error", "quotations", q["block"], f"{q['qid']}: the block is gone"))
        elif sources.verify(q["text"], [body]):
            out.append(("error", "quotations", q["block"], f"{q['qid']} ({q['locator']}) has changed: the locked words are no longer all there"))
    for bid, body in text_of.items():
        p = prose(body)
        for rule, words in forbid.items():
            for w in words:
                if re.search(rf"(?<![א-ת]){re.escape(w)}(?![א-ת])", p):
                    out.append(("error", "style", bid, f"{rule}: '{w}' in the translator's prose"))
        n = len(FLAG_RE.findall(body))
        if n:
            out.append(("info", "flags", bid, f"{n} open [לבדיקה]"))
    return out


def run(project, units):
    checklist = project.root / "style" / "style-checklist.yaml"
    forbid = {}
    if checklist.exists():
        for r in yaml.safe_load(checklist.read_text(encoding="utf-8")).get("rules", []):
            if r.get("forbid") and r.get("severity") == "error":
                forbid[r["id"]] = r["forbid"]
    results = {u["id"]: check_unit(project, u, forbid) for u in units}
    bib = notes.bibliography_conflicts(records.load(project, "bibliography"))
    if bib:
        results["(book)"] = [("error", "bibliography", "-", m) for m in bib]
    return results


def errors(results, unit_id):
    return [r for r in results.get(unit_id, []) + results.get("(book)", []) if r[0] == "error"]
