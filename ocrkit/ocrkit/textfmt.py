"""The proofread page-text format, and helpers to read it.

    Body paragraphs, separated by blank lines. Footnote references as ^n^.
    > Block quotes start with "> ".
    Doubtful readings as {?word}.
    --- notes ---
    12. Text of note 12.
    (cont.) Text of a note continued from the previous page.

The printed page number is returned by the model as a last line "p. N"; it is
moved into the record's printed_page field and is not part of the page text.
Running heads are dropped.
"""

import re
from collections import Counter

NOTES_SEP = "--- notes ---"
REF_RE = re.compile(r"\^(\d+)\^")
NOTE_LINE_RE = re.compile(r"^(\d+)\.\s", re.M)
CONT_LINE_RE = re.compile(r"^\(cont\.\)\s", re.M)
DOUBT_RE = re.compile(r"\{\?([^{}]*)\}")
PRINTED_RE = re.compile(r"^p\.\s*(\S+)\s*$", re.I)
BRACKET_REF_RE = re.compile(r"\[\d{1,3}\]")
# A standalone number of 3+ digits: years, page numbers, section numbers.
LONG_NUMBER_RE = re.compile(r"(?<![\w^])(\d{3,})(?![\w^])")

HEB_RE = re.compile(r"[א-ת]")
LAT_RE = re.compile(r"[A-Za-z]")


def split_printed_page(text):
    """(text without the 'p. N' line, N or None)."""
    lines = text.rstrip().split("\n")
    if lines and PRINTED_RE.match(lines[-1].strip()):
        n = PRINTED_RE.match(lines[-1].strip()).group(1)
        return "\n".join(lines[:-1]).rstrip(), n
    return text.rstrip(), None


def split_body_notes(text):
    """(body, notes) - notes is '' when the page has no notes section."""
    if NOTES_SEP not in text:
        return text, ""
    body, notes = text.split(NOTES_SEP, 1)
    return body.rstrip(), notes.strip()


def separator_count(text):
    return sum(1 for line in text.split("\n") if line.strip() == NOTES_SEP)


def refs(body):
    return [int(n) for n in REF_RE.findall(body)]


def note_numbers(notes):
    return [int(n) for n in NOTE_LINE_RE.findall(notes)]


def has_continuation(notes):
    return bool(CONT_LINE_RE.search(notes))


def doubtful(text):
    return DOUBT_RE.findall(text)


def hebrew_share(text):
    """Share of Hebrew among Hebrew+Latin letters, or None if the page has under 30 letters."""
    h, l = len(HEB_RE.findall(text)), len(LAT_RE.findall(text))
    return None if h + l < 30 else h / (h + l)


def long_numbers(text):
    return Counter(LONG_NUMBER_RE.findall(text))


def strip_markup(text):
    """Proofread text reduced to plain words, for comparison with the OCR."""
    text = REF_RE.sub("", text)
    text = DOUBT_RE.sub(r"\1", text)
    text = CONT_LINE_RE.sub("", text)
    text = "\n".join(l for l in text.split("\n") if l.strip() != NOTES_SEP)
    text = re.sub(r"^> ", "", text, flags=re.M)
    return text
