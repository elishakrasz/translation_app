# ocrkit

OCR scanned books with Tesseract, then proofread the OCR with Claude, keeping
a record of every page and every change. This is the shared OCR package used
by the translation app (Step 0) and by the reference library of scanned
seforim.

```
python final_ocr.py  BOOK.pdf books/ocr/book --lang heb --split-2up
python proofreader.py books/ocr/book --batch
```

Both scripts are thin wrappers around `python -m ocrkit ocr …` and
`python -m ocrkit proofread …`.

## Install

```
pip install -r requirements.txt
```

You also need Tesseract 5 with the `eng`, `heb` and `osd` language files, and
Poppler (for `pdftoppm`). Put `ANTHROPIC_API_KEY=…` in a `.env` file.

## What goes where

Everything for one book lives in one folder:

| File | Written by | What it is |
| --- | --- | --- |
| `ocr.jsonl` | ocr | One record per page: the raw OCR, never changed afterwards |
| `ocr-meta.json` | ocr | Source PDF and its SHA-256, settings, rotation, Tesseract version |
| `pages/page_NNNN.jpg` | ocr | Page images (the proofreader reads them; so can you) |
| `ocr.txt` | ocr | The OCR as text with `PAGE n` markers |
| `proof.jsonl` | proofread | One record per page: proofread text, status, warnings, changes |
| `proof.txt` | proofread | Proofread text with `PAGE n  (p. N)` markers — the input to Step 1 |
| `proof-report.md` | proofread | What to review: pages kept as OCR, warnings, doubtful readings, changes |
| `proof-batch.json` | proofread | Only while a batch is running: lets an interrupted run pick it up |

`python -m ocrkit render DIR` rewrites the three text files from the records.

## Commands

**OCR** — `python -m ocrkit ocr BOOK.pdf DIR`

| Option | Effect |
| --- | --- |
| `--lang eng` | Tesseract languages (`eng`, `heb`, `heb+eng`). A page detected as Hebrew is OCR'd as `heb+eng` anyway. |
| `--split-2up` | Two book pages per scan. Each scan is turned upright on its own, and split at the gutter (found, not assumed to be the middle). A portrait scan among the spreads is kept as one page. |
| `--rtl auto` | With `--split-2up`: right-hand page first. `auto` decides from the script of the first scan. |
| `--no-images` | Don't save page images. Vision proofreading needs them, so images are on by default. |
| `--restart` | Start over. Old records are kept as `ocr.jsonl.bak-<time>`. |

Pages are written as soon as each scan is done. If a run stops, run the same
command again and it continues. Running it on a folder that holds a different
PDF, or with different settings, is refused.

**Proofread** — `python -m ocrkit proofread DIR`

| Option | Effect |
| --- | --- |
| `--batch` | Use the Message Batches API: half the price, results usually within an hour (at most 24). Pages that fail are retried one by one afterwards. |
| `--vision auto` | Send the page image with the OCR text when `pages/` has it (`on` / `off`). |
| `--language auto` | Per page, from the OCR language (`english`, `hebrew`, `mixed`). |
| `--repair` | Redo pages that are missing or were kept as OCR. |
| `--pages 1,7-9` | Redo these pages. `--all` redoes every page. |
| `--effort low` | Thinking effort (`low`, `medium`, `high`, `none`). |
| `--change-flag 0.15` | Flag pages where more than this share of words changed. |
| `--model` | Default `claude-sonnet-5`. Prices are in `PRICING` in `proofread.py`; check them against Anthropic's current pricing. An unknown model shows "cost unknown". |

A plain re-run continues with the pages not yet done.

**Import** — `python -m ocrkit import-txt OLD.txt DIR [--images OLD_pages/]`
turns a text file from the old scripts into `ocr.jsonl`, so books OCR'd
before can be proofread with the new checks.

## The proofread page format

Text-only and vision proofreading produce the same format:

```
Body paragraphs, lines joined, separated by blank lines.
A footnote reference sits right after its word.^12^
> Block quotes start with "> ".
A word the proofreader could not read for certain is kept as OCR and marked {?wrod}.
--- notes ---
(cont.) The end of a note that began on the previous page.
12. Text of note 12.
```

Running heads are dropped. The model returns the printed page number as a last
line `p. N`; it is moved into the record (`printed_page`) and the text files
show it in the page header.

## Checks

A response that fails a **hard check** is retried with the reason as feedback.
After three failures the OCR text is kept (`status: kept_ocr`) and the page is
listed at the top of the report. Network and rate-limit errors are retried
separately and don't use up the three attempts.

Hard checks: refusal or truncation; empty response; text lost (under 70% of
the OCR's length) or added (over 130%, 175% with the image); commentary
instead of text; CJK characters; more than one `--- notes ---` line; footnote
references written as `[n]`; the page's Hebrew share of letters changing by
more than 35 points.

**Warnings** don't trigger a retry. They put the page on the review list:

- footnote references out of order on the page
- a reference without a note on the page, or a note without a reference
- a number of three or more digits (a year, a page, a section) in the OCR that is missing from the proofread text
- doubtful readings marked `{?…}`
- a high change rate (default: over 15% of words, on pages of 40+ words)
- across pages, in the report: footnote numbering that jumps, other than a restart at 1

## Page records

`ocr.jsonl`, one line per page:

```json
{"page": 12, "scan": 6, "half": 1, "parts": 2, "split_x": 2560, "rotation": 270,
 "lang": "heb+eng", "script": "Hebrew", "image": "pages/page_0012.jpg",
 "mean_conf": 81.4, "low_conf": ["ובכל", "וברדו"], "note": null, "text": "…"}
```

`low_conf` lists the words Tesseract was least sure of (confidence under 60).
They are sent to the proofreader as words to check in particular.

`proof.jsonl`, one line per page:

```json
{"page": 12, "status": "ok", "text": "…", "printed_page": "57",
 "model": "claude-sonnet-5", "mode": "vision", "language": "hebrew", "attempts": 1,
 "warnings": ["references without a note on this page: [41]"],
 "doubtful": ["וברדו"], "change_rate": 0.06,
 "changes": [["replace", "Kotzlcer", "Kotzker"]], "usage": {"input": 2310, "output": 905}, "at": "…"}
```

## Changes from the earlier scripts

- **Change record.** Every accepted page stores a word-level list of changes and a change rate, so nothing changes without a trace.
- **No guessing.** Doubtful words are kept and marked `{?…}` instead of being restored from context. The prompt forbids replacing wording from a familiar version of a text, so edition differences in quotations survive.
- **One output format** for text-only and vision mode, with `^n^` references to match the chapter files.
- **Footnote, number and script checks.**
- **Page records** (JSONL) instead of text files with checkpoints. Runs resume; nothing piles up.
- **Gutter detection** for two-page scans, per-scan rotation, automatic right-to-left order, and portrait scans kept whole.
- **Word confidence** from Tesseract, reported and passed to the proofreader. Hebrew pages are detected even when Tesseract's orientation check can't read them.
- **Batch mode** at half price.
- **Fixes:** rate limits no longer use up attempts; an unknown model no longer reports $0; `.tif` and other image types work; output names no longer depend on a `.txt` ending.

## Tests

```
python -m unittest discover -s tests
```

27 tests. The proofreader tests use a fake Claude client (no key, no network).
The OCR tests generate English and Hebrew scans, including rotated two-page
spreads with an off-centre gutter, and run real Tesseract on them. They are
skipped if Tesseract or Poppler is missing.
