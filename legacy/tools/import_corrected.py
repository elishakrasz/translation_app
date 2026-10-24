"""Import the translator's corrected Word masters back into the chapter files (DRY RUN by default).

Usage: python3 tools/import_corrected.py [chNN ...] [--write]
Source: drafts/updates/chNN-*-koren-edited-corrected.docx (the text of record). Target: chNN-*_temp/output_chunkNNNN.md.
Dry run: writes previews to work/import/preview/<temp>/ and work/import/dry-run-report.md (+ chNN.json); nothing else.
--write (later, after review): backs up the temp folder and writes the chunk files.

How: the Koren build turns each chunk paragraph into blocks (one per quote line / list item); the corrected docx
paragraphs are aligned to those blocks by sequence alignment on the text; each block takes the docx text with Word
formatting turned back into markdown (highlight → ==…==, italic → *…*, bold → **…**, footnote reference → ^n^).
Notes come from the docx footnotes (numbered as the build numbers them: the asterisk note first, then by number).
"""
import os
import difflib, html, json, re, shutil, sys, zipfile
from pathlib import Path
ROOT = (Path(os.environ["TRANSLATOR_PROJECT"]).expanduser().resolve() if os.environ.get("TRANSLATOR_PROJECT")
        else sys.exit("Set TRANSLATOR_PROJECT to the book folder, e.g. TRANSLATOR_PROJECT=~/the_translator"))
ITAL = [0]
HEAD_IN_PARA = {}   # (chunk, para) → notes heading that shares a paragraph with the first note
OUT = ROOT / "work" / "import"
LABEL = re.compile(r"^(פרק|נספח) [א-ת\"']+$")

# ---------- docx side ----------
def _runs_of(p):
    runs = []
    for r in re.finditer(r"<w:r[ >].*?</w:r>", p, re.S):
        rx = r.group(0)
        if "<w:delText" in rx and "<w:t" not in rx.replace("<w:delText", ""): continue
        pr = re.search(r"<w:rPr>(.*?)</w:rPr>", rx, re.S); pr = pr.group(1) if pr else ""
        f = {"i": bool(re.search(r"<w:i/>|<w:i w:val=\"(1|true)\"/>", pr)), "b": bool(re.search(r"<w:b/>|<w:b w:val=\"(1|true)\"/>", pr)),
             "hl": "<w:highlight" in pr}
        fr = re.search(r'<w:footnoteReference [^>]*w:id="(\d+)"', rx)
        if fr: runs.append({"fn": int(fr.group(1))}); continue
        t = "".join(html.unescape(m) for m in re.findall(r"<w:t(?: [^>]*)?>(.*?)</w:t>", rx, re.S))
        if "<w:tab/>" in rx: t = t or " "
        if t: runs.append({"t": t, **f})
    return runs

def docx_read(path):
    z = zipfile.ZipFile(path)
    x = z.read("word/document.xml").decode()
    body = [r for r in (_runs_of(p) for p in re.findall(r"<w:p[ >].*?</w:p>", x, re.S)) if any(q.get("t", "").strip() or "fn" in q for q in r)]
    fx = z.read("word/footnotes.xml").decode()
    notes = {}
    for fid, inner in re.findall(r'<w:footnote [^>]*w:id="(\d+)"[^>]*>(.*?)</w:footnote>', fx, re.S):
        if int(fid) < 1: continue
        ps = [r for r in (_runs_of(p) for p in re.findall(r"<w:p[ >].*?</w:p>", inner, re.S)) if any(q.get("t", "").strip() for q in r)]
        notes[int(fid)] = ps
    return body, notes

