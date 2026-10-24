"""JSONL page records: append-as-you-go, crash-tolerant load, atomic compaction."""

import json
import os
import re
from pathlib import Path

PAGE_MARK = "=" * 70
LEGACY_PAGE_RE = re.compile(r"={70}\nPAGE (\d+)\n={70}\n")


def append_record(path, record):
    """Append one record and flush it to disk, so a crash loses at most this page."""
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def load_records(path):
    """All records in file order. A torn last line (crash mid-write) is skipped."""
    path = Path(path)
    if not path.exists():
        return []
    out = []
    lines = path.read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            if i == len(lines):
                print(f"  ⚠ {path.name}: last line is incomplete (interrupted write) - ignored")
            else:
                raise ValueError(f"{path}: line {i} is not valid JSON")
    return out


def latest_by_page(records):
    """{page: record}, the last record for each page winning."""
    out = {}
    for r in records:
        out[r["page"]] = r
    return out


def write_records_atomic(path, records):
    """Rewrite a records file in one step (write to a temp file, then rename)."""
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def compact(path):
    """Keep one record per page (the latest), sorted by page."""
    latest = latest_by_page(load_records(path))
    write_records_atomic(path, [latest[n] for n in sorted(latest)])
    return latest


def render_pages(pages, printed=None):
    """Text file with PAGE markers: {page: text} -> str."""
    printed = printed or {}
    parts = []
    for n in sorted(pages):
        head = f"PAGE {n}" + (f"  (p. {printed[n]})" if printed.get(n) else "")
        parts.append(f"{PAGE_MARK}\n{head}\n{PAGE_MARK}\n\n{pages[n].strip()}\n")
    return "\n".join(parts)


def split_legacy_txt(text):
    """{page: text} from an old final_ocr.py/proofreader.py text file."""
    pages = {}
    matches = list(LEGACY_PAGE_RE.finditer(text))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[m.end():end].strip()
        if body:
            pages[int(m.group(1))] = body
    return pages
