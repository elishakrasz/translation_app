"""Report (default) or apply the decided-term changes to the translated chapters.

Usage:
    python3 tools/conform_terms.py            # dry run: counts per chapter and term
    python3 tools/conform_terms.py --apply    # replace, with backups in backups/before-conform/

Reads eval/term-changes.json (written by merge_decided_terms.py). Replaces the old
Hebrew rendering with the decided one, including prefixed forms (ב־, ל־, מ־, ה־, ו־,
ש־, כ־), but never inside paragraphs that are verified original sources.
"""
import os
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = (Path(os.environ["TRANSLATOR_PROJECT"]).expanduser().resolve() if os.environ.get("TRANSLATOR_PROJECT")
        else sys.exit("Set TRANSLATOR_PROJECT to the book folder, e.g. TRANSLATOR_PROJECT=~/the_translator"))
CHAPTERS = ["ch01-introduction_temp", "ch02-holy-rebellion_temp", "ch03-biographical-sketch_temp",
            "ch04-torah-and-theology_temp", "ch05-zaddik-and-leadership_temp", "ch06-quest-for-truth_temp"]


# אין is also "there is not"; תורת הצדיק can be the doctrine of the zaddik, not Zaddikism.
MANUAL = {"ayin", "Zaddikism", "frumkeit"}   # frumkeit: quoted in the text, done by hand


def with_prefix(prefix, new):
    """ב/ל/כ absorb the article: ל + הרבי → לרבי."""
    if prefix and prefix[-1] in "בלכ" and new.startswith("ה"):
        return prefix + new[1:]
    return prefix + new


def paras(text):
    return re.split(r"(\n\s*\n)", text)


def source_paragraphs(chapter, name, blocks):
    """Indexes (into blocks) of paragraphs that hold an inserted original source (sources/source-paragraphs.json)."""
    man = json.loads((ROOT / "sources" / "source-paragraphs.json").read_text(encoding="utf-8"))
    chunk = name[12:16]
    nums = {int(k.split("-")[1]) for ch, keys in man.items() if chapter.startswith(ch) for k in keys if k.startswith(chunk + "-")}
    paras = [i for i, b in enumerate(blocks) if b.strip() and not re.fullmatch(r"\n\s*\n", b)]
    return {paras[n - 1] for n in nums if n <= len(paras)}


def main():
    apply = "--apply" in sys.argv
    changes = json.loads((ROOT / "eval" / "term-changes.json").read_text(encoding="utf-8"))
    # Only single-rendering changes can be applied mechanically. MANUAL terms are
    # reported but never replaced: the old form is also an ordinary word or sense.
    rules = [(c["old"], c["new"], c["source"]) for c in changes
             if c["old"] and c["new"] and c["source"] not in MANUAL]
    grand = {}
    for chapter in CHAPTERS:
        d = ROOT / chapter
        for f in sorted(d.glob("output_chunk*.md")):
            blocks = paras(f.read_text(encoding="utf-8"))
            skip = source_paragraphs(chapter, f.name, blocks)
            changed = False
            for i, b in enumerate(blocks):
                if i in skip or not b.strip():
                    continue
                for old, new, src in rules:
                    pat = re.compile(r"(?<![א-ת])([ובלמהכש]{0,3})" + re.escape(old) + r"(?![א-ת])")
                    n = len(pat.findall(b))
                    if n:
                        grand.setdefault(src, {}).setdefault(chapter, 0)
                        grand[src][chapter] += n
                        if apply:
                            b = pat.sub(lambda m: with_prefix(m.group(1), new), b)
                            changed = True
                blocks[i] = b
            if apply and changed:
                bk = ROOT / "backups" / "before-conform" / chapter
                bk.mkdir(parents=True, exist_ok=True)
                if not (bk / f.name).exists():
                    shutil.copy2(f, bk / f.name)
                f.write_text("".join(blocks), encoding="utf-8")
    print("APPLIED" if apply else "DRY RUN — nothing changed", "\n")
    for src, per in sorted(grand.items(), key=lambda kv: -sum(kv[1].values())):
        old, new = next((o, n) for o, n, s in rules if s == src)
        print(f"{src}: {old} → {new}   total {sum(per.values())}   " +
              ", ".join(f"{c[:4]} {n}" for c, n in per.items()))
    manual = [c for c in changes if c["source"] in MANUAL]
    if manual:
        print("\nNot replaced automatically (needs a reader):")
        for c in manual:
            print(f"  {c['source']}: {c['old']} → {c['new']}")


main()
