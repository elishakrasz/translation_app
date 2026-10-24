"""End-to-end OCR on generated scans. Needs tesseract (eng, heb, osd) and poppler."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from ocrkit import records as rec
from ocrkit.ocr import ocr_pdf

FONTS = ["/usr/share/fonts/truetype/freefont/FreeSerif.ttf",       # Linux
         "/System/Library/Fonts/Supplemental/Times New Roman.ttf",   # macOS; both have Hebrew
         "/System/Library/Fonts/Supplemental/Arial.ttf"]
FONT = next((f for f in FONTS if Path(f).exists()), FONTS[0])
HAVE_TOOLS = shutil.which("tesseract") and shutil.which("pdftoppm") and Path(FONT).exists()

EN_LEFT = ["Przysucha and the quest for truth", "The Kotzker taught that a man must",
           "never imitate another person in his", "service of God, for imitation is a lie."]
EN_RIGHT = ["Rabbi Simhah Bunim of Przysucha", "spoke often about the danger of habit",
            "and of prayer said by rote without", "attention to the meaning of words."]
HE_LINES = ["אמר הרבי מקוצק שאין לחקות", "את עבודת חברו כי החיקוי שקר",
            "ועל האדם לעבוד את בוראו", "בדרכו שלו ובכל לבבו ונפשו"]


def page(lines, size=(1240, 1754), rtl=False):
    img = Image.new("RGB", size, "white")
    d = ImageDraw.Draw(img)
    f = ImageFont.truetype(FONT, 38)
    y = 220
    for line in lines:
        text = line                                    # Pillow with raqm lays out RTL itself
        w = d.textlength(text, font=f)
        x = size[0] - 140 - w if rtl else 140
        d.text((x, y), text, font=f, fill="black")
        y += 70
    return img


def spread(left, right, gutter_shift=120):
    """Two pages side by side, gutter off centre, then rotated 90° as some scanners do."""
    l, r = page(left), page(right)
    w, h = l.size
    s = Image.new("RGB", (2 * w + 2 * gutter_shift, h), "white")
    s.paste(l, (0, 0))
    s.paste(r, (w + 2 * gutter_shift, 0))
    return s.rotate(90, expand=True)


@unittest.skipUnless(HAVE_TOOLS, "tesseract/poppler/font not available")
class OcrEndToEnd(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())

    def test_two_up_english_resume_and_guard(self):
        pdf = self.d / "en.pdf"
        scans = [spread(EN_LEFT, EN_RIGHT), spread(EN_RIGHT, EN_LEFT), page(EN_LEFT)]
        scans[0].save(pdf, save_all=True, append_images=scans[1:], resolution=150)
        out = self.d / "out"
        ocr_pdf(pdf, out, lang="eng", split_2up=True)
        r = rec.latest_by_page(rec.load_records(out / "ocr.jsonl"))
        self.assertEqual(len(r), 5)                         # 2 + 2 + 1 portrait page kept whole
        self.assertIn("Kotzker", r[1]["text"])
        self.assertIn("Bunim", r[2]["text"])
        self.assertIn("Bunim", r[3]["text"])
        self.assertIn("portrait", r[5]["note"])
        self.assertTrue((out / r[1]["image"]).exists())
        self.assertIsNotNone(r[1]["mean_conf"])

        # Resume: drop the last scan's record and the second half of scan 2.
        recs = rec.load_records(out / "ocr.jsonl")
        rec.write_records_atomic(out / "ocr.jsonl", recs[:3])
        ocr_pdf(pdf, out, lang="eng", split_2up=True)
        again = rec.latest_by_page(rec.load_records(out / "ocr.jsonl"))
        self.assertEqual(len(again), 5)
        self.assertEqual(again[4]["text"], r[4]["text"])

        # Different settings on the same folder are refused.
        with self.assertRaises(SystemExit):
            ocr_pdf(pdf, out, lang="heb", split_2up=True)

    def test_hebrew_page_detected(self):
        pdf = self.d / "he.pdf"
        page(HE_LINES, rtl=True).save(pdf, resolution=150)
        out = self.d / "he"
        ocr_pdf(pdf, out, lang="eng")                       # Hebrew not requested
        r = rec.latest_by_page(rec.load_records(out / "ocr.jsonl"))[1]
        self.assertEqual(r["lang"], "heb+eng")              # re-OCR'd as Hebrew
        self.assertIn("מקוצק", r["text"])
        meta = json.loads((out / "ocr-meta.json").read_text())
        self.assertEqual(meta["pages"], 1)


if __name__ == "__main__":
    unittest.main()
