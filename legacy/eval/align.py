"""Step 1 — pair each Hebrew paragraph with its English paragraph.

The translation is kept paragraph-for-paragraph with the English (tools/check_structure.py
enforces it), so alignment is by position within each chunk; footnote markers are checked
as anchors, and any chunk whose counts or markers disagree is logged and not guessed.

    python -m eval.align --chapter ch02 [--include-notes]
"""
import argparse
import json
import re
import sys
from pathlib import Path

from .config import CHAPTERS, EVAL, ROOT

MARKER = re.compile(r"\^(\d+)\^")
FLAG = re.compile(r"\[(לבדיקה|תרגום מקובל קיים|צ\"ע|לא אומת)\]")


def paras(text):
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def kind_of(he):
    if re.match(r"#+ ", he):
        return "heading"
    if he.startswith(">"):
        return "quote"
    return "prose"


def align_chunk(chapter, chunk, en_text, he_text, source_paras=(), in_notes=False):
    """source_paras: paragraph numbers in this chunk that hold an inserted original source.
    Returns (records, log lines, in_notes after this chunk)."""
    en, he = paras(en_text), paras(he_text)
    log = []
    if len(en) != len(he):
        log.append(f"{chapter}-{chunk}: UNALIGNED — {len(en)} English vs {len(he)} Hebrew paragraphs")
        return [], log, in_notes
    records = []
    for i, (e, h) in enumerate(zip(en, he), 1):
        rid = f"{chapter}-{chunk}-{i}"
        if re.match(r"#+ .*(Notes|הערות)", h) or re.match(r"#+ Notes", e):
            in_notes = True
        em, hm = [int(m) for m in MARKER.findall(e)], [int(m) for m in MARKER.findall(h)]
        kind = kind_of(h)
        if kind != "heading" and in_notes:
            kind = "note"
        if kind in ("prose", "quote", "note") and i in source_paras:
            kind = "source-quote"   # original Hebrew inserted from the verified sources
        flags = FLAG.findall(h)
        rec = {"id": rid, "chapter": chapter, "chunk": chunk, "para": i, "kind": kind,
               "he": FLAG.sub("", h).strip(), "en": e, "markers": hm, "flags": flags, "align": "1:1"}
        if em != hm:
            rec["align"] = "marker-mismatch"
            log.append(f"{rid}: markers differ — English {em}, Hebrew {hm}")
        records.append(rec)
    return records, log, in_notes


def align_chapter(chapter, root=ROOT):
    temp = root / CHAPTERS[chapter][0]
    manifest = root / "sources" / "source-paragraphs.json"
    src = json.loads(manifest.read_text(encoding="utf-8")).get(chapter, []) if manifest.exists() else []
    records, log, in_notes = [], [], False
    for en_file in sorted(temp.glob("chunk[0-9][0-9][0-9][0-9].md")):
        n = en_file.name[5:9]
        out = temp / f"output_chunk{n}.md"
        if not out.exists():
            log.append(f"{chapter}-{n}: UNALIGNED — no translation")
            continue
        in_chunk = {int(k.split("-")[1]) for k in src if k.startswith(n + "-")}
        recs, lg, in_notes = align_chunk(chapter, n, en_file.read_text(encoding="utf-8"), out.read_text(encoding="utf-8"),
                                         in_chunk, in_notes)
        records += recs
        log += lg
    return records, log


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--chapter", required=True, choices=sorted(CHAPTERS))
    a = ap.parse_args(argv)
    records, log = align_chapter(a.chapter)
    write(a.chapter, records, log)


def write(chapter, records, log):
    d = EVAL / "aligned"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{chapter}.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")
    (d / f"{chapter}.log").write_text("\n".join(log) + ("\n" if log else ""), encoding="utf-8")
    counts = {}
    for r in records:
        counts[r["kind"]] = counts.get(r["kind"], 0) + 1
    unaligned = sum(1 for l in log if "UNALIGNED" in l)
    print(f"{chapter}: {len(records)} paragraphs {counts}; alignment log: {len(log)} lines ({unaligned} unaligned chunks)")
    for l in log:
        print("  " + l)
    if unaligned:
        sys.exit("Alignment is not clean — fix the chunks above before evaluating.")


if __name__ == "__main__":
    main()
