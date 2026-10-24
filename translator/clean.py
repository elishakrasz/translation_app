"""Step 1, clean: the proofread OCR pages become one Markdown file per unit in source/cleaned/.

Joins lines and pages, repairs hyphenation at line and page ends, drops running heads and chapter labels, marks
headings and block quotes, gathers the notes, and keeps a <!--page:N--> marker at each printed page break. Every
change is written to records/edits.jsonl; nothing is guessed silently (section 8, Step 1).
"""

import re
from dataclasses import dataclass, field

from ocrkit import records as orec

from . import records

TERMINAL = tuple('.!?:;")]…”’\'')
LABEL_RE = re.compile(r"^(chapter|part|addendum|appendix)\s+[\w.]+$", re.I)
PAGE_NO_RE = re.compile(r"^(\d{1,4}|[ivxlcdm]{1,8})$", re.I)
NOTE_RE = re.compile(r"^(\d+|\*)\.\s+(.*)$")
CONT_RE = re.compile(r"^\(cont\.\)\s*(.*)$")
WORD_RE = re.compile(r"[A-Za-z]+(?:-[A-Za-z]+)*")
REF_RE = re.compile(r"\^(\d+|\*)\^")
NOTES_SEP = "--- notes ---"


def norm(s):
    """Lower case, punctuation and dashes dropped: for comparing titles and running heads."""
    return re.sub(r"[\W_]+", " ", s.lower()).strip()


@dataclass
class Block:
    kind: str            # page | h1 | h2 | para | quote | lines
    text: str


@dataclass
class Note:
    num: str
    text: str
    pages: list


@dataclass
class UnitResult:
    unit: dict
    blocks: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    edits: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    pages: list = field(default_factory=list)
    joins: int = 0
    quotes_normalised: int = 0


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

def load_pages(project):
    """[(part, page, printed, text)] in book order, the blank pages skipped, and a list of problems."""
    pages, problems, blank = [], [], []
    for src in project.cfg.get("sources_received") or []:
        part = src["ocr"]
        d = project.ocr_dir(part)
        if not (d / "ocr.jsonl").exists():
            problems.append(f"{part}: no OCR yet ({d}/ocr.jsonl)")
            continue
        ocr = orec.latest_by_page(orec.load_records(d / "ocr.jsonl"))
        proof = orec.latest_by_page(orec.load_records(d / "proof.jsonl")) if (d / "proof.jsonl").exists() else {}
        for n in sorted(ocr):
            p = proof.get(n)
            if p and p.get("status") == "ok":
                pages.append((part, n, p.get("printed_page") or f"{part}:{n}", p["text"]))
            elif len(ocr[n]["text"].split()) < 30:
                blank.append(f"{part} p{n}")
            else:
                problems.append(f"{part} p{n}: not proofread ({p['status'] if p else 'no record'}) - "
                                f"run `ocrkit proofread {d} --repair` or `--pages {n}`")
    return pages, problems, blank


def vocabulary(pages):
    """Words and hyphenated words as they occur inside lines: the evidence for repairing hyphenation."""
    words, hyph = set(), set()
    for *_, text in pages:
        for tok in WORD_RE.findall(re.sub(r"-\n", " ", text)):
            (hyph if "-" in tok else words).add(tok.lower())
    return words, hyph, dictionary()


def dictionary(path="/usr/share/dict/words"):
    """The system word list (macOS has one), as a second opinion when the book itself gives no evidence."""
    try:
        with open(path, encoding="utf-8") as f:
            return {w.strip().lower() for w in f}
    except OSError:
        return set()


# ---------------------------------------------------------------------------
# Joining
# ---------------------------------------------------------------------------

