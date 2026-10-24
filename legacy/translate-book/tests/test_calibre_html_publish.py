import inspect
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import calibre_html_publish  # noqa: E402


class ConvertHtmlWithCalibreTests(unittest.TestCase):
    def test_builds_expected_epub_command(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_html = Path(temp_dir) / "input.html"
            output_file = Path(temp_dir) / "output.epub"
            input_html.write_text("<html><head><title>Book</title></head></html>", encoding="utf-8")

            def fake_run(cmd, capture_output, text, timeout):
                output_file.write_text("epub", encoding="utf-8")
                return mock.Mock(returncode=0, stderr="")

            with mock.patch.object(
                calibre_html_publish, "find_calibre_convert", return_value="/usr/bin/ebook-convert"
            ), mock.patch.object(
                calibre_html_publish, "extract_html_metadata", return_value=("Book", "Author")
            ), mock.patch.object(
                calibre_html_publish.subprocess, "run", side_effect=fake_run
            ) as run_mock:
                ok = calibre_html_publish.convert_html_with_calibre(
                    str(input_html), str(output_file), "epub", timeout=12, lang="ja"
                )

            self.assertTrue(ok)
            cmd = run_mock.call_args.args[0]
            self.assertEqual(cmd[0], "/usr/bin/ebook-convert")
            self.assertEqual(cmd[1], str(input_html))
            self.assertEqual(cmd[2], str(output_file))
            self.assertIn("--title", cmd)
            self.assertIn("--authors", cmd)
            self.assertIn("--language", cmd)
            self.assertIn("ja", cmd)
            self.assertIn("--epub-version", cmd)
            self.assertIn("3", cmd)
            self.assertNotIn("--disable-font-rescaling", cmd)

    @unittest.skipUnless(
        "cover" in inspect.signature(calibre_html_publish.convert_html_with_calibre).parameters,
        "cover parameter unavailable",
    )
    def test_includes_cover_argument_when_requested(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_html = Path(temp_dir) / "input.html"
            output_file = Path(temp_dir) / "output.epub"
            cover_file = Path(temp_dir) / "cover.jpg"
            input_html.write_text("<html><head><title>Book</title></head></html>", encoding="utf-8")
            cover_file.write_text("img", encoding="utf-8")

            def fake_run(cmd, capture_output, text, timeout):
                output_file.write_text("epub", encoding="utf-8")
                return mock.Mock(returncode=0, stderr="")

            with mock.patch.object(
                calibre_html_publish, "find_calibre_convert", return_value="/usr/bin/ebook-convert"
            ), mock.patch.object(
                calibre_html_publish, "extract_html_metadata", return_value=("Book", "Author")
            ), mock.patch.object(
                calibre_html_publish.subprocess, "run", side_effect=fake_run
            ) as run_mock:
                ok = calibre_html_publish.convert_html_with_calibre(
                    str(input_html),
                    str(output_file),
                    "epub",
                    timeout=12,
                    lang="ja",
                    cover=str(cover_file),
                )

            self.assertTrue(ok)
            cmd = run_mock.call_args.args[0]
            self.assertIn("--cover", cmd)
            self.assertIn(str(cover_file), cmd)


class HebrewFontTests(unittest.TestCase):
    def test_hebrew_uses_hebrew_capable_fonts(self):
        self.assertIn("Noto Serif Hebrew", calibre_html_publish._get_font_family_for_lang("he"))
        self.assertEqual(calibre_html_publish._get_pdf_font_for_lang("he"), "Times New Roman")


class DocxRtlTests(unittest.TestCase):
    def test_inserts_bidi_before_spacing_in_defaults(self):
        styles = ('<w:docDefaults><w:pPrDefault><w:pPr><w:spacing w:after="0"/></w:pPr>'
                  '</w:pPrDefault></w:docDefaults>')
        patched = calibre_html_publish._add_default_bidi(styles)
        self.assertIn('<w:pPr><w:bidi/><w:spacing w:after="0"/></w:pPr>', patched)

    def test_expands_empty_defaults(self):
        patched = calibre_html_publish._add_default_bidi('<w:pPrDefault/>')
        self.assertEqual(patched, '<w:pPrDefault><w:pPr><w:bidi/></w:pPr></w:pPrDefault>')

    def test_leaves_existing_bidi_alone(self):
        styles = '<w:pPrDefault><w:pPr><w:bidi/></w:pPr></w:pPrDefault>'
        self.assertEqual(calibre_html_publish._add_default_bidi(styles), styles)

    def test_returns_none_without_defaults(self):
        self.assertIsNone(calibre_html_publish._add_default_bidi('<w:styles/>'))

    def test_make_docx_rtl_rewrites_only_styles(self):
        import zipfile
        with tempfile.TemporaryDirectory() as temp_dir:
            docx = Path(temp_dir) / "book.docx"
            with zipfile.ZipFile(docx, "w") as zf:
                zf.writestr("word/styles.xml", "<w:pPrDefault><w:pPr></w:pPr></w:pPrDefault>")
                zf.writestr("word/document.xml", "<w:document/>")
            with mock.patch("builtins.print"):
                self.assertTrue(calibre_html_publish.make_docx_rtl(str(docx)))
            with zipfile.ZipFile(docx) as zf:
                self.assertIn("<w:bidi/>", zf.read("word/styles.xml").decode("utf-8"))
                self.assertEqual(zf.read("word/document.xml"), b"<w:document/>")
            self.assertEqual(sorted(p.name for p in Path(temp_dir).iterdir()), ["book.docx"])

    def test_only_hebrew_is_rtl(self):
        self.assertTrue(calibre_html_publish._is_rtl_lang("he"))
        self.assertFalse(calibre_html_publish._is_rtl_lang("zh-CN"))


if __name__ == "__main__":
    unittest.main()
