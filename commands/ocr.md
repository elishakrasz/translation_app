---
description: Step 0 — OCR and proofread a scanned PDF from source/original/
argument-hint: <file in source/original/> <part name>
---
Step 0 for `$ARGUMENTS` (a PDF in source/original/ and a short part name, e.g. `Part3.pdf part3`).

1. Check the PDF (`pdfinfo`) and look at one page image, to choose the options: `--split-2up` for two book pages per
   scan, `--lang eng`, `heb` or `heb+eng`.
2. Run `ocrkit ocr source/original/<file> source/ocr/<part> <options>` (the ocrkit next to {{TRANSLATOR}}).
3. Summarise the OCR per page (words, confidence) and list blank pages. Then ask me before proofreading: it calls the
   API and costs money. With my yes: `ocrkit proofread source/ocr/<part> --batch --pages <the non-blank pages>`.
4. Show me the summary of source/ocr/<part>/proof-report.md and every page it lists for review.
5. Add the part to `sources_received` in project.yaml, and propose `units` entries (id, slug, title, start) for the
   units that begin in it. Don't edit `units` until I agree.