class Joiner:
    def __init__(self, words, hyph, dict_words, res):
        self.words, self.hyph, self.dict, self.res = words, hyph, dict_words, res
        self.page = None

    def keep_hyphen(self, left, right):
        """Is 'left-|right' at a line break a real hyphen? The book's own usage first, then the dictionary."""
        hyph, whole = f"{left}-{right}".lower(), f"{left}{right}".lower()
        if hyph in self.hyph and whole not in self.words:
            return True
        if whole in self.words or self.is_word(whole):
            return False
        # No evidence for the joined word, and both halves are words: a compound, kept and flagged for review.
        return len(left) > 1 and len(right) > 1 and self.is_word(left.lower()) and self.is_word(right.lower())

    def is_word(self, w):
        """In the dictionary, directly or as an inflected form (the system list has 'love' but not 'loved')."""
        if w in self.dict:
            return True
        for suf in ("s", "es", "ed", "d", "ing", "ly", "er", "ers", "est"):
            stem = w[:-len(suf)]
            if w.endswith(suf) and len(stem) > 2 and (stem in self.dict or stem + "e" in self.dict):
                return True
        return False

    def join(self, a, b, marker=""):
        """Join two pieces of one paragraph, repairing a hyphen at the break. A page marker goes at the break."""
        a, b = a.rstrip(), b.lstrip()
        m, n = re.search(r"([A-Za-z]+)-$", a), re.match(r"[a-z][A-Za-z]*", b)
        if m and n and not a.endswith("--"):
            left, right = m.group(1), n.group(0)
            keep = self.keep_hyphen(left, right)
            self.res.edits.append({"unit": self.res.unit["id"], "page": self.page,
                                   "kind": "hyphen-kept" if keep else "dehyphenated",
                                   "before": f"{left}-|{right}", "after": f"{left}-{right}" if keep else left + right})
            head = a if keep else a[:-1]
            return head + right + marker + b[len(right):]
        return a + (f" {marker} " if marker else " ") + b

    def lines(self, lines):
        out = lines[0]
        for nxt in lines[1:]:
            out = self.join(out, nxt)
        return out


def ends_sentence(text):
    """Does the block end a sentence? Footnote references after the final punctuation don't count."""
    return re.sub(r"(\^(\d+|\*)\^)+$", "", text.rstrip()).endswith(TERMINAL)


def is_caps_heading(text):
    letters = [c for c in text if c.isalpha()]
    return len(letters) >= 4 and all(c.isupper() for c in letters) and len(text) < 120 and not text.endswith(".")


def is_margin_scrap(lines):
    """Letters cut off from the facing page at the edge of a two-page scan: three or more very short lines."""
    return len(lines) >= 3 and max(len(l.strip()) for l in lines) <= 8


def body_blocks(body, joiner):
    blocks = []
    for para in re.split(r"\n\s*\n", body.strip()):
        lines = [l.rstrip() for l in para.split("\n") if l.strip()]
        if not lines:
            continue
        if is_margin_scrap(lines):
            joiner.res.edits.append({"unit": joiner.res.unit["id"], "page": joiner.page, "kind": "margin-scrap-dropped",
                                     "before": " / ".join(l.strip() for l in lines), "after": ""})
            continue
        if all(l.lstrip().startswith(">") for l in lines):
            inner = [re.sub(r"^\s*>\s?", "", l) for l in lines]
            inner = [l for l in inner if l.strip()]
            if inner:
                blocks.append(Block("quote", joiner.lines(inner)))
        elif len(lines) >= 2 and is_caps_heading(" ".join(l.strip() for l in lines)):
            blocks.append(Block("h2", " ".join(l.strip() for l in lines)))
        elif (len(lines) >= 2 and all(len(l) < 40 for l in lines) and not any(l.endswith("-") for l in lines)
              and not ends_sentence(lines[-1])):
            # Short lines that are not prose wrapped short: a signature, an address, a title over two lines.
            blocks.append(Block("lines", "<br>".join(l.strip() for l in lines)))
        else:
            text = joiner.lines([l.strip() for l in lines])
            blocks.append(Block("h2" if is_caps_heading(text) else "para", text))
    return blocks


# ---------------------------------------------------------------------------
# One unit
# ---------------------------------------------------------------------------