def to_md(runs, fnmap):
    """Runs → markdown inline text (==hl==, *i*, **b**, ^n^)."""
    out, open_hl = [], False
    for r in runs:
        hl = r.get("hl", False)
        if "fn" in r:
            n = fnmap.get(r["fn"]); tok = f"^{n}^" if n is not None else f"^?{r['fn']}^"
            out.append(tok); continue          # a footnote reference never opens or closes a highlight
        if hl != open_hl: out.append("=="); open_hl = hl
        t = r["t"]
        core = t.strip()
        if core and (r.get("b") or r.get("i")):
            lead, trail = t[:len(t) - len(t.lstrip())], t[len(t.rstrip()):]
            mark = "**" if r.get("b") else "*"
            t = f"{lead}{mark}{core}{mark}{trail}"
        out.append(t)
    if open_hl: out.append("==")
    s = "".join(out)
    s = re.sub(r"\*\*\*\*|(?<!\*)\*\*(?!\*)(?=\S)", lambda m: "" if m.group(0) == "****" else m.group(0), s)
    s = re.sub(r"(?<![*\s])\*(\s*)\*(?![*\s])", r"\1", s)        # merge adjacent italic runs: *a**b* → *ab*
    s = s.replace("====", "")
    return re.sub(r"[ \t]+", " ", s).strip()

# ---------- chunk side (mirror of tools/book_data.py) ----------
def chunk_paras(f):
    return [p.strip() for p in re.split(r"\n\s*\n", f.read_text(encoding="utf-8")) if p.strip()]

def blocks_of(temp):
    """Body blocks with provenance, in book order, and the notes section by note number."""
    blocks, notes, in_notes, cur = [], {}, False, None
    HEAD_IN_PARA.clear()                     # per unit (keys are chunk·para, which repeat across units)
    for f in sorted(temp.glob("output_chunk[0-9][0-9][0-9][0-9].md")):
        n = f.name[12:16]
        for i, p in enumerate(chunk_paras(f), 1):
            if re.match(r"^#+\s*(?:הערות|Notes)\s*$", p): in_notes = True; continue
            hm = re.match(r"^(#+\s*(?:הערות|Notes)\s*)\n", p)   # heading and first note in one paragraph
            if hm: in_notes = True; HEAD_IN_PARA[(n, i)] = hm.group(1); p = p[hm.end():]
            if in_notes:
                m = re.match(r"^(\d+)\\?\.\s*(.+)$", p, re.S)
                if m: cur = int(m.group(1)); notes[cur] = {"main": (n, i), "more": []}
                elif re.match(r"^\\?\*", p): cur = "*"; notes["*"] = {"main": (n, i), "more": []}
                elif cur is not None: notes[cur]["more"].append((n, i))
                continue
            if all(re.match(r"^\s*[-*] ", l) for l in p.split("\n")):
                for k, l in enumerate(p.split("\n")):
                    blocks.append({"chunk": n, "para": i, "line": k, "kind": "li", "prefix": re.match(r"^(\s*[-*]\s+)", l).group(1),
                                   "text": re.sub(r"^\s*[-*]\s+", "", l)})
                continue
            quote = p.startswith(">"); level = len(re.match(r"^(#*)", p).group(1))
            lines = p.split("\n") if quote else [p.replace("\n", " ")]
            for k, l in enumerate(lines):
                body = re.sub(r"^>\s?", "", l) if quote else l
                body = re.sub(r"^#+\s*", "", body)
                if body.strip():
                    blocks.append({"chunk": n, "para": i, "line": k, "kind": "h" if level else ("q" if quote else "p"),
                                   "prefix": ("#" * level + " ") if level else ("> " if quote else ""), "text": body.strip()})
                elif quote:
                    blocks.append({"chunk": n, "para": i, "line": k, "kind": "qblank", "prefix": ">", "text": ""})
    return blocks, notes

def restore_italics(old, new):
    """Re-italicize titles that were *italic* in the chapter file and survive unitalicized in the new text."""
    n = 0
    for m in re.finditer(r"(?<!\*)\*(?!\s|\*)([^*\n]+?)\*(?!\*)", old):
        x = m.group(1)
        if f"*{x}*" in new or x not in new: continue
        new = new.replace(x, f"*{x}*", 1); n += 1
    return new, n

