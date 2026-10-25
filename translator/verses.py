"""Check the vocalised Bible verses in a translated unit against Sefaria (the Masoretic text).

The English gives the references (Gen. 2:1, Ex. 16:29). Every chapter they name is fetched from Sefaria once and
cached in the library. Each vocalised phrase in the Hebrew is looked up by its letters, first in the chapters cited in
the same paragraph, then in all of them:
- letters and vowels found as written: correct;
- letters found, vowels different, two words or more: Sefaria's vocalisation is the correction (no cantillation or
  meteg; qamats qatan as a plain qamats; the Tetragrammaton as ה');
- a single word that differs is reported, not changed: it may be Polen's dictionary form (בֵּרֵךְ for "barekh");
- letters not found: reported for a person to look at, never guessed.
"""

import html
import json
import re
import unicodedata
import urllib.request
from pathlib import Path

from . import records

BOOKS = {  # English forms in the book -> Sefaria's names
    "Gen": "Genesis", "Genesis": "Genesis", "Ex": "Exodus", "Exod": "Exodus", "Exodus": "Exodus",
    "Lev": "Leviticus", "Leviticus": "Leviticus", "Num": "Numbers", "Numbers": "Numbers",
    "Deut": "Deuteronomy", "Deuteronomy": "Deuteronomy", "Josh": "Joshua", "Joshua": "Joshua",
    "Judg": "Judges", "Judges": "Judges", "I Sam": "I Samuel", "II Sam": "II Samuel", "1 Sam": "I Samuel",
    "2 Sam": "II Samuel", "I Kings": "I Kings", "II Kings": "II Kings", "1 Kings": "I Kings", "2 Kings": "II Kings",
    "Is": "Isaiah", "Isa": "Isaiah", "Isaiah": "Isaiah", "Jer": "Jeremiah", "Jeremiah": "Jeremiah",
    "Ezek": "Ezekiel", "Ezekiel": "Ezekiel", "Hos": "Hosea", "Amos": "Amos", "Mic": "Micah", "Zech": "Zechariah",
    "Mal": "Malachi", "Ps": "Psalms", "Psalm": "Psalms", "Psalms": "Psalms", "Prov": "Proverbs", "Proverbs": "Proverbs",
    "Job": "Job", "Song": "Song of Songs", "Ruth": "Ruth", "Lam": "Lamentations", "Eccl": "Ecclesiastes",
    "Esth": "Esther", "Dan": "Daniel", "Ezra": "Ezra", "Neh": "Nehemiah", "Nehemiah": "Nehemiah",
    "I Chron": "I Chronicles", "II Chron": "II Chronicles", "1 Chron": "I Chronicles", "2 Chron": "II Chronicles",
    "I Samuel": "I Samuel", "II Samuel": "II Samuel", "I Chronicles": "I Chronicles", "II Chronicles": "II Chronicles",
    "Ecclesiastes": "Ecclesiastes", "Lamentations": "Lamentations", "Esther": "Esther", "Daniel": "Daniel",
    "Hosea": "Hosea", "Micah": "Micah", "Zechariah": "Zechariah", "Malachi": "Malachi", "Lev.": "Leviticus",
}
REF_RE = re.compile(r"\b(" + "|".join(sorted((re.escape(k) for k in BOOKS), key=len, reverse=True)) +
                    r")\.?\s+(\d+):(\d+)")

LETTER = "א-ת"
POINT = "ְ-ׇּׁׂ"
MAQAF = "־"
CANTILLATION = re.compile("[֑-ֽ֯׀׃ׅׄ׆]")   # te'amim, meteg, paseq, sof pasuq
POINTS = re.compile(f"[{POINT}]")
WORD = f"[{LETTER}{POINT}]*[{POINT}][{LETTER}{POINT}]*"
VOC_RUN = re.compile(f"{WORD}(?:[\\s{MAQAF}]+{WORD})*")
SEP = re.compile(f"[\\s{MAQAF}]+")
# The Tetragrammaton, with any prefix, as the book writes it: ה' (לַיהוָה -> לַה').
TETRAGRAMMATON = re.compile(f"([{LETTER}][{POINT}]*)?י[{POINT}]*ה[{POINT}]*ו[{POINT}]*ה[{POINT}]*(?![{LETTER}])")


