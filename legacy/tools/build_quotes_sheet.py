"""Spreadsheet of every quotation in chapters 1–12: original found or still needed.

Usage: python3 tools/build_quotes_sheet.py [sources/quotations-status.xlsx]

Reads the status table (section B) of each chapter bundle — sources/bundles/ch01-r2.md
… ch06-r2.md (round 2) and ch07.md … ch12.md — one row per quotation. Sheets:
Summary (formulas), All quotations, Still needed, Books to obtain.
"""
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

ROOT = (Path(os.environ["TRANSLATOR_PROJECT"]).expanduser().resolve() if os.environ.get("TRANSLATOR_PROJECT")
        else sys.exit("Set TRANSLATOR_PROJECT to the book folder, e.g. TRANSLATOR_PROJECT=~/the_translator"))
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "sources" / "quotations-status.xlsx"
BUNDLES = [f"ch0{i}-r2.md" for i in range(1, 7)] + [f"ch{i:02d}.md" for i in range(7, 13)]
TITLES = {1: "Introduction", 2: "The Holy Rebellion", 3: "Biographical Sketch", 4: "Torah and Theology",
          5: "Zaddik and Leadership", 6: "Quest for Truth", 7: "Torat ha-Adam: Human Psychology",
          8: "Psychology of the Soul", 9: "Psychology of Service", 10: "Prayer",
          11: "Reaction against Przysucha", 12: "End of the Holy Rebellion"}
OUTCOME = {"verified-text": "Original in text", "already-original": "Original in text",
           "located-scan": "Parallel / partial only", "not-found": "Still translation",
           "not-in-scans": "Still translation"}
# located-scan entries whose full transcription was inserted (sources/applied/ch12-SOURCES-APPLIED.md)
# found in Tiferet ha-Yehudi (Tiferet/hayehudy0*.pdf, 2026-10-12) and inserted — sources/applied/chNN-SOURCES-APPLIED-tiferet.md
TIFERET_FOUND = {(2, "30"), (3, "43"), (4, "22"), (4, "46"), (5, "17"), (6, "107"), (6, "116"), (7, "8"), (8, "13"), (8, "25"),
                 (8, "26"), (8, "61"), (8, "76"), (9, "7"), (9, "32"), (10, "19"), (11, "49"), (11, "86"), (11, "89")}
APPLIED_LOCATED = {(12, n) for n in ["7", "8", "10", "12", "13", "24", "25", "29", "30", "43"]}
# common spellings of the books we lack → one name (for "Books to obtain")
BOOKS = [
    (r"me'?ir einei|meir einei|מאיר עיני|MEG", "Me'ir Einei ha-Golah — מאיר עיני הגולה"),
    (r"tiferet ha-?yehudi|תפארת היהודי", "Tiferet ha-Yehudi — תפארת היהודי"),
    (r"keter kehun|כתר כהונה", "Keter Kehunnah — כתר כהונה"),
    (r"he-?hadash|החדש", "Siah Sarfei Kodesh he-Hadash — שיח שרפי קודש החדש"),
    (r"ohel yitz|אוהל יצחק|אהל יצחק", "Ohel Yitzhak (Warka) — אוהל יצחק"),
    (r"kol mevaser|קול מבשר", "Kol Mevaser — קול מבשר"),
    (r"likkutei maharil|ליקוטי מהרי\"ל|לקוטי מהרי\"ל", "Likkutei Maharil — ליקוטי מהרי\"ל"),
    (r"emet ve-?emunah|אמת ואמונה", "Emet ve-Emunah (sections beyond §422) — אמת ואמונה"),
    (r"migdal david|מגדל דוד", "Migdal David — מגדל דוד"),
    (r"ba'?al shem tov|בעל שם טוב|zava'?at|צוואת הריב\"ש", "Sefer Ba'al Shem Tov / Tzava'at ha-Rivash"),
    (r"bet ya'?akov|beit ya'?akov|בית יעקב", "Beit Ya'akov — בית יעקב"),
    (r"yekhahen|יכהן פאר", "Yekhahen Pe'er — יכהן פאר"),
    (r"or ha-?ner|אור הנר", "Or ha-Ner — אור הנר"),
    (r"aescoly|אשכולי", "Aescoly (modern Hebrew)"),
    (r"eretz zvi|ארץ צבי", "Eretz Zvi — ארץ צבי"),
    (r"amud ha-?emet|עמוד האמת", "Amud ha-Emet — עמוד האמת"),
    (r"imrei kodesh|אמרי קודש", "Imrei Kodesh — אמרי קודש"),
    (r"pri zaddik|פרי צדיק", "Pri Zaddik — פרי צדיק"),
    (r"wilensky|וילנסקי", "Wilensky, Hasidim u-Mitnaggedim (modern Hebrew)"),
]


