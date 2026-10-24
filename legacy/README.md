# legacy

Rosen's working code, copied from `~/the_translator/` on 24 October 2026, to be ported into the `translator`
package (see `docs/book-translator-app.md`, section 14 and Appendix A). The originals in `~/the_translator/` are
unchanged.

| Folder | Copied from | Left out |
| --- | --- | --- |
| `tools/` | `the_translator/tools/` | `__pycache__/`, `build_review.py.bak` |
| `translate-book/` | `the_translator/translate-book/` (deusyu/translate-book, commit `bd5424b`, 24 Sep 2026) | `.git/` |
| `eval/` | `the_translator/eval/` (code only) | the book's data: `cache/`, `results/`, `aligned/`, `findings/`, `report/`, `decided-terms.md`, `style-sheet.md`, `term-changes.json` |
| `tests/` | `the_translator/tests/` (the eval tests) | — |

## Changes made in the copies

- **Book folder from the environment.** The 29 scripts that set `ROOT = Path(__file__).resolve().parent.parent`
  read it from `TRANSLATOR_PROJECT` instead, and exit with a message when it isn't set. So nothing writes into this
  folder by mistake.
- **Sibling tools from here.** `build_koren.py`, `build_sources_overview.py` and `quote_register.py` find the other
  tools next to themselves, not under `ROOT / "tools"`. `build_prompts.py` and `build_pairs.py` run translate-book
  from `legacy/translate-book/` with the current Python, not `.venv/bin/python` and `translate-book/` relative
  to the working folder.

Nothing else was changed.

`tools/node_docx/node_modules/` (the `docx` package the Word builders use) is not in git. After cloning, restore it
with `cd legacy/tools/node_docx && npm ci`.

## Running a tool

From the book folder, so that tools taking relative paths (for example `quotes_add_parsha.py`) find their files:

```bash
cd ~/the_translator
export TRANSLATOR_PROJECT=~/the_translator
~/translation_app/.venv/bin/python ~/translation_app/legacy/tools/import_corrected.py ch04          # dry run
~/translation_app/.venv/bin/python ~/translation_app/legacy/tools/import_corrected.py ch04 --write  # after review
```

The eval module runs as a package from this folder:

```bash
cd ~/translation_app/legacy
TRANSLATOR_PROJECT=~/the_translator ../.venv/bin/python -m eval.run --chapter mered-kadosh --providers gemini,openai --limit 20
```

## Tests

```bash
cd ~/translation_app/legacy && TRANSLATOR_PROJECT=~/the_translator ../.venv/bin/python -m pytest -q tests   # 22 pass
```