def nfc(text):
    """One canonical form: the combining grapheme joiner Sefaria uses to fix the order of two vowels (ירושלִַם) is
    dropped, then Unicode NFC orders the marks, so the same pointing always compares equal."""
    return unicodedata.normalize("NFC", text.replace("\u034F", ""))


def clean_verse(text):
    """Sefaria's text as the book prints it."""
    text = html.unescape(text)
    # ketiv / qere: a vocalised quotation prints the qere (read) form; the ketiv (written) letters are dropped
    text = re.sub(r'<span class="mam-kq-k">.*?</span>', "", text)
    text = re.sub(r'<span class="mam-kq-q">\[(.*?)\]</span>', r"\1", text)
    text = re.sub(r"<(big|small|sup)[^>]*>|</(big|small|sup)>", "", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\{[^}]*\}", "", text)
    text = CANTILLATION.sub("", text).replace("ׇ", "ָ")
    text = TETRAGRAMMATON.sub(lambda m: (m.group(1) or "") + "ה'", nfc(text))
    text = re.sub(f"{MAQAF}\\s+", MAQAF, text)
    return re.sub(r"\s+", " ", text).strip()


def skeleton(word):
    return POINTS.sub("", word)


def bare(word):
    return re.sub(f"[^{LETTER}{POINT}]", "", word)


def split_prefix(word):
    """A Hebrew prefix written unpointed before a quoted pointed word (לוַיְבָרֶךְ): (prefix, word)."""
    for n in (1, 2):
        if len(word) > n + 1 and not POINTS.search(word[:n + 1]):   # the prefix letters carry no vowel of their own
            yield word[:n], word[n:]


def fetch_chapter(cache, book, chapter):
    """[(ref, cleaned verse text)] for a chapter, from the cache or from Sefaria."""
    f = cache / f"{book.replace(' ', '_')}.{chapter}.json"
    if not f.exists():
        url = f"https://www.sefaria.org/api/v3/texts/{book.replace(' ', '_')}.{chapter}?version=hebrew"
        with urllib.request.urlopen(url, timeout=30) as r:
            data = json.loads(r.read().decode("utf-8"))
        v = data["versions"][0]
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({"version": v.get("versionTitle"), "text": v["text"]}, ensure_ascii=False), encoding="utf-8")
    data = json.loads(f.read_text(encoding="utf-8"))
    return [(f"{book} {chapter}:{i}", clean_verse(t)) for i, t in enumerate(data["text"], 1) if isinstance(t, str)]


def references(text):
    return sorted({(BOOKS[m.group(1)], int(m.group(2))) for m in REF_RE.finditer(text)})


def loose(word):
    """The letters without the vowel letters ו and י: to find a verse quoted in plene spelling (השביעי for השבעי)."""
    k = skeleton(word)
    return k[:1] + re.sub("[וי]", "", k[1:])          # never at the start: a leading ו is a word, not a spelling


def find(run_words, verses, key=skeleton):
    """('exact', ref, words) if found as written, ('vowels', ref, words) if only the letters match, or None."""
    target = [key(w) for w in run_words]
    first = None
    for ref, text in verses:
        words = [w for w in (bare(x) for x in SEP.split(text)) if w]
        skel = [key(w) for w in words]
        for i in range(len(skel) - len(target) + 1):
            if skel[i:i + len(target)] == target:
                if words[i:i + len(target)] == run_words:
                    return "exact", ref, run_words
                first = first or ("vowels", ref, words[i:i + len(target)])
    return first


