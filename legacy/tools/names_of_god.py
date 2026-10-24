"""Overview of how references to God are rendered in the Hebrew (chapters 1–6).

Usage: python3 tools/names_of_god.py [out.html]   (default review/names-of-god.html)

For every paragraph pair it records the English references to God and the Hebrew
forms used, and the paragraph's kind: author's voice, quotation (translated),
verified original source, or note. Paragraphs with a single English reference give
a clean English → Hebrew mapping; the page also lists every occurrence.
"""
import os
import html
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = (Path(os.environ["TRANSLATOR_PROJECT"]).expanduser().resolve() if os.environ.get("TRANSLATOR_PROJECT")
        else sys.exit("Set TRANSLATOR_PROJECT to the book folder, e.g. TRANSLATOR_PROJECT=~/the_translator"))
CHAPTERS = [("ch01", "ch01-introduction_temp", "1 Introduction"), ("ch02", "ch02-holy-rebellion_temp", "2 The Holy Rebellion"),
            ("ch03", "ch03-biographical-sketch_temp", "3 Biographical Sketch"), ("ch04", "ch04-torah-and-theology_temp", "4 Torah and Theology"),
            ("ch05", "ch05-zaddik-and-leadership_temp", "5 Zaddik and Leadership"), ("ch06", "ch06-quest-for-truth_temp", "6 Quest for Truth")]

# English references, most specific first (matched spans are blanked so they are not counted twice)
EN = [
    ("the Holy One, blessed be He", r"Holy One,? [Bb]lessed be He"),
    ("Master of the World / Universe", r"Master of the (?:World|Universe)|Ribbono shel Olam|Lord of the Universe"),
    ("God-consciousness", r"God-consciousness"),
    ("Godliness", r"Godliness"),
    ("the Divine (noun)", r"\bthe Divine\b(?! \w)"),
    ("Divine / divine (adj.)", r"\b[Dd]ivine\b"),
    ("Divinity", r"\b[Dd]ivinity\b"),
    ("the Creator", r"\b(?:the |his |His |their |our )?Creator\b"),
    ("the Almighty", r"\bAlmighty\b"),
    ("Hashem / the Name", r"\bHashem\b|\bthe Name\b"),
    ("Shekhinah", r"\bShekhin?ah\b"),
    ("Ein Sof / the Infinite", r"\bEin Sof\b|\bthe Infinite\b"),
    ("the Lord", r"\b(?:the )?Lord\b"),
    ("Heaven (for God)", r"\bHeaven\b"),
    ("God", r"\bGod(?:'s)?\b"),
]
P = "(?:[ובלמהכש]{0,3})"
HE = [
    ("הקדוש ברוך הוא", r"הקדוש ברוך הוא"),
    ('הקב"ה', r'קב"ה|קב״ה'),
    ("רבונו של עולם", r"רבו?נו של עולם|ריבונו של עולם"),
    ("בורא / הבורא", r"(?<![א-ת])" + P + r"בורא(?:ו|ם|נו|י|ך)?(?![א-ת])|בורא עולם"),
    ("יתברך", r"יתברך"),
    ("אלוקות / אלוהות", r"(?<![א-ת])" + P + r"אלו?[קה]ות(?![א-ת])"),
    ("האלוהי / האלוקי (adj./noun)", r"(?<![א-ת])" + P + r"אלו?[קה]י(?:ת|ים|ות)?(?![א-ת])"),
    ("אלוהים / אלוקים", r"(?<![א-ת])" + P + r"אלו?[קה]ים(?![א-ת])"),
    ("האל", r"(?<![א-ת])(?:[ובמש]{0,2}ה|[וש]?[בל])אל(?![א-ת'\"])(?=[\s,.;:?!)\]—–״\"־-]|$)"),
    ("ה' (the Name)", r"(?<![א-ת])" + P + r"ה['׳](?![א-ת])"),
    ("השם", r"(?<![א-ת])[ובלמכש]{0,2}השם(?![א-ת])"),
    ("השכינה", r"(?<![א-ת])" + P + r"שכינ(?:ה|תו)(?![א-ת])"),
    ("אין סוף", r"אין[ ־-]?סוף"),
    ("המקום", r"(?<![א-ת])[ובלמכש]{0,2}המקום(?= ברוך)"),
    ("שמים (for God)", r"(?<![א-ת])[ובלמכש]{0,2}(?:ה?שמים)(?![א-ת])"),
]
# ה' that is a letter/number, not the Name
NOT_NAME = re.compile(r"(?:נספח|כרך|פרק|חלק|סימן|אות|שער|מהדורה|עמ'|דף|פרשה|סעיף|יום|ספר|שורה|הערה) ה['׳]")


def paras(t):
    return [p.strip() for p in re.split(r"\n\s*\n", t) if p.strip()]


