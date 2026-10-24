"""
OCR a scanned PDF with Tesseract into page records (<dir>/ocr.jsonl).

Each scan's pages are appended as soon as they are done, so an interrupted
run resumes where it stopped. Settings found by diagnostics: 300 dpi,
Tesseract's default automatic page segmentation (psm 3).
"""

import csv
import hashlib
import io
import json
import re
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

import pytesseract
from pdf2image import convert_from_path
from pdf2image.pdf2image import pdfinfo_from_path

from . import records as rec
from .layout import split_spread

BATCH = 20        # scans converted to images at a time (keeps memory flat)
DPI = 300
IMAGE_MAX = 1400  # long edge, px, of saved page images (what the proofreader sees)
LOW_CONF = 60     # Tesseract word confidence below this is reported

try:
    HAVE_HEB = "heb" in pytesseract.get_languages(config="")
except Exception:
    HAVE_HEB = False


# --------------------------------------------------------------------------
# Tesseract
# --------------------------------------------------------------------------

def osd(img):
    """(angle to make img upright, script name) via Tesseract OSD, or raise."""
    out = pytesseract.image_to_osd(img, config="--psm 0")
    rotate_cw = int(re.search(r"Rotate: (\d+)", out).group(1))
    script = re.search(r"Script: (\w+)", out)
    return (-rotate_cw) % 360, (script.group(1) if script else None)


def safe_osd(img):
    try:
        return osd(img)
    except (pytesseract.TesseractError, AttributeError):
        return None, None


def detect_orientation(pdf_path):
    """Angle and script from the first scan with enough text (covers can be blank)."""
    for scan in range(1, 6):
        img = convert_from_path(pdf_path, dpi=150, first_page=scan, last_page=scan)[0]
        angle, script = safe_osd(img)
        if angle is not None:
            return angle, script
    return 0, None


def ocr_text_and_conf(img, lang):
    """
    One Tesseract run giving both the text and per-word confidence.
    Returns (text, mean_conf, low_conf_words).
    """
    try:
        out = pytesseract.run_and_get_multiple_output(img, extensions=["txt", "tsv"], lang=lang)
        text, tsv = out
    except (AttributeError, TypeError):   # older pytesseract: two runs
        text = pytesseract.image_to_string(img, lang=lang)
        tsv = pytesseract.image_to_data(img, lang=lang)
    confs, low = [], []
    for row in csv.DictReader(io.StringIO(tsv), delimiter="\t", quoting=csv.QUOTE_NONE):
        word = (row.get("text") or "").strip()
        try:
            c = float(row.get("conf", -1))
        except ValueError:
            continue
        if not word or c < 0:
            continue
        confs.append(c)
        if c < LOW_CONF and word not in low:
            low.append(word)
    mean = round(sum(confs) / len(confs), 1) if confs else None
    return text, mean, low[:80]


def ocr_page(img, lang):
    """
    OCR one page. If the page is Hebrew but Hebrew is not in `lang`, OCR it as
    heb+eng: English-only OCR turns Hebrew into Latin gibberish no proofreader
    can recover. Returns (text, mean_conf, low_conf, lang_used, script).

    Tesseract's script detection fails on pages with little text. Then a
    low-confidence result is OCR'd again as heb+eng and the more confident
    reading is kept.
    """
    script = None
    if "heb" not in lang:
        _, script = safe_osd(img)
        if script == "Hebrew":
            lang = "heb+eng"
    text, mean, low = ocr_text_and_conf(img, lang)
    if "heb" not in lang and script is None and (mean is None or mean < 70) and HAVE_HEB:
        t2, m2, l2 = ocr_text_and_conf(img, "heb+eng")
        if m2 is not None and (mean is None or m2 > mean + 5):
            return t2, m2, l2, "heb+eng", "Hebrew?"
    return text, mean, low, lang, script


