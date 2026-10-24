"""
ocrkit command line.

    python -m ocrkit ocr BOOK.pdf DIR [--lang heb] [--split-2up] [--rtl auto|yes|no]
    python -m ocrkit proofread DIR [--batch] [--repair] [--pages 1,7-9] [--all]
    python -m ocrkit render DIR          rewrite ocr.txt, proof.txt and proof-report.md
    python -m ocrkit import-txt OLD.txt DIR [--images OLD_pages/]
"""

import argparse
import sys
from pathlib import Path


def main(argv=None):
    # A .env found from the working folder wins; the translation app's shared key file fills in the rest.
    try:
        from dotenv import load_dotenv
        load_dotenv()
        load_dotenv(Path.home() / ".config" / "translator" / ".env")
    except ImportError:
        pass

    ap = argparse.ArgumentParser(prog="ocrkit", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    o = sub.add_parser("ocr", help="OCR a scanned PDF into DIR/ocr.jsonl")
    o.add_argument("pdf")
    o.add_argument("dir")
    o.add_argument("--lang", default="eng", help="Tesseract language(s): eng, heb, heb+eng")
    o.add_argument("--split-2up", action="store_true", help="two book pages per scan: rotate and split")
    o.add_argument("--rtl", choices=["auto", "yes", "no"], default="auto",
                   help="with --split-2up: right-hand page first (auto: yes when the scan is Hebrew)")
    o.add_argument("--no-images", action="store_true", help="do not save page images (vision proofreading needs them)")
    o.add_argument("--restart", action="store_true", help="start over; existing records are kept as a backup")

    p = sub.add_parser("proofread", help="proofread DIR/ocr.jsonl into DIR/proof.jsonl")
    p.add_argument("dir")
    p.add_argument("--language", choices=["auto", "english", "hebrew", "mixed"], default="auto")
    p.add_argument("--model", default=None)
    p.add_argument("--effort", choices=["low", "medium", "high", "none"], default="low",
                   help="thinking effort (default low: much cheaper than high with no measured quality loss)")
    p.add_argument("--vision", choices=["auto", "on", "off"], default="auto",
                   help="send the page image with the text (auto: when DIR/pages has it)")
    p.add_argument("--batch", action="store_true", help="use the Message Batches API: half price, results within 24 h")
    p.add_argument("--repair", action="store_true", help="redo pages that are missing or kept as OCR")
    p.add_argument("--pages", help="only these pages, e.g. 1,7-9,31")
    p.add_argument("--all", action="store_true", help="redo every page")
    p.add_argument("--change-flag", type=float, default=None,
                   help="flag pages where more than this share of words changed (default 0.15)")

    r = sub.add_parser("render", help="rewrite the text files and the report from the records")
    r.add_argument("dir")

    i = sub.add_parser("import-txt", help="turn an old PAGE-marker text file into DIR/ocr.jsonl")
    i.add_argument("txt")
    i.add_argument("dir")
    i.add_argument("--images", help="folder of page_NNNN.jpg from the old run")
    i.add_argument("--lang", default="eng")

    a = ap.parse_args(argv)

    if a.cmd == "ocr":
        from .ocr import ocr_pdf
        ocr_pdf(a.pdf, a.dir, lang=a.lang, split_2up=a.split_2up, rtl=a.rtl,
                save_images=not a.no_images, restart=a.restart)
        print(f"\nNext: python -m ocrkit proofread {a.dir}")
    elif a.cmd == "proofread":
        from . import proofread as pr
        pr.run(a.dir, language=a.language, model=a.model or pr.DEFAULT_MODEL,
               effort=None if a.effort == "none" else a.effort, vision=a.vision,
               repair=a.repair, pages=pr.parse_pages(a.pages) if a.pages else None,
               redo_all=a.all, batch=a.batch,
               change_flag=pr.CHANGE_FLAG if a.change_flag is None else a.change_flag)
    elif a.cmd == "render":
        from . import proofread as pr, records as rec
        d = Path(a.dir)
        ocr = rec.latest_by_page(rec.load_records(d / "ocr.jsonl"))
        (d / "ocr.txt").write_text(rec.render_pages({n: x["text"] for n, x in ocr.items()}), encoding="utf-8")
        _, path = pr.finish(d, d / "proof.jsonl", ocr, pr.CHANGE_FLAG)
        print(f"✓ Wrote ocr.txt, proof.txt and {path.name}")
    elif a.cmd == "import-txt":
        from .ocr import import_legacy
        import_legacy(a.txt, a.dir, a.images, a.lang)


if __name__ == "__main__":
    sys.exit(main())
