"""The project's JSONL records (section 6.4). The engine assigns every record id."""

import datetime as dt
import json
import re

PREFIX = {"decisions": "d", "author-questions": "aq", "quotations": "q", "findings": "f",
          "edits": "e", "bibliography": "b"}
ID_KEY = {"decisions": "did", "author-questions": "aqid", "quotations": "qid", "findings": "fid",
          "edits": "eid", "bibliography": "bid"}


def now():
    return dt.datetime.now().isoformat(timespec="seconds")


def path(project, name):
    return project.records / f"{name}.jsonl"


def load(project, name):
    p = path(project, name)
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def _next_number(rows, name):
    key, pre = ID_KEY[name], PREFIX[name]
    nums = [int(m.group(1)) for r in rows if (m := re.fullmatch(rf"{pre}(\d+)", str(r.get(key, ""))))]
    return max(nums, default=0) + 1


def append(project, name, rows, by):
    """Append rows to records/<name>.jsonl, giving each an id, `at` and `by`. Returns the ids."""
    project.records.mkdir(parents=True, exist_ok=True)
    existing = load(project, name)
    n, key, pre = _next_number(existing, name), ID_KEY[name], PREFIX[name]
    ids = []
    with path(project, name).open("a", encoding="utf-8") as f:
        for r in rows:
            rid = f"{pre}{n:04d}"
            f.write(json.dumps({key: rid, **r, "at": now(), "by": by}, ensure_ascii=False) + "\n")
            ids.append(rid)
            n += 1
    return ids
