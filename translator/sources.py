"""Step 5, sources: the provisional quotations of rabbinic, kabbalistic and Hasidic sources are replaced by the
verified originals.

The translators wrote Polen's English back into Hebrew as a placeholder and flagged it
`[לבדיקה: מקור — תרגום זמני]`. `list` finds them, with the English and the note that gives the reference. An agent
locates each on Sefaria (`find`, `text`) and writes a bundle (work/sources/<unit>-bundle.json): the Sefaria ref, the
original exactly as there (unpointed: rabbinic texts are not vocalised in this book), and the Hebrew to put in place.
`integrate` checks every word of each original against Sefaria's text before anything is written, replaces the
placeholder, removes the flag, and records the quotation (records/quotations.jsonl) with its SHA-256: that record is
the lock. Where the original differs from Polen's reading, an author question is written with it as evidence.
"""

import hashlib
import html
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

from . import records
from .verses import CANTILLATION, POINTS, nfc

FLAG_RE = re.compile(r"\s*\[לבדיקה:\s*(?:מקור|נוסח)[^\]]*\]")
QUOTE_RE = re.compile(r'"([^"\n]{2,1500})"')
LIB = Path(__file__).resolve().parent.parent / "library" / "sefaria" / "texts"
API = "https://www.sefaria.org/api"


# ---------------------------------------------------------------------------
# Sefaria
# ---------------------------------------------------------------------------

def _get(url, data=None):
    req = urllib.request.Request(url, data=json.dumps(data).encode() if data else None,
                                 headers={"Content-Type": "application/json"} if data else {})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def flatten(t):
    if isinstance(t, str):
        return [t]
    return [s for x in t for s in flatten(x)]


def clean(text):
    """Sefaria's text as plain, unpointed Hebrew: no markup, cantillation or vowels."""
    text = re.sub(r"<[^>]+>", "", html.unescape(text))
    text = POINTS.sub("", CANTILLATION.sub("", nfc(text)))
    return re.sub(r"\s+", " ", text).strip()


def text(ref):
    """{'ref', 'version', 'segments': [unpointed text]} for a Sefaria ref, cached in the library."""
    f = LIB / (re.sub(r"[^\w.\-]+", "_", ref) + ".json")
    if not f.exists():
        d = _get(f"{API}/v3/texts/{urllib.parse.quote(ref)}?version=hebrew")
        v = d["versions"][0]
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({"ref": d.get("ref", ref), "version": v.get("versionTitle"),
                                 "segments": [clean(s) for s in flatten(v["text"])]}, ensure_ascii=False), encoding="utf-8")
    return json.loads(f.read_text(encoding="utf-8"))


def find(query, size=8):
    """[(ref, version, snippet)] for Hebrew words, from Sefaria's search (lemmatised, words within a short distance)."""
    d = _get(f"{API}/search-wrapper", {"query": query, "type": "text", "field": "naive_lemmatizer", "size": size,
                                       "source_proj": True, "slop": 10})
    out = []
    for h in d.get("hits", {}).get("hits", []):
        s = h.get("_source", {})
        snippet = clean(" ".join(h.get("highlight", {}).get("naive_lemmatizer", []))) or clean(s.get("exact", ""))[:160]
        out.append((s.get("ref"), s.get("version"), snippet[:200]))
    return out


# ---------------------------------------------------------------------------
# Matching an original against the source
# ---------------------------------------------------------------------------

