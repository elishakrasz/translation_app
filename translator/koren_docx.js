// Hebrew book-format chapter with real Word footnotes (Koren-style layout), one bookmark per block.
// Usage: node translator/koren_docx.js <data.json from translator/build.py> <out.docx>
// From the Rosen builder (legacy/tools/build_book_docx.js); new: every paragraph and every note carries its
// permanent block ID as a Word bookmark (p_ch02_0014, n_ch02_012), so the import maps edits back by ID.
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, FootnoteReferenceRun, AlignmentType, Footer, PageNumber, BorderStyle,
  Bookmark,
} = require(path.join(__dirname, "..", "legacy", "tools", "node_docx", "node_modules", "docx"));
// "ch02.p0014" -> "p_ch02_0014"; "ch02.n012" -> "n_ch02_012" (Word: a letter first, letters, digits and _ only)
const bm = id => { const [u, b] = id.split("."); return `${b[0]}_${u}_${b.slice(1)}`.replace(/[^A-Za-z0-9_]/g, "_"); };
const marked = (id, runs) => (id ? [new Bookmark({ id: bm(id), children: runs })] : runs);

const [, , dataPath, outPath] = process.argv;
const data = JSON.parse(fs.readFileSync(dataPath, "utf8"));
const FONT = { ascii: "Times New Roman", hAnsi: "Times New Roman", cs: "Times New Roman" };
// The editor's asterisk note (custom mark "*", outside the numbering) gets footnote id 1 and the numbered
// notes shift up by one, so the footnotes file lists them in reference order (LibreOffice pairs by order).
const HAS_STAR = Object.prototype.hasOwnProperty.call(data.notes, "*");
const STAR = 1;
const fid = n => (n === "*" ? STAR : Number(n) + (HAS_STAR ? 1 : 0));
const isLatin = s => /[A-Za-z]/.test(s) && !/[֐-׿]/.test(s);

// Split mixed Hebrew/English text into direction runs, so an English phrase inside a Hebrew
// paragraph (e.g. an editor's "[לבדיקה: …]" remark) keeps its word order.
const LATIN_SPAN = /([A-Za-z][A-Za-z0-9 .,;:'’"“”()\-–—/&?!§]*[A-Za-z0-9.)'’"”?!])|([A-Za-z])/g;
function dirSegments(t) {
  if (isLatin(t) || !/[A-Za-z]/.test(t)) return [[t, !isLatin(t)]];
  const segs = []; let last = 0;
  for (const m of t.matchAll(LATIN_SPAN)) {
    if (m.index > last) segs.push([t.slice(last, m.index), true]);
    segs.push([m[0], false]); last = m.index + m[0].length;
  }
  if (last < t.length) segs.push([t.slice(last), true]);
  return segs;
}

// An English remark that contains Hebrew words ("[לבדיקה: Original applied … נפלאות היהודי 22 …]") is wrapped
// as one left-to-right embedding (LRE … PDF), so the bidi algorithm keeps it as a single English sentence.
const LRE = "‪", PDF = "‬";
const REMARK = /(\[לבדיקה:\s*)([^\]]*[A-Za-z][^\]]*)(\])/g;
function embedSegments(t) {
  const segs = []; let last = 0;
  for (const m of t.matchAll(REMARK)) {
    const start = m.index + m[1].length;
    if (start > last) segs.push(...dirSegments(t.slice(last, start)));
    segs.push([LRE + m[2] + PDF, false]);
    last = start + m[2].length;
  }
  if (last < t.length) segs.push(...dirSegments(t.slice(last)));
  return segs;
}

function textRuns(rs, size, extra = {}) {
  const out = [];
  for (const r of rs) {
    if (r.fn !== undefined) { out.push(new FootnoteReferenceRun(fid(r.fn))); continue; }
    if (r.br) { out.push(new TextRun({ break: 1, font: FONT, size })); continue; }   // line break inside a paragraph
    for (const [text, rtl] of embedSegments(r.t)) {
      out.push(new TextRun({
        text, font: FONT, size, sizeComplexScript: size, rightToLeft: rtl,
        bold: !!(r.b || extra.bold), boldComplexScript: !!(r.b || extra.bold),
        highlight: r.hl ? "yellow" : undefined, italics: !!r.i, italicsComplexScript: false,
      }));
    }
  }
  return out;
}

// Book page 15.5 × 23 cm (a common Koren/Maggid trim), 2 cm margins
const W = 8787, H = 13041, M = 1134;
const footnotes = {};
for (const [n, rs] of Object.entries(data.notes)) {
  const more = (data.notes_more || {})[n] || [];   // continuation paragraphs of a long note (block quotes indented)
  footnotes[fid(n)] = { children: [new Paragraph({ bidirectional: true, alignment: AlignmentType.START, spacing: { after: 40, line: 240 },
    children: marked((data.note_ids || {})[n], textRuns(rs, 18)) }), ...more.map(m => new Paragraph({ bidirectional: true, alignment: AlignmentType.BOTH,
    indent: m.q ? { start: 340, end: 340 } : undefined, spacing: { after: 40, line: 240 }, children: textRuns(m.runs, m.q ? 17 : 18) }))] };
}

