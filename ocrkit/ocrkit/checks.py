"""
Checks on a proofread page.

Hard failures mean the response is unusable: the page is retried with the
reason as feedback, and in the end the OCR text is kept. Warnings mean the
page is usable but a person should look at it: they go into the record and
the review report and never trigger a retry.
"""

from . import textfmt as tf

META_PHRASES = (
    "please provide", "here is the corrected", "here's the corrected", "i cannot",
    "i can't", "i'm unable", "i am unable", "as an ai", "the text appears to",
    "no text to proofread", "corrected text:",
)
# CJK / Hangul / fullwidth: never in these books, a sign of a degenerate response.
CJK_RANGES = ((0x2E80, 0x9FFF), (0xAC00, 0xD7AF), (0xF900, 0xFAFF), (0xFF00, 0xFFEF))
SCRIPT_FLIP = 0.35   # max change in Hebrew share of letters


def _is_cjk(ch):
    o = ord(ch)
    return any(lo <= o <= hi for lo, hi in CJK_RANGES)


def _plain(text):
    return text.lower().translate(str.maketrans("‘’“”", "''\"\""))


def check_page(ocr_text, response, stop_reason="end_turn", vision=False):
    """
    Returns a dict:
      ok, reason        - hard verdict
      text, printed     - page text without the 'p. N' line, and N
      warnings          - list of strings
    """
    res = {"ok": False, "reason": "", "text": "", "printed": None, "warnings": []}

    if stop_reason == "refusal":
        res["reason"] = "model refused the request"
        return res
    if stop_reason == "max_tokens":
        res["reason"] = "response hit max_tokens and is truncated"
        return res
    if stop_reason != "end_turn":
        res["reason"] = f"unexpected stop_reason {stop_reason!r}"
        return res

    text, printed = tf.split_printed_page(response.strip())
    res["text"], res["printed"] = text, printed
    if not text.strip():
        res["reason"] = "empty response"
        return res

    lo, li = len(ocr_text.strip()), len(tf.strip_markup(text).strip())
    ratio = li / lo if lo else 0
    if abs(li - lo) > 150:
        if ratio < 0.70:
            res["reason"] = f"output is only {ratio:.0%} of input length ({li} vs {lo} chars) - text lost"
            return res
        if ratio > (1.75 if vision else 1.30):
            res["reason"] = f"output is {ratio:.0%} of input length ({li} vs {lo} chars) - text added"
            return res

    low, orig = _plain(text), _plain(ocr_text)
    for phrase in META_PHRASES:
        if phrase in low and phrase not in orig:
            res["reason"] = f"response contains commentary ({phrase!r})"
            return res

    bad = sorted({c for c in text if _is_cjk(c)} - {c for c in ocr_text if _is_cjk(c)})
    if bad:
        res["reason"] = f"unexpected characters {''.join(bad)!r} - degenerate response"
        return res

    if tf.separator_count(text) > 1:
        res["reason"] = f"more than one '{tf.NOTES_SEP}' line - put all notes in one section"
        return res

    if tf.BRACKET_REF_RE.search(text) and not tf.BRACKET_REF_RE.search(ocr_text):
        res["reason"] = "footnote references written as [n] - write them as ^n^"
        return res

    s_ocr, s_new = tf.hebrew_share(ocr_text), tf.hebrew_share(text)
    if s_ocr is not None and s_new is not None and abs(s_ocr - s_new) > SCRIPT_FLIP:
        res["reason"] = (f"Hebrew share of letters changed from {s_ocr:.0%} to {s_new:.0%} - "
                         "the page's language was changed")
        return res

    res["ok"] = True
    res["warnings"] = page_warnings(ocr_text, text, printed)
    return res


def page_warnings(ocr_text, text, printed=None):
    w = []
    body, notes = tf.split_body_notes(text)
    r, n = tf.refs(body), tf.note_numbers(notes)

    if any(b <= a for a, b in zip(r, r[1:])):
        w.append(f"footnote references out of order: {r}")
    missing_notes = sorted(set(r) - set(n))
    if missing_notes:
        w.append(f"references without a note on this page: {missing_notes}")
    orphan_notes = sorted(set(n) - set(r))
    if orphan_notes:
        w.append(f"notes without a reference on this page: {orphan_notes}")

    lost = tf.long_numbers(ocr_text) - tf.long_numbers(text + (f"\n{printed}" if printed else ""))
    if lost:
        w.append(f"numbers in the OCR missing from the proofread text: {sorted(lost)}")

    d = tf.doubtful(text)
    if d:
        w.append(f"{len(d)} doubtful reading(s) marked {{?…}}: {d[:10]}")
    return w


def footnote_sequence(pages):
    """
    Cross-page check. pages: [(page, refs_on_page)] in page order.
    A page's first reference should continue the previous one, or restart at 1
    (a new chapter). Returns a list of warning strings.
    """
    w, last, last_page = [], None, None
    for page, r in pages:
        if not r:
            continue
        first = r[0]
        if last is not None and first != last + 1 and first != 1:
            w.append(f"footnote numbering jumps from {last} (page {last_page}) to {first} (page {page})")
        last, last_page = r[-1], page
    return w
