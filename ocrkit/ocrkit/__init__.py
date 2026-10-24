"""ocrkit - OCR scanned books with Tesseract and proofread them with Claude.

Two steps, each writing one JSONL file of page records:

    ocr        scanned PDF  -> <dir>/ocr.jsonl   (+ page images, ocr.txt)
    proofread  ocr.jsonl    -> <dir>/proof.jsonl (+ proof.txt, proof-report.md)

The OCR records are evidence and are never changed by the proofreader.
See README.md for the page-text format and the record schemas.
"""

__version__ = "2.0.0"
