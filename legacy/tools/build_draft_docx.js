// Bilingual Word draft: English (left) | Hebrew (right, RTL), one table row per paragraph.
// Usage: node tools/build_draft_docx.js <data.json from draft_data.py> <out.docx>
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, WidthType, BorderStyle,
  AlignmentType, ShadingType, Footer, PageNumber, TableLayoutType,
} = require(path.join(__dirname, "node_docx", "node_modules", "docx"));

const [, , dataPath, outPath] = process.argv;
const data = JSON.parse(fs.readFileSync(dataPath, "utf8"));

const FONT = { ascii: "Times New Roman", hAnsi: "Times New Roman", cs: "Times New Roman" };
const PAGE_W = 11906, MARGIN = 1008;                 // A4, 0.7" margins
const TABLE_W = PAGE_W - 2 * MARGIN;                 // 9890
const COLS = [4550, TABLE_W - 4550];
const line = { style: BorderStyle.SINGLE, size: 4, color: "D9D9D9" };
const borders = { top: line, bottom: line, left: line, right: line };

function runs(parts, he, size, extra = {}) {
  return parts.map(r => new TextRun({
    text: r.t, font: FONT, size, sizeComplexScript: size, rightToLeft: he,
    bold: !!(r.b || extra.bold), boldComplexScript: !!(r.b || extra.bold),
    highlight: r.hl ? "yellow" : undefined, italics: !!r.i, italicsComplexScript: !!r.i, superScript: !!r.sup,
    color: r.sup ? "666666" : undefined,
  }));
}

function cellParas(c, he, notes) {
  const base = he ? (notes ? 20 : 24) : (notes ? 18 : 21);          // half-points
  return c.paras.map(p => {
    const heading = c.kind === "h";
    const size = heading ? base + (c.level === 1 ? 8 : 4) : base;
    return new Paragraph({
      bidirectional: he,
      alignment: he ? AlignmentType.START : AlignmentType.LEFT,
      spacing: { after: 60, line: he ? 300 : 264 },
      indent: c.kind === "q" ? { start: 284, end: 142 } : undefined,
      children: runs(p, he, size, { bold: heading }),
    });
  });
}

function cell(c, he, notes) {
  return new TableCell({
    width: { size: he ? COLS[1] : COLS[0], type: WidthType.DXA },
    borders,
    margins: { top: 60, bottom: 60, left: 120, right: 120 },
    shading: c.kind === "q" ? { fill: "F5F5F2", type: ShadingType.CLEAR, color: "auto" } : undefined,
    children: cellParas(c, he, notes),
  });
}

const header = new TableRow({
  tableHeader: true,
  children: [
    new TableCell({ width: { size: COLS[0], type: WidthType.DXA }, borders, shading: { fill: "EFEFEF", type: ShadingType.CLEAR, color: "auto" },
      children: [new Paragraph({ children: [new TextRun({ text: "English", font: FONT, size: 18, bold: true })] })] }),
    new TableCell({ width: { size: COLS[1], type: WidthType.DXA }, borders, shading: { fill: "EFEFEF", type: ShadingType.CLEAR, color: "auto" },
      children: [new Paragraph({ bidirectional: true, alignment: AlignmentType.START,
        children: [new TextRun({ text: "עברית", font: FONT, size: 20, sizeComplexScript: 20, bold: true, boldComplexScript: true, rightToLeft: true })] })] }),
  ],
});

const rows = [header, ...data.rows.map(r => new TableRow({ cantSplit: false, children: [cell(r.en, false, r.notes), cell(r.he, true, r.notes)] }))];
const today = new Date().toISOString().slice(0, 10);

const doc = new Document({
  creator: "The Quest for Authenticity — Hebrew translation",
  title: data.title,
  styles: { default: { document: { run: { font: FONT, size: 21 } } } },
  sections: [{
    properties: { page: { size: { width: PAGE_W, height: 16838 }, margin: { top: MARGIN, bottom: MARGIN, left: MARGIN, right: MARGIN } } },
    footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER,
      children: [new TextRun({ children: [PageNumber.CURRENT], font: FONT, size: 18, color: "666666" })] })] }) },
    children: [
      new Paragraph({ spacing: { after: 60 }, children: [new TextRun({ text: data.title, font: FONT, size: 32, bold: true })] }),
      new Paragraph({ spacing: { after: 200 }, border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: "BFBFBF", space: 4 } },
        children: [new TextRun({ text: `English | Hebrew draft · ${today}`, font: FONT, size: 18, color: "666666" })] }),
      new Table({ width: { size: TABLE_W, type: WidthType.DXA }, columnWidths: COLS, layout: TableLayoutType.FIXED, rows }),
    ],
  }],
});

Packer.toBuffer(doc).then(buf => { fs.writeFileSync(outPath, buf); console.log(outPath, data.rows.length, "rows"); });
