"""Step 10, build: a unit's Koren draft (docx and pdf) in drafts/koren/, every block bookmarked by its ID.

The data comes from the output chunks block by block: headings, block quotes, paragraphs and notes, with their
inline marks (^n^ footnotes, ==highlight==, **bold**, *italic*, <br>). translator/koren_docx.js (the Rosen builder plus
bookmarks) writes the docx; LibreOffice converts it to pdf. After the build: every ID has its bookmark, every note
referenced is present, no page of the pdf is blank, and the draft's SHA-256 is recorded in state.yaml (the text of
record: a Word master that differs from it is an edit not yet imported).
"""

import hashlib
import json
import re
import subprocess
import tempfile
import zipfile
from pathlib import Path

from .project import ENGINE

BLOCK_RE = re.compile(r"(.*?)\s*<!--id:([^>]*)-->", re.S)
INLINE = re.compile(r"(<br>|\^\*\^|\*\*.+?\*\*|(?<!\*)\*(?!\s).+?(?<!\s)\*(?!\*)|\^\d+\^)")
SOFFICE = "/Applications/LibreOffice.app/Contents/MacOS/soffice"


def _runs(text):
    out = []
    for part in INLINE.split(text):
        if not part:
            continue
        if part == "<br>":
            out.append({"br": True})
        elif part.startswith("**"):
            out.append({"t": part[2:-2], "b": True})
        elif part == "^*^":
            out.append({"fn": "*"})
        elif part.startswith("^"):
            out.append({"fn": int(part.strip("^"))})
        elif part.startswith("*") and part.endswith("*") and len(part) > 2:
            out.append({"t": part[1:-1], "i": True})
        else:
            out.append({"t": part})
    return out


def runs(text):
    """Inline runs; text between == and == is highlighted (an original that differs from the author)."""
    out = []
    for k, seg in enumerate(text.split("==")):
        for r in _runs(seg):
            if k % 2:
                r["hl"] = True
            out.append(r)
    return out


def bookmark(bid):
    unit, b = bid.split(".")
    return re.sub(r"[^A-Za-z0-9_]", "_", f"{b[0]}_{unit}_{b[1:]}")


def data(project, unit):
    udir = project.unit_dir(unit)
    blocks, notes, note_ids, title = [], {}, {}, unit.get("title", "")
    for p in sorted(udir.glob("output_chunk[0-9]*.md")):
        for m in BLOCK_RE.finditer(p.read_text(encoding="utf-8")):
            text, bid = m.group(1).strip(), m.group(2)
            if ".n" in bid:
                nm = re.match(r"^(\d+|\\\*)\\?\.\s*(.*)$", text, re.S)
                n = "*" if nm.group(1) == "\\*" else int(nm.group(1))
                notes[str(n)] = runs(nm.group(2).replace("\\.", ".").replace("\n", " ").strip())
                note_ids[str(n)] = bid
                continue
            level = len(re.match(r"^(#*)", text).group(1))
            if level:
                t = re.sub(r"^#+\s*", "", text).strip()
                if level == 1:
                    title = t
                blocks.append({"kind": "h", "level": level, "runs": runs(t), "id": bid})
            elif text.startswith(">"):
                t = " ".join(re.sub(r"^>\s?", "", l) for l in text.split("\n")).strip()
                blocks.append({"kind": "q", "level": 0, "runs": runs(t), "id": bid})
            else:
                blocks.append({"kind": "p", "level": 0, "runs": runs(text.replace("\n", " ")), "id": bid})
    used = {str(r["fn"]) for b in blocks for r in b["runs"] if "fn" in r}
    return {"title": title, "label": unit.get("label"), "blocks": blocks,
            "notes": {n: notes[n] for n in sorted(used, key=lambda x: (x != "*", int(x) if x.isdigit() else 0)) if n in notes},
            "note_ids": note_ids, "missing_notes": sorted(used - set(notes)), "unused_notes": sorted(set(notes) - used)}


def bookmarks_in(docx):
    with zipfile.ZipFile(docx) as z:
        xml = z.read("word/document.xml").decode("utf-8") + z.read("word/footnotes.xml").decode("utf-8")
    return set(re.findall(r'<w:bookmarkStart [^>]*w:name="([^"]+)"', xml))


def blank_pages(pdf):
    out = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, text=True).stdout
    pages = out.split("\f")
    return [i + 1 for i, p in enumerate(pages[:-1] if pages and not pages[-1].strip() else pages)
            if len(re.sub(r"\s+|\d+", "", p)) < 5]


def build(project, unit, pdf=True):
    """Build the draft. Returns a report dict; raises if the draft is open in Word."""
    out_dir = project.root / "drafts" / "koren"
    out_dir.mkdir(parents=True, exist_ok=True)
    docx = out_dir / f"{project.unit_name(unit)}-koren.docx"
    if (out_dir / f"~${docx.name}").exists() or (out_dir / f"~${docx.name[2:]}").exists():
        raise RuntimeError(f"{docx.name} is open in Word (a ~$ lock file is next to it): close it and build again")
    d = data(project, unit)
    with tempfile.TemporaryDirectory() as tmp:
        dj = Path(tmp) / "data.json"
        dj.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        r = subprocess.run(["node", str(ENGINE / "translator" / "koren_docx.js"), str(dj), str(docx)],
                           capture_output=True, text=True)
        if r.returncode:
            raise RuntimeError("the Word builder failed: " + r.stderr[-800:])
    report = {"docx": docx, "paragraphs": len(d["blocks"]), "notes": len(d["notes"]),
              "missing_notes": d["missing_notes"], "unused_notes": d["unused_notes"]}
    want = {bookmark(b["id"]) for b in d["blocks"]} | {bookmark(i) for n, i in d["note_ids"].items() if n in d["notes"]}
    have = bookmarks_in(docx)
    report["bookmarks"] = len(want & have)
    report["missing_bookmarks"] = sorted(want - have)
    if pdf and Path(SOFFICE).exists():
        subprocess.run([SOFFICE, "--headless", "--convert-to", "pdf", "--outdir", str(out_dir), str(docx)],
                       capture_output=True, check=True)
        p = docx.with_suffix(".pdf")
        report["pdf"] = p
        report["pages"] = len(subprocess.run(["pdftotext", str(p), "-"], capture_output=True, text=True).stdout.split("\f")) - 1
        report["blank_pages"] = blank_pages(p)
    report["sha256"] = hashlib.sha256(docx.read_bytes()).hexdigest()
    return report
