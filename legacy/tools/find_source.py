"""Search the original Hebrew sources for a quotation.

Usage:
  python3 tools/find_source.py hb "<Hebrew words>" [--books 67708,51418] [--top 5]
      Fuzzy word search over the HebrewBooks scans (sources/hb/<n>.txt, one
      "<<<pdf page N>>>" block per PDF page). Pages are ranked by how many query
      words they contain (OCR-tolerant: final letters, niqqud and common OCR
      confusions are normalized; a word counts if it appears as a prefix-stripped
      substring). Prints book, PDF page, score and the best-matching window.
  python3 tools/find_source.py page <hb-number> <pdf-page> [--context 1]
      Print the OCR text of a PDF page (and neighbours).
  python3 tools/find_source.py sefaria "<Hebrew words>" [--top 5]
      Word search over every downloaded Sefaria text (sources/sefaria/json).
  python3 tools/find_source.py ref "<Work as in the path, e.g. Deuteronomy | Berakhot | Pirkei Avot>" "<ref, e.g. 30:14 | 30b | 2:1>"
      Print one verse / amud / mishnah / halakha from Sefaria.
  python3 tools/find_source.py books
      List the scans with their titles.
"""
import os
import json
import re
import sys
from pathlib import Path

ROOT = (Path(os.environ["TRANSLATOR_PROJECT"]).expanduser().resolve() if os.environ.get("TRANSLATOR_PROJECT")
        else sys.exit("Set TRANSLATOR_PROJECT to the book folder, e.g. TRANSLATOR_PROJECT=~/the_translator"))
HB = ROOT / "sources" / "hb"
SEF = ROOT / "sources" / "sefaria" / "json"
TITLES = {
    "3622": "נפלאות הרבי", "3625": "זאת זכרון (?)", "3662": "שמחת ישראל (אור שמחה / מאמרי שמחה / תורת שמחה)",
    "3880": "נפלאות היהודי", "9297": "תורת היהודי (חידושי ש\"ס)", "19051": "קול שמחה", "19056": "נועם אלימלך",
    "20392": "אמת ואמונה (מספור שונה ממהדורת המחבר)", "21531": "חידושי הרי\"ם על התורה", "22258": "קדושת היהודי",
    "30843": "עשרה למאה", "38368": "(לא זוהה)", "43701": "חשבה לטובה", "43944": "שיח שרפי קודש ה",
    "43945": "שיח שרפי קודש ג", "51418": "שיח שרפי קודש א", "52770": "שיח שרפי קודש — מילואים",
    "57970": "אור לשמים", "57983": "אהל תורה", "58254": "אוהל יצחק (ספר שחיטה — לא של וורקי!)",
    "67708": "רמתים צופים",
    "tiferet-hayehudy01": "תפארת היהודי, חלק 1 (Tesseract OCR; Tiferet/hayehudy01.pdf)",
    "tiferet-hayehudy02": "תפארת היהודי, חלק 2 (Tesseract OCR; Tiferet/hayehudy02.pdf)",
    "tiferet-hayehudy03": "תפארת היהודי, חלק 3 (Tesseract OCR; Tiferet/hayehudy03.pdf)",
    "tiferet-hayehudy01-layer": "תפארת היהודי 1 (old text layer)", "tiferet-hayehudy02-layer": "תפארת היהודי 2 (old text layer)", "tiferet-hayehudy03-layer": "תפארת היהודי 3 (old text layer)", "67717": "שיח שרפי קודש ב", "67718": "שיח שרפי קודש ד",
}
FINALS = str.maketrans("ךםןףץ", "כמנפצ")
CONFUSE = str.maketrans({"ה": "ח", "ר": "ד", "ו": "י", "ס": "מ", "ט": "מ", "ע": "צ", "ב": "כ", "ג": "נ"})


def norm(s, loose=True):
    s = re.sub(r"[֑-ׇ]", "", s).replace("״", '"').replace("׳", "'").translate(FINALS)
    s = re.sub(r"[^א-ת ]", " ", s)
    return s.translate(CONFUSE) if loose else s


def words(q):
    ws = [w for w in norm(q).split() if len(w) >= 2]
    return [re.sub(r"^[ובלמהכש]{1,2}(?=..)", "", w) for w in ws]


