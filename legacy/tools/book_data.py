"""Export a chapter's Hebrew text with its notes as footnotes, for tools/build_book_docx.js.

Usage: python3 tools/book_data.py <temp_dir> <out.json> "<Title>" [notes_override.json]

Body paragraphs come from output_chunkNNNN.md up to the notes heading; ^n^ markers
become footnote references. Note texts come from the chapter's notes section, or
from notes_override.json ({"notes":[{"n":1,"koren":"..."}]}) when given (pilot of
the Koren-style notes before they are written into the chapter).
"""
import json
import re
import sys
from pathlib import Path

INLINE = re.compile(r"(<br>|\^\*\^|\*\*.+?\*\*|(?<!\*)\*(?!\s).+?(?<!\s)\*(?!\*)|\^\d+\^)")


def _runs(text):
    out = []
    for part in INLINE.split(text):
        if not part:
            continue
        if part == "<br>":                      # a line break inside a paragraph (the translator's own break)
            out.append({"br": True})
        elif part.startswith("**"):
            out.append({"t": part[2:-2], "b": True})
        elif part == "^*^":                      # editor's asterisk note (e.g. the source of a motto)
            out.append({"fn": "*"})
        elif part.startswith("^"):
            out.append({"fn": int(part.strip("^"))})
        elif part.startswith("*") and part.endswith("*") and len(part) > 2:
            out.append({"t": part[1:-1], "i": True})
        else:
            out.append({"t": part})
    return out



def runs(text):
    """Inline runs; text between == and == is the editor's highlight ("hl": True)."""
    out = []
    for k, seg in enumerate(text.split("==")):
        for r in _runs(seg):
            if k % 2:
                r["hl"] = True
            out.append(r)
    return out

def main():
    temp, out, title = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
    override = json.loads(Path(sys.argv[4]).read_text(encoding="utf-8")) if len(sys.argv) > 4 else None
    text = "\n\n".join((temp / f"output_{p.name}").read_text(encoding="utf-8") for p in sorted(temp.glob("chunk[0-9][0-9][0-9][0-9].md")))
    parts = re.split(r"(?m)^#+\s*(?:הערות|Notes)\s*$", text)
    body, notes_text = parts[0], (parts[1] if len(parts) > 1 else "")
    blocks = []
    for p in [x.strip() for x in re.split(r"\n\s*\n", body) if x.strip()]:
        if re.fullmatch(r"(\\?\*\s*){3}", p):                    # section separator "* * *"
            blocks.append({"kind": "sep", "level": 0, "runs": []})
            continue
        if all(re.match(r"^\s*[-*] ", l) for l in p.split("\n")):   # a list: one block per item, depth from indentation
            for l in p.split("\n"):
                depth = (len(l) - len(l.lstrip(" "))) // 2
                blocks.append({"kind": "li", "level": depth, "runs": runs(re.sub(r"^\s*[-*]\s+", "", l).replace("\\.", ".").strip())})
            continue
        quote = p.startswith(">")
        level = len(re.match(r"^(#*)", p).group(1))
        lines = [re.sub(r"^>\s?", "", l) for l in p.split("\n")] if quote else [p.replace("\n", " ")]
        for l in lines:
            l = re.sub(r"^#+\s*", "", l).replace("\\.", ".").strip()
            if l:
                blocks.append({"kind": "h" if level else ("q" if quote else "p"), "level": level, "runs": runs(l)})
    notes, more, cur = {}, {}, None   # a note may continue over several paragraphs (quoted letters, block quotes)
    for para in [x.strip() for x in re.split(r"\n\s*\n", notes_text) if x.strip()]:
        m = re.match(r"^(\d+)\\?\.\s*(.+)$", para, re.S)
        if m:
            cur = int(m.group(1)); notes[cur] = m.group(2).replace("\\.", ".").replace("\n", " ").strip()
        elif re.match(r"^\\?\*", para):   # an asterisk note is a note of its own, never a continuation
            cur = None
        elif cur is not None:
            q = para.startswith(">")
            more.setdefault(cur, []).append({"q": q, "text": re.sub(r"(?m)^>\s?", "", para).replace("\\.", ".").replace("\n", " ").strip()})
    star = re.search(r"(?m)^\\?\*\\?\.\s*(.+)$", notes_text)
    if star:
        notes["*"] = star.group(1).replace("\\.", ".").strip()
    if override:
        for x in override["notes"]:
            notes[int(x["n"])] = x["koren"]
    fns = {r["fn"] for b in blocks for r in b["runs"] if "fn" in r}
    used = (["*"] if "*" in fns else []) + sorted(n for n in fns if n != "*")
    missing = [n for n in used if n not in notes]
    data = {"title": title, "blocks": blocks, "notes": {str(n): runs(notes[n]) for n in used if n in notes},
            "notes_more": {str(n): [{"q": x["q"], "runs": runs(x["text"])} for x in more[n]] for n in used if n in more}}
    out.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    print(out, len(blocks), "paragraphs,", len(data["notes"]), "footnotes", f"(missing {missing})" if missing else "")


main()