def book_of(work):
    for pat, name in BOOKS:
        if re.search(pat, work, re.I):
            return name
    w = re.sub(r"\(.*?\)", "", work)
    w = re.split(r"[0-9§,;:]| p\.| pp\.| vol\.|עמ'|סי'|פרק", w)[0].strip(" .\"'—-")
    return w or work.strip()


def rows():
    out = []
    for b in BUNDLES:
        ch = int(b[2:4])
        text = (ROOT / "sources" / "bundles" / b).read_text(encoding="utf-8")
        sec = text[text.index("## B"):]
        for line in sec.splitlines():
            if not line.startswith("|") or re.match(r"\|\s*(note|-)", line):
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) < 6:
                continue
            note, chunk, work, kind, status, where = cells[:6]
            key = re.match(r"[a-z-]+", status.lower())
            key = key.group(0) if key else status
            outcome = OUTCOME.get(key, "Check")
            if (ch, note.split()[0]) in APPLIED_LOCATED:
                outcome = "Original in text"
            if (ch, note.split()[0]) in TIFERET_FOUND:
                outcome, key, where = "Original in text", "verified-text", "Tiferet ha-Yehudi (Tiferet/hayehudy0*.pdf) — " + where
            out.append(dict(ch=ch, title=TITLES[ch], note=note, chunk=chunk, work=work,
                            kind=kind.split()[0] if kind else "", status=key, raw_status=status,
                            outcome=outcome, where=where))
    return out


HEAD = Font(name="Arial", bold=True, color="FFFFFF")
FILL = PatternFill("solid", fgColor="1F4E79")
BODY = Font(name="Arial", size=10)
COLORS = {"Original in text": "E2F0D9", "Parallel / partial only": "FFF2CC", "Still translation": "FCE4D6"}


def sheet(ws, header, data, widths, wrap_cols=()):
    ws.append(header)
    for c in ws[1]:
        c.font, c.fill, c.alignment = HEAD, FILL, Alignment(vertical="center", wrap_text=True)
    for r in data:
        ws.append(r)
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    for row in ws.iter_rows(min_row=2):
        for c in row:
            c.font = BODY
            c.alignment = Alignment(vertical="top", wrap_text=c.column in wrap_cols)
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions


def main():
    data = rows()
    wb = Workbook()
    summ = wb.active
    summ.title = "Summary"

    # All quotations
    ws = wb.create_sheet("All quotations")
    hdr = ["Chapter", "Chapter title", "Note", "Chunk", "Work as cited by Rosen", "Kind", "Status", "In the translation", "Where found / search notes"]
    sheet(ws, hdr, [[r["ch"], r["title"], r["note"], r["chunk"], r["work"], r["kind"], r["status"], r["outcome"], r["where"]] for r in data],
          [8, 26, 10, 9, 48, 12, 15, 22, 60], wrap_cols=(5, 9))
    for row in ws.iter_rows(min_row=2):
        col = COLORS.get(row[7].value)
        if col:
            row[7].fill = PatternFill("solid", fgColor=col)
    n_all = len(data) + 1

    # Still needed
    need = [r for r in data if r["outcome"] != "Original in text"]
    ws2 = wb.create_sheet("Still needed")
    sheet(ws2, ["Chapter", "Note", "Chunk", "Work as cited by Rosen", "Book to obtain", "Kind", "Status", "Search notes"],
          [[r["ch"], r["note"], r["chunk"], r["work"], book_of(r["work"]), r["kind"], r["status"], r["where"]] for r in need],
          [8, 10, 9, 48, 36, 12, 15, 60], wrap_cols=(4, 5, 8))

    # Books to obtain
    by_book = defaultdict(list)
    for r in need:
        if r["status"] == "not-in-scans":
            by_book[book_of(r["work"])].append(r)
    ws3 = wb.create_sheet("Books to obtain")
    books = sorted(by_book.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    sheet(ws3, ["Book (not in our scans)", "Quotations it would supply", "Chapters", "Notes"],
          [[b, None, ", ".join(str(c) for c in sorted({r["ch"] for r in rs})),
            "; ".join(f'ch{r["ch"]} n{r["note"]}' for r in rs)] for b, rs in books],
          [48, 14, 14, 70], wrap_cols=(1, 4))
    for i in range(2, len(books) + 2):          # count from the Still needed sheet
        ws3.cell(i, 2).value = f"=COUNTIFS('Still needed'!$E:$E,$A{i},'Still needed'!$G:$G,\"not-in-scans\")"
    ws3.cell(len(books) + 3, 1).value = "Counts are formulas over the 'Still needed' sheet (rows with status not-in-scans)."
    ws3.cell(len(books) + 3, 1).font = Font(name="Arial", italic=True, size=9)

    # Summary (formulas over 'All quotations')
    summ.append(["Quotations in The Quest for Authenticity — original Hebrew found vs. still needed"])
    summ["A1"].font = Font(name="Arial", bold=True, size=13)
    summ.append([f"Built from the chapter bundles (sources/bundles/ch01-r2 … ch06-r2, ch07 … ch12), status table B. One row per quotation."])
    summ["A2"].font = Font(name="Arial", italic=True, size=9)
    summ.append([])
    hdr = ["Chapter", "Title", "Quotations", "Original in text", "Parallel / partial", "Still translation", "% original"]
    summ.append(hdr)
    for c in summ[4]:
        c.font, c.fill = HEAD, FILL
    rng = lambda col: f"'All quotations'!${col}$2:${col}${n_all}"
    for ch in range(1, 13):
        r = summ.max_row + 1
        summ.append([ch, TITLES[ch],
                     f"=COUNTIF({rng('A')},A{r})",
                     f"=COUNTIFS({rng('A')},A{r},{rng('H')},\"Original in text\")",
                     f"=COUNTIFS({rng('A')},A{r},{rng('H')},\"Parallel / partial only\")",
                     f"=COUNTIFS({rng('A')},A{r},{rng('H')},\"Still translation\")",
                     f"=IF(C{r}=0,0,D{r}/C{r})"])
    t = summ.max_row + 1
    summ.append(["Total", "", f"=SUM(C5:C{t-1})", f"=SUM(D5:D{t-1})", f"=SUM(E5:E{t-1})", f"=SUM(F5:F{t-1})", f"=IF(C{t}=0,0,D{t}/C{t})"])
    for c in summ[t]:
        c.font = Font(name="Arial", bold=True)
    for row in summ.iter_rows(min_row=5, max_row=t):
        for c in row:
            if c.font != Font(name="Arial", bold=True):
                c.font = BODY
        row[6].number_format = "0%"
    summ.append([])
    notes = ["Status meanings: verified-text / already-original = the original wording is in the translation;",
             "located-scan = only a parallel or partial text was found (usually left as translation with [לבדיקה]);",
             "not-found = searched the scans and Sefaria without result; not-in-scans = the cited book is not among our scans.",
             "A few verified rows were not inserted because Rosen paraphrases rather than quotes; see the chapter logs in sources/applied/."]
    for n in notes:
        summ.append([n])
        summ.cell(summ.max_row, 1).font = Font(name="Arial", size=9)
    for col, w in zip("ABCDEFG", [9, 34, 12, 16, 17, 16, 11]):
        summ.column_dimensions[col].width = w

    wb.save(OUT)
    print(OUT, len(data), "quotations;", len(need), "still needed;", len(books), "books to obtain")


main()