def plain(s):
    s = re.sub(r"<br>|\^[^^]*\^|==|\*|\\", "", s)
    return re.sub(r"[^\w]", "", s)

def align(a, b):
    """Global alignment of docx paragraphs a (plain strings) to blocks b (plain strings). Returns list of (i or None, j or None)."""
    n, m = len(a), len(b)
    sim = {}
    def S(i, j):
        if (i, j) not in sim:
            x, y = a[i], b[j]
            sim[(i, j)] = 1.0 if x == y else difflib.SequenceMatcher(None, x, y, autojunk=False).ratio() if abs(len(x) - len(y)) < 4 * max(len(x), len(y), 1) else 0.0
        return sim[(i, j)]
    GAP = -0.35; band = 40
    import math
    D = [[-math.inf] * (m + 1) for _ in range(n + 1)]; B = [[None] * (m + 1) for _ in range(n + 1)]
    D[0][0] = 0
    for i in range(n + 1):
        for j in range(max(0, i - band), min(m, i + band) + 1):
            if i == 0 and j == 0: continue
            best, arg = -math.inf, None
            if i and j and D[i-1][j-1] > -math.inf:
                v = D[i-1][j-1] + (S(i-1, j-1) - 0.5) * 2
                if v > best: best, arg = v, "d"
            if i and D[i-1][j] > -math.inf and D[i-1][j] + GAP > best: best, arg = D[i-1][j] + GAP, "u"
            if j and D[i][j-1] > -math.inf and D[i][j-1] + GAP > best: best, arg = D[i][j-1] + GAP, "l"
            D[i][j], B[i][j] = best, arg
    i, j, path = n, m, []
    while i or j:
        mv = B[i][j]
        if mv == "d": path.append((i-1, j-1, S(i-1, j-1))); i, j = i-1, j-1
        elif mv == "u": path.append((i-1, None, 0)); i -= 1
        else: path.append((None, j-1, 0)); j -= 1
    return path[::-1]

