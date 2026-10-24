"""Side-by-side reading draft of a chapter: English on the left, the current Hebrew on the right.

Usage: python3 tools/build_draft.py <temp_dir> <out.html> "<Title>"
"""
import html
import re
import sys
from datetime import date
from pathlib import Path


def paras(path):
    return [p.strip() for p in re.split(r"\n\s*\n", path.read_text(encoding="utf-8")) if p.strip()]


def render(p):
    quote = p.startswith(">")
    p = re.sub(r"(?m)^>\s?", "", p)
    level = len(re.match(r"^(#*)", p).group(1))
    p = re.sub(r"^#+\s*", "", p)
    p = html.escape(p)
    p = re.sub(r"\^(\*|\d+)\^", r"<sup>\1</sup>", p)
    p = re.sub(r"==(.+?)==", r"<mark>\1</mark>", p, flags=re.S)
    p = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", p)
    p = re.sub(r"(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)", r"<em>\1</em>", p)
    p = p.replace("\\.", ".").replace("\n", "<br>")
    if level:
        return f'<h{min(level + 1, 4)}>{p}</h{min(level + 1, 4)}>'
    return f'<blockquote>{p}</blockquote>' if quote else f"<p>{p}</p>"


def main():
    temp_dir, out, title = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
    rows = []
    for src in sorted(temp_dir.glob("chunk[0-9][0-9][0-9][0-9].md")):
        n = src.name[5:9]
        en, he = paras(src), paras(temp_dir / f"output_chunk{n}.md")
        for e, h in zip(en, he):
            notes = " notes" if re.match(r"#+ .*(Notes|הערות)", e + h) else ""
            rows.append(f'<tr class="row{notes}"><td class="en" dir="ltr" lang="en">{render(e)}</td>'
                        f'<td class="he" dir="rtl" lang="he">{render(h)}</td></tr>')
    page = TEMPLATE.replace("$TITLE$", html.escape(title)).replace("$DATE$", date.today().isoformat()).replace("$ROWS$", "\n".join(rows))
    out.write_text(page, encoding="utf-8")
    print(out, len(rows), "paragraphs")


TEMPLATE = """<!DOCTYPE html>
<html lang="he"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>$TITLE$</title>
<style>
:root { --bg:#fff; --fg:#1d1d1f; --muted:#6b6b6b; --line:#e2e2e2; --quote:#f6f6f4; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { --bg:#16181c; --fg:#e8e8e8; --muted:#9aa0a6; --line:#33363b; --quote:#1f2226; } }
body { background:var(--bg); color:var(--fg); margin:0 auto; max-width:1200px; padding:24px 16px 64px; font-family:'Times New Roman', serif; }
header { border-bottom:1px solid var(--line); margin-bottom:8px; padding-bottom:8px; }
header h1 { font-size:22px; margin:0 0 4px; } header div { font-family:sans-serif; font-size:13px; color:var(--muted); }
table { border-collapse:collapse; width:100%; table-layout:fixed; }
td { vertical-align:top; padding:6px 14px; border-bottom:1px solid var(--line); }
td.en { font-size:15px; line-height:1.55; border-right:1px solid var(--line); }
td.he { font-size:19px; line-height:1.75; text-align:right; }
td p, td h2, td h3, td h4 { margin:0; }
h2 { font-size:21px; } h3 { font-size:19px; } h4 { font-size:17px; }
blockquote { margin:0; padding:4px 10px; background:var(--quote); border-inline-start:3px solid var(--line); }
sup { font-size:.7em; color:var(--muted); }
tr.notes ~ tr td { font-size:14px; } tr.notes ~ tr td.he { font-size:16px; }
@media (max-width:700px) { td { display:block; border-right:none !important; } td.en { border-bottom:none; padding-bottom:0; } }
@media print { body { max-width:none; padding:0; } td { padding:4px 8px; } tr { break-inside:avoid; } }
</style></head><body>
<header><h1>$TITLE$</h1><div>English | Hebrew draft · $DATE$</div></header>
<table><colgroup><col style="width:46%"><col style="width:54%"></colgroup><tbody>
$ROWS$
</tbody></table></body></html>"""

main()
