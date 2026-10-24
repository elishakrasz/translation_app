#!/usr/bin/env python3
"""Step 2: proofread. Same as `python -m ocrkit proofread ...`.

    python proofreader.py books/ocr/book [--batch] [--repair] [--pages 1,7-9]
"""
import sys

from ocrkit.__main__ import main

if __name__ == "__main__":
    sys.exit(main(["proofread", *sys.argv[1:]]))
