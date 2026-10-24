{{MARK}}
# Project: {{TITLE}} ({{AUTHOR}}) → Hebrew, house: {{HOUSE}}

This folder is one book, run by the book translator (engine: ~/translation_app, design in its docs/). Each step is
a slash command; `translator status` shows where every unit stands. Read state.md (below) before any work.

## Rules (binding)
- The text of record for each unit is in state.md. Where it is a Word master, run /import before anything else.
- Never edit source/original/, units/*/output_chunk*.md outside a command, or drafts/koren/.
- Never change the <!--id:...--> comments or the ^n^ markers; copy them exactly in every translation.
- Never change a quotation that has a record in records/quotations.jsonl; use `translator quote amend`.
- Never invent a page, locator, title, year or identification: flag it [לבדיקה: …].
- Translate the author; don't correct the author. Disagreements go to records/author-questions.jsonl, never into the text.
- Decided terms (terms/decided-terms.yaml) override the glossary and every reviewer.
- Every writing command is a dry run first; run it with --write only after I have seen the dry run.
- A step that ends at a gate waits for my decision; never pass a gate yourself (`translator gate` is mine to run).

## Where things are
- source/original/ as received · source/ocr/<part>/ OCR and proofreading · source/cleaned/ one file per unit
- units/<unit>/ chunks, translations, manifest, blocks.jsonl (IDs and printed pages)
- records/ decisions, author questions, quotations, findings, edits, bibliography (JSONL)
- work/ reports and intermediate files (rebuildable) · review/ review pages and decisions

## Commands
/status /doctor /ocr /clean /chunk /gate (see .claude/commands/)

@state.md
