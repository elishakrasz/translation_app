"""Step 1, chunk: a cleaned unit becomes translate-book chunks, and every block gets its permanent ID.

Body blocks get <unit>.pNNNN in order, notes <unit>.nNNN by their number (n000 for an asterisk note). The ID goes at
the end of the block as <!--id:...--> (section 6.1). Page markers stay in the cleaned file; each block's printed
pages are kept in blocks.jsonl. IDs are assigned once: a unit that already has them is never re-chunked here.
"""

import hashlib
import json
import re

PAGE_LINE = re.compile(r"^<!--page:([^>]*)-->$")
INLINE_PAGE = re.compile(r"<!--page:([^>]*)-->")
NOTE_LINE = re.compile(r"^(\d+|\\\*)\\\.\s")


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def parse(text):
    """The cleaned file as blocks: kind, text (page markers removed), first and last printed page."""
    blocks, page = [], None
    for para in re.split(r"\n\s*\n", text.strip()):
        para = para.strip()
        if m := PAGE_LINE.match(para):
            page = m.group(1)
            continue
        start, inline = page, INLINE_PAGE.findall(para)
        if inline:
            page = inline[-1]
        clean = re.sub(r" {2,}", " ", INLINE_PAGE.sub("", para)).strip()
        if clean.startswith("#"):
            kind = "heading"
        elif clean.startswith(">"):
            kind = "quote"
        elif m := NOTE_LINE.match(clean):
            kind = "note"
        else:
            kind = "para"
        blocks.append({"kind": kind, "text": clean, "page_start": start, "page_end": page})
    return blocks


def assign_ids(uid, blocks):
    p = 0
    for b in blocks:
        if b["kind"] == "note":
            num = NOTE_LINE.match(b["text"]).group(1)
            b["id"] = f"{uid}.n000" if num == "\\*" else f"{uid}.n{int(num):03d}"
        else:
            p += 1
            b["id"] = f"{uid}.p{p:04d}"
    return blocks


def pack(blocks, target, maximum):
    """Group blocks into chunks of whole blocks: body first, notes in chunks of their own."""
    chunks = []
    for group in ([b for b in blocks if b["kind"] != "note"], [b for b in blocks if b["kind"] == "note"]):
        cur, size = [], 0
        for b in group:
            n = len(b["text"]) + 2
            # Close the chunk when it is full, or before a heading once it is most of the way there.
            if cur and (size + n > maximum or size >= target or (b["kind"] == "heading" and size >= 0.6 * target)):
                chunks.append(cur)
                cur, size = [], 0
            cur.append(b)
            size += n
        if cur:
            chunks.append(cur)
    return chunks


def run(project, unit, write=False):
    """Chunk one unit. Returns (summary dict, problem or None)."""
    src = project.cleaned_file(unit)
    if not src.exists():
        return None, f"{unit['id']}: no cleaned file ({src.relative_to(project.root)}); run `translator clean --write` first"
    text = src.read_text(encoding="utf-8")
    blocks = assign_ids(unit["id"], parse(text))
    ids = [b["id"] for b in blocks]
    if len(ids) != len(set(ids)):
        dup = sorted({i for i in ids if ids.count(i) > 1})
        return None, f"{unit['id']}: duplicate IDs {', '.join(dup)} (a note number used twice?)"

    out = project.unit_dir(unit)
    existing = out / "blocks.jsonl"
    if existing.exists():
        old = [json.loads(l) for l in existing.read_text(encoding="utf-8").splitlines() if l.strip()]
        if [(b["id"], b["sha"]) for b in old] == [(b["id"], sha(b["text"])) for b in blocks]:
            return {"unit": unit["id"], "unchanged": True, "blocks": len(blocks), "chunks": None}, None
        return None, (f"{unit['id']}: already chunked, and its IDs are permanent. The cleaned source has changed since; "
                      f"a changed source is re-chunked by the ID-preserving rerun (milestone 4), not by `chunk`.")

    cfg = project.cfg.get("chunking") or {}
    chunks = pack(blocks, cfg.get("target_chars", 6000), cfg.get("max_chars", 8000))
    summary = {"unit": unit["id"], "unchanged": False, "blocks": len(blocks),
               "notes": sum(1 for b in blocks if b["kind"] == "note"),
               "chunks": [(len(c), sum(len(b["text"]) for b in c), c[0]["id"], c[-1]["id"]) for c in chunks]}
    if not write:
        return summary, None

    out.mkdir(parents=True, exist_ok=True)
    entries, rows = [], []
    for k, c in enumerate(chunks, 1):
        name = f"chunk{k:04d}.md"
        body = "\n\n".join(f"{b['text']} <!--id:{b['id']}-->" for b in c) + "\n"
        (out / name).write_text(body, encoding="utf-8")
        entries.append({"id": name[:-3], "order": k, "source_file": name, "source_hash": sha(body),
                        "output_file": f"output_{name}"})
        rows += [{"id": b["id"], "kind": b["kind"], "chunk": name[:-3], "page_start": b["page_start"],
                  "page_end": b["page_end"], "sha": sha(b["text"])} for b in c]
    # translate-book's manifest format, so its glossary and merge scripts read these chunks as their own.
    (out / "manifest.json").write_text(json.dumps({"chunk_count": len(entries), "source_hash": sha(text),
                                                   "chunks": entries}, indent=2), encoding="utf-8")
    existing.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    return summary, None
