"""Tracking workbook of Hebrew sources still to be located, and of footnote items to verify.

Usage: python3 tools/build_sources_sheet.py [out.xlsx]   (default sources/hebrew-sources-tracker.xlsx)
Sheets: Summary (formulas) · Sources to locate (quote-verification table, status provisional /
checked-not-found) · Notes to verify (Koren conversion flags, ch. 1–4) · Bibliography gaps ·
Hebrew editions exist (modern works quoted via back-translation).
"""
import os
import csv, json, re, sys
from pathlib import Path
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

ROOT = (Path(os.environ["TRANSLATOR_PROJECT"]).expanduser().resolve() if os.environ.get("TRANSLATOR_PROJECT")
        else sys.exit("Set TRANSLATOR_PROJECT to the book folder, e.g. TRANSLATOR_PROJECT=~/the_translator"))
out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "sources" / "hebrew-sources-tracker.xlsx"
CH = {"מבוא": "1", "המרד הקדוש": "2", "סקירה ביוגרפית": "3", "תורה ותאולוגיה": "4", "צדיק והנהגה": "5", "החיפוש אחר אמת": "6"}
FONT = "Arial"
HEAD = PatternFill("solid", fgColor="DDE3EA"); INPUT = PatternFill("solid", fgColor="FFF9C4")


def sheet(wb, name, headers, rows, widths, rtl_cols=(), input_cols=()):
    ws = wb.create_sheet(name)
    ws.append(headers)
    for c in ws[1]:
        c.font = Font(name=FONT, bold=True); c.fill = HEAD; c.alignment = Alignment(wrap_text=True, vertical="top")
    for r in rows:
        ws.append(r)
    for row in ws.iter_rows(min_row=2):
        for c in row:
            c.font = Font(name=FONT, size=10)
            c.alignment = Alignment(wrap_text=True, vertical="top", horizontal="right" if c.column in rtl_cols else "left")
            if c.column in input_cols:
                c.fill = INPUT
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    return ws


wb = Workbook(); wb.remove(wb.active)

# --- 1. Sources to locate
tbl = list(csv.DictReader((ROOT / "sources" / "s2" / "quote-verification-table.csv").open(encoding="utf-8")))
rows = []
for r in tbl:
    if r["status"] == "verified-text":
        continue
    loc = f"note {r['marker']}" if r["marker"] else "body (no note)"
    rows.append([int(CH.get(r["chapter"], 0)), r["chapter"], loc, r["kind"], (r["source"] or "").strip(), (r["quote"] or "")[:90],
                 r["status"], (r["notes"] or "")[:200], "", "", ""])
rows.sort(key=lambda x: (x[0], int(re.sub(r"\D", "", x[2]) or 0)))
sheet(wb, "Sources to locate",
      ["Ch.", "Chapter", "Location", "Kind", "Rosen's citation", "Hebrew (opening words, current back-translation)", "Status", "Verifier's note",
       "Edition / scan to get (HebrewBooks id, pages)", "Done?", "My notes"],
      rows, [5, 16, 12, 14, 34, 40, 18, 34, 30, 8, 30], rtl_cols=(2, 5, 6, 8), input_cols=(9, 10, 11))

# --- 2. Notes to verify (Koren conversion flags)
nrows = []
for ch in ("ch01", "ch02", "ch03", "ch04"):
    p = ROOT / "review" / ch / "notes_koren.json"
    if not p.exists():
        continue
    for x in json.loads(p.read_text(encoding="utf-8"))["notes"]:
        if x.get("verify"):
            nrows.append([int(ch[2:]), x["n"], x["koren"][:120], x["verify"], x.get("changes", "")[:160], "", ""])
sheet(wb, "Notes to verify", ["Ch.", "Note", "Koren-style note (opening)", "What to verify", "What the conversion changed", "Resolved?", "My notes"],
      nrows, [5, 6, 44, 60, 40, 9, 30], rtl_cols=(3,), input_cols=(6, 7))

# --- 3. Bibliography gaps
brows, seen = [], set()
for ch in ("ch01", "ch02", "ch03", "ch04"):
    p = ROOT / "review" / ch / "notes_koren.json"
    if not p.exists():
        continue
    for b in json.loads(p.read_text(encoding="utf-8")).get("bibliography", []):
        if b.get("verify") and b["short"] not in seen:
            seen.add(b["short"])
            brows.append([b["short"], b["full"], b.get("lang", ""), b.get("type", ""), b.get("why", ""), f"ch. {int(ch[2:])} nn. " + ", ".join(map(str, b.get("source_notes", []))), "", ""])
sheet(wb, "Bibliography gaps", ["Short form", "Full entry (as drafted)", "Lang", "Type", "What is missing / doubtful", "First cited", "Corrected entry", "Done?"],
      brows, [30, 50, 6, 10, 50, 18, 50, 8], rtl_cols=(1, 2, 7), input_cols=(7, 8))