def find(table, text, blank=True):
    found, t = [], text
    for label, pat in table:
        for m in re.finditer(pat, t):
            found.append((label, m.group(0)))
        if blank:
            t = re.sub(pat, lambda m: " " * len(m.group(0)), t)
    return found


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "review" / "names-of-god.html"
    src = json.loads((ROOT / "sources" / "source-paragraphs.json").read_text(encoding="utf-8"))
    occ = []
    for ch, temp, title in CHAPTERS:
        notes = False
        for f in sorted((ROOT / temp).glob("chunk[0-9][0-9][0-9][0-9].md")):
            n = f.name[5:9]
            for i, (e, h) in enumerate(zip(paras(f.read_text(encoding="utf-8")), paras((ROOT / temp / f"output_chunk{n}.md").read_text(encoding="utf-8"))), 1):
                if re.match(r"#+ .*Notes", e):
                    notes = True
                kind = ("note" if notes else "source" if f"{n}-{i}" in src.get(ch, []) else "quote" if h.startswith(">") else "author")
                h_clean = NOT_NAME.sub(lambda m: " " * len(m.group(0)), h)
                en = find(EN, e)
                he = [x for x in find(HE, h_clean) if not (x[0] == "שמים (for God)" and re.search(r"יראת|ירא[יי]? |לשם", h_clean[max(0, h_clean.find(x[1]) - 6):h_clean.find(x[1])]))]
                if en or he:
                    occ.append(dict(ch=ch, title=title, id=f"{n}·{i}", kind=kind, en=en, he=he, en_text=e, he_text=h))
    write(out, occ)


def write(out, occ):
    kinds = {"author": "Author's voice", "quote": "Quotation (translated)", "source": "Original source", "note": "Note"}
    # 1. overall Hebrew form counts by kind
    tot = defaultdict(Counter)
    for o in occ:
        for lab, _ in o["he"]:
            tot[lab][o["kind"]] += 1
    # 2. clean mapping: paragraphs with exactly one English term type (author voice + translated quotes)
    mapping = defaultdict(Counter)
    for o in occ:
        labs = {l for l, _ in o["en"]}
        if len(labs) == 1 and o["kind"] in ("author", "quote", "note"):
            for lab, _ in o["he"]:
                mapping[(next(iter(labs)), o["kind"] if o["kind"] != "note" else "note")][lab] += 1
    # 3. per chapter, author voice
    perch = defaultdict(Counter)
    for o in occ:
        if o["kind"] == "author":
            for lab, _ in o["he"]:
                perch[lab][o["ch"]] += 1
    he_labels = [l for l, _ in HE]
    chs = [c for c, _, _ in CHAPTERS]

    def t1():
        rows = "".join(f"<tr><td dir='rtl' class='he'>{html.escape(l)}</td>" + "".join(f"<td>{tot[l][k] or ''}</td>" for k in kinds) +
                       f"<td><b>{sum(tot[l].values())}</b></td></tr>" for l in he_labels if tot[l])
        return f"<table><tr><th>Hebrew form</th>{''.join(f'<th>{v}</th>' for v in kinds.values())}<th>Total</th></tr>{rows}</table>"

    def t2():
        rows = ""
        for (enl, kind), c in sorted(mapping.items(), key=lambda kv: (-sum(kv[1].values()))):
            forms = " · ".join(f"<span dir='rtl'>{html.escape(l)}</span> <b>{n}</b>" for l, n in c.most_common())
            rows += f"<tr><td>{html.escape(enl)}</td><td>{kinds[kind]}</td><td class='forms'>{forms}</td></tr>"
        return f"<table><tr><th>English</th><th>Where</th><th>Hebrew forms used in the same paragraph (count)</th></tr>{rows}</table>"

    def t3():
        rows = "".join(f"<tr><td dir='rtl' class='he'>{html.escape(l)}</td>" + "".join(f"<td>{perch[l][c] or ''}</td>" for c in chs) + "</tr>"
                       for l in he_labels if perch[l])
        return f"<table><tr><th>Hebrew form</th>{''.join(f'<th>{c}</th>' for c in chs)}</tr>{rows}</table>"

    def mark(text, items, rtl):
        t = html.escape(text)
        for _, s in sorted(set(items), key=lambda x: -len(x[1])):
            e = html.escape(s)
            t = re.sub(("(?<![א-ת])" if rtl else r"\b") + re.escape(e) if not rtl else re.escape(e), lambda m: f"<mark>{m.group(0)}</mark>", t) if False else t.replace(e, f"<mark>{e}</mark>")
        return re.sub(r"\^(\d+)\^", r"<sup>\1</sup>", t).replace("\n", "<br>")

    rows = []
    for o in occ:
        rows.append(
            f"<tr data-kind='{o['kind']}' data-en='{html.escape('|'.join(sorted({l for l, _ in o['en']})))}' data-he='{html.escape('|'.join(sorted({l for l, _ in o['he']})))}'>"
            f"<td class='id'>{o['ch']}<br>{o['id']}<br><span class='k {o['kind']}'>{kinds[o['kind']]}</span></td>"
            f"<td dir='ltr' class='en'>{mark(o['en_text'], o['en'], False)}</td><td dir='rtl' class='he'>{mark(o['he_text'], o['he'], True)}</td></tr>")
    en_opts = "".join(f"<option>{html.escape(l)}</option>" for l, _ in EN)
    he_opts = "".join(f"<option>{html.escape(l)}</option>" for l in he_labels)
    page = TEMPLATE.replace("$T1$", t1()).replace("$T2$", t2()).replace("$T3$", t3()).replace("$ROWS$", "".join(rows)) \
        .replace("$ENOPTS$", en_opts).replace("$HEOPTS$", he_opts).replace("$N$", str(len(occ)))
    out.write_text(page, encoding="utf-8")
    print(out, len(occ), "paragraphs with references to God")