def check(project, unit, write=False):
    """Returns (corrections, single words differing, not found, chapters checked)."""
    udir = project.unit_dir(unit)
    cache = Path(__file__).resolve().parent.parent / "library" / "sefaria"
    english = {}
    for p in sorted(udir.glob("chunk[0-9]*.md")):
        for m in re.finditer(r"(.*?)\s*<!--id:([^>]*)-->", p.read_text(encoding="utf-8"), re.S):
            english[m.group(2)] = m.group(1)
    chapters = references("\n".join(english.values()))
    by_chapter = {(b, c): fetch_chapter(cache, b, c) for b, c in chapters}
    all_verses = [v for vs in by_chapter.values() for v in vs]
    fixes, singles, missing, edits = [], [], [], []
    for out in sorted(udir.glob("output_chunk[0-9]*.md")):
        text = nfc(out.read_text(encoding="utf-8"))
        new_text = text
        flags = [(f.start(), f.end()) for f in re.finditer(r"\[לבדיקה[^\]]*\]", text)]
        for m in VOC_RUN.finditer(text):
            if any(a <= m.start() < b for a, b in flags):
                continue                                  # inside a translator's note, not the text
            run = m.group(0)
            raw = [w for w in SEP.split(run) if w]
            if len(raw) == 1 and (len(skeleton(raw[0])) <= 2 or len(POINTS.findall(raw[0])) < 2):
                continue                                  # a lone, lightly pointed word: a reading aid, not a quotation
            block = re.search(r"<!--id:([^>]*)-->", text[m.end():])
            bid = block.group(1) if block else "?"
            near = [v for c in references(english.get(bid, "")) for v in by_chapter.get(c, [])]
            prefix, words = "", raw
            hit = find(words, near + all_verses)
            if not hit:                                   # perhaps a Hebrew prefix written before the quoted word
                for p, first in split_prefix(raw[0]):
                    if (alt := find([first] + raw[1:], near + all_verses)):
                        prefix, words, hit = p, [first] + raw[1:], alt
                        break
            if not hit and len(raw) >= 2:                 # spelled differently from the Masoretic text (plene / defective)
                alt = find(raw, near + all_verses, key=loose)
                if alt:
                    hit = ("spelling", alt[1], alt[2])
            if not hit:
                missing.append((out.name, bid, run))
                continue
            kind, ref, good = hit
            if kind == "exact":
                continue
            if kind == "spelling":
                kind = "vowels"
            if len(words) == 1:
                singles.append((out.name, bid, ref, run, good[0]))
                continue
            seps = SEP.findall(run)
            fixed = prefix + good[0] + "".join(s + w for s, w in zip(seps, good[1:]))
            fixes.append((out.name, bid, ref, run, fixed))
            new_text = new_text.replace(run, fixed, 1)
            edits.append({"command": "translator verses check", "unit": unit["id"], "block": bid,
                          "before": run, "after": fixed, "reason": f"vocalisation as in Sefaria, {ref}"})
        if write and new_text != text:
            out.write_text(new_text, encoding="utf-8")
    if write and edits:
        records.append(project, "edits", edits, by="translator verses check")
    return fixes, singles, missing, chapters


# ---------------------------------------------------------------------------
# Vocalising the verses a translator left unpointed
# ---------------------------------------------------------------------------

QUOTED = re.compile(r'"([^"\n]{3,600})"|^> (.+)$', re.M)
# An unpointed word: letters, with a geresh or gershayim inside (רש"י) or a geresh at the end (ה'); never a closing quote.
PLAIN_WORD = f"(?:[{LETTER}]{{1,2}}'(?![{LETTER}])|[{LETTER}]+(?:[\"'][{LETTER}]+)?)"


def _plain_runs(segment):
    """Runs of unpointed Hebrew words in a quoted segment: [(start, end, [words])]."""
    out = []
    for m in re.finditer(f"{PLAIN_WORD}(?:[\\s{MAQAF}]+{PLAIN_WORD})+", segment):
        words = [w for w in SEP.split(m.group(0)) if w]
        if len(words) >= 2 and not POINTS.search(m.group(0)):
            out.append((m.start(), m.end(), words))
    return out


