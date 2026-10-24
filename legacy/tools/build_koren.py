"""Build the Koren-layout drafts (docx + pdf) in drafts/koren/ from the current chapter files.

Usage: python3 tools/build_koren.py [chNN ...]      (default: ch01–ch12, the chapters whose notes are in Koren form)

Each draft gets its chapter label ("פרק א'" …) above the title. A draft that is open in Word
(a ~$ lock file next to it) is skipped, so an open document is never overwritten.
"""
import os
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = (Path(os.environ["TRANSLATOR_PROJECT"]).expanduser().resolve() if os.environ.get("TRANSLATOR_PROJECT")
        else sys.exit("Set TRANSLATOR_PROJECT to the book folder, e.g. TRANSLATOR_PROJECT=~/the_translator"))
OUT = ROOT / "drafts" / "koren"
SOFFICE = "/Applications/LibreOffice.app/Contents/MacOS/soffice"
LABELS = {1: "פרק א'", 2: "פרק ב'", 3: "פרק ג'", 4: "פרק ד'", 5: "פרק ה'", 6: "פרק ו'", 7: "פרק ז'", 8: "פרק ח'",
          9: "פרק ט'", 10: "פרק י'", 11: 'פרק י"א', 12: 'פרק י"ב',
          13: "נספח א'", 14: "נספח ב'", 15: "נספח ג'", 16: "נספח ד'", 17: "נספח ה'", 18: "נספח ו'"}


def build(ch, tmp):
    n = int(ch[2:])
    temp = next(ROOT.glob(f"{ch}-*_temp"))
    stem = temp.name.removesuffix("_temp")
    docx = OUT / f"{stem}-koren.docx"
    if (OUT / f"~${docx.name[2:]}").exists() or (OUT / f"~${docx.name}").exists():
        print(f"{ch}: SKIPPED — {docx.name} is open in Word; close it and run again")
        return None
    first = (temp / "output_chunk0001.md").read_text(encoding="utf-8")
    title = next((l[2:].strip() for l in first.splitlines() if l.startswith("# ")), "")
    data = Path(tmp) / f"{ch}.json"
    subprocess.run(["python3", str(Path(__file__).resolve().parent / "book_data.py"), str(temp), str(data), title], check=True, capture_output=True)
    d = json.loads(data.read_text(encoding="utf-8"))
    if n == 0:   # front matter: centred title page, then each section (copyright, contents, preface, lineage) on a new page
        heads = [i for i, b in enumerate(d["blocks"]) if b["kind"] == "h"]
        d["centerUntil"] = heads[2] if len(heads) > 2 else 0
        d["pageBreakBefore"] = heads[2:]
    else:
        d["label"] = LABELS[n]
    data.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    r = subprocess.run(["node", str(Path(__file__).resolve().parent / "build_book_docx.js"), str(data), str(docx)], check=True, capture_output=True, text=True)
    print(f"{ch}: {LABELS.get(n, 'front matter')} · {title} — {r.stdout.strip().split(' ', 1)[1]}")
    return docx


def main():
    chs = sys.argv[1:] or [f"ch{i:02d}" for i in range(1, 13)]
    with tempfile.TemporaryDirectory() as tmp:
        built = [p for p in (build(c, tmp) for c in chs) if p]
    if built:
        subprocess.run([SOFFICE, "--headless", "--convert-to", "pdf", "--outdir", str(OUT), *map(str, built)],
                       check=True, capture_output=True)
        print("pdf:", len(built), "converted")


if __name__ == "__main__":
    main()