TEMPLATE = """<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Names of God</title><style>
:root{--bg:#fff;--fg:#1d1d1f;--muted:#666;--line:#ddd;--head:#f3f3f3;--mark:#fff1a8}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#16181c;--fg:#e8e8e8;--muted:#9aa0a6;--line:#3a3d42;--head:#23262b;--mark:#5c4d00}}
body{background:var(--bg);color:var(--fg);font-family:sans-serif;margin:0 auto;max-width:1250px;padding:16px}
h1{font-size:22px} h2{font-size:17px;margin-top:28px} p.help{color:var(--muted);font-size:13px;max-width:900px}
table{border-collapse:collapse;width:100%;margin:6px 0} th,td{border:1px solid var(--line);padding:5px 8px;font-size:13px;vertical-align:top} th{background:var(--head);text-align:left}
td.he{font-family:'Times New Roman',serif;font-size:17px;text-align:right} td.en{font-family:'Times New Roman',serif;font-size:14px;color:var(--muted)} td.forms{font-size:14px}
td.id{width:90px;font-size:12px;color:var(--muted)} mark{background:var(--mark);color:inherit} .k{font-size:11px;font-weight:bold}
.k.source{color:#0f766e}.k.quote{color:#7c3aed}.k.note{color:#a16207}.k.author{color:#1d4ed8}
.bar{position:sticky;top:0;background:var(--bg);padding:8px 0;border-bottom:1px solid var(--line);display:flex;gap:10px;flex-wrap:wrap;align-items:center;font-size:13px}
select{font:inherit;padding:3px} #all td:nth-child(2),#all td:nth-child(3){width:44%}
@media(max-width:700px){#all td{display:block;width:auto!important}}
</style></head><body>
<h1>Names of God — how they are rendered (chapters 1–6)</h1>
<p class="help">Automatic survey of the current Hebrew. "Author's voice" is Rosen's own prose; "Quotation" is a translated quotation; "Original source" is verified Hebrew inserted from the sources (not ours to change); "Note" is the endnotes. Matching is by paragraph, so a paragraph with two English terms shows both; the mapping table uses only paragraphs with a single English term. Counts are approximate — האל can occasionally be a different word, and שמים is counted only where it is not part of יראת/לשם שמים.</p>
<h2>1. Hebrew forms used, by kind of text</h2>$T1$
<h2>2. English term → Hebrew forms (paragraphs with one English term)</h2>$T2$
<h2>3. Author's voice only, by chapter</h2>$T3$
<h2>4. Every occurrence ($N$ paragraphs)</h2>
<div class="bar">English <select id="fen"><option value="">any</option>$ENOPTS$</select> Hebrew <select id="fhe"><option value="">any</option>$HEOPTS$</select>
Kind <select id="fk"><option value="">any</option><option value="author">Author's voice</option><option value="quote">Quotation</option><option value="source">Original source</option><option value="note">Note</option></select> <span id="cnt"></span></div>
<table id="all"><tr><th>Where</th><th>English</th><th>Hebrew</th></tr>$ROWS$</table>
<script>
const rows=[...document.querySelectorAll("#all tr[data-kind]")];
function f(){const e=fen.value,h=fhe.value,k=fk.value;let n=0;rows.forEach(r=>{const ok=(!e||r.dataset.en.split("|").includes(e))&&(!h||r.dataset.he.split("|").includes(h))&&(!k||r.dataset.kind===k);r.style.display=ok?"":"none";n+=ok});cnt.textContent=n+" paragraphs";}
[fen,fhe,fk].forEach(s=>s.onchange=f);f();
</script></body></html>"""

main()
