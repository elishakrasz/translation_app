"""Build the register of inserted original-source quotations and check the masters against it.

Usage: python3 tools/quote_register.py build   -> work/quotes/register.json (from sources/applied logs + chunk files)
       python3 tools/quote_register.py check [chNN ...]  -> reports quotations not found verbatim in
       drafts/updates/chNN-*-koren-edited-corrected.docx (body + notes)
Comparison ignores ^n^/^Fk^ markers, == highlights, '>' prefixes, whitespace, and hyphen vs maqaf.
"""
import os
import glob, json, re, sys
from pathlib import Path
ROOT = (Path(os.environ["TRANSLATOR_PROJECT"]).expanduser().resolve() if os.environ.get("TRANSLATOR_PROJECT")
        else sys.exit("Set TRANSLATOR_PROJECT to the book folder, e.g. TRANSLATOR_PROJECT=~/the_translator"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from align_koren_edits import doc_paras

def norm(s):
    s = re.sub(r"\^[^^]*\^|==", "", s)
    s = re.sub(r"(?m)^>\s?", "", s)
    s = s.replace("־", "-").replace("–", "-").replace("—", "-").replace("״", '"').replace("׳", "'")
    s = s.replace("\\", "")
    return re.sub(r"\s+", " ", s).strip()

QUOTE_PAIRS = {'"': '"', '„': '"', '“': '”'}

def log_entries(ch):
    out = []
    for f in sorted(glob.glob(str(ROOT / f"sources/applied/{ch}-SOURCES-APPLIED*.md"))):
        for line in open(f, encoding="utf-8"):
            if not line.startswith("- **"): continue
            m = re.search(r'→\s*"(.+?)(?:\.\.\.|…)?"\s*(?:·|$)', line)
            if not m: continue
            note = re.match(r"- \*\*([^*]+)\*\*", line).group(1)
            src = line.split("·")[1].strip() if "·" in line else ""
            out.append({"log": Path(f).name, "note": note, "source": src, "start": m.group(1)})
    return out

def chunk_paras(temp):
    for f in sorted(glob.glob(f"{temp}/output_chunk[0-9][0-9][0-9][0-9].md")):
        n = f[-7:-3]
        for i, p in enumerate([p for p in re.split(r"\n\s*\n", open(f, encoding="utf-8").read()) if p.strip()], 1):
            yield n, i, p

def extract(par, start_norm):
    """Return the full quotation in paragraph `par` that begins with start_norm (normalized)."""
    P = norm(par)
    k = P.find(start_norm)
    if k < 0: return None
    if par.lstrip().startswith(">"):      # block quote: the whole paragraph minus a trailing attribution line
        q = re.sub(r"\s*-\s*[^-]{0,80}$", "", P) if re.search(r"\s-\s[^\s]", P[-80:]) else P
        return q
    # inline: from start to the closing quotation mark (or end of sentence/paragraph)
    before = P[:k]
    opened = before.rstrip()[-1:] in '"“„' if before.strip() else False
    rest = P[k:]
    if opened:
        e = rest.find('"')
        e2 = rest.find('”')
        ends = [x for x in (e, e2) if x > 0]
        return rest[:min(ends)] if ends else rest
    m = re.search(r'["”]', rest)
    return rest[:m.start()] if m else rest

def build():
    reg = []
    for c in range(1, 13):
        ch = f"ch{c:02d}"; temp = glob.glob(str(ROOT / f"{ch}-*_temp"))[0]
        paras = list(chunk_paras(temp))
        for e in log_entries(ch):
            st = norm(e["start"]); words = st.split()
            key = " ".join(words[:6]) if len(words) >= 6 else st
            hits = [(n, i, p) for n, i, p in paras if key in norm(p)]
            if not hits:
                reg.append({**e, "chapter": ch, "status": "not-located"}); continue
            n, i, p = hits[0]
            q = extract(p, key)
            reg.append({**e, "chapter": ch, "chunk": n, "para": i, "in_note": bool(re.match(r"^\d+\\?\.", p.strip())),
                        "text": q, "status": "ok" if q and len(q.split()) >= 3 else "short"})
    # de-duplicate identical texts
    seen = set(); out = []
    for r in reg:
        k = (r["chapter"], r.get("text") or r["start"])
        if k in seen: continue
        seen.add(k); out.append(r)
    (ROOT / "work/quotes").mkdir(exist_ok=True)
    json.dump(out, open(ROOT / "work/quotes/register.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    from collections import Counter
    print(len(out), "quotations;", Counter(r["status"] for r in out), Counter(r["chapter"] for r in out))

def check(chs):
    reg = json.load(open(ROOT / "work/quotes/register.json", encoding="utf-8"))
    res = {}
    for ch in chs:
        f = glob.glob(str(ROOT / f"drafts/updates/{ch}-*-edited-corrected.docx"))[0]
        p, n = doc_paras(f); T = norm(" ".join(p) + " " + " ".join(n.values()))
        rows = [r for r in reg if r["chapter"] == ch and r["status"] == "ok"]
        miss = [r for r in rows if r["text"] not in T]
        res[ch] = miss
        print(f"{ch}: {len(rows)} quotations, {len(rows) - len(miss)} intact, {len(miss)} changed")
    json.dump(res, open(ROOT / "work/quotes/check.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

if __name__ == "__main__":
    if sys.argv[1] == "build": build()
    else: check(sys.argv[2:] or [f"ch{c:02d}" for c in range(1, 13)])
