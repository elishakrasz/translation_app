#!/usr/bin/env python3
"""Step 1: OCR. Same as `python -m ocrkit ocr ...`.

    python final_ocr.py BOOK.pdf books/ocr/book --lang heb --split-2up
"""
import sys

from ocrkit.__main__ import main

if __name__ == "__main__":
    sys.exit(main(["ocr", *sys.argv[1:]]))
