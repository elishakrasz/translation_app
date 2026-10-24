"""Alignment on a synthetic chapter: markers 1–5, a split paragraph, a merged paragraph, sources, notes."""
from eval.align import align_chunk

EN = """# The Chapter

First paragraph.^1^

Second paragraph with two notes.^2^ ^3^

> A quotation from a Hasidic book.^4^

Last paragraph.^5^
"""
HE = """# הפרק

פסקה ראשונה.^1^

פסקה שנייה עם שתי הערות.^2^ ^3^

> ציטוט מספר חסידי.^4^

פסקה אחרונה.^5^ [לבדיקה]
"""


def test_one_to_one_with_anchors():
    recs, log, _ = align_chunk("ch02", "0001", EN, HE)
    assert log == []
    assert [r["kind"] for r in recs] == ["heading", "prose", "prose", "quote", "prose"]
    assert [r["markers"] for r in recs] == [[], [1], [2, 3], [4], [5]]
    assert recs[1]["id"] == "ch02-0001-2" and recs[1]["para"] == 2
    assert recs[4]["flags"] == ["לבדיקה"] and "[לבדיקה]" not in recs[4]["he"]


def test_split_paragraph_is_unaligned_not_guessed():
    split = HE.replace("פסקה שנייה עם שתי הערות.^2^ ^3^", "פסקה שנייה.^2^\n\nעם שתי הערות.^3^")
    recs, log, _ = align_chunk("ch02", "0001", EN, split)
    assert recs == [] and "UNALIGNED" in log[0] and "5 English vs 6 Hebrew" in log[0]


def test_merged_paragraph_is_unaligned_not_guessed():
    merged = HE.replace("פסקה ראשונה.^1^\n\nפסקה שנייה", "פסקה ראשונה.^1^ פסקה שנייה")
    recs, log, _ = align_chunk("ch02", "0001", EN, merged)
    assert recs == [] and "5 English vs 4 Hebrew" in log[0]


def test_marker_mismatch_is_logged():
    moved = HE.replace("פסקה ראשונה.^1^", "פסקה ראשונה.").replace("הערות.^2^ ^3^", "הערות.^1^ ^2^ ^3^")
    recs, log, _ = align_chunk("ch02", "0001", EN, moved)
    assert len(recs) == 5
    assert recs[1]["align"] == "marker-mismatch" and recs[2]["align"] == "marker-mismatch"
    assert len(log) == 2


def test_inserted_source_becomes_source_quote():
    recs, _, _ = align_chunk("ch02", "0001", EN, HE, {4})
    assert recs[3]["kind"] == "source-quote"
    assert [r["kind"] for r in recs if r["kind"] == "source-quote"] == ["source-quote"]


def test_notes_section():
    en = EN + "\n## Notes\n\n1\\. A note.\n"
    he = HE + "\n## הערות\n\n1\\. הערה.\n"
    recs, log, in_notes = align_chunk("ch02", "0001", en, he)
    assert log == [] and in_notes
    assert recs[-1]["kind"] == "note" and recs[-2]["kind"] == "heading"
    recs2, _, _ = align_chunk("ch02", "0002", "2\\. More.", "2\\. עוד.", in_notes=True)
    assert recs2[0]["kind"] == "note"