# --- 4. Hebrew editions exist (quoted via back-translation)
hrows = [
    ["1", "epigraph; 0003·2; n. 12", "Lev Shestov, Job's Balances (In Job's Balances)", "check for a Hebrew edition", "", ""],
    ["1", "0005·8; n. 19", "Gershom Scholem, Major Trends in Jewish Mysticism", "זרמים ראשיים במיסטיקה היהודית (עם עובד)", "", ""],
    ["1", "n. 2 / 0002·6", "A.Z. Aescoly, Hasidut be-Polin", "החסידות בפולין, ed. D. Assaf, Jerusalem 1999 — quote from the Hebrew", "", ""],
    ["2", "0002·11", "A.B. Gottlober, memoirs", "זכרונות ומסעות, ed. R. Goldberg, Jerusalem 1976", "", ""],
    ["2", "0007·1", "The snuffbox parable (Buber)", "אור הגנוז, pp. 443–445 — printed Hebrew", "", ""],
    ["3", "0002·15; n. 23", "A. Zederbaum, Keter Kehunnah", "כתר כהונה, Odessa 1866 — Hebrew original", "", ""],
    ["3", "0003·2", "Letter of R. Shneur Zalman of Liadi", "Hebrew original in the standard editions of his letters", "", ""],
    ["4", "0006·1; nn. 63, 66, 96", "R. Mahler, Hasidism and the Jewish Enlightenment", "החסידות וההשכלה, Merhavia 1961 — quote and page numbers from the Hebrew", "", ""],
    ["4", "0007·7; n. 75", "G. Scholem on Buber (essay)", "דברים בגו — Hebrew text", "", ""],
    ["4", "0007·9; n. 76", "G. Scholem, Major Trends", "זרמים ראשיים במיסטיקה היהודית", "", ""],
    ["4", "0012·1 + editor's note", "A. Zederbaum, Keter Kehunnah", "כתר כהונה, Odessa 1866", "", ""],
    ["4", "n. 103", "R. Elior's study (exists in Hebrew)", "cite the Hebrew version", "", ""],
    ["4", "0013·2", "M. Buber, Gog u-Magog", "written in German; Hebrew edition גוג ומגוג exists — quote from it if the passage is quoted", "", ""],
]
sheet(wb, "Hebrew editions exist", ["Ch.", "Location", "Work quoted via back-translation", "Hebrew edition / what to do", "Done?", "My notes"],
      hrows, [5, 22, 44, 60, 8, 30], rtl_cols=(4,), input_cols=(5, 6))

# --- Summary (formulas)
ws = wb.create_sheet("Summary", 0)
ws["A1"] = "Hebrew sources tracker — The Quest for Authenticity (Hebrew translation)"; ws["A1"].font = Font(name=FONT, bold=True, size=13)
ws["A2"] = "Built from sources/s2/quote-verification-table.csv (the verification project), the Koren footnote conversions (review/chNN/notes_koren.json) and the style-pass reports. Yellow cells are yours to fill; the counts below update as you mark items Done."
ws["A2"].alignment = Alignment(wrap_text=True); ws.merge_cells("A2:D2"); ws.row_dimensions[2].height = 45
ws.append([]); ws.append(["Sheet", "Items", "Marked done", "Open"])
for c in ws[4]:
    c.font = Font(name=FONT, bold=True); c.fill = HEAD
specs = [("Sources to locate", "G", "J"), ("Notes to verify", "D", "F"), ("Bibliography gaps", "A", "H"), ("Hebrew editions exist", "C", "E")]
for i, (name, keycol, donecol) in enumerate(specs, 5):
    ws[f"A{i}"] = name
    ws[f"B{i}"] = f"=COUNTA('{name}'!{keycol}2:{keycol}1000)"
    ws[f"C{i}"] = f"=COUNTIF('{name}'!{donecol}2:{donecol}1000,\"*\")"
    ws[f"D{i}"] = f"=B{i}-C{i}"
ws.append([]); ws.append(["Sources to locate, by chapter", "Items", "", ""])
for c in ws[ws.max_row]:
    c.font = Font(name=FONT, bold=True); c.fill = HEAD
for n in range(1, 7):
    r = ws.max_row + 1
    ws[f"A{r}"] = f"Chapter {n}"; ws[f"B{r}"] = f"=COUNTIF('Sources to locate'!A2:A1000,{n})"
ws.append([]); ws.append(["Status of all 229 quotations in the verification table", "", "", ""])
ws[ws.max_row][0].font = Font(name=FONT, bold=True)
tot = {s: sum(1 for r in tbl if r["status"] == s) for s in ("verified-text", "provisional", "checked-not-found")}
for s, v in tot.items():
    ws.append([s, v])
ws.cell(row=ws.max_row, column=3, value="(hardcoded from the CSV at build time — provisional = not yet looked up; checked-not-found = not found in the editions available)")
for row in ws.iter_rows(min_row=5):
    for c in row:
        if c.font.name != FONT or not c.font.bold:
            c.font = Font(name=FONT, size=10, bold=c.font.bold)
for col, w in zip("ABCD", (44, 10, 14, 10)):
    ws.column_dimensions[col].width = w
wb.save(out)
print(out, "| sources to locate:", len(rows), "| notes to verify:", len(nrows), "| bibliography gaps:", len(brows), "| Hebrew editions:", len(hrows))