def pages(n):
    t = (HB / f"{n}.txt").read_text(encoding="utf-8", errors="ignore")
    for m in re.finditer(r"<<<pdf page (\d+)>>>\n(.*?)(?=<<<pdf page|\Z)", t, re.S):
        yield int(m.group(1)), m.group(2)


def best_window(text, ws, width=60):
    toks = text.split()
    nt = [norm(x) for x in toks]
    best, at = -1, 0
    for i in range(0, max(1, len(toks) - width + 1), 5):
        sc = sum(1 for w in ws if any(w in x for x in nt[i:i + width]))
        if sc > best:
            best, at = sc, i
    return " ".join(toks[at:at + width])


def cmd_hb(q, books=None, top=5):
    ws = words(q)
    res = []
    for f in sorted(HB.glob("*.txt")):
        n = f.stem
        if books and n not in books:
            continue
        for p, txt in pages(n):
            nt = norm(txt)
            sc = sum(1 for w in ws if w in nt)
            if sc:
                res.append((sc, n, p, txt))
    res.sort(key=lambda r: -r[0])
    print(f"query words ({len(ws)}): {' '.join(ws)}")
    for sc, n, p, txt in res[:top]:
        print(f"\n== {sc}/{len(ws)}  hb {n} {TITLES.get(n, '')}  pdf page {p}\n{best_window(txt, ws)}")


def flat(x, path=()):
    if isinstance(x, str):
        yield path, x
    elif isinstance(x, list):
        for i, y in enumerate(x):
            yield from flat(y, path + (i + 1,))
    elif isinstance(x, dict):
        for k, y in x.items():
            yield from flat(y, path + (k,))


def sef_files():
    return sorted(SEF.rglob("merged.json"))


def work_name(f):
    return f.parent.parent.name


def cmd_sefaria(q, top=5):
    ws = words(q)
    res = []
    for f in sef_files():
        d = json.loads(f.read_text(encoding="utf-8"))
        for path, s in flat(d.get("text", d)):
            clean = re.sub(r"<[^>]+>", "", s)
            nt = norm(clean)
            sc = sum(1 for w in ws if w in nt)
            if sc >= max(2, len(ws) // 2):
                res.append((sc, work_name(f), path, clean))
    res.sort(key=lambda r: -r[0])
    print(f"query words ({len(ws)}): {' '.join(ws)}")
    for sc, w, path, s in res[:top]:
        print(f"\n== {sc}/{len(ws)}  {w} {':'.join(map(str, path))}\n{s[:700]}")


def cmd_ref(work, ref):
    fs = [f for f in sef_files() if work_name(f).lower() == work.lower()]
    if not fs:
        sys.exit(f"no Sefaria text named {work!r}; available: " + ", ".join(sorted(work_name(f) for f in sef_files())))
    d = json.loads(fs[0].read_text(encoding="utf-8"))["text"]
    m = re.fullmatch(r"(\d+)([ab])(?::(\d+))?", ref)
    if m:                                   # Talmud: list of amudim from 1a
        idx = (int(m.group(1)) - 1) * 2 + (m.group(2) == "b")
        seg = d[idx]
        if m.group(3):
            seg = seg[int(m.group(3)) - 1]
    else:
        seg = d
        for part in ref.split(":"):
            seg = seg[int(part) - 1]
    for path, s in flat(seg):
        print((":".join(map(str, path)) + "  " if path else "") + re.sub(r"<[^>]+>", "", s))


def main():
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    opt = lambda k, d=None: a[a.index(k) + 1] if k in a else d
    if a[0] == "hb":
        cmd_hb(a[1], set(opt("--books").split(",")) if opt("--books") else None, int(opt("--top", 5)))
    elif a[0] == "page":
        c = int(opt("--context", 0))
        for p, txt in pages(a[1]):
            if abs(p - int(a[2])) <= c:
                print(f"<<<hb {a[1]} pdf page {p}>>>\n{txt}")
    elif a[0] == "sefaria":
        cmd_sefaria(a[1], int(opt("--top", 5)))
    elif a[0] == "ref":
        cmd_ref(a[1], a[2])
    elif a[0] == "books":
        for f in sorted(HB.glob("*.txt"), key=lambda f: (not f.stem.isdigit(), int(f.stem) if f.stem.isdigit() else 0, f.stem)):
            print(f.stem, TITLES.get(f.stem, ""), sum(1 for _ in pages(f.stem)), "pages")


main()
