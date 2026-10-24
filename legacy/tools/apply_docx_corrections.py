"""Apply fidelity corrections to a COPY of an edited Koren docx.

Usage: python3 tools/apply_docx_corrections.py <edited.docx> <corrections.json> <out.docx>

corrections.json: {"corrections":[{"id":"B12"|"N5","current":"…","proposed":"…"}]}
B<n> = the n-th non-empty paragraph of the document (the numbering of tools/align_koren_edits.py);
N<n> = footnote n (Word footnote id; chapters with an asterisk note shift by one — pass ids as in the bundle).
Each `current` is replaced inside that paragraph only, across Word runs if needed; the formatting of the
first affected run is kept. Prints one line per correction; nothing is written if any correction fails.
"""
import html
import json
import re
import sys
import zipfile

esc = lambda s: html.escape(s, quote=False)


def paragraph_spans(xml):
    """Non-empty paragraphs in document order, numbered as align_koren_edits.py does."""
    out = []
    for pm in re.finditer(r"<w:p[ >].*?</w:p>", xml, re.S):
        p = re.sub(r"<w:footnoteReference [^>]*w:id=\"(\d+)\"/>", lambda m: f"^F{m.group(1)}^", pm.group(0))
        t = html.unescape(re.sub(r"<[^>]+>", "", re.sub(r"<w:delText>.*?</w:delText>", "", p))).strip()
        if t:
            out.append((pm.start(), pm.end()))
    return out


def replace_in_paragraph(p, cur, new):
    ts = list(re.finditer(r"(<w:t(?: [^>]*)?>)(.*?)(</w:t>)", p, re.S))
    full = "".join(html.unescape(t.group(2)) for t in ts)
    if full.count(cur) != 1:
        return None, f"found {full.count(cur)}×"
    k = full.index(cur); end = k + len(cur); pos = 0; edits = []; first = True
    for t in ts:
        txt = html.unescape(t.group(2)); a, b = pos, pos + len(txt); pos = b
        if b <= k or a >= end:
            continue
        before = txt[:max(0, k - a)]; after = txt[end - a:] if end < b else ""
        edits.append((t, before + (new if first else "") + after)); first = False
    for t, newtxt in reversed(edits):
        tag = t.group(1) if "xml:space" in t.group(1) else t.group(1).replace("<w:t", '<w:t xml:space="preserve"', 1)
        p = p[:t.start()] + tag + esc(newtxt) + t.group(3) + p[t.end():]
    return p, "ok"


def main():
    src, cpath, dst = sys.argv[1:4]
    corr = json.load(open(cpath, encoding="utf-8"))["corrections"]
    z = zipfile.ZipFile(src); files = {n: z.read(n) for n in z.namelist()}
    doc = files["word/document.xml"].decode(); fn = files["word/footnotes.xml"].decode()
    failed = []
    for c in corr:
        iid = c["id"]
        if iid.startswith("B"):
            spans = paragraph_spans(doc); n = int(iid[1:])
            if n > len(spans):
                failed.append(iid); print(iid, "paragraph out of range"); continue
            a, b = spans[n - 1]
            newp, msg = replace_in_paragraph(doc[a:b], c["current"], c["proposed"])
            if newp is None:
                failed.append(iid); print(iid, "NOT applied:", msg, "|", c["current"]); continue
            doc = doc[:a] + newp + doc[b:]
        else:
            m = re.search(rf'(<w:footnote [^>]*w:id="{int(iid[1:])}"[^>]*>)(.*?)(</w:footnote>)', fn, re.S)
            if not m:
                failed.append(iid); print(iid, "footnote not found"); continue
            body = m.group(2); done = False
            for pm in re.finditer(r"<w:p[ >].*?</w:p>", body, re.S):
                newp, msg = replace_in_paragraph(pm.group(0), c["current"], c["proposed"])
                if newp is not None:
                    body = body[:pm.start()] + newp + body[pm.end():]; done = True; break
            if not done:
                failed.append(iid); print(iid, "NOT applied: text not found in the footnote |", c["current"]); continue
            fn = fn[:m.start(2)] + body + fn[m.end(2):]
        print(iid, "ok:", c["current"], "→", c["proposed"])
    if failed:
        print("NOTHING WRITTEN —", len(failed), "failed:", failed); sys.exit(1)
    files["word/document.xml"] = doc.encode(); files["word/footnotes.xml"] = fn.encode()
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as out:
        for n, b in files.items():
            out.writestr(n, b)
    print("written", dst)


if __name__ == "__main__":
    main()