def norm(s):
    """Letters and spaces only: punctuation, vowels, quotation marks and brackets don't decide a match."""
    s = POINTS.sub("", CANTILLATION.sub("", nfc(s)))
    s = re.sub(r"[^א-ת ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def verify(quote, segments):
    """Is every part of the quote (parts separated by … or ...) found, in order, in the source text? Returns the
    parts not found ([] = verified). Words inside [ ] are Polen's additions and are not looked for."""
    source = norm(" ".join(segments))
    q = re.sub(r"\[[^\]]*\]", "…", quote)
    parts = [norm(p) for p in re.split(r"…|\.\.\.", q)]
    missing, pos = [], 0
    for p in (x for x in parts if x):
        i = source.find(p, pos)
        if i < 0:
            missing.append(p)
        else:
            pos = i + len(p)
    return missing


# ---------------------------------------------------------------------------
# The placeholders
# ---------------------------------------------------------------------------

def _blocks(path):
    return [(m.group(2), m.group(1), m.start(1), m.end(1))
            for m in re.finditer(r"(.*?)\s*<!--id:([^>]*)-->", path.read_text(encoding="utf-8"), re.S)]


def placeholders(project, unit):
    """Every provisional quotation in a unit: its block, the flag, the quoted Hebrew before it, and the English."""
    udir = project.unit_dir(unit)
    english, notes = {}, {}
    for p in sorted(udir.glob("chunk[0-9]*.md")):
        for bid, body, *_ in _blocks(p):
            english[bid] = body.strip()
            m = re.match(r"(\d+)\\\.", body.strip())
            if ".n" in bid and m:
                notes[m.group(1)] = body.strip()
    items = []
    for p in sorted(udir.glob("output_chunk[0-9]*.md")):
        for bid, body, *_ in _blocks(p):
            for k, flag in enumerate(FLAG_RE.finditer(body)):
                before = body[:flag.start()]
                quotes = list(QUOTE_RE.finditer(before))
                placeholder = quotes[-1].group(0) if quotes else before.strip().split("\n")[-1][-300:]
                refs = re.findall(r"\^(\d+)\^", english.get(bid, ""))
                items.append({"item": f"{bid}#{k + 1}", "block": bid, "chunk": p.name,
                              "flag": flag.group(0).strip(), "placeholder": placeholder,
                              "english": english.get(bid, ""), "notes": {n: notes.get(n, "") for n in refs}})
    return items


def write_list(project, unit):
    items = placeholders(project, unit)
    out = project.work("sources") / f"{unit['id']}-placeholders.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    return items, out


# ---------------------------------------------------------------------------
# Integrating the originals
# ---------------------------------------------------------------------------

def sha(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def integrate(project, unit, bundle_path, write=False):
    """Check every bundle entry against Sefaria and (with write) put the verified originals in. Returns a report:
    [(item, status, detail)]. Nothing is written unless every verified entry checks out."""
    bundle = json.loads(Path(bundle_path).read_text(encoding="utf-8"))
    udir = project.unit_dir(unit)
    report, changes = [], []
    for e in bundle["items"]:
        if e.get("status") != "verified-text":
            report.append((e["item"], e.get("status", "?"), e.get("note", "")))
            continue
        src = text(e["ref"])
        missing = verify(e["quote"], src["segments"])
        if missing:
            report.append((e["item"], "FAILS", f"not in {e['ref']}: {' | '.join(missing)[:200]}"))
            continue
        if any(m for m in verify(e["quote"], [e["replacement"]])):
            report.append((e["item"], "FAILS", "the replacement does not contain the quote as verified"))
            continue
        f = udir / e["chunk"]
        body = f.read_text(encoding="utf-8")
        target = e["placeholder"] + (" " if not e["placeholder"].endswith(" ") else "") + e["flag"]
        # The placeholder must stand right before its own flag, and exactly once: then only that flag is removed.
        old = next((t for t in (e["placeholder"] + " " + e["flag"], e["placeholder"] + e["flag"]) if body.count(t) == 1), None)
        if old is None:
            report.append((e["item"], "FAILS", "placeholder + flag not found together, exactly once, in " + e["chunk"]))
            continue
        changes.append((e, f, old, src))
        report.append((e["item"], "ok", f"{e['ref']} ({src['version']})"))
    if write and not any(s == "FAILS" for _, s, _ in report):
        qrows, arows, erows = [], [], []
        for e, f, old, src in changes:
            body = f.read_text(encoding="utf-8")
            f.write_text(body.replace(old, e["replacement"], 1), encoding="utf-8")
            erows.append({"command": "translator sources integrate", "unit": unit["id"], "block": e["block"],
                          "before": old, "after": e["replacement"], "reason": f"original from {e['ref']}"})
            qrows.append({"unit": unit["id"], "block": e["block"], "work": e.get("work", ""), "locator": e["ref"],
                          "edition": f"Sefaria: {src['version']}", "library": f"library/sefaria/texts ({e['ref']})",
                          "status": "verified-text", "text": e["quote"], "sha256": sha(norm(e["quote"])),
                          "author_differs": bool(e.get("author_differs")), "difference": e.get("difference", ""),
                          "glosses": [], "inserted": records.now()[:10]})
        ids = records.append(project, "quotations", qrows, by="translator sources integrate") if qrows else []
        for (e, *_), qid in zip(changes, ids):
            if e.get("author_differs"):
                arows.append({"unit": unit["id"], "block": e["block"], "kind": e.get("kind", "reading-the-argument-depends-on"),
                              "text": e.get("difference", ""), "evidence": [qid], "raised_by": "sources", "status": "open"})
        if arows:
            records.append(project, "author-questions", arows, by="translator sources integrate")
        if erows:
            records.append(project, "edits", erows, by="translator sources integrate")
    return report