# ---------- per unit ----------
def unit(ch):
    temp = next(ROOT.glob(f"{ch}-*_temp"))
    src = next((ROOT / "drafts" / "updates").glob(f"{ch}-*-koren-edited-corrected.docx"))
    body, fnotes = docx_read(src)
    blocks, notes = blocks_of(temp)
    # footnote id → note number, as tools/book_data.py numbers them
    used_body = []
    for bl in blocks:
        for m in re.finditer(r"\^(\*|\d+)\^", bl["text"]):
            v = m.group(1); v = "*" if v == "*" else int(v)
            if v not in used_body: used_body.append(v)
    used = (["*"] if "*" in used_body else []) + sorted(x for x in used_body if x != "*")
    # footnote id → note number: align the docx footnotes (in id order) with the chapter notes (in build order) by text,
    # so a numbering gap or an older build cannot shift the mapping
    files0 = {f.name[12:16]: chunk_paras(f) for f in sorted(temp.glob("output_chunk[0-9][0-9][0-9][0-9].md"))}
    def note_text(n):
        c, p = notes[n]["main"]; t = files0[c][p - 1]
        return re.sub(r"^#+\s*(?:הערות|Notes)\s*\n", "", t)
    fids = sorted(fnotes)
    a_ = [plain(to_md(fnotes[f][0], {}) if fnotes[f] else "") for f in fids]
    b_ = [plain(note_text(n)) if n in notes else "" for n in used]
    fnmap, fnweak = {}, []
    if len(fids) == len(used):                     # same count: the build's own numbering (position)
        for k, f in enumerate(fids):
            fnmap[f] = used[k]
            sc = difflib.SequenceMatcher(None, a_[k], b_[k], autojunk=False).ratio()
            if sc < 0.5: fnweak.append({"footnote_id": f, "note": used[k], "sim": round(sc, 2), "how": "position"})
    else:                                          # counts differ: align by text
        for i, j, sc in align(a_, b_):
            if i is not None and j is not None:
                fnmap[fids[i]] = used[j]
                if sc < 0.5: fnweak.append({"footnote_id": fids[i], "note": used[j], "sim": round(sc, 2), "how": "text"})
    if body and LABEL.match("".join(r.get("t", "") for r in body[0]).strip()): body = body[1:]
    dmd = [to_md(r, fnmap) for r in body]
    path = align([plain(x) for x in dmd], [plain(b["text"]) for b in blocks])
    rep = {"unit": ch, "docx": src.name, "docx_paras": len(dmd), "blocks": len(blocks), "changed": 0, "same": 0,
           "weak": [], "docx_unmatched": [], "blocks_unmatched": [], "notes": {}, "highlights": {}, "format": {}, "structure": {}}
    new_text = {}
    last_j = None
    ITAL[0] = 0
    for i, j, s in path:
        if i is not None and j is not None:
            new_text[j] = dmd[i]; last_j = j
            if plain(dmd[i]) == plain(blocks[j]["text"]): rep["same"] += 1
            else: rep["changed"] += 1
            if s < 0.6: rep["weak"].append({"block": f"{blocks[j]['chunk']}·{blocks[j]['para']}", "sim": round(s, 2), "docx": dmd[i][:90], "was": blocks[j]["text"][:90]})
        elif i is not None:
            rep["docx_unmatched"].append({"after_block": f"{blocks[last_j]['chunk']}·{blocks[last_j]['para']}" if last_j is not None else "start", "docx": dmd[i][:120]})
            if last_j is not None: new_text[last_j] = new_text.get(last_j, blocks[last_j]["text"]) + " <br>" + dmd[i]   # the translator's split: kept as a line break inside the paragraph
        else:
            if blocks[j]["kind"] != "qblank":
                rep["blocks_unmatched"].append({"block": f"{blocks[j]['chunk']}·{blocks[j]['para']}", "was": blocks[j]["text"][:120]})
    # rebuild chunk files
    files = {}
    for f in sorted(temp.glob("output_chunk[0-9][0-9][0-9][0-9].md")):
        files[f.name[12:16]] = chunk_paras(f)
    groups = {}
    for j, bl in enumerate(blocks): groups.setdefault((bl["chunk"], bl["para"]), []).append(j)
    for (c, p), js in groups.items():
        lines = []
        for j in js:
            bl = blocks[j]; t = new_text.get(j, bl["text"])
            t, k = restore_italics(bl["text"], t); ITAL[0] += k
            if bl["kind"] == "qblank": lines.append(">"); continue
            if bl["kind"] in ("p", "q", "li") and re.match(r"^\d+\.", t): t = re.sub(r"^(\d+)\.", r"\1\\.", t)
            lines.append(bl["prefix"] + t)
        files[c][p - 1] = "\n".join(lines)
    # notes
    nrep = {"replaced": 0, "same": 0, "missing_in_docx": [], "paragraph_count_differs": []}
    for fid, n in fnmap.items():
        if n not in notes: continue
        dps = [to_md(r, fnmap) for r in fnotes.get(fid, [])]
        if not dps: nrep["missing_in_docx"].append(n); continue
        c, p = notes[n]["main"]; old = files[c][p - 1]
        head = HEAD_IN_PARA.get((c, p), ""); old_body = old[len(head) + 1:] if head else old
        pm = re.match(r"^(\d+\\?\.\s*|\\?\*\\?\.\s*)", old_body)
        if not pm: nrep.setdefault("not_a_note_paragraph", []).append(n); continue
        prefix = pm.group(1)
        d0, k = restore_italics(old_body, dps[0]); ITAL[0] += k
        new_main = (head + "\n" if head else "") + prefix + d0
        nrep["same" if plain(new_main) == plain(old) else "replaced"] += 1
        files[c][p - 1] = new_main
        more = notes[n]["more"]
        if len(dps) - 1 != len(more):
            nrep["paragraph_count_differs"].append({"note": n, "docx": len(dps), "chunk": 1 + len(more)})
            if len(dps) > 1 and not more: files[c][p - 1] = new_main + " " + " ".join(dps[1:])
        for k, (c2, p2) in enumerate(more):
            if k + 1 < len(dps):
                q = files[c2][p2 - 1].startswith(">")
                files[c2][p2 - 1] = ("> " if q else "") + dps[k + 1]
    nrep["weak_mapping"] = fnweak
    nrep["unmapped_footnotes"] = [f for f in fids if f not in fnmap]
    rep["notes"] = nrep
    # write previews + compare structure with the English
    pv = OUT / "preview" / temp.name; pv.mkdir(parents=True, exist_ok=True)
    hl_old = hl_new = it_old = it_new = 0; bad = {}
    for c, ps in files.items():
        new = "\n\n".join(ps) + "\n"; (pv / f"output_chunk{c}.md").write_text(new, encoding="utf-8")
        old = (temp / f"output_chunk{c}.md").read_text(encoding="utf-8"); en = (temp / f"chunk{c}.md").read_text(encoding="utf-8")
        hl_old += old.count("==") // 2; hl_new += new.count("==") // 2
        it_old += len(re.findall(r"(?<!\*)\*(?!\s|\*)[^*\n]+\*", old)); it_new += len(re.findall(r"(?<!\*)\*(?!\s|\*)[^*\n]+\*", new))
        P = lambda s: [x for x in re.split(r"\n\s*\n", s) if x.strip()]
        chk = {"paras": (len(P(en)), len(P(new))), "markers": (re.findall(r"\^(\d+)\^", en), re.findall(r"\^(\d+)\^", new)),
               "quote-lines": (len(re.findall(r"(?m)^>", en)), len(re.findall(r"(?m)^>", new))),
               "headings": (len(re.findall(r"(?m)^#+ ", en)), len(re.findall(r"(?m)^#+ ", new)))}
        d = [k for k, (a, b) in chk.items() if a != b]
        if d: bad[c] = d
    rep["highlights"] = {"now": hl_old, "after": hl_new}; rep["format"] = {"italic_now": it_old, "italic_after": it_new, "italics_reapplied": ITAL[0]}
    rep["structure"] = bad
    return rep