def clean_unit(project, unit, upages, vocab):
    res = UnitResult(unit)
    joiner = Joiner(*vocab, res)
    titles = {norm(u["title"]) for u in project.units}
    heads = titles | {norm(project.title)} | {norm(h) for h in project.cfg.get("running_heads") or []}
    uid = unit["id"]

    for i, (part, n, printed, text) in enumerate(upages):
        joiner.page = printed
        res.pages.append(printed)
        body, _, notes = text.partition(NOTES_SEP)
        blocks = body_blocks(body, joiner)

        if i == 0:
            # The unit's opening: an optional label ("Chapter 1"), then the title from project.yaml.
            if blocks and blocks[0].kind in ("para", "lines") and LABEL_RE.match(blocks[0].text.replace("<br>", " ")):
                res.edits.append({"unit": uid, "page": printed, "kind": "label-dropped", "before": blocks[0].text,
                                  "after": "", "note": "the chapter label comes from project.yaml at the build"})
                blocks.pop(0)
            want, got, used = norm(unit["title"]), "", 0
            for b in blocks[:3]:
                got = (got + " " + b.text.replace("<br>", " ")).strip()
                used += 1
                if norm(got) == want:
                    break
            if norm(got) == want:
                blocks = [Block("h1", got)] + blocks[used:]
            else:
                res.errors.append(f"title {unit['title']!r} not found at the top of {part} p{n} "
                                  f"(found {blocks[0].text[:60]!r})" if blocks else f"{part} p{n} is empty")
        else:
            while blocks and "\n" not in blocks[0].text and len(blocks[0].text) < 80 and (
                    norm(blocks[0].text) in heads or PAGE_NO_RE.match(blocks[0].text.strip())):
                res.edits.append({"unit": uid, "page": printed, "kind": "running-head-dropped",
                                  "before": blocks[0].text, "after": ""})
                blocks.pop(0)
        while blocks and PAGE_NO_RE.match(blocks[-1].text.strip()):
            res.edits.append({"unit": uid, "page": printed, "kind": "page-number-dropped",
                              "before": blocks[-1].text, "after": ""})
            blocks.pop()

        # A paragraph running on from the previous page is joined to it, with the page marker at the break.
        prev = next((b for b in reversed(res.blocks) if b.kind != "page"), None)
        if (i > 0 and blocks and prev and prev is res.blocks[-1] and blocks[0].kind == prev.kind
                and prev.kind in ("para", "quote")
                and (not ends_sentence(prev.text) or blocks[0].text[:1].islower())):
            if re.search(r"[.!?…][\"')\]”’]*$", re.sub(r"(\^(\d+|\*)\^)+$", "", prev.text)):
                res.warnings.append(f"p. {printed} starts in lower case after a finished sentence; joined to the "
                                    f"paragraph before - check the scan: …{prev.text[-40:]!r} | {blocks[0].text[:40]!r}…")
            prev.text = joiner.join(prev.text, blocks[0].text, f"<!--page:{printed}-->")
            res.joins += 1
            blocks.pop(0)
            res.blocks.extend(blocks)
        else:
            res.blocks.append(Block("page", printed))
            res.blocks.extend(blocks)

        add_notes(res, joiner, notes, printed, part, n)

    normalise_quotes(res)
    check_notes(res, project)
    return res


def add_notes(res, joiner, notes, printed, part, n):
    for line in (l.strip() for l in notes.strip().split("\n") if l.strip()):
        m, c = NOTE_RE.match(line), CONT_RE.match(line)
        if m:
            if any(x.num == m.group(1) for x in res.notes):
                res.errors.append(f"note {m.group(1)} appears twice ({part} p{n})")
            res.notes.append(Note(m.group(1), m.group(2), [printed]))
        elif res.notes:
            last = res.notes[-1]
            if not c and printed not in last.pages:
                res.warnings.append(f"note {last.num} continues on p. {printed} without '(cont.)'")
            last.text = joiner.join(last.text, c.group(1) if c else line)
            if printed not in last.pages:
                last.pages.append(printed)
        else:
            res.errors.append(f"note text with no note number at the top of the notes on {part} p{n}: {line[:60]!r}")


def normalise_quotes(res):
    """One form of quotation marks: the proofreader left some pages curly and others straight."""
    table = str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'"})
    for item in [*res.blocks, *res.notes]:
        new = item.text.translate(table)
        res.quotes_normalised += sum(1 for a, b in zip(item.text, new) if a != b)
        item.text = new
    if res.quotes_normalised:
        res.edits.append({"unit": res.unit["id"], "page": None, "kind": "quotes-normalised",
                          "before": "“ ” ‘ ’", "after": "\" \" ' '", "count": res.quotes_normalised})


def check_notes(res, project):
    refs = [r for b in res.blocks if b.kind != "page" for r in REF_RE.findall(b.text)]
    nums = [x.num for x in res.notes]
    quirks = [q.get("note", "") for q in project.cfg.get("source_quirks") or [] if q.get("unit") == res.unit["id"]]
    for r in sorted(set(refs) - set(nums), key=lambda x: (x == "*", x.zfill(4))):
        res.errors.append(f"reference ^{r}^ has no note")
    for x in sorted(set(nums) - set(refs), key=lambda x: (x == "*", x.zfill(4))):
        res.errors.append(f"note {x} has no reference in the text")
    for r in {r for r in refs if refs.count(r) > 1}:
        res.warnings.append(f"reference ^{r}^ appears {refs.count(r)} times")
    digits = [int(x) for x in nums if x.isdigit()]
    gaps = sorted(set(range(1, max(digits, default=0) + 1)) - set(digits))
    if gaps:
        msg = f"note numbering skips {', '.join(map(str, gaps))}"
        (res.warnings if quirks else res.errors).append(msg + (f" (source quirk: {'; '.join(quirks)})" if quirks else ""))


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def render(res):
    out = []
    for b in res.blocks:
        out.append({"page": f"<!--page:{b.text}-->", "h1": f"# {b.text}", "h2": f"## {b.text}",
                     "quote": f"> {b.text}"}.get(b.kind, b.text))
    for x in res.notes:
        out.append(f"{'\\*' if x.num == '*' else x.num}\\. {x.text}")
    return "\n\n".join(out) + "\n"


