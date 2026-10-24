"""Word-level record of what the proofreader changed."""

import difflib
import re

from .textfmt import strip_markup

MAX_CHANGES = 400   # per page, to keep records readable


def words(text):
    return re.findall(r"\S+", text)


def word_changes(ocr_text, proof_text):
    """
    Compare OCR and proofread text word by word.
    Returns (change_rate, changes): change_rate = changed words / OCR words;
    changes = [[op, ocr_words, new_words], ...] with op replace/delete/insert.
    """
    a, b = words(ocr_text), words(strip_markup(proof_text))
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    changes, changed = [], 0
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            continue
        changed += max(i2 - i1, j2 - j1)
        if len(changes) < MAX_CHANGES:
            changes.append([op, " ".join(a[i1:i2]), " ".join(b[j1:j2])])
    return round(changed / max(len(a), 1), 4), changes
