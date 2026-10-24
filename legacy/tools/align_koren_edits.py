"""Align an edited Koren docx (drafts/updates/chNN-*-koren-edited.docx) with the chapter's English paragraphs.

Usage: python3 tools/align_koren_edits.py chNN [--json out.json] [--corrected]
(--corrected: read drafts/updates/chNN-*-koren-edited-corrected.docx instead of the edited file)
Body: each Word paragraph of the edited file is matched to a paragraph of the current Koren build
(the same blocks book_data.py makes from output_chunkNNNN.md), and through it to the English paragraph
(chunk NNNN, paragraph P). Splits and merges are detected by text similarity. Footnotes are matched by number.
"""
import os
import difflib, json, re, sys, zipfile
from pathlib import Path
ROOT = (Path(os.environ["TRANSLATOR_PROJECT"]).expanduser().resolve() if os.environ.get("TRANSLATOR_PROJECT")
        else sys.exit("Set TRANSLATOR_PROJECT to the book folder, e.g. TRANSLATOR_PROJECT=~/the_translator"))

def doc_paras(path):
    z = zipfile.ZipFile(path); x = z.read("word/document.xml").decode()
    out = []
    for p in re.findall(r"<w:p[ >].*?</w:p>", x, re.S):
        p = re.sub(r"<w:footnoteReference [^>]*w:id=\"(\d+)\"/>", lambda m: f"^F{m.group(1)}^", p)
        t = re.sub(r"<[^>]+>", "", re.sub(r"<w:delText>.*?</w:delText>", "", p)).replace("&apos;", "'").replace("&quot;", '"').replace("&amp;", "&").strip()
        if t: out.append(t)
    fx = z.read("word/footnotes.xml").decode()
    notes = {}
    for fid, body in re.findall(r'<w:footnote [^>]*w:id="(\d+)"[^>]*>(.*?)</w:footnote>', fx, re.S):
        if int(fid) < 1: continue
        t = re.sub(r"<[^>]+>", "", body).replace("&apos;", "'").replace("&quot;", '"').replace("&amp;", "&").strip()
        notes[int(fid)] = t
    return out, notes

def source_blocks(temp):
    """The blocks book_data.py builds, with their source (chunk, paragraph) and the English paragraph."""
    blocks = []
    for f in sorted(temp.glob("output_chunk[0-9][0-9][0-9][0-9].md")):
        n = f.name[12:16]
        he = [p.strip() for p in re.split(r"\n\s*\n", f.read_text(encoding="utf-8")) if p.strip()]
        en = [p.strip() for p in re.split(r"\n\s*\n", (temp / f"chunk{n}.md").read_text(encoding="utf-8")) if p.strip()]
        for i, (h, e) in enumerate(zip(he, en), 1):
            if re.match(r"^#+\s*(הערות|Notes)\s*$", h) or re.match(r"^\d+\\?\.", h): continue
            if all(re.match(r"^\s*[-*] ", l) for l in h.split("\n")):
                lines = [re.sub(r"^\s*[-*]\s+", "", l) for l in h.split("\n")]
            elif h.startswith(">"):
                lines = [re.sub(r"^>\s?", "", l) for l in h.split("\n")]
            else:
                lines = [h.replace("\n", " ")]
            for l in lines:
                l = re.sub(r"^#+\s*", "", l).strip()
                if l: blocks.append({"chunk": n, "para": i, "he": l, "en": e})
    return blocks

def norm(s): return re.sub(r"[^א-ת0-9A-Za-z]", "", re.sub(r"\^[^^]*\^|==", "", s))

def main():
    ch = sys.argv[1]; temp = next(ROOT.glob(f"{ch}-*_temp"))
    suffix = "-koren-edited-corrected.docx" if "--corrected" in sys.argv else "-koren-edited.docx"
    ed = next((ROOT / "drafts" / "updates").glob(f"{ch}-*{suffix}"))
    paras, notes = doc_paras(ed); blocks = source_blocks(temp)
    a = [norm(p) for p in paras]; b = [norm(x["he"]) for x in blocks]
    # dynamic alignment: each edited paragraph → best block (monotonic), allowing 1→many and many→1
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    pairs = []
    j = 0
    for i, p in enumerate(a):
        best, bj = 0, None
        for k in range(max(0, j - 1), min(len(b), j + 4)):
            r = difflib.SequenceMatcher(None, p, b[k], autojunk=False).quick_ratio()
            if r > best: best, bj = r, k
        if bj is not None and best > 0.35:
            pairs.append((i, bj, round(best, 2))); j = bj + 1 if best > 0.5 else j
        else:
            pairs.append((i, None, round(best, 2)))
    # second pass for weak matches: footnote markers first, then the slot between matched neighbours
    star = any(x.startswith("*") for x in []) 
    mark = {}
    for k, x in enumerate(blocks):
        for m in re.findall(r"\^(\d+)\^", x["he"]): mark.setdefault(int(m), k)
    fixed = []
    for idx, (i, k, r) in enumerate(pairs):
        if k is not None and r >= 0.6: fixed.append((i, k, r, "text")); continue
        fids = [int(x) for x in re.findall(r"\^F(\d+)\^", paras[i])]
        cand = [mark.get(f) for f in fids] + [mark.get(f - 1) for f in fids]
        cand = [c for c in cand if c is not None]
        if cand: fixed.append((i, cand[0], r, "note marker")); continue
        prev = next((fk for _, fk, fr, _m in reversed(fixed) if fk is not None and fr >= 0.6), -1)
        nxt = next((pk for pi, pk, pr in pairs[idx + 1:] if pk is not None and pr >= 0.6), len(blocks))
        if nxt - prev >= 2: fixed.append((i, prev + 1 if nxt - prev == 2 else min(prev + 1, nxt - 1), r, "position"))
        else: fixed.append((i, k, r, "weak text"))
    out = []
    for i, k, r, how in fixed:
        blk = blocks[k] if k is not None else None
        out.append({"edited_index": i + 1, "he_edited": paras[i], "match": r, "how": how,
                    "chunk": blk and blk["chunk"], "para": blk and blk["para"], "en": blk and blk["en"], "he_before": blk and blk["he"]})
    res = {"chapter": ch, "body": out, "notes": notes}
    if "--json" in sys.argv: Path(sys.argv[sys.argv.index("--json") + 1]).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    low = [o for o in out if o["chunk"] is None or o["how"] in ("weak text",)]
    print(f"{ch}: {len(paras)} edited paragraphs, {len(blocks)} source blocks; matched {len(out) - len(low)}; weak/unmatched {len(low)}; notes {len(notes)}")
    hows = {}
    for o in out: hows[o["how"]] = hows.get(o["how"], 0) + 1
    print("   by method:", hows)
    for o in low[:8]: print("   weak:", o["edited_index"], o["match"], o["he_edited"][:70])

if __name__ == "__main__":
    main()