def main():
    chs = [a for a in sys.argv[1:] if a.startswith("ch")] or [f"ch{c:02d}" for c in range(1, 19)]
    OUT.mkdir(parents=True, exist_ok=True)
    reps = []
    for ch in chs:
        r = unit(ch); reps.append(r)
        (OUT / f"{ch}.json").write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{ch}: docx {r['docx_paras']} / blocks {r['blocks']} | changed {r['changed']} same {r['same']} | weak {len(r['weak'])} "
              f"| docx-only {len(r['docx_unmatched'])} | blocks-only {len(r['blocks_unmatched'])} | notes repl {r['notes']['replaced']} "
              f"same {r['notes']['same']} diffcount {len(r['notes']['paragraph_count_differs'])} | hl {r['highlights']['now']}→{r['highlights']['after']} "
              f"| ital {r['format']['italic_now']}→{r['format']['italic_after']} | structure {'OK' if not r['structure'] else r['structure']}")
    if "--write" in sys.argv:
        stamp = "before-import-20261023"
        for ch in chs:
            temp = next(ROOT.glob(f"{ch}-*_temp")); pv = OUT / "preview" / temp.name
            bk = ROOT / "backups" / stamp / temp.name
            if not bk.exists():
                bk.mkdir(parents=True)
                for f in temp.glob("output_chunk[0-9][0-9][0-9][0-9].md"): shutil.copy2(f, bk / f.name)
            for f in sorted(pv.glob("output_chunk[0-9][0-9][0-9][0-9].md")): shutil.copy2(f, temp / f.name)
            print(f"{ch}: written ({len(list(pv.glob('output_chunk*.md')))} files); backup in backups/{stamp}/{temp.name}")

if __name__ == "__main__":
    main()