const children = [];
let first = true;
const breaks = new Set(data.pageBreakBefore || []), centerUntil = data.centerUntil || 0;
for (const [bi, b] of data.blocks.entries()) {
  if (b.kind === "li") {   // list item (contents, lineage chart): no bullet, indented by depth
    children.push(new Paragraph({ bidirectional: true, alignment: AlignmentType.START, pageBreakBefore: breaks.has(bi),
      indent: { start: 425 * b.level }, spacing: { after: 40, line: 276 }, children: textRuns(b.runs, b.level ? 21 : 22, { bold: !b.level }) }));
    continue;
  }
  if (b.kind === "sep") {  // section separator: a centred "* * *"
    children.push(new Paragraph({ bidirectional: true, alignment: AlignmentType.CENTER, spacing: { before: 200, after: 200 },
      children: textRuns([{ t: "* * *" }], 22) }));
    first = true;
    continue;
  }
  if (bi < centerUntil) {  // title page: centred, larger
    children.push(new Paragraph({ bidirectional: true, alignment: AlignmentType.CENTER, pageBreakBefore: breaks.has(bi),
      spacing: { before: bi === 0 ? 2400 : 240, after: 240 }, children: textRuns(b.runs, b.kind === "h" ? (b.level === 1 ? 44 : 30) : 26, { bold: b.kind === "h" }) }));
    continue;
  }
  if (b.kind === "h") {
    // chapter label ("פרק א'") above the chapter title, as in the Koren model book
    if (b.level === 1 && data.label && !children.length) {
      children.push(new Paragraph({ bidirectional: true, alignment: AlignmentType.CENTER, spacing: { before: 0, after: 120 }, keepNext: true,
        children: textRuns([{ t: data.label }], 26) }));
    }
    children.push(new Paragraph({ bidirectional: true, alignment: b.level === 1 ? AlignmentType.CENTER : AlignmentType.START, pageBreakBefore: breaks.has(bi),
      spacing: { before: b.level === 1 ? 0 : 280, after: b.level === 1 ? 360 : 120 }, keepNext: true,
      children: marked(b.id, textRuns(b.runs, b.level === 1 ? 36 : 26, { bold: true })) }));
    first = true;
    continue;
  }
  children.push(new Paragraph({
    bidirectional: true, alignment: AlignmentType.BOTH,
    indent: b.kind === "q" ? { start: 425, end: 425 } : (first ? undefined : { firstLine: 284 }),
    spacing: { after: b.kind === "q" ? 120 : 0, before: b.kind === "q" ? 120 : 0, line: 300 },
    children: marked(b.id, textRuns(b.runs, b.kind === "q" ? 20 : 22)),
  }));
  first = b.kind === "q";
}

const doc = new Document({
  title: data.title,
  styles: { default: { document: { run: { font: FONT, size: 22, sizeComplexScript: 22, rightToLeft: true } } } },
  footnotes,
  sections: [{
    properties: { page: { size: { width: W, height: H }, margin: { top: M, bottom: M, left: M, right: M } } },
    footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER,
      children: [new TextRun({ children: [PageNumber.CURRENT], font: FONT, size: 18 })] })] }) },
    children,
  }],
});
// Right-to-left section: footnote separator and page layout on the right
const JSZip = require(path.join(__dirname, "..", "legacy", "tools", "node_docx", "node_modules", "jszip"));
Packer.toBuffer(doc).then(async buf => {
  const zip = await JSZip.loadAsync(buf);
  const xml = await zip.file("word/document.xml").async("string");
  // schema order: …titlePg, textDirection, bidi, rtlGutter, docGrid
  const fixed = xml.replace(/<w:sectPr\b[\s\S]*?<\/w:sectPr>/g, sp => sp.includes("<w:bidi/>") ? sp
    : sp.includes("<w:docGrid") ? sp.replace("<w:docGrid", "<w:bidi/><w:docGrid") : sp.replace("</w:sectPr>", "<w:bidi/></w:sectPr>"));
  zip.file("word/document.xml", !HAS_STAR ? fixed : fixed.replace(`<w:footnoteReference w:id="${STAR}"/>`, `<w:footnoteReference w:customMarkFollows="1" w:id="${STAR}"/><w:t>*</w:t>`));
  // separator lines: right-to-left paragraphs (so the rule sits on the right), without a stray reference mark
  const fx = await zip.file("word/footnotes.xml").async("string");
  const fx2 = !HAS_STAR ? fx : fx.replace(new RegExp(`(<w:footnote w:id="${STAR}">[\\s\\S]*?)<w:footnoteRef/>`), "$1<w:t>*</w:t>");
  zip.file("word/footnotes.xml", fx2.replace(/(<w:footnote w:type="(?:separator|continuationSeparator)" w:id="-?\d+">)[\s\S]*?(<\/w:footnote>)/g,
    (m, a, b) => a + `<w:p><w:pPr><w:bidi/><w:spacing w:after="0" w:line="240" w:lineRule="auto"/></w:pPr><w:r><w:${m.includes("continuationSeparator") ? "continuationSeparator" : "separator"}/></w:r></w:p>` + b));
  fs.writeFileSync(outPath, await zip.generateAsync({ type: "nodebuffer" }));
  console.log(outPath, data.blocks.length, "paragraphs,", Object.keys(footnotes).length, "footnotes");
});
