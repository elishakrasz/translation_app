import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from ocrkit import checks, records as rec, textfmt as tf
from ocrkit.diff import word_changes
from ocrkit.layout import find_gutter, split_spread

OCR_EN = ("The Kotzker said that truth cannot be imitated.12 He repeated it in 1847\n"
          "and again later, as recorded on page 213 of the collection. " * 3)
GOOD = ("The Kotzker said that truth cannot be imitated.^12^ He repeated it in 1847 "
        "and again later, as recorded on page 213 of the collection. " * 3
        ).rstrip() + "\n--- notes ---\n12. See Emet ve-Emunah, 41.\np. 57"


class TextFormat(unittest.TestCase):
    def test_printed_page(self):
        t, p = tf.split_printed_page("body\n\np. 57")
        self.assertEqual((t, p), ("body", "57"))
        self.assertEqual(tf.split_printed_page("body")[1], None)

    def test_body_notes_refs(self):
        body, notes = tf.split_body_notes(tf.split_printed_page(GOOD)[0])
        self.assertEqual(tf.refs(body), [12, 12, 12])
        self.assertEqual(tf.note_numbers(notes), [12])

    def test_continuation_and_doubtful(self):
        t = "a {?wrod} b\n--- notes ---\n(cont.) rest of note\n13. next"
        self.assertTrue(tf.has_continuation(tf.split_body_notes(t)[1]))
        self.assertEqual(tf.doubtful(t), ["wrod"])
        self.assertNotIn("{?", tf.strip_markup(t))

    def test_hebrew_share(self):
        self.assertIsNone(tf.hebrew_share("short"))
        self.assertGreater(tf.hebrew_share("אמר הרבי מקוצק שהאמת אינה ניתנת לחיקוי כלל ועיקר"), 0.9)


class Checks(unittest.TestCase):
    def test_good_page(self):
        r = checks.check_page(OCR_EN, GOOD)
        self.assertTrue(r["ok"], r["reason"])
        self.assertEqual(r["printed"], "57")
        self.assertFalse(any("numbers" in w for w in r["warnings"]))

    def test_hard_failures(self):
        cases = {
            "stop": (GOOD, "max_tokens"),
            "empty": ("", "end_turn"),
            "lost": ("The Kotzker said.", "end_turn"),
            "meta": ("Here is the corrected text: " + GOOD, "end_turn"),
            "cjk": (GOOD + " 真", "end_turn"),
            "brackets": (GOOD.replace("^12^", "[12]"), "end_turn"),
            "two seps": (GOOD.replace("p. 57", "--- notes ---\n13. x"), "end_turn"),
        }
        for name, (resp, stop) in cases.items():
            with self.subTest(name):
                self.assertFalse(checks.check_page(OCR_EN, resp, stop)["ok"])

    def test_script_flip(self):
        heb = "אמר הרבי מקוצק שהאמת אינה ניתנת לחיקוי כלל ועיקר והוסיף עוד דברים רבים " * 3
        r = checks.check_page(heb, "The rabbi of Kotzk said that truth cannot be imitated at all and more " * 3)
        self.assertFalse(r["ok"])
        self.assertIn("Hebrew share", r["reason"])

    def test_warnings(self):
        resp = GOOD.replace("1847", "1874").replace("12. See", "14. See")
        w = checks.check_page(OCR_EN, resp)["warnings"]
        self.assertTrue(any("without a note" in x for x in w))
        self.assertTrue(any("without a reference" in x for x in w))
        self.assertTrue(any("1847" in x for x in w))

    def test_footnote_sequence(self):
        w = checks.footnote_sequence([(1, [1, 2]), (2, [3]), (3, [7, 8]), (4, [1]), (5, [])])
        self.assertEqual(len(w), 1)
        self.assertIn("from 3 (page 2) to 7 (page 3)", w[0])


class Diff(unittest.TestCase):
    def test_changes(self):
        rate, ch = word_changes("the Kotzlcer said tbat", "the Kotzker said that^3^")
        self.assertEqual(rate, 0.5)
        self.assertEqual(ch, [["replace", "Kotzlcer", "Kotzker"], ["replace", "tbat", "that"]])

    def test_unchanged(self):
        self.assertEqual(word_changes("a b c", "a b c"), (0.0, []))


class Records(unittest.TestCase):
    def test_append_torn_compact(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "r.jsonl"
            rec.append_record(p, {"page": 2, "v": 1})
            rec.append_record(p, {"page": 1, "v": 1})
            rec.append_record(p, {"page": 2, "v": 2})
            with open(p, "a") as f:
                f.write('{"page": 3, "v"')        # torn write
            latest = rec.compact(p)
            self.assertEqual(sorted(latest), [1, 2])
            self.assertEqual(latest[2]["v"], 2)
            self.assertEqual([r["page"] for r in rec.load_records(p)], [1, 2])

    def test_legacy_roundtrip(self):
        txt = rec.render_pages({1: "one", 2: "two"})
        self.assertEqual(rec.split_legacy_txt(txt), {1: "one", 2: "two"})


def spread(gutter_x, w=2000, h=1300, shadow=False):
    """Synthetic upright spread: lines of 'text' on both sides of gutter_x."""
    img = Image.new("L", (w, h), 245)
    d = ImageDraw.Draw(img)
    for y in range(120, h - 120, 28):
        for x0, x1 in ((90, gutter_x - 70), (gutter_x + 70, w - 90)):
            x = x0
            while x < x1 - 40:
                d.rectangle((x, y, x + 30, y + 12), fill=30)
                x += 42
    if shadow:
        d.rectangle((gutter_x - 25, 0, gutter_x + 25, h), fill=60)
    return img


class Layout(unittest.TestCase):
    def test_off_centre_gutter(self):
        x, note = find_gutter(spread(1120))
        self.assertIsNone(note)
        self.assertLess(abs(x - 1120), 40)

    def test_dark_shadow_gutter(self):
        x, note = find_gutter(spread(880, shadow=True))
        self.assertIsNone(note)
        self.assertLess(abs(x - 880), 40)

    def test_blank_and_portrait(self):
        self.assertIsNotNone(find_gutter(Image.new("L", (2000, 1300), 250))[1])
        parts, x, note = split_spread(Image.new("L", (1000, 1500), 250))
        self.assertEqual((len(parts), x), (1, None))
        self.assertIn("portrait", note)

    def test_rtl_order(self):
        img = spread(1000)
        ltr, _, _ = split_spread(img, rtl=False)
        rtl, _, _ = split_spread(img, rtl=True)
        self.assertEqual(ltr[0].size, rtl[1].size)


if __name__ == "__main__":
    unittest.main()
