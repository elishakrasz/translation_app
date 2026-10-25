"""Step 4, translate: the prompt for each chunk, assembled from the project's foundations.

A prompt is the brief (style/translation-brief.md), the style sheet, the decided terms that bear on the chunk (the
divine names and the book's rubric always), the chunk's term table from the glossary, read-only excerpts of the
neighbouring chunks, and the chunk itself with the paths to write. Prompts go to work/translate/<unit>/.
"""

import json
import re

import yaml

ID_RE = re.compile(r"\s*<!--id:[^>]*-->")
ALWAYS = ("Divine names", "The book's rubric")      # decided-term groups included in every prompt


class FoundationsMissing(Exception):
    pass


def foundations(project):
    need = {"brief": project.root / "style" / "translation-brief.md",
            "style sheet": project.root / "style" / "style-sheet.md",
            "glossary": project.root / "terms" / "glossary.json",
            "decided terms": project.root / "terms" / "decided-terms.yaml"}
    missing = [f"{k} ({p.relative_to(project.root)})" for k, p in need.items() if not p.exists()]
    if missing:
        raise FoundationsMissing("Step 2 isn't finished: missing " + ", ".join(missing))
    decided = yaml.safe_load(need["decided terms"].read_text(encoding="utf-8"))
    if not str(decided.get("status", "")).startswith("decided"):
        raise FoundationsMissing("terms/decided-terms.yaml is still a draft: confirm it first")
    return {"brief": need["brief"].read_text(encoding="utf-8"),
            "style": need["style sheet"].read_text(encoding="utf-8"),
            "glossary": json.loads(need["glossary"].read_text(encoding="utf-8"))["terms"],
            "decided": decided}


def occurs(form, text, category):
    """Does an English form occur in the text as a whole word? Names, places and works match case-sensitively."""
    flags = 0 if category in ("person", "place", "work") else re.I
    return re.search(rf"(?<![\w-]){re.escape(form)}(?![\w-])", text, flags) is not None


# Sentences about how a rendering was chosen, not how to use it: the translator doesn't need the review history.
REVIEW_TALK = re.compile(r"\b(reviews?|reviewers?|Fresh|first pass|extractors?|agree|withdraw|proposed form|"
                         r"no recommendation|Kept against|Proposed\.?$|Decide\.?$|\bcount)", re.I)


REVIEW_PREFIX = re.compile(r"^(?:Fresh assessment|Second review|Both new reviews|All (?:three )?agree|"
                           r"Kept against[^:.;]*|[^:.;]{0,60}\b(?:agree|converge|first pass|review|assessment)[^:.;]*)\s*[:.;]\s*", re.I)


def usage_note(raw, limit=200):
    """The usage guidance in a glossary note, for the translator: the reviewed recommendation if there is one
    (its reviewer prefixes stripped, sentences about the review dropped), otherwise the first extractor's note."""
    segments = [s.strip() for s in re.split(r"\s·\s", re.sub(r"\s+", " ", raw or "")) if s.strip()]
    if not segments:
        return ""
    first = segments[0]
    if first.startswith("recommended (three reviews):"):
        text = first.removeprefix("recommended (three reviews):").strip()
        while (m := REVIEW_PREFIX.match(text)):
            text = text[m.end():]
        parts = [p for p in re.split(r"(?<=[.;])\s+", text) if p and not REVIEW_TALK.search(p)]
        note = " ".join(parts)
    else:
        rest = [s for s in segments if not REVIEW_TALK.search(s)]
        note = rest[0] if rest else ""
    return note if len(note) <= limit else note[:limit].rsplit(" ", 1)[0] + "…"


def term_table(glossary, text):
    rows = []
    for t in glossary:
        forms = [t["source"], *t.get("aliases", [])]
        if any(occurs(f, text, t.get("category")) for f in forms):
            rows.append((t["source"], ", ".join(t.get("aliases", [])), t["target"], usage_note(t.get("notes", ""))))
    return rows


def decided_for(decided, text):
    out = []
    for group in decided.get("groups", []):
        always = group["group"].startswith(ALWAYS)
        terms = [t for t in group["terms"] if always or occurs(t["source"], text, "concept")]
        if terms:
            out.append((group["group"], terms))
    return out


def excerpt(path, chars, tail):
    if not path.exists():
        return ""
    s = ID_RE.sub("", path.read_text(encoding="utf-8")).strip()
    return ("…" + s[-chars:]) if tail and len(s) > chars else (s[:chars] + "…") if len(s) > chars else s


def build(project, unit, f, chunks=None, context_chars=500):
    """Write the prompts for a unit. Returns [(chunk name, path, terms in table, decided terms)]."""
    udir = project.unit_dir(unit)
    names = sorted(p.name for p in udir.glob("chunk[0-9]*.md"))
    if chunks:
        wanted = {f"chunk{int(c):04d}.md" for c in chunks}
        names = [n for n in names if n in wanted]
    out_dir = project.work("translate") / project.unit_name(unit)
    out_dir.mkdir(parents=True, exist_ok=True)
    built = []
    all_names = sorted(p.name for p in udir.glob("chunk[0-9]*.md"))
    for name in names:
        text = (udir / name).read_text(encoding="utf-8")
        i = all_names.index(name)
        prev = excerpt(udir / all_names[i - 1], context_chars, tail=True) if i > 0 else ""
        nxt = excerpt(udir / all_names[i + 1], context_chars, tail=False) if i + 1 < len(all_names) else ""
        table = term_table(f["glossary"], text)
        decided = decided_for(f["decided"], text)
        rel = lambda p: p.relative_to(project.root)
        parts = [f["brief"].strip(), "", "---", "", "# Style sheet (binding)", "", f["style"].strip(), "",
                 "# Decided terms for this chunk (binding: they override the glossary and every reviewer)", "",
                 "| English | Hebrew | Never | Note |", "| --- | --- | --- | --- |"]
        for group, terms in decided:
            parts.append(f"| **{group}** | | | |")
            parts += [f"| {t['source']} | {t['target']} | {', '.join(t.get('never', []))} | {t.get('note', '')} |" for t in terms]
        parts += ["", "# Term table for this chunk (from the book's glossary)", ""]
        if table:
            parts += ["| מונח באנגלית | צורות נוספות | עברית | הערה |", "| --- | --- | --- | --- |"]
            parts += [f"| {a} | {b} | {c} | {d} |" for a, b, c, d in table]
        else:
            parts.append("(no glossary terms in this chunk)")
        parts += ["", "# Context — read only, do not translate", ""]
        if prev:
            parts += ["End of the previous chunk:", "", "> " + prev.replace("\n", "\n> "), ""]
        if nxt:
            parts += ["Start of the next chunk:", "", "> " + nxt.replace("\n", "\n> "), ""]
        if not (prev or nxt):
            parts.append("(this is the unit's only chunk)")
        parts += ["", "# Your chunk", "",
                  f"Unit {unit['id']} ({unit.get('title', '')}), {name[:-3]} of {len(all_names)}.",
                  f"- Source: `{rel(udir / name)}`",
                  f"- Write the Hebrew to: `{rel(udir / ('output_' + name))}`",
                  f"- Write your notes to: `{rel(udir / 'notes' / (name[:-3] + '-notes.md'))}`", "",
                  "The chunk, exactly as in the source file:", "", "````markdown", text.rstrip(), "````", ""]
        path = out_dir / f"prompt_{name[5:9]}.md"
        path.write_text("\n".join(parts), encoding="utf-8")
        built.append((name[:-3], path, len(table), sum(len(t) for _, t in decided)))
    (udir / "notes").mkdir(exist_ok=True)
    return built