def scan_angle(img, fallback):
    """Upright angle for one scan, read at half resolution; fallback when OSD can't tell."""
    small = img.copy()
    small.thumbnail((img.width // 2, img.height // 2))
    a, _ = safe_osd(small)
    return fallback if a is None else a


def save_page_image(img, path):
    im = img.copy()
    im.thumbnail((IMAGE_MAX, IMAGE_MAX))
    im.convert("RGB").save(path, "JPEG", quality=85)


# --------------------------------------------------------------------------
# Run
# --------------------------------------------------------------------------

def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def ocr_pdf(pdf_path, out_dir, lang="eng", split_2up=False, rtl="auto",
            save_images=True, restart=False):
    pdf_path, out_dir = Path(pdf_path), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rec_path, meta_path = out_dir / "ocr.jsonl", out_dir / "ocr-meta.json"
    images_dir = out_dir / "pages"

    print("=" * 70 + "\nTesseract OCR\n" + "=" * 70)
    print(f"\nInput:  {pdf_path}\nOutput: {out_dir}/\nLang:   {lang}")

    settings = {"lang": lang, "split_2up": split_2up, "rtl": rtl, "dpi": DPI}
    digest = sha256(pdf_path)

    if restart and rec_path.exists():
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        shutil.move(rec_path, out_dir / f"ocr.jsonl.bak-{stamp}")
        print(f"✓ Previous records moved to ocr.jsonl.bak-{stamp}")

    meta = json.loads(meta_path.read_text()) if meta_path.exists() and rec_path.exists() else None
    if meta:
        if meta["source_sha256"] != digest or meta["settings"] != settings:
            raise SystemExit(
                "This folder holds OCR of a different PDF or different settings.\n"
                "Use another output folder, or --restart to start over (old records are kept as a backup).")
        angle, rtl_used = meta["rotation"], meta["rtl_used"]
    else:
        angle, script = (0, None)
        if split_2up:
            print("\nDetecting page orientation...")
            angle, script = detect_orientation(str(pdf_path))
        rtl_used = (script == "Hebrew") if rtl == "auto" else (rtl == "yes")
        meta = {
            "source": str(pdf_path), "source_sha256": digest, "settings": settings,
            "rotation": angle, "rtl_used": rtl_used,
            "tesseract": str(pytesseract.get_tesseract_version()),
            "started": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False))

    if split_2up:
        print(f"✓ Rotating scans by {angle}°, splitting each into two pages"
              f" ({'right page first' if rtl_used else 'left page first'})")
    if save_images:
        images_dir.mkdir(exist_ok=True)

    done = rec.load_records(rec_path)
    if done:
        # A crash between a scan's two page records leaves that scan half
        # written: drop it and do it again.
        last_scan = max(r["scan"] for r in done)
        last = [r for r in done if r["scan"] == last_scan]
        if len(last) < last[0].get("parts", 1):
            done = [r for r in done if r["scan"] != last_scan]
            rec.write_records_atomic(rec_path, done)
    done_scans = {r["scan"] for r in done}
    page_no = max((r["page"] for r in done), default=0)
    n_scans = pdfinfo_from_path(str(pdf_path))["Pages"]
    first_todo = max(done_scans, default=0) + 1
    if done:
        print(f"✓ Resuming: {len(done_scans)} scans already done, continuing at scan {first_todo}")
    if first_todo > n_scans:
        print("\nNothing to do.")
    else:
        print(f"\n{n_scans} scans. Converting and OCRing in batches of {BATCH}...")

    start = time.time()
    hebrew_pages = [r["page"] for r in done if r["lang"] != lang]
    for first in range(first_todo, n_scans + 1, BATCH):
        last = min(first + BATCH - 1, n_scans)
        images = convert_from_path(str(pdf_path), dpi=DPI, fmt="png", thread_count=4,
                                   first_page=first, last_page=last)
        for scan_no, image in zip(range(first, last + 1), images):
            scan_rot = 0
            if split_2up:
                # Each scan is checked on its own: a cover or a single page
                # among the spreads may lie differently from the rest.
                scan_rot = scan_angle(image, angle)
                if scan_rot:
                    image = image.rotate(scan_rot, expand=True)
                parts, split_x, note = split_spread(image, rtl_used)
            else:
                parts, split_x, note = [image], None, None

            scan_records = []
            for half, part in enumerate(parts):
                page_no += 1
                part_angle = 0
                if part.width > part.height:   # a page still lying on its side
                    a, _ = safe_osd(part)
                    if a:
                        part, part_angle = part.rotate(a, expand=True), a
                text, mean, low, used, script = ocr_page(part, lang)
                if used != lang:
                    hebrew_pages.append(page_no)
                image_rel = None
                if save_images:
                    image_rel = f"pages/page_{page_no:04d}.jpg"
                    save_page_image(part, out_dir / image_rel)
                scan_records.append({
                    "page": page_no, "scan": scan_no,
                    "half": half if len(parts) > 1 else None,
                    "parts": len(parts),
                    "split_x": split_x, "rotation": (scan_rot + part_angle) % 360,
                    "lang": used, "script": script, "image": image_rel,
                    "mean_conf": mean, "low_conf": low, "note": note,
                    "text": text,
                })
            for r in scan_records:   # a scan's pages are written together
                rec.append_record(rec_path, r)
            if note:
                print(f"  ⚠ scan {scan_no}: {note}")

            if scan_no % 10 == 0 or scan_no == n_scans:
                elapsed = time.time() - start
                rate = elapsed / (scan_no - first_todo + 1)
                print(f"  Scan {scan_no}/{n_scans} (page {page_no}) - "
                      f"ETA {(n_scans - scan_no) * rate / 60:.1f} min")
        del images

    records = rec.compact(rec_path)
    (out_dir / "ocr.txt").write_text(
        rec.render_pages({n: r["text"] for n, r in records.items()}), encoding="utf-8")
    meta["finished"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    meta["pages"] = len(records)
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False))

    confs = [r["mean_conf"] for r in records.values() if r["mean_conf"] is not None]
    weak = sorted(n for n, r in records.items() if r["mean_conf"] is not None and r["mean_conf"] < 75)
    print("\n" + "=" * 70 + "\n✓ OCR COMPLETE\n" + "=" * 70)
    print(f"Scans: {n_scans}   pages: {len(records)}")
    if confs:
        print(f"Mean word confidence: {sum(confs) / len(confs):.0f}")
    if weak:
        print(f"Pages with low confidence (<75): {weak[:30]}{' …' if len(weak) > 30 else ''}")
    if hebrew_pages:
        print(f"Hebrew detected, OCR'd as heb+eng: pages {sorted(set(hebrew_pages))}")
    print(f"Records: {rec_path}\nText:    {out_dir / 'ocr.txt'}")
    print("=" * 70)
    return out_dir


def import_legacy(txt_path, out_dir, images_dir=None, lang="eng"):
    """Turn an old PAGE-marker text file into ocr.jsonl so it can be proofread."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rec_path = out_dir / "ocr.jsonl"
    if rec_path.exists():
        raise SystemExit(f"{rec_path} already exists")
    pages = rec.split_legacy_txt(Path(txt_path).read_text(encoding="utf-8"))
    out = []
    for n in sorted(pages):
        image = None
        if images_dir:
            src = Path(images_dir) / f"page_{n:04d}.jpg"
            if src.exists():
                (out_dir / "pages").mkdir(exist_ok=True)
                shutil.copy(src, out_dir / "pages" / src.name)
                image = f"pages/{src.name}"
        out.append({"page": n, "scan": None, "half": None, "split_x": None, "rotation": None,
                    "lang": lang, "script": None, "image": image, "mean_conf": None,
                    "low_conf": [], "note": "imported from legacy text file", "text": pages[n]})
    rec.write_records_atomic(rec_path, out)
    (out_dir / "ocr-meta.json").write_text(json.dumps(
        {"source": str(txt_path), "imported": True, "pages": len(out)}, indent=2))
    print(f"✓ Imported {len(out)} pages into {rec_path}")