def unit_pages(project, pages, errors):
    """{unit id: its pages}, each unit running from its start to the next unit's start."""
    index = {(part, n): i for i, (part, n, *_) in enumerate(pages)}
    starts = []
    for u in project.units:
        s = u.get("start") or {}
        key = (s.get("part"), s.get("page"))
        if key not in index:
            errors.append(f"{u['id']}: start {s} is not among the proofread pages")
            continue
        starts.append((index[key], u["id"]))
    starts.sort()
    out = {}
    for k, (i, uid) in enumerate(starts):
        end = starts[k + 1][0] if k + 1 < len(starts) else len(pages)
        out[uid] = pages[i:end]
    return out


def run(project, units, write=False):
    """Clean the given units. Returns (results, report path, problems that stop the step)."""
    pages, problems, blank = load_pages(project)
    vocab = vocabulary(pages)
    ranges = unit_pages(project, pages, problems)
    results = [clean_unit(project, u, ranges[u["id"]], vocab) for u in units if u["id"] in ranges]

    rep = report(project, results, problems, blank, write)
    if write and not problems and not any(r.errors for r in results):
        for r in results:
            f = project.cleaned_file(r.unit)
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(render(r), encoding="utf-8")
            if r.edits:
                records.append(project, "edits", [{"command": "clean", **e} for e in r.edits], by="translator clean")
    else:
        prev = project.work("clean") / "preview"
        prev.mkdir(parents=True, exist_ok=True)
        for r in results:
            (prev / project.cleaned_file(r.unit).name).write_text(render(r), encoding="utf-8")
    return results, rep, problems


def report(project, results, problems, blank, write):
    lines = [f"# Clean report — {project.title}", "",
             f"{'Written' if write else 'Dry run'}: files {'in source/cleaned/' if write else 'previewed in work/clean/preview/'}.", ""]
    if problems:
        lines += ["## Problems that stop the step", ""] + [f"- {p}" for p in problems] + [""]
    if blank:
        lines += [f"Blank pages skipped: {', '.join(blank)}", ""]
    lines += ["| Unit | Pages | Blocks | Headings | Quotes | Notes | Joined across pages | Dehyphenated | Hyphens kept | Running heads dropped | Errors |",
              "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in results:
        k = lambda kind: sum(1 for b in r.blocks if b.kind == kind)
        e = lambda kind: sum(1 for x in r.edits if x["kind"] == kind)
        span = f"{r.pages[0]}–{r.pages[-1]}" if r.pages else "—"
        lines.append(f"| {r.unit['id']} | {span} | {k('para') + k('quote') + k('lines')} | {k('h1') + k('h2')} | {k('quote')} | "
                     f"{len(r.notes)} | {r.joins} | {e('dehyphenated')} | {e('hyphen-kept')} | {e('running-head-dropped')} | {len(r.errors)} |")
    for r in results:
        lines += ["", f"## {r.unit['id']} — {r.unit['title']}", ""]
        for msg in r.errors:
            lines.append(f"- **error:** {msg}")
        for msg in r.warnings:
            lines.append(f"- warning: {msg}")
        heads = [b.text for b in r.blocks if b.kind in ("h1", "h2")]
        if heads:
            lines.append("- headings: " + " · ".join(heads))
        dropped = [f"p. {x['page']}: {x['before']!r}" for x in r.edits
                   if x["kind"] in ("running-head-dropped", "label-dropped", "page-number-dropped", "margin-scrap-dropped")]
        if dropped:
            lines.append("- dropped: " + "; ".join(dropped))
        kept = [f"{x['after']} (p. {x['page']})" for x in r.edits if x["kind"] == "hyphen-kept"]
        if kept:
            lines.append("- hyphens kept at a line break (check these): " + ", ".join(kept))
        if r.quotes_normalised:
            lines.append(f"- quotation marks made straight: {r.quotes_normalised}")
        multi = [b.text for b in r.blocks if b.kind == "lines"]
        if multi:
            lines.append("- kept with line breaks: " + " · ".join(m.replace("<br>", " / ") for m in multi))
    path = project.work("clean") / "report.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