def _longest_match(words, verses):
    """The longest stretch (2+ words) of `words`, from its start, matching a verse by letters: (n, ref, Sefaria text)."""
    best = None
    for ref, text in verses:
        vwords = [w for w in SEP.split(text) if w]
        vskel = [skeleton(bare(w)) for w in vwords]
        target = [skeleton(re.sub(f"[^{LETTER}]", "", w)) for w in words]
        for i in range(len(vskel)):
            n = 0
            while i + n < len(vskel) and n < len(target) and vskel[i + n] == target[n]:
                n += 1
            if n >= 2 and (not best or n > best[0]):
                # rebuild Sefaria's span with its own separators (maqaf matters for the vowels)
                span = re.split(f"([\\s{MAQAF}]+)", text)
                tokens = [t for t in span if t and not re.fullmatch(f"[\\s{MAQAF}]+", t)]
                seps = [t for t in span if t and re.fullmatch(f"[\\s{MAQAF}]+", t)]
                keep = lambda w: re.sub(f"[^{LETTER}{POINT}']", "", w)           # keeps the geresh of ה'
                piece = keep(tokens[i]) + "".join(s + keep(w) for s, w in zip(seps[i:i + n - 1], tokens[i + 1:i + n]))
                best = (n, ref, piece)
    return best


def vocalise(project, unit, write=False):
    """Vocalise every unpointed Bible verse quoted in the translator's text, from Sefaria. Returns [(block, ref, before, after)]."""
    udir = project.unit_dir(unit)
    cache = Path(__file__).resolve().parent.parent / "library" / "sefaria"
    english = {}
    for p in sorted(udir.glob("chunk[0-9]*.md")):
        for m in re.finditer(r"(.*?)\s*<!--id:([^>]*)-->", p.read_text(encoding="utf-8"), re.S):
            english[m.group(2)] = m.group(1)
    changes, edits = [], []
    for out in sorted(udir.glob("output_chunk[0-9]*.md")):
        text = nfc(out.read_text(encoding="utf-8"))
        pieces = list(re.finditer(r"(.*?)(\s*<!--id:([^>]*)-->)", text, re.S))
        rebuilt, pos = [], 0
        for b in pieces:
            body, bid = b.group(1), b.group(3)
            if "מקור — תרגום זמני" not in body and "מקור – תרגום זמני" not in body:
                near = [v for c in references(english.get(bid, "")) for v in fetch_chapter(cache, *c)]
                if near:
                    for q in reversed(list(QUOTED.finditer(body))):
                        seg_start = q.start(1) if q.group(1) is not None else q.start(2)
                        seg = q.group(1) if q.group(1) is not None else q.group(2)
                        for a, z, words in reversed(_plain_runs(seg)):
                            hit = _longest_match(words, near)
                            if not hit:
                                continue
                            n, ref, piece = hit
                            piece = nfc(piece)
                            # the matched words only: cut the run after its n-th word
                            run_text = seg[a:z]
                            cut = [m.end() for m in re.finditer(PLAIN_WORD, run_text)][n - 1]
                            before = run_text[:cut]
                            s0 = seg_start + a
                            body = body[:s0] + piece + body[s0 + len(before):]
                            changes.append((bid, ref, before, piece))
                            edits.append({"command": "translator verses vocalise", "unit": unit["id"], "block": bid,
                                          "before": before, "after": piece, "reason": f"verse vocalised from Sefaria, {ref}"})
            rebuilt.append(text[pos:b.start()] + body + b.group(2))
            pos = b.end()
        rebuilt.append(text[pos:])
        new_text = "".join(rebuilt)
        if write and new_text != text:
            out.write_text(new_text, encoding="utf-8")
    if write and edits:
        records.append(project, "edits", edits, by="translator verses vocalise")
    return changes
