---
name: book-translator
description: Run the book translation process (scholarly books into Hebrew for Koren) in a project folder made by `translator init` - OCR, cleaning, chunking with permanent block IDs, and the later steps with their gates. Use when working inside a book project (a folder with project.yaml) or when asked to start, continue or check a book translation.
---

# Book translator

The engine is this folder (`~/translation_app`); the full design is `docs/book-translator-app.md`. Each book is a
project folder under `~/translation_app/projects/<book>/` with a `project.yaml`, a generated `CLAUDE.md` and
`state.md`, and one slash command per step in `.claude/commands/`.

## How to work in a project

1. Read the project's `CLAUDE.md` and `state.md` first. `translator status` gives the live state.
2. Run each step through its slash command, or through the `translator` command in this engine's `.venv/bin/`.
   Every writing command is a dry run unless given `--write`; show the dry run's report before writing.
3. Each step ends at a gate. The person decides, with `translator gate <unit> <step> --accept`. Never run it for them.
4. A command that refuses (a step it needs hasn't passed) is right; say what is missing, don't use `--force`.

## Steps available now

| Step | Command | What it does |
| --- | --- | --- |
| 0 | `/ocr` (`ocrkit ocr`, `ocrkit proofread`) | Scans → page records, proofread with Claude |
| 1 | `/clean` (`translator clean`) | Proofread pages → one cleaned Markdown file per unit, edits recorded |
| 1 | `/chunk` (`translator chunk`) | Cleaned units → translate-book chunks; permanent IDs `<unit>.pNNNN`, `<unit>.nNNN` |
| — | `/status`, `/doctor`, `/gate` | State, prerequisites, decisions |

Later steps (translation, sources, notes, review, style, Koren build, import) are still the legacy tools in
`legacy/tools/`; run them with `TRANSLATOR_PROJECT=<project folder>` set (see `legacy/README.md`).
