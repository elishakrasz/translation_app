# Book Translator — design of the process app

*Turning the Rosen translation process into a reusable app: one engine, run in VS Code with Claude Code, with
a project folder per book. Takes an English (or other-language) scholarly book to a Koren/Maggid-ready Hebrew
manuscript with original-source quotations, house-style notes, bibliography and indexes.*

Draft, 24 October 2026; revised the same day after a review (hooks, bookmarks, round-trip test, reruns, review
pages, record IDs, engine location). Built from:

- `book-translation-process.md`, the process as run on Michael Rosen, *The Quest for Authenticity*
- [deusyu/translate-book](https://github.com/deusyu/translate-book), the base skill the project grew from: chunking, glossary, manifest, merge
- `ocrkit` 2.0, the rebuilt OCR and proofreading package (source in `~/translation_app/ocrkit/`)
- from `the_translator/`: `CLAUDE_addendum.md` (style workflow and fixed conventions), `CLAUDE-CODE-eval-passes.md`
  (the outside evaluation, built as `eval/`), `CLAUDE_index.md` (the indexes), and an inventory of `tools/`
  (Appendix A)

---

## Contents

1. [What the app is](#1-what-the-app-is)
2. [Principles, and what enforces each](#2-principles-and-what-enforces-each)
3. [Architecture](#3-architecture)
4. [Setup: VS Code and Claude Code](#4-setup-vs-code-and-claude-code)
5. [The project folder](#5-the-project-folder)
6. [Core mechanisms](#6-core-mechanisms)
7. [Commands at a glance](#7-commands-at-a-glance)
8. [The steps](#8-the-steps)
9. [`translator check`](#9-translator-check)
10. [Reviewers](#10-reviewers)
11. [Running agents](#11-running-agents)
12. [Shared resources](#12-shared-resources)
13. [Testing](#13-testing)
14. [What the app takes from `the_translator/`](#14-what-the-app-takes-from-the_translator)
15. [Build plan](#15-build-plan)
16. [Open questions](#16-open-questions)
17. [Appendices](#appendices)

---

## 1. What the app is

A **Claude Code skill plus a Python engine**, installed once on the Mac. Each book is a **project folder** made by
`translator init`. You open the project folder in VS Code; Claude Code reads the project's `CLAUDE.md` and runs each
step through a slash command (`/sources ch05`, `/check`, `/import`). The engine's scripts do the mechanical work,
Claude Code agents do the reading and writing work, translation included, and you decide at every gate.

The target language is Hebrew throughout: the markers, house profiles and checks assume it. The source language
can be English or another language.

What changes from the Rosen project:

| Rosen project | The app |
| --- | --- |
| One folder, `the_translator/`, holding tools and one book together | Engine installed once; one folder per book |
| Order of work kept by memory and the process document | Order enforced: each step checks that the steps it needs have passed |
| "One text of record" as a rule to remember | Recorded in the project state and enforced by a hook |
| Paragraphs and notes matched by alignment at every import | Every paragraph and note has a permanent ID from chunking onwards |
| Logs in Markdown, parsed afterwards | Records in JSONL, written when the work happens; Markdown reports generated from them |
| Dated backups in `backups/` | Git: a commit at every gate |
| Questions for the author merged at the end | One register from the first day |
| OCR as separate scripts | `ocrkit` as Step 0, shared with the reference library |

Not in scope: typesetting (Koren does it), a web interface (VS Code is the interface), other publishers' house
styles beyond making room for them (section 3).

---

## 2. Principles, and what enforces each

| # | Principle | Enforced by |
| --- | --- | --- |
| 1 | One text of record at a time | `state.yaml` names it; every tool reads only the record and refuses when a Word master's hash differs from its build; the pre-edit hook blocks Claude's edits to the chapter files while a Word master is the record; `check` catches everything else |
| 2 | Back up and dry-run before every write | Every writing command defaults to dry run and writes a report; `--write` applies; the engine commits before and after |
| 3 | A human decides at every gate | Steps end in state `awaiting-gate`; the next step refuses to start; `translator gate` records the decision and commits |
| 4 | Translate the author, don't correct the author | Briefs; disagreements go to the author-questions register, never into silent changes |
| 5 | Quote originals exactly | Quotations are records with a verified text and a hash; `check` fails if the text in a chapter differs |
| 6 | Decided terms beat everything | `decided-terms.yaml` is injected into every brief and checked by `check` |
| 7 | Never invent | Briefs; unknowns are `[לבדיקה: …]` flags, which `check` counts and the reports list |
| 8 | Keep the structure aligned | Stable IDs; the structure check runs after every engine write, after every edit by Claude (post-edit hook), and at every gate |
| 9 | Two reviewers, findings only | Reviewer briefs produce findings as JSON; applying a finding is a separate, human-approved command |

---

## 3. Architecture

```
~/translation_app/                       ENGINE — installed once, under git (this design lives in docs/)
├── SKILL.md                             how Claude Code runs the steps (linked into ~/.claude/skills/)
├── .venv/                               the virtual environment shared with ocrkit
├── translator/                          Python package: the CLI and all tools
├── briefs/                              brief templates for the agents (Jinja)
├── commands/                            the slash commands, copied into each project by `init` / `upgrade`
├── templates/                           project skeleton, CLAUDE.md, review pages, Koren docx builder
├── houses/koren/                        HOUSE PROFILE — one per publisher
│   ├── footnote-style.md
│   ├── house.yaml                       divine names, title marking, spelling policy, markers
│   └── index-spec.md
├── tests/                               fixture book + golden outputs
├── ocrkit/                              the OCR package (its own pyproject.toml and tests)
└── legacy/                              Rosen's tools/, translate-book/ and eval/, copied in to be ported (see legacy/README.md)

~/Library/TextLibrary/                   REFERENCE LIBRARY — shared by all books, outside git
├── scans/<book-id>/                     ocrkit folders: ocr.jsonl, proof.jsonl, pages/
├── sefaria/                             local Sefaria export
├── catalog.yaml                         every book: title, edition, year, scan folder, numbering notes
└── quotations.jsonl                     VERIFIED QUOTATIONS — grows with every book

~/translation_app/projects/<book>/      PROJECT — one per book; kept out of the app's repository
```

`ocrkit` is its own package inside the engine folder, `~/translation_app/ocrkit/`, used by Step 0 and by the
library ingest. It runs as `ocrkit …` or
`python -m ocrkit …` (`final_ocr.py` and `proofreader.py` remain as wrappers). Done on 24 October 2026, to fit it to
the app:

- a `pyproject.toml` with an `ocrkit` console script; installed with `pip install -e ~/translation_app/ocrkit` into the engine's venv
- `ocrkit/__main__.py` reads `~/.config/translator/.env` after any `.env` found from the working folder, so one key file serves every project and the library
- the model's slips in the page format are normalised before the checks: an unclosed reference `^4` becomes `^4^`, and a notes separator written `---notes---` becomes `--- notes ---` (both found on the first book)
- `ocrkit recheck DIR` reruns the checks on the saved proofread text without calling the API, for pages proofread before a check was added
- two test fixes: `test_proofread.py` imports `httpx2` (the `anthropic` 2.x library is built on it, not on `httpx`), and `test_ocr_e2e.py` finds a macOS font with Hebrew (it looked only for a Linux font, so the OCR tests always skipped on the Mac)

All 30 tests pass on the Mac, including the two that run real Tesseract on generated Hebrew and English scans.

The engine lives in `~/translation_app/`, next to the other projects in the home folder (`the_translator/`,
`the_melamed/`), and not inside `~/.claude/`, because it holds a package, a virtual environment and tests. Only
`SKILL.md` needs to be where Claude Code finds skills, so `~/.claude/skills/book-translator` is a symlink to the
engine folder. `~/.claude/skills/synced/` is managed by Claude and is left alone.

All the app's code lives in `~/translation_app/`: the engine, `ocrkit`, and (until they are ported into the
`translator` package) Rosen's tools in `legacy/`. Book files don't: each book is its own project under
`~/translation_app/projects/` (ignored by the app's git), and Rosen's book stays in `the_translator/` (section 14).

**The legacy tools run from here against a book folder.** In the copies, every tool that used to find its files
from its own location (`ROOT = Path(__file__).resolve().parent.parent`, 29 scripts) reads the book folder from
`TRANSLATOR_PROJECT` instead, and exits with a message if it isn't set. Tools that call each other, or call
translate-book, use the copies in `legacy/`. For example:

```bash
cd ~/the_translator
TRANSLATOR_PROJECT=~/the_translator ~/translation_app/.venv/bin/python ~/translation_app/legacy/tools/import_corrected.py ch04
```

The originals in `the_translator/tools/` are left as they were.

Why four layers: the engine changes when the method improves, the house profile when the publisher changes,
the library grows with every book, and the project holds one book. Rosen-specific logic in today's tools moves
into the project's `project.yaml`: the נספח labels for ch13–ch18 (in `build_koren.py`'s `LABELS`, the label regex
of `import_corrected.py`, and `names_of_god.py`), the chapter lists hard-coded in a dozen scripts (several stop at
ch06 or ch12), the HebrewBooks titles in `find_source.py`, and the decided terms written into
`merge_decided_terms.py`. The asterisk note is already handled generically (`^*^`), and no script treats the
note-80 gap specially: both stay as `source_quirks`, for the checks.

---

## 4. Setup: VS Code and Claude Code

### Prerequisites (Mac)

- Python 3.12+, in a virtual environment shared by the engine and `ocrkit`
- Tesseract 5 with `eng`, `heb`, `osd`; Poppler; LibreOffice; Node (for the docx builder); Pandoc; Calibre (only for publisher EPUB/DOCX intake)
- Word, for the translator's edit round
- VS Code with the Claude Code extension
- Keys in `~/.config/translator/.env`: `ANTHROPIC_API_KEY`, read only by `ocrkit` (for OCR proofreading); `GEMINI_API_KEY`, `OPENAI_API_KEY` and, optionally, `HF_TOKEN`, read only by the outside evaluation (Step 8). Translation and every other agent step run in Claude Code on your Claude Code login. Never export `ANTHROPIC_API_KEY` in the shell profile: if Claude Code sees `ANTHROPIC_API_KEY` in its environment it bills the API key instead of your Claude Code login.

### Install

```bash
git clone <engine repo> ~/translation_app   # the repository holds docs/, ocrkit/ and legacy/
cd ~/translation_app
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ./ocrkit pytest         # done: puts `ocrkit` in .venv/bin
pip install -e .                       # once the engine package exists (milestone 1)
ln -s ~/translation_app ~/.claude/skills/book-translator
translator doctor                      # checks every prerequisite and prints what is missing
```

The hooks and the VS Code tasks call the engine by its absolute path (`~/translation_app/.venv/bin/translator`),
so they work whether or not the virtual environment is active in the shell that started VS Code.

### Start a book

```bash
translator init ~/translation_app/projects/stop-look-listen --house koren --title "Stop, Look, Listen"
code ~/translation_app/projects/stop-look-listen
```

In VS Code, the Claude Code panel opens in the project folder and reads its `CLAUDE.md`. Type `/status` to see
where every unit stands.

### What `init` sets up for VS Code

- `.claude/commands/*.md`: one slash command per step (section 7), copied from the engine's `commands/`. Each command is a short prompt telling Claude Code which `translator` command to run, which brief to give the agents, and what to report back. The copies carry the engine version they came from; `translator upgrade` refreshes them (and the hooks) after the engine changes, and `doctor` and `/status` warn when a project's copies are older than the engine.
- `.claude/settings.json`: the hooks (section 6.3).
- `.vscode/settings.json`: a Hebrew-capable editor font, `"editor.unicodeHighlight.ambiguousCharacters": false` (Hebrew triggers it), word wrap on for `*.md`, and the review pages opening in VS Code's built-in browser.
- `.vscode/tasks.json`: `translator check` and `translator status` as tasks, so they also run without Claude.

---

## 5. The project folder

The examples in this section and the next use the Rosen book, where the problems they solve came up. The first
real project is `projects/stop-look-listen/`.

### Layout

```
rosen-quest/
├── CLAUDE.md                     generated at init: rules and where things are; imports state.md
├── state.md                      generated: the current state table (regenerated whenever state.yaml changes)
├── project.yaml                  the book's settings (below)
├── state.yaml                    machine-written: step state per unit, gates, text of record, build hashes
├── .claude/  .vscode/  .gitignore
├── source/
│   ├── original/                 publisher files and scans as received; never edited
│   ├── ocr/                      ocrkit folder for the book (ocr.jsonl, proof.jsonl, proof-report.md)
│   └── cleaned/                  cleaned source per unit + back matter (Step 1)
├── units/
│   └── ch05-zaddik/              ONE FOLDER PER UNIT
│       ├── chunk0001.md          source, paragraphs carry IDs
│       ├── output_chunk0001.md   Hebrew, same IDs, same order
│       ├── manifest.json         chunk hashes (from translate-book)
│       └── notes/                translator's notes for the unit
├── style/
│   ├── corpus/                   model passages for the style analysis
│   ├── profiles/                 one profile per model author
│   ├── style-sheet.md            the result (Step 2)
│   └── style-checklist.yaml      testable rules derived from it
├── terms/
│   ├── glossary.json             English → Hebrew (translate-book v2 schema)
│   └── decided-terms.yaml        the translator's fixed renderings
├── records/                      JSONL — the project's memory (section 6.4)
│   ├── decisions.jsonl
│   ├── author-questions.jsonl
│   ├── quotations.jsonl
│   ├── findings.jsonl
│   ├── edits.jsonl
│   └── bibliography.jsonl
├── review/<step>/<unit>/         review pages and decision files
├── work/                         intermediate files by step (can be deleted and rebuilt)
├── drafts/
│   ├── koren/                    built from the chapter files; never edited
│   └── word/                     the translator's Word masters (*-edited.docx) and corrected copies
├── index/                        authority files, tags, rendered indexes
└── out/                          the publisher package
```

### `project.yaml`

```yaml
book:
  title: The Quest for Authenticity
  author: Michael Rosen
  edition: Urim, 2008
  source_language: en
  target_language: he
house: koren                       # engine/houses/koren/
units:                             # order = book order
  - {id: ch00, slug: front,  label: null,      kind: front}
  - {id: ch01, slug: holy-rebellion, label: "פרק א'"}
  # …
  - {id: ch13, slug: addendum-a, label: "נספח א'", kind: addendum}
source_quirks:                     # recorded, never "fixed"
  - {unit: ch05, note: "no note 80 in the original"}
  - {unit: ch06, note: "asterisk note before note 1", asterisk_note: true}
audience: educated lay reader
style_sheet: style/style-sheet.md
reviewers: [fable, opus]           # two models, findings only
translator_model: opus             # the model the translation sub-agents run on
agents:
  parallel: 4                      # units at a time (an instruction to Claude Code, see section 11)
policies:                          # house defaults, overridable per book
  spelling: ktiv-male
  spelling_forms: {אמיתיות: אמתיות, לעיתים: לעתים}
  divine_names: koren-default
  keep_yiddish: true
  glosses_in_quotes: true
```

### The generated `CLAUDE.md` and `state.md`

`CLAUDE.md` holds the rules, which rarely change; it pulls in `state.md`, which is regenerated whenever the
state changes. Keeping them apart means the rules file doesn't change in git at every gate.

Claude Code reads `CLAUDE.md` (and its imports) when a session starts, not during it. A new session therefore
starts with the current picture; within a long session, `/status` gives the live state, and every command checks
`state.yaml` itself rather than relying on what Claude remembers.

```markdown
# Project: The Quest for Authenticity (Rosen) → Hebrew, house: Koren

## Rules (binding)
- The text of record for each unit is in state.md. Where it is a Word master, run /import before anything else.
- Never edit units/*/output_chunk*.md by hand outside a command; never edit drafts/koren/.
- Never change a quotation that has a record in records/quotations.jsonl; use `translator quote amend`.
- Never invent a page, locator, title, year or identification: flag it [לבדיקה: …].
- Disagreements with the author go to records/author-questions.jsonl, never into the text.
- Decided terms (terms/decided-terms.yaml) override the glossary and every reviewer.
- Never run git commit yourself; the engine commits.

## Commands
/status /check /translate <unit> /sources <unit> … (see .claude/commands/)

@state.md
```

`state.md`:

```markdown
## State (generated 2026-08-20 14:02)
Text of record: chapter files, except ch04 and ch07 (Word masters changed since their build — run /import first).

| Unit | Last step passed | Waiting for |
| ch01 | review | your decisions on review/review/ch01/ |
| ch02 | sources | — |
```

### `.gitignore`

`work/` (except `work/translate/`, the record of each translation run, and `work/*/scripts/`), `review/**/*.html`
(rebuilt), `~$*` (Word lock files), `.DS_Store`. Word masters **are** committed: they are the text of record during
the edit round.

`.gitignore` can't filter by size, so large files are kept out by a pre-commit hook that `init` installs: it refuses
any staged file over 50 MB and names it. Large scans belong in the reference library; `source/original/` keeps a
note of where each one is (`source/original/LARGE-FILES.md`).

---

## 6. Core mechanisms

### 6.1 Stable IDs

Every paragraph, block quote, heading and note gets a permanent ID when the source is chunked (Step 1). The ID
travels through translation, Word and import, so nothing is ever matched by guessing.

**Form.** `ch05.p0123` for body blocks, `ch05.n045` for notes (`ch06.n000` for an asterisk note). Numbers are
assigned once and never reused. A paragraph split later becomes `ch05.p0123a`, `ch05.p0123b`.

**In Markdown** (chunk and output files), as an HTML comment at the end of the block, which Markdown previews and
Pandoc ignore:

```markdown
The Kotzker said that truth cannot be imitated.^12^ <!--id:ch05.p0123-->

12\. See Emet ve-Emunah, 41. <!--id:ch05.n012-->
```

The translation brief says to copy the comment unchanged, as it does for `^n^` markers. The structure check
compares the ID sequence of source and output: same IDs, same order.

**In Word**, as bookmarks (`p_ch05_0123`, `n_ch05_012`, `p_ch05_0123a`). Word bookmark names must start with a
letter, allow only letters, digits and `_`, and are at most 40 characters; names starting with `_` are hidden, so
none do. The Koren build wraps each paragraph and each footnote's text in its bookmark.

**On import**, each Word paragraph is mapped by the bookmarks it contains. Word keeps a bookmark when the text
inside it is edited, but not in every case, and the import has to handle what Word actually does:

| What the translator did | What Word does to the bookmarks | What the import sees |
| --- | --- | --- |
| Edited text inside the paragraph | Bookmark kept | One paragraph, one bookmark: mapped |
| Deleted the whole paragraph | Bookmark deleted | A missing ID: reported as deleted |
| Merged two paragraphs (deleted the paragraph mark) | Both bookmarks kept | One paragraph, two bookmarks: reported as merged |
| Split a paragraph (Enter inside it) | One bookmark now spans both paragraphs | One bookmark across two paragraphs: reported as split |
| Selected the whole paragraph and retyped it, or typed at its very start or end | Bookmark deleted, or new text left outside it | A paragraph with no bookmark, or text between bookmarks: reported, matched by sequence alignment |
| Inserted a new paragraph | No bookmark | A paragraph with no bookmark: reported as new |

Sequence alignment is kept only as a fallback for the reported cases, and each case is shown to you before
anything is written. Because these behaviours come from Word, not from the engine, they are tested in real Word
before the import is built (milestone 4a, section 15), and the fixture's Word edit (section 13) contains each case.
This removes the pitfalls about alignment drift, footnote mapping by position, and spot-checking the last third of
each chapter.

**Everything else attaches to IDs:** quotation records, findings, author questions, edits, index tags. An index tag
on `ch05.p0123` survives every later edit of that paragraph's wording. That means indexing can start before
the final text (section 8, Step 14).

### 6.2 Steps, state and gates

`state.yaml` holds, per unit, the state of each step and the decisions taken at its gate:

```yaml
text_of_record: {ch04: word, default: chapters}
units:
  ch05:
    clean:      {state: passed, gate: 2026-07-02, commit: 1a2b3c}
    translate:  {state: passed, gate: 2026-07-20, commit: 4d5e6f}
    sources:    {state: awaiting-gate, report: review/sources/ch05/}
    notes:      {state: blocked, needs: [sources]}
```

States: `blocked` (a needed step hasn't passed) → `ready` → `running` → `awaiting-gate` → `passed`. A step can
also be `stale`: a step it depends on has been redone since it passed. Stale steps show in `/status`, and
`check` warns about them.

**Redoing an earlier step.** Once later steps have changed a unit, an earlier step must not overwrite their work.
Re-running a step whose later steps have passed is therefore allowed only on named IDs
(`translator translate ch05 --ids ch05.p0123,ch05.p0124`), never on a whole unit. For those IDs:

- the old text is kept in git and the new text is shown as a diff before `--write`
- locked quotations inside the blocks are put back from their records automatically, with their glosses
- edits recorded in `edits.jsonl` for those blocks are listed, so you can reapply the ones still wanted (`translator edits reapply <eid>…`)
- every later step becomes `stale` for those IDs only, and its next run covers just them

Re-running a whole unit after later steps have passed needs `--force` and a note, and is recorded in
`decisions.jsonl`.

Each command checks the state before it runs and refuses with a plain message, for example: "ch05: the style pass
needs the sources round to pass first (it is waiting for your decisions in review/sources/ch05/)." The order of
steps is in section 8; each step lists what it needs. `--force` exists for emergencies and is recorded in
`decisions.jsonl`.

`translator gate ch05 sources --accept [--note "…"]` passes a gate. It reads the decision file the review page
saved, records the decisions, commits with a message such as `ch05 sources: gate passed — 41 originals inserted,
6 differences to the author`, and updates `CLAUDE.md`.

### 6.3 Text of record and the hooks

`state.yaml` names the text of record per unit: `chapters` (the `output_chunk*.md` files) or `word` (the
translator's Word master). It is the single source of truth; nothing is inferred from file dates, which copying
and OneDrive sync change.

- `translator word prepare` (Step 11) sets the unit to `word`; `translator import --write` sets it back to `chapters`. Nothing else changes it.
- The Koren build and `word prepare` record each file's SHA-256 in `state.yaml`. If a unit is `chapters` but its Word master's hash differs from the recorded one (an edit nobody announced), every command that reads the unit refuses and `/status` says so. You then either import the Word file or record that its changes are to be discarded (`translator word discard ch05`).
- While a unit is `word`, every command that reads its text refuses until `/import` has run.

Two Claude Code hooks in `.claude/settings.json` enforce this inside VS Code. They call the engine by its absolute
path, so they don't depend on the virtual environment being active:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Edit|Write|MultiEdit|NotebookEdit|Bash",
        "hooks": [{"type": "command", "command": "~/translation_app/.venv/bin/translator hook pre-edit"}]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Edit|Write|MultiEdit|NotebookEdit|Bash",
        "hooks": [{"type": "command", "command": "~/translation_app/.venv/bin/translator hook post-edit"}]
      }
    ]
  }
}
```

- `translator hook pre-edit` reads the hook input (JSON on stdin). It blocks, by exiting with code 2 and a reason on stderr, in these cases:
    - an edit to an `output_chunk` file of a unit whose text of record is Word
    - any edit under `drafts/koren/` or `source/original/`
    - an edit that would change the text of a recorded quotation. For `Edit`, the hook applies `old_string` → `new_string` to the file in memory; for `Write`, it takes the new content. It then compares each recorded quotation's text at its ID, as `check` does.
    - a `Bash` command that writes to any of those paths by shell means (`sed -i`, `>`, `>>`, `tee`, `mv`, `cp`, `rm`, a `python` or `perl` one-liner naming the path), or runs `git commit`, `git checkout`, `git reset` or `git stash` (the engine owns git, section 6.5). Commands that start with the engine's own path are allowed: the engine does its own checks.
- `translator hook post-edit` runs the structure check and the quotation check on the units the tool touched. On a failure it exits with code 2 and writes the failure to stderr, which is how a PostToolUse hook's output reaches Claude; on success it exits 0 silently.

**The hooks fail open, so the gates don't rely on them.** Claude Code treats only exit code 2 as a block. Any other
failure (the engine not found, a crash) is a non-blocking error, and the edit goes ahead. Three things guard
against that:

- `translator doctor` and `/status` run a test call of each hook (a fake blocked edit) and report if it didn't block
- the hook wraps its own body, so an internal error exits 2 with "hook error: …" instead of crashing
- `translator check` runs every check again at each gate, and a gate can't pass with errors

Bash commands can write files in more ways than any pattern catches (a script that writes files, for example), and
hooks only cover Claude's own actions, not an edit you make by hand in VS Code or Word. The hooks are the first line
of defence, there to stop mistakes as they happen; `translator check` at the gate is the guarantee.

### 6.4 Records

Records are JSONL files, one object per line, appended as the work happens and committed at each gate. Reports,
spreadsheets and the author list are generated from them, so nothing has to be parsed back out of Markdown.

**Record IDs are assigned by the engine, never by an agent.** Agents running in parallel write their lines to
`records/.pending/<agent>.jsonl` (section 11) with a temporary ID made of the agent's name and a counter
(`ch05-sources.3`). When the engine merges the pending files, it assigns the permanent IDs (`q0412`, `aq0031`) in
sequence and rewrites every reference between records (an author question's `evidence`, a quotation's
`author_question`) in the same pass. Two agents can then never produce the same ID.

| File | One line per | Written by |
| --- | --- | --- |
| `decisions.jsonl` | decision at a gate or on a question | `gate`, review pages |
| `author-questions.jsonl` | question for the author | every step |
| `quotations.jsonl` | quotation from a Hebrew/Aramaic/Yiddish source | sources round |
| `findings.jsonl` | reviewer finding (review, style, fidelity, footnote pass) | reviewer agents |
| `edits.jsonl` | change applied to the text | every writing command |
| `bibliography.jsonl` | work cited, with short form and full entry | notes step |

Schemas are in Appendix B. Two of them matter most:

**Quotation** — the lock on the original texts:

```json
{"qid": "q0412", "unit": "ch05", "block": "ch05.p0123", "work": "emet-ve-emunah",
 "locator": "סי' תמ\"ב", "edition": "ירושלים תשנ\"ה", "library": "scans/emet-ve-emunah/page 112",
 "status": "verified-scan", "text": "…", "sha256": "…",
 "author_differs": true, "difference": "Rosen reads 'truth' where the text has 'faith'",
 "author_question": "aq0031", "inserted": "2026-08-04", "glosses": []}
```

**Author question:**

```json
{"aqid": "aq0031", "unit": "ch05", "block": "ch05.p0123", "kind": "wrong-speaker",
 "text": "The saying is attributed to R. Bunim; Emet ve-Emunah §442 gives it in the name of the Kotzker.",
 "evidence": ["q0412"], "raised_by": "sources", "raised": "2026-08-04", "status": "open"}
```

Kinds: `wrong-speaker`, `wrong-reference`, `reading-the-argument-depends-on`, `garbled-english`,
`edition-difference`, `other`.

### 6.5 Git

Each project is a git repository. `init` makes the first commit; `gate` commits; every writing command commits
before it writes, with the message `pre: <command>`. That replaces `backups/`: any write can be undone with
`git checkout`, and `git diff` shows exactly what a command changed. Tags mark milestones (`translated`,
`sent-to-author`, `to-publisher`).

**Only the engine commits, one commit at a time.** Agents working in parallel would otherwise collide on git's
index lock. Every engine command that commits first takes a project lock (`.git/translator.lock`, waiting up to a
minute), then commits, then releases it. Agents never run `git commit`; the pre-edit hook blocks it. If the
working tree has changes the command didn't make (a hand edit, say), the `pre:` commit names them in its message,
so the command's own commit shows only its own changes.

The engine is its own repository. `ocrkit` is its own repository. The reference library is outside git (large,
binary): back it up with Time Machine and an external copy.

---

## 7. Commands at a glance

All commands take a unit (`ch05`), a list (`ch01-ch04,ch13`) or `all`. Writing commands dry-run unless given `--write`.

| Slash command | Engine command | Step |
| --- | --- | --- |
| `/status` | `translator status` | — |
| `/check` | `translator check [unit]` | all |
| `/ocr` | `ocrkit ocr` + `ocrkit proofread` | 0 |
| `/clean <unit>` | `translator clean` | 1 |
| `/chunk` | `translator chunk` | 1 |
| `/style-analysis` | `translator style …` | 2 |
| `/glossary` | `translator glossary …` | 2 |
| `/terms` | `translator terms conform` | 2, 9 |
| `/pilot <unit>` | runs Steps 4–12 on one unit | 3 |
| `/translate <unit>` | `translator translate` | 4 |
| `/sources <unit>` | `translator sources locate / integrate` | 5 |
| `/notes <unit>` | `translator notes convert / write` | 6 |
| `/review <unit>` | `translator review pairs / build / apply` | 8 |
| — | `translator serve` | review pages (section 10) |
| — | `translator quote amend <qid>` | 7, 12 |
| `/style <unit>` | `translator style-pass …` | 9 |
| `/build <unit>` | `translator build koren` | 10 |
| `/import <unit>` | `translator import` | 11 |
| `/fidelity <unit>` | `translator fidelity …` | 12 |
| `/restore <unit>` | `translator restore …` | 12 |
| `/footnotes` | `translator footnotes …` | 12 |
| `/glosses <unit>` | `translator glosses` | 13 |
| `/index …` | `translator index …` | 14 |
| `/author-list` | `translator author-questions render` | 15 |
| `/package` | `translator package` | 15 |
| — | `translator gate <unit> <step> --accept` | gates |
| — | `translator upgrade` | refresh `.claude/` from the engine |

---

## 8. The steps

Each step lists what it needs, what it does, what it produces, the checks, and the gate. The step order is the
recommended order from the process document, plus a pilot step. Old stage numbers are in brackets.

### Step 0 — Intake and OCR [Stage 0, first half]

**Needs:** nothing. **Command:** `/ocr`.

1. Put everything received in `source/original/`: publisher docx/PDF/EPUB, scans, the author's corrections, the author's Hebrew source list.
2. **Scans:** `ocrkit ocr source/original/book.pdf source/ocr --split-2up` (add `--lang heb+eng` for a Hebrew book; `--rtl auto` sets the page order of two-page spreads), then `ocrkit proofread source/ocr --batch`. Review `source/ocr/proof-report.md`: pages kept as OCR, doubtful readings `{?…}`, footnote numbering jumps, references without notes, missing numbers, high change rates. Redo pages with `--repair` (missing or kept-as-OCR pages) or `--pages 7,12-14`.
3. **Fixes by hand** go into Step 1, not into `proof.txt`: `proof.txt` is rendered from `proof.jsonl` and is rewritten by every `ocrkit proofread` or `ocrkit render`. Each hand fix is made in the cleaned file and recorded in `edits.jsonl` with the page number, so it stays traceable to the scan.
4. **A book OCR'd with the old scripts** (`mickey8c_ocr_proofread.txt`, for example) is brought in with `ocrkit import-txt OLD.txt source/ocr --images OLD_pages/` and proofread again with the new checks.
5. **Publisher EPUB/DOCX:** convert with translate-book's `convert.py` (Calibre → HTMLZ → Markdown), keeping footnotes.

**Produces:** `source/ocr/proof.txt` (or converted Markdown), with `PAGE n (p. N)` headers carrying the printed page
numbers, and `^n^` footnote references in the chapter-file form.
**Gate:** the proofreading report is reviewed; open doubtful readings are either resolved or carried as `[לבדיקה]` into Step 1.

### Step 1 — Clean, split, chunk, assign IDs [Stage 0, second half]

**Needs:** Step 0. **Commands:** `/clean`, `/chunk`.

1. `translator clean` turns the proofread pages into one file per unit in `source/cleaned/`:
    - join pages, keeping a `<!--page:57-->` marker at each page break (for the index and for the questions to the author)
    - separate body and notes, and convert `^n^` / `--- notes ---` into chapter-file form
    - mark block quotes, headings and lists
    - split off the back matter: bibliography, indexes, Hebrew sources list, addenda
    Each change, and each question about the source, goes into `edits.jsonl` and `author-questions.jsonl` (`kind: garbled-english` and so on).
2. Units come from `project.yaml`. Source quirks (a missing note number, asterisk notes) are recorded there, not fixed.
3. `translator chunk` splits each unit into chunks (whole paragraphs, 5–8 K characters, as translate-book does) and assigns the stable IDs. It writes `manifest.json`.

**Checks:** note numbering matches `source_quirks`; every note has a reference; no empty blocks.
**Gate:** you confirm the source and the unit list.

### Step 2 — Foundations [Stage 1]

**Needs:** Step 1 (the source must exist to extract terms). Every decision made here saves a book-wide sweep later.

**2a. Style analysis → style sheet → prompt.** Goal: a written description of the Hebrew voice, which becomes part
of every translation prompt and a checklist the reviewers score against. This is stages 1–3 of the style workflow
in `CLAUDE_addendum.md`; each stage's output must be on disk before the next starts.

1. **Corpus.** Choose model authors in the target register. On Rosen the brief began as a three-voice blend (Steinsaltz for the base register, Rav Shagar for philosophical and existential passages, Sacks for rhetorical high points) and was then narrowed to a single Steinsaltz register, tested on chapter 2. Choose passages of the same kind as the book: exposition of a Hasidic text, argument, biography. Layout, one folder per author:
    ```
    style/corpus/<author-slug>/
      README.md       who the author is, which works the samples come from, why chosen
      sample-01.md
      sample-02.md
    ```
    A sample not under an author folder is not used until you say whose it is. Samples are for analysis only: their sentences are never copied into the translation.
2. **Profiles** (stage 1). One agent per author writes `style/profiles/<author-slug>.md`, one page or less, from close reading of 2–3 paragraphs per sample. It covers:
    - **lexicon and register:** biblical and rabbinic vocabulary against modern academic Hebrew; foreign and technical terms; recurring words
    - **syntax and rhythm:** typical sentence length; nominal or verbal style (heavy סמיכות or lighter); clause chaining; how often the passive appears
    - **discourse:** how paragraphs open and close; preferred connectives (אמנם, ברם, מכאן ש־); how arguments are signposted and hedged
    - **source handling:** how quotations from seforim are introduced, framed and commented on; what goes in the body and what in the notes
    - **three sentences worth imitating**, quoted exactly from the samples

    Light counts (average sentence length, connectives and passives per page) confirm the impressions; they don't replace the reading.
3. **Comparison** (stage 2). `style/comparison.md`: one table, features as rows, authors as columns. Each feature is then sorted:
    - **shared** by most authors: a convention of the genre, which goes into the style sheet by default
    - **distinctive** to one author: a choice, adopted only if it suits the book's author
    - **contradictory** across authors: must be decided, never mixed. The tiebreaker is which model author is closest to the book's author in temperament (how they argue, how much they hedge, how they move between close reading and broad claims). That author is the primary anchor; the others supplement.
4. **Style sheet** (stage 3). You decide; the agent writes `style/style-sheet.md`, one working document of 1–2 pages:
    - rules from the shared conventions
    - the few signature features chosen deliberately, each with the author it comes from
    - a bank of preferred transitions and framing phrases
    - a do / don't list, with one short example each
    - model sentences to imitate
    - the book's fixed conventions: fidelity to the author's structure (free reworking is the exception), no explanatory glosses, metaphors kept, Yiddish kept, audience

    The style sheet is the authority for all revision. A decision made later, during translation or review, is added to it in the same session.
5. **Checklist.** `translator style checklist` derives `style/style-checklist.yaml`: testable rules ("average sentence under 28 words", "no אשר where ש fits", "metaphors kept, not explained", "no gloss the English doesn't have"). Reviewers score against it in Steps 8 and 9, and the outside evaluation (Step 8) receives it as the list of choices it must not "correct".
6. **Prompt.** The translation brief template includes the style sheet. This fills the slot that translate-book leaves open as `custom_instructions` (on Rosen, `tools/custom_instructions.txt` and `custom_instructions_part2.txt`).

The pilot (Step 3) is the test: if the pilot chapter doesn't sound like the style sheet, the style sheet is revised,
not the chapter. When the style sheet changes, the outside evaluation's copy is regenerated from it: on Rosen,
`eval/style-sheet.md` was a separate, hand-kept copy.

**2b. Glossary.** Two agents extract terms; a merge; a review page; the result is `terms/glossary.json`. The
translate-book v2 schema is used: term, aliases, target, category, plus the per-chunk term table and the
merge of new terms that agents discover.

**2c. Decided terms.** `terms/decided-terms.yaml`: key concepts, the customary forms of personal names, and titles
of works. They are merged into the glossary with priority over it.

**2d. House policies,** from the house profile, confirmed or overridden for this book in `project.yaml`:

- divine names (Koren default: א־לוהים with a maqaf, א־לוהות, ה', הקב"ה; never אלוהים or האל in the translator's prose; quotations keep their own spelling)
- footnote style (`houses/koren/footnote-style.md`)
- title marking: Hebrew titles unmarked, articles in quotation marks, foreign titles italic
- spelling policy: ktiv male plus a list of fixed forms. Rosen left this open and the text ended up mixed, so `init` asks for it.
- editorial markers (Appendix D)

**2e. Index plan.** Which of the house's indexes the book needs (from `index-spec.md`), and when tagging starts:
after Step 9, which stable IDs make possible, or only on the final text, as in the Rosen project (open question 7).
The choice is recorded in `project.yaml` as `index.tagging_from: style | final`.

**Gate:** you approve the style sheet, decided terms, footnote style, spelling policy and index plan. They are
written into `decisions.jsonl`.

### Step 3 — Pilot chapter (new)

**Needs:** Step 2. **Command:** `/pilot ch02`.

Run one chapter, ideally one rich in quotations and notes, through Steps 4–12 before translating the rest:
translate, sources, notes, quotation lock, review, style pass, Koren build, a Word edit round, import, fidelity
check. Everything the Rosen project discovered late (spelling, title marking, divine names, footnote edge cases,
import surprises) shows up here, at the cost of one chapter.

**Gate:** you list what changes in the foundations. They are revised, and the pilot chapter is brought into line.
Only then do the other units start.

### Step 4 — Translate [Stage 2]

**Needs:** Step 2 (and Step 3 for every unit but the pilot). **Command:** `/translate ch05`.

1. `translator translate prompts ch05` builds one prompt per chunk from the brief, containing:
    - the style sheet
    - the decided terms
    - the per-chunk term table (translate-book's `glossary.py print-terms-for-chunk`)
    - read-only excerpts from the neighbouring chunks, to resolve pronouns and names (translate-book's `chunk_context.py`)
    - the rules: keep `^n^` markers and `<!--id:-->` comments exactly; one Hebrew block per source block; flag doubts with `[לבדיקה: …]`; quotations from Hebrew sources are provisional until Step 5 replaces them
2. `/translate ch05` has Claude Code start sub-agents, one chunk each, in parallel (section 11), on the model named in `project.yaml`. Each agent reads its prompt file and writes `output_chunkNNNN.md`, and with it a meta file of new names and terms, as translate-book does. They are merged into the glossary between batches. `translator translate log ch05` records, per chunk, the prompt's hash, the model, the date and the output's hash in `work/translate/ch05/log.jsonl`, so any chunk's output can be traced to the prompt that produced it. A chunk can be re-run on its own (`/translate ch05 --chunks 0007`).
3. The structure check runs after every chunk (post-edit hook) and again over the unit. A chunk that fails is given back to its agent with the failure; if it fails again, it is reported.
4. Translator's notes go to `units/ch05/notes/translator-notes.md`; problems in the author's English go to `author-questions.jsonl`.
5. `translator draft ch05` renders a side-by-side HTML for reading.
6. Claude Code reports back: the chunks that failed, new terms that need a decision, and the `[לבדיקה]` flags.

**Gate:** structure check passes on every chunk.

### Step 5 — Sources round [Stage 4]

**Needs:** Step 4. **Must come before review and style passes,** so reviewers never polish back-translations that
will be replaced. **Command:** `/sources ch05`.

1. **Locate.** One agent per unit lists every quotation that has an original and searches for it:
    - the verified-quotation library first (a quotation verified for an earlier book is reused, with its record)
    - then the scans, with `translator find hb "<words>" [--books N]` and `translator find page <book> <page>`
    - then Sefaria (`find sefaria`, `find ref`)
    It transcribes from the proofread scan, never from memory. Uncertain words go in `[...]`. Output: `work/sources/ch05-bundle.md` and a status per quotation: verified-text, located-scan, not-found, not-in-scans.
2. **Integrate.** Verified originals are inserted. Only as much as the author quotes; "..." where he skips; Yiddish as printed; `[לבדיקה]` removed from replaced quotations. Each insertion writes a quotation record with its hash (section 6.4). That record is the lock.
3. **House rules after insertion.** Where the original differs from the author:
    - keep the original exactly, and keep the author's prose that relies on his reading
    - highlight both with `==…==`; put the author's own insertions inside a quotation back as `==[…]==`
    - write an author question with the difference as evidence
4. **Further rounds** as material arrives: the author's own list, newly scanned books (OCR'd into the library with `ocrkit`). The quotations spreadsheet (`translator sources sheet`) is generated from `quotations.jsonl`, with parsha, key ideas and category columns.

**Pitfalls:** an edition that numbers sections differently is recorded as `edition-difference`, not as an error. A
book with the same title may be a different book: check the title page and running heads; `catalog.yaml` records
which is which. "Wrong speaker" findings are often real and matter for the argument: they go to the author.

**Gate:** you review the differences (the review page lists every `author_differs` quotation).

### Step 6 — Notes in house style and bibliography [Stage 5]

**Needs:** Step 5 (the conversion uses the quotation records). **Command:** `/notes ch05`.

1. `translator notes input ch05` builds the English and current Hebrew of every note.
2. One agent per unit converts the notes to Koren style, using the quotation records:
    - corrects wrong references, recording each in `edits.jsonl` and, where the author erred, in `author-questions.jsonl`
    - records content differences as `verify` items
    - writes the unit's works to `bibliography.jsonl`, reusing existing short forms exactly
    - gives a new work a conventional short form; never invents details
3. Review page → your decisions → `translator notes write ch05 --write`. Open `verify` items become `[לבדיקה: …]` flags.
4. **Cross-unit consistency.** When units are converted in parallel, `translator bibliography check` compares short forms and full entries across units before writing. The same work gets the same short form and full entry.

**Gate:** you accept the notes.

### Step 7 — Quotation lock [Stage 13]

**Needs:** Step 5. Not a separate run any more: the quotation records written in Step 5 *are* the register.
`translator check` (section 9) compares every recorded quotation's text with the chapter file at that ID, after
every step and in the post-edit hook. In the Rosen project the register reached only about 264 of roughly 570
quotations, because it was parsed from logs in several formats afterwards. That gap goes away.

A `[=…]` gloss (Step 13) is recorded in the quotation's `glosses` list, and the check treats it as an
addition, not a change.

**Changing a locked quotation.** Sometimes a recorded quotation is itself wrong: a transcription error found in the
footnote pass, a better scan, an author's correction. `translator quote amend q0412 --reason "…"` shows the
recorded text and the scan page, takes the corrected text (dry run first), and on `--write` updates the chapter
file, the record's `text` and `sha256`, and the library's copy (section 12). The old text is kept in the record's
`history`, and the change is written to `edits.jsonl` and `decisions.jsonl`. It is the only way to change a locked
quotation; the hook and `check` refuse every other way.

### Step 8 — Review round [Stage 3]

**Needs:** Steps 6 and 7. **Command:** `/review ch05`.

1. `translator review pairs ch05` builds numbered English/Hebrew pairs by ID. Locked quotations are shown but marked "do not review".
2. Two reviewer agents (section 10) write findings: span, proposed change, reason, category, style-checklist rule if any.
3. `translator review build ch05` builds the review page: English | Hebrew | reviewer 1 | reviewer 2, with findings both flagged first. You accept, edit or reject each; the page saves the decisions through `translator serve` (section 10).
4. `translator review apply ch05 --write` applies them, records `edits.jsonl` and updates the acceptance statistics.
5. Optional: an **outside evaluation** with other model families (`translator eval ch05`). This is the `eval/` module built on Rosen from `CLAUDE-CODE-eval-passes.md`, moved into the engine:
    - each Hebrew paragraph, with its English, the decided terms, the glossary and the style sheet, goes to two model families other than Claude (Gemini Pro and the current GPT flagship), and each returns an MQM-style verdict as JSON: scores for fidelity, register and terminology, and findings with category, severity, the exact Hebrew span and a one-sentence note, never a rewrite. A note with more than 8 Hebrew words counts as a rewrite and is asked again once; a span not found in the paragraph is rejected.
    - an optional third pass through DictaLM (`--with-dicta`) reads the Hebrew alone and reports only naturalness
    - locked quotations and headings are skipped and listed as "original Hebrew, not evaluated"
    - the resolved model names are logged in every result; responses are cached by a hash of provider, model and prompt, so reruns are free and repeatable; temperature 0; at most 4 requests in flight per provider; a cost estimate is printed first, and a run over the cap (`EVAL_COST_CAP_USD`, default $10) needs `--yes`
    - the first run on a book is `--limit 20`, read by you before a whole chapter is run
    - the report (`review/eval/ch05/`, RTL HTML and CSV) sorts paragraphs by "human look": either provider found a critical problem, the providers' fidelity scores differ by 2 or more, one reports a major problem the other doesn't mention, or DictaLM reports חמורה. The summary shows the recurring categories per provider, so an evaluator's bias (flagging every short sentence as "register") is visible.

    The findings go into `findings.jsonl` with `reviewer: gemini` / `openai` / `dicta` and are decided on the same review page as the Claude reviewers'. What changes from Rosen: pairs come from the stable IDs instead of `eval/align.py`'s alignment by footnote anchors, and the glossary and style sheet are read from the project instead of `eval/`'s own copies.

**Gate:** you decide each item.

### Step 9 — Style passes and consistency sweeps [Stage 6]

**Needs:** Step 8. **Command:** `/style ch05`.

1. **Diagnosis** (stage 4 of the style workflow), `review/style/ch05/diagnosis.md`. No unit is revised before it has one. It marks passages that read as translated rather than written: English word order, calques, cleft constructions ("it is X that…"), overuse of זה/זו, sentences that follow the English length instead of a Hebrew rhythm, explanatory glosses not in the original.
2. **Pilot the passes** on 2–3 pages of the first unit, compare side by side with a passage from the corpus, adjust the style sheet, then scale up.
3. **The five passes,** run separately and in this order, never all at once. Each agent states which pass it is doing and stays inside it:
    1. **structure:** split and merge sentences, paragraph flow
    2. **lexicon and terminology:** apply the glossary, decided terms and register
    3. **voice and transitions:** the argument moves as Hebrew scholarly prose moves
    4. **fidelity against the English:** style changes must not shift claims or hedges; every changed Hebrew sentence is shown with its English
    5. **footnote consistency:** citation format and how sources are quoted

    Merge, review page, apply. Locked quotations are never restyled.
4. Book-wide sweeps:
    - `translator terms sweep`: variant names and terms
    - `translator terms conform`: decided terms
    - `translator check divine-names`
    - `translator check spelling`: the fixed forms from the spelling policy

**Gate:** you accept.

### Step 10 — Koren drafts [Stage 7]

**Needs:** Step 9. **Command:** `/build ch05`.

`translator build koren ch05` → `drafts/koren/ch05-zaddik-koren.docx` and `.pdf`:

- chapter label (פרק א' / נספח א', from `project.yaml`) above the title
- real Word footnotes
- indented block quotes
- `==…==` as yellow highlight
- `[לבדיקה]` remarks embedded left-to-right
- lists and multi-paragraph notes
- `* * *` as a centred section break; `<br>` as a line break inside a paragraph
- the front matter from `ch00`
- **new:** a bookmark per paragraph and per note (section 6.1)

The build records each draft's hash in `state.yaml`. A file open in Word (`~$` lock) is skipped with a message.
A stale lock is removed only after `lsof` confirms Word doesn't hold the file.

**Checks:** no blank pages (`pdftotext`, page lengths); labels right; every note present; every ID has a bookmark.
**Gate:** you read the draft.

### Step 11 — The translator's Word round, and import [Stages 8, 12]

**Needs:** Step 10. **Command:** `/import ch05`.

**The edit round.** `translator word prepare ch05` copies the Koren draft to `drafts/word/ch05-…-edited.docx`,
tags the commit (`ch05-pre-edit`, the reference "original" for restorations in Step 12) and prints the editing
rules to give the translator:

- edit text, punctuation and italics freely
- keep footnotes as Word footnotes; don't renumber them
- avoid splitting or merging paragraphs; if you must, the import reports it
- no tracked changes or comments for content
- keep the highlights

From now until import, the text of record for the unit is the Word file. The hooks enforce it.

**Import.** As soon as the edited file is back:

1. Dry run: `translator import ch05`. Paragraphs and notes are matched by bookmark. Word formatting goes back to Markdown: highlight → `==`, italic → `*`, bold → `**`, footnote reference → `^n^`. Italic titles are restored. Reported: deleted, merged and new paragraphs, sections missing in Word, italics that couldn't be restored. Report in `work/import/ch05-report.md`.
2. You decide the reported cases. A split paragraph becomes `p0123a` / `p0123b`, or a `<br>` inside one paragraph.
3. `translator import ch05 --write`. It commits, sets the text of record back to `chapters`, rebuilds the Koren draft, and runs the **round-trip test**: the rebuilt draft must equal the Word file in body and notes.

**What "equal" means in the round-trip test.** Both files are reduced to the same form before comparing:

- **Compared:** per ID, in order: the text, the footnote references and their notes' text, and the formatting the app carries (highlight, italic, bold, block quote, section break, line break).
- **Normalised first:** Unicode to NFC; bidi control characters (RLM, LRM, RLE and so on) removed; non-breaking and ordinary spaces treated alike, runs of spaces collapsed; Word's smart quotes and the gershayim/geresh characters mapped to the house forms (the same mapping the gershayim/maqaf check uses); adjacent runs with the same formatting joined.
- **Ignored:** fonts, sizes, colours other than the highlight, paragraph spacing, and every other formatting the app doesn't carry.

A difference that survives normalisation fails the test and is shown per ID. Formatting the translator applied
that the app can't carry (a font change, say) is listed as a warning in the import report, so it isn't lost
without notice.

Any later change made in a Word file, as in Step 12, is followed by another import.

### Step 12 — Restorations, fidelity check, footnote pass [Stages 10, 9, 11]

**Needs:** Step 11. Run in this order, each followed by `/import`. **Commands:** `/restore`, `/fidelity`, `/footnotes`.

Corrections to a Word file are made in a copy (`*-edited-corrected.docx`) by `translator word apply <in> <corrections.json> <out>`.
Nothing is written if any span fails to match, and the file is re-read afterwards to confirm each change. Corrections
address an ID and a span, never a guessed paragraph number.

**Restorations** (only if an outside reviewer compared the pre-edit draft with the edited file):

- Agent maps each item to an ID and an exact span; dry run; apply.
- Your rules: restore the original verbatim, never the reviewer's suggestion or a hybrid. A reviewer quote with "…" restores the whole sentence. Items the reviewer keeps need only verifying. Keep the target's maqaf, and keep a colon that introduces a following block quote.
- Check every item against both files: reviewers have swapped "Original" and "Edited".
- Keep the content of earlier fidelity fixes unless the restored sentence carries the same content.
- The "original" is the draft tagged by `word prepare` (Step 11), recovered from git, so no copy of `drafts/koren/` needs keeping by hand.
- After any bulk correction, `translator check formatting` compares highlights and italics before and after. A span replacement takes the formatting of the run it starts in, so restored text can gain or lose highlighting or italics.

**Fidelity check** (on the corrected text, so it checks the wording that will stand):

- Bundle per unit by ID, English and Hebrew, locked quotations marked.
- Two reviewers, following the fidelity brief. Categories: meaning shift, omission, addition, attribution, modality, number/negation, reference. Severities: critical, major, minor. House choices are not flagged. Every Hebrew span must be an exact substring.
- Report with items flagged by both reviewers first. You choose ("all omissions and attributions"), and the corrections are applied.

**Footnote pass:**

- Every open note problem (fidelity findings on notes, all `[לבדיקה]` flags) is collected.
- Agents check each against the library and propose one of: fix / remove the flag / reword the flag to the open question / keep the flag (naming the book needed) / no change (deliberate, with evidence). Each comes with a confidence.
- A review sheet with a decision column. The accepted rows are applied. Quotation records, bibliography and author questions are updated from the same decisions.

### Step 13 — Inline glosses in quotations [Stage 14]

**Needs:** Step 12. **Command:** `/glosses ch05`.

Gloss Yiddish, Aramaic and uncommon rabbinic abbreviations inside quotations as `[=…]`, for example פ"ש [=פעם שנית].
Leave the common ones (ז"ל, הקב"ה, ה', א"כ). One sample chapter first, then the rest after your approval. Each gloss
is added to the quotation record's `glosses` list.

**Gate:** sample chapter approved.

### Step 14 — Back matter [Stage 15]

**Bibliography / רשימת קיצורים.** `translator bibliography consolidate`: one short form and one full entry per
work across the book. Variants are resolved; missing details are filled only from the title page.
Rendered to `out/reshimat-kitzurim.md` and into the Koren build.

**Indexes,** following the house's `index-spec.md` and the index plan from Step 2e. Because tags attach to IDs,
tagging can run after Step 9 and survives later edits, if the plan says so (`tagging_from: style`); otherwise it
runs on the final text. Tags on a block that is later split or merged are reported by the import for you to
reassign.

On Rosen the index work is specified in `CLAUDE_index.md`. In the app it splits in two:

- **House level** (`houses/koren/index-spec.md`, the same for every book): the Hebrew sort key (a `sort_as` override; the definite ה dropped only where `article: true` is set, never automatically, since it belongs to words like השכלה and הכנה; final letters normalised; geresh, gershayim, maqaf and spaces ignored; Hebrew before Latin, digits last; honorifics never sorted on); `ראו` as a pure redirect and `ראו גם` for related entries, with no chains or cycles; two levels of nesting; the render rules (main discussion first and bold, en-dash ranges, `87 הע' 12`); the source display forms from the house footnote style; the validator's errors and warnings (more than 25 undifferentiated locators warns, more than 40 is an error).
- **Book level** (the project's `index/`): which indexes the book has and in what order (Rosen: concepts and subjects, sources, persons, places, parashiyot and festivals, kept separate); the authority files `concepts.yaml`, `persons.yaml`, `places.yaml`, `sources-order.yaml` (Tanach order, Shas order, calendar order, the dynastic order of Hasidic authors and the anthology sub-group "קבצים ואנתולוגיות"); the seed vocabulary; the user note and the house-rules sheet for the publisher.

The rules that bind index work:

- the translation is never modified during index work; a task that seems to need a text change stops and says so
- a locator is never invented: a passage not found gets `anchor: null`, `todo: locate`
- ideas are indexed, not words; a passing mention gets no locator
- headwords are a controlled vocabulary: a new headword or variant goes to `pending.md` and waits for your approval
- decided terms and the divine-names policy apply to headwords

**Anchors.** On Rosen an anchor is `chNN·CCCC·P` (chunk file and paragraph number) with a snippet of the first 4–8
words. In the app it is the stable ID (`ch07.p0042`), still with the snippet. `validate.py`'s check that the snippet
is found in that paragraph then reports wording changes rather than shifted paragraph numbers.

- **Phase 0:** authority-file skeletons, `sources-order.yaml`, the Hebrew sort key with a unit test for every rule, conversion of any draft index into YAML, the validator. On Rosen, the three drafts in `work/index/*-he.md` (279 concept heads from Rosen's 603 lines) are converted rather than redone.
- **Phase A:** vocabulary proposals with evidence (heads, glosses for terms whose meaning shifts between the masters, per-master sub-entries, variants, see-also) → your approval.
- **Phase B:** tagging per unit (concepts, sources, persons, parashiyot), with the validator after each unit; a rendered draft every 2–3 units; you mark the main discussions.
- **Phase C:** page numbers from the proofs (`resolve_pages.py` matches each snippet in the proof PDF; a page set by hand is never overwritten); you spot-check 30 random locators.
- **Phase D:** the publisher package: `mafteach.docx` (RTL, the book's body font), the user note and the house-rules sheet. If the press asks for an indexed Word file instead, XE fields go into a copy of the final manuscript, never into the masters.

**Front matter:** title page, contents, preface (`ch00`), built with the same tools.

### Step 15 — Questions for the author, and the publisher package [Stage 16]

- `/author-list` renders `author-questions.jsonl`, grouped by chapter and kind, each with its evidence and the passage in English and Hebrew. Because the register exists from Step 1, it can go to the author (or the author's editor) chapter by chapter, not only at the end. Answers are recorded on the question and can reopen a unit's steps.
- `/package` assembles `out/`: the rebuilt Koren drafts, the רשימת קיצורים, the indexes, the front matter, the house-rules note for the publisher. `check` must pass with no errors first. Tag `to-publisher`.

---

## 9. `translator check`

One command runs every check, like a test suite. It runs over the units named or all. It runs automatically
after each step, in the post-edit hook (for the edited unit), and before `/package`.

| Check | Fails when | Level |
| --- | --- | --- |
| structure | source and output differ in block IDs or their order, `^n^` markers, note count, headings, quote lines | error |
| text of record | a unit is `word` and hasn't been imported, or a Word master's hash differs from the one recorded at its build | error |
| quotations | a recorded quotation's text differs from the chapter file (glosses excepted) | error |
| decided terms | a decided term's source appears and the Hebrew uses another rendering | error |
| divine names | the translator's prose has אלוהים or האל, or no maqaf in א־לוהים (quotations exempt) | error |
| spelling | a word the spelling policy fixes appears in another form | warning |
| markers | a malformed `==…==`, `[לבדיקה` without `]`, a `[=…]` outside a quotation | error |
| gershayim/maqaf | ASCII `"` used for gershayim, or `-` where the house uses a maqaf (house setting) | warning |
| flags | count of open `[לבדיקה]` per unit | info |
| stale | a step passed before a step it depends on was redone | warning |
| bibliography | one work with two short forms; a short form with no full entry | error |
| formatting | highlights or italics changed by a correction that wasn't meant to change them | warning |
| index | the index validator (Step 14). When it reports an error the data looks right for, fix the rule: on Rosen, validators demanded sub-entries from a fixed list and knew only an old draft's tractates | error |

`check` prints a table and writes `work/check.json`. A step's gate can't be passed while its unit has errors.

---

## 10. Reviewers

Every check by models uses **two independent reviewers** (Fable and Opus in the Rosen project; set in
`project.yaml`). They report problems and never rewrite the text. When both flag the same span, the finding ranks
first.

**Finding schema** (`findings.jsonl`):

```json
{"fid": "f2291", "step": "review", "unit": "ch05", "block": "ch05.p0123", "reviewer": "opus",
 "category": "omission", "severity": "major", "he_span": "…", "proposed": "…", "reason": "…",
 "checklist_rule": null, "agreed_with": "f2290", "decision": "accepted", "decided": "2026-08-20"}
```

**Briefs** are templates in the engine (`briefs/`). Every brief states:

- its inputs
- the binding rules (decided terms, locked quotations, house choices not to flag)
- the output format
- the checks the agent must run before finishing (every `he_span` is an exact substring)
- a short reply format: counts, plus the decisions needed from you

**Review pages and saving decisions.** A review page opened as a file can't write to disk, so the pages are served
by `translator serve`, a small local web server (localhost only, started by the slash command that builds the page,
stopped when it closes). The page shows the findings; each decision you make (accept, edit, reject, with a note) is
sent to the server, which writes it at once to `review/<step>/<unit>/decisions.json`. Closing the page loses
nothing, and reopening it shows the decisions so far. `translator gate` reads that file.

If the server isn't running, the page still opens (from VS Code's built-in browser or any browser). It then works
as the Rosen pages do today: it keeps the decisions in the browser's `localStorage` and offers "Download decisions"
(a JSON file) and "Copy decisions" (to paste to Claude). The downloaded file is passed to
`translator gate ch05 review --decisions <file>`. On Rosen this was the only way: every page saved by download, and
two of them (the pilot review and the revised-chapter review) produced files no script read. In the app, every
page's decisions are read by `gate`.

**Acceptance statistics.** `translator review stats` shows, per reviewer and category, how many findings were
accepted, edited and rejected, across the book and across books. Categories you almost always reject can be
dropped from the brief, or demoted to "only if critical", for the next book. That cuts the review load where it
adds least.

---

## 11. Running agents

All model work except OCR proofreading runs in Claude Code, as sub-agents: translation (Step 4), the sources
round, notes, reviews, restorations, the footnote pass. `ocrkit` calls the API itself, and can use the Message
Batches API at half price when the result isn't needed within the hour.

- **In Claude Code.** The slash command tells Claude Code to start one sub-agent per unit (or per chunk, for translation) with the brief the engine generated. `agents.parallel` in `project.yaml` is written into the command as an instruction ("start at most 4 at a time"). Claude Code has no setting that enforces it, so it is a request, not a limit.
- **Own files only.** Each agent writes only its unit's files and its own record lines (each record file gets one temporary file per agent, `records/.pending/<agent>.jsonl`, merged at the end by the engine, which assigns the permanent IDs; section 6.4). No two agents append to the same file, and no agent commits (section 6.5).
- **Save after each unit,** so an interruption loses little. A stopped agent is resumed with a message; it continues from its transcript.
- **Scripts agents write** go into `work/<step>/scripts/` in the project, never only in a temporary folder.

**Keep the Mac awake** during long runs, lid open, on power. `ocrkit proofread` starts `caffeinate -i -s` itself for
the length of the run. For a long sub-agent session (a whole book's translation, say), the slash command starts
`caffeinate -i -s -t 21600` in the background at the beginning and stops it at the end.

---

## 12. Shared resources

### Reference library

Every scanned book is OCR'd once into `scans/<book-id>/` with `ocrkit`, proofread with `--batch`, and entered in
`catalog.yaml`:

```yaml
emet-ve-emunah:
  title: אמת ואמונה
  edition: ירושלים תשנ"ה
  hebrewbooks_id: 12345
  scan: scans/emet-ve-emunah/
  numbering: "sections numbered differently from the Bnei Brak edition used by Rosen"
  same_title_as: null
```

`translator find` searches the proofread text of all catalogued books, returning book, page and the matching
lines. The scan page image is one click away in VS Code.

### Verified quotations

When a project's quotation reaches `verified-scan` or `verified-text`, it is also added to the library's
`quotations.jsonl`, keyed by **work, edition and locator**. The edition is part of the key because editions number
sections differently (the `edition-difference` pitfall, Step 5): §442 in one edition is not §442 in another.

The next book's sources round checks the library first. A match on the key is a candidate, not an answer: the
agent confirms that the author's quotation is a stretch of the library's text, and takes only the part the author
quotes. A match on the same work in another edition is shown with the `catalog.yaml` numbering note, and is
verified against the scan before it's reused. Hasidic sources recur across Przysucha and Kotzk books, so each book
should make the next one's sources round shorter.

### House profiles

`houses/koren/` holds what belongs to the publisher, not the book: footnote style, divine-names policy, title
marking, default spelling policy, marker conventions, the index spec, and the Koren docx template. A second
publisher gets a second folder; `project.yaml` names the house.

---

## 13. Testing

- **Fixture book** in the engine's `tests/fixture/`: two short units with notes, an asterisk note, a gap in note numbering, a block quote, a Hebrew quotation, a split paragraph. It includes a "translator's Word edit" docx made by hand **in real Word** (not generated), with every case in the bookmark table of section 6.1: an edit, a deletion, a merge, a split, a retyped paragraph, text typed at a paragraph's edge, a new paragraph, smart quotes from autocorrect, and a font change.
- **Golden outputs:** the expected chunk files, Koren draft text, import result and check report. `pytest` runs every command on a copy of the fixture and compares. This replaces the "never test a writing tool on a real unit" rule with an actual test.
- **Unit tests** for the parts that broke before: alignment and bookmark mapping, footnote mapping with asterisk notes and gaps, the heading that shares a paragraph with note 1, per-unit state reset, the Hebrew sort key. And for the new parts: the hooks (each blocked case exits 2; an internal error exits 2), record-ID assignment when pending files are merged, rerunning named IDs with locked quotations put back, and the round-trip normalisation.
- `ocrkit` has its own 27 tests (OCR on generated scans, proofreading with a fake client).
- `translator doctor` checks the installation, and `translator check` checks a project; neither replaces the tests.

---

## 14. What the app takes from `the_translator/`

The Rosen translation is not moved onto the app; it stays in `the_translator/` as it is. The first book on the app
is a new one, *Stop, Look, Listen* (`projects/stop-look-listen/`). What Rosen gives the app is its method and
its reusable material:

| From `the_translator/` | Goes to | Status |
| --- | --- | --- |
| `tools/`, `translate-book/`, `eval/` and its tests | `legacy/`, then ported into the `translator` package one command at a time (Appendix A) | copied; 29 tools read the book folder from `TRANSLATOR_PROJECT` |
| `custom_instructions*.txt`, the `*-brief.md` files, `sources/integration_rules.md` | the engine's brief templates, with the book's name, register and terms as variables (milestone 11) | to do |
| `CLAUDE_addendum.md` (style workflow, fixed conventions, working rules) | the engine's briefs and generated `CLAUDE.md`; Rosen's own values (Steinsaltz register, "greatness" → אדם גדול) stay with Rosen | written into Steps 2a and 9 |
| `CLAUDE-CODE-eval-passes.md` | `translator eval` (Step 8) | written into Step 8 |
| `CLAUDE_index.md` | `houses/koren/index-spec.md` (the house rules); the book-level parts are a model for each new book's `index/` | written into Step 14 |
| `sources/style/footnote-style.md`, `sources/style/koren/` | `houses/koren/` | to do |
| `eval/decided-terms.md`, `glossary/glossary-book.json` | a starting point for a new book's decided terms where the subject overlaps (Hasidic terms, names of masters, divine names); each term is confirmed for the new book, never copied blindly | to do, per book |
| `style-corpus/`, `style/` (profiles, comparison) | reusable for a new book in the same register; the comparison is redone against the new book's author | per book |
| verified quotations (sources logs, `quotations-status.xlsx`) | the library's `quotations.jsonl`, keyed by work, edition and locator, so a new book's sources round finds them first | importer to do (milestone 7) |
| scanned seforim (`Tiferet/`, `sources/hb/`, `texts/`, `keter.pdf`, `Mickey*.pdf` and their OCR) | the reference library, through `ocrkit import-txt` where only old OCR exists | to do (milestone 7) |
| `sources/style/bibliography.json`, `work/bibliography/reshimat-kitzurim.md` | the library's bibliography: short forms and full entries a new book can reuse | to do |

Not taken: Rosen's chapter files, drafts, Word masters, reviews and logs. They belong to that book.

## 15. Build plan

Estimates are working days of focused work with Claude Code. The first book, *Stop, Look, Listen*, is already
waiting, so the order lets it start the early steps (OCR, cleaning, foundations) while the later machinery is built.

| # | Milestone | Contents | Est. |
| --- | --- | --- | --- |
| 0 | Repository and inventory | The app's repository; `ocrkit` installed; `legacy/` copied and pointed at a book folder; the tools inventory (Appendix A) | done |
| 1 | Engine skeleton | Package, CLI, `init`, `upgrade`, `project.yaml`, generated `CLAUDE.md` and `state.md`, slash commands, `doctor`. **Done 24 Oct 2026**, with Step 1 (`clean`, `chunk` with permanent IDs) and a first `gate`; 5 tests | done |
| 2 | Tools on the project root | Legacy tools behind commands, paths from the project, chapter lists and labels from `project.yaml` | 3–5 |
| 3 | State, gates, check, hooks | `state.yaml` and hashes, refusals, `gate`, `check`, pre/post-edit hooks with their self-test, git lock and commits, pre-commit size check, reruns on named IDs | 4–5 |
| 4a | Word bookmark trial | Build a draft with bookmarks; make every edit in the section 6.1 table in real Word; confirm what Word does; this becomes the fixture's Word edit | 1 |
| 4 | Stable IDs end to end | IDs at chunking, translation brief, structure check, Koren bookmarks, bookmark import, round-trip test with normalisation | 5–7 |
| 5 | Records | Schemas, writers in each step, ID assignment at merge, `quote amend`, reports generated from records | 3–4 |
| 6 | OCR as Step 0 | `ocrkit` wired into `/ocr` and `translator clean`. **Done 24 Oct 2026**: `/ocr` command; `ocrkit` normalises references and the notes separator, and `ocrkit recheck` reruns the checks on saved pages without the API (30 tests) | done |
| 7 | Library | `catalog.yaml`, `find` over the library, verified-quotation library keyed by edition, importers for Rosen's verified quotations, seforim and bibliography (section 14) | 3–4 |
| 8 | Fixture and tests | Fixture book, golden outputs, unit tests | 2–3 |
| 10 | Review pages | `translator serve`, saving decisions, the download fallback, the existing review pages moved onto it | 2–3 |
| 11 | Briefs to templates | Rosen's briefs and `custom_instructions*.txt` as Jinja templates (section 14), rendered and checked against the originals | 2 |
| 12 | Outside evaluation | `legacy/eval/` moved into the engine; pairs from stable IDs; glossary, decided terms and style sheet read from the project; findings into `findings.jsonl` | 1–2 |
| 9 | First book through the pilot | *Stop, Look, Listen*: Steps 0–3 on the app, the pilot chapter through Steps 4–12 | runs alongside |

Total: roughly 31–42 days of building. Order: 1 → 6 → 2 → 3 → 4a → 8 (tests early, so the riskier milestones are
covered; 4a first, so the fixture records what Word really does) → 4 → 5 → 11 → 10 → 7 → 12. Milestone 6 comes
early because the first book's OCR is done and its cleaning (Step 1) can start; Step 2 (foundations) needs no new
machinery and can run alongside milestones 2–4. Milestone 4 is the
one most likely to run over; 4a is there so its surprises appear in a day, not in the middle of it.

Milestones 1–3 alone already give per-book folders, enforced order, the hooks and git. Each milestone ends with
`check` passing on the fixture book and on *Stop, Look, Listen* as far as it has gone.

---

## 16. Open questions

1. **Skill or plugin?** This design uses a skill (linked into `~/.claude/skills/`) plus a per-project `.claude/` copied by `init` and refreshed by `upgrade`. That is simpler to start with, but the copies can drift from the engine, and `upgrade` has to be run on every project. A Claude Code plugin would ship the commands, hooks and skill together and update them in one place for every project. Moving to a plugin after milestone 3 costs little, since the commands and hooks already live in the engine's `commands/` and are only copied. Start as a skill and move later, or build as a plugin from the start?
2. **Reviewer models.** Keep Fable and Opus, or use the acceptance statistics after the pilot to choose?
3. **Word round alternative.** Bookmarks keep the Word round, which the translator knows. The other option is editing in the review pages (HTML, by ID), which removes the import entirely but changes how the translator works. Stay with Word?
4. **Author questions during the work.** Is there an author or editor to send questions to chapter by chapter, or only at the end?
5. **Spelling policy for the next book.** Ktiv male plus which fixed forms? `init` will ask.
6. **Library location and backup.** Is `~/Library/TextLibrary/` right, and should it sync to OneDrive?
7. **Index from the start.** Tag after Step 9 (possible with IDs) or keep the Rosen order (only on the final text)? Decided per book in Step 2e; the question is which default `init` should propose.

---

## Appendices

### A. Old tools → new commands

From an inventory of `the_translator/tools/` (45 scripts, 24 October 2026). The full inventory, with inputs, outputs
and line numbers, goes into `docs/tools-inventory.md`.

| Old (`tools/`) | New | Notes from the inventory |
| --- | --- | --- |
| `build_prompts.py` | `translator translate prompts` (and `translate log`, new) | Target language "Hebrew" and the brief's file name are hard-coded; calls translate-book's `glossary.py` and `chunk_context.py` |
| `custom_instructions.txt`, `custom_instructions_part2.txt` | brief templates (milestone 11) | Part 2's "context-dependent renderings" point at Rosen paragraphs (ch08 ¶35, ch09 ¶64–66); they stay with Rosen and are not carried into the templates |
| `check_structure.py` | `translator check structure` (also in the post-edit hook) | Generic already |
| `build_draft.py` | `translator draft` (HTML) | |
| `draft_data.py`, `build_draft_docx.js` | `translator draft --docx` | Missing from the first mapping; the book's title is hard-coded in the docx creator string |
| `build_glossary_page.py`, `apply_glossary_edits.py` | `translator glossary review / apply` | The current pair; chapter lists ch01–06 / ch07–12 hard-coded |
| `build_glossary_review.py`, `apply_glossary_review.py` | dropped | The earlier pair, replaced by the two above |
| `merge_decided_terms.py` | `translator terms merge` | Its term list is hard-coded (`DECIDED`), not read from `eval/decided-terms.md` as its docstring says. When it is ported, the terms come from the project's `decided-terms.yaml` |
| `conform_terms.py` | `translator terms conform` | Already dry-run by default; limited to ch01–06 |
| `names_of_god.py` | `translator check divine-names` | Limited to ch01–06 |
| `consistency_sweep.py` | `translator terms sweep`, `translator check spelling` | Covers ch01–12; its spelling variants (`VARIANTS`) seed the spelling policy |
| `build_pairs.py`, `build_review.py`, `apply_review.py` | `translator review pairs / build / apply` | Reviewer models fixed to Fable/Opus in `build_review.py`; read from `project.yaml` instead |
| `find_source.py` | `translator find` (over the library) | Its HebrewBooks titles (`TITLES`) seed `catalog.yaml` |
| `build_quotes_sheet.py`, `quotes_add_parsha.py` | `translator sources sheet` (from `quotations.jsonl`) | Together they make `quotations-status.xlsx`; `quotes_add_parsha.py` only works when run from the project root. Rosen's sheet feeds the library's verified-quotation importer (milestone 7) |
| `build_sources_sheet.py` | `translator sources tracker` | A separate workbook of sources and notes still to verify; ch01–04 hard-coded |
| `build_sources_overview.py` | `translator sources overview` | Per-note data hard-coded (`STEP2`); this becomes records |
| `build_notes_input.py`, `build_notes_review.py`, `apply_notes_review.py` | `translator notes input / review / write` | `write` applies only the accepted notes |
| `write_koren_notes.py` | `translator notes write --all` | An alternative to the review, not a step after it: writes every note, with flags, without review |
| `build_diagnosis.py` | `translator style-pass diagnose` | Built from the evaluator findings; ch01–06 |
| `build_style_input.py`, `merge_style_passes.py`, `apply_style_passes.py` | `translator style-pass input / merge / apply` | |
| `restore_quote_layout.py` | dropped | Needed a backup folder to restore `>` layout on locked rows; the quotation records make it unnecessary |
| `build_pilot_review.py` | `translator review build --pilot` | Missing from the first mapping; its downloaded decisions were never read |
| `merge_revised_check.py`, `build_revised_review.py`, `build_revised_book.py` | `translator import` and `review` | The flow for a chapter the translator revised; missing from the first mapping |
| `build_koren.py`, `book_data.py`, `build_book_docx.js`, `node_docx/` | `translator build koren` | Default list ch01–12 (no ch00, no addenda); LibreOffice path hard-coded; the asterisk note becomes footnote 1 and shifts the rest, which the bookmarks make safe |
| `align_koren_edits.py` | the fallback inside `import` | Not used by `import_corrected.py`, which has its own aligner; only `quote_register.py` imports it |
| `build_fidelity_report.py` | `translator fidelity report` | Its page has no way to save decisions; it gets one (section 10) |
| `apply_docx_corrections.py` | `translator word apply` | Addresses paragraphs by B/N number with its own copy of the numbering; becomes ID-addressed |
| `import_corrected.py` | `translator import` | Dry run by default; aligns footnotes by text, so numbering gaps can't shift them; default ch01–18; the backup folder name is a fixed date |
| `quote_register.py` | replaced by `quotations.jsonl` + `translator check quotations` | Builds the register from `sources/applied/*-SOURCES-APPLIED*.md`, ch01–12 only |
| `eval/` (`align.py`, `run.py`, `report.py`, `providers/`) | `translator eval` | Built from `CLAUDE-CODE-eval-passes.md`; alignment replaced by stable IDs |
| `work/index/scripts/*` | `translator index …` | |
| `final_ocr.py`, `proofreader.py` | `ocrkit ocr`, `ocrkit proofread` | Thin wrappers in `ocrkit` 2.0 |
| translate-book `convert.py`, `glossary.py`, `chunk_context.py`, `manifest.py`, `merge_meta.py` | kept, vendored into the engine | |

### B. Record schemas

Common fields on every record: an id, `unit`, `block` (a stable ID, when the record is about a passage), `at` (time
written), `by` (command or agent).

| Record | Fields |
| --- | --- |
| decision | `did`, `step`, `unit`, `question`, `answer`, `note`, `commit` |
| author question | `aqid`, `kind`, `text`, `evidence[]`, `raised_by`, `status` (open / sent / answered / closed), `answer` |
| quotation | `qid`, `work`, `locator`, `edition`, `library`, `status`, `text`, `sha256`, `author_differs`, `difference`, `author_question`, `glosses[]`, `history[]` (earlier texts, from `quote amend`) |
| finding | `fid`, `step`, `reviewer`, `category`, `severity`, `he_span`, `proposed`, `reason`, `checklist_rule`, `agreed_with`, `decision` |
| edit | `eid`, `command`, `before`, `after`, `reason`, `finding` / `decision`, `commit` |
| bibliography | `work`, `short_form`, `full_entry`, `script`, `units[]`, `variants[]`, `source` (title page / catalogue) |

### C. Unit step dependencies

```
clean → chunk → translate → sources → notes
                               └──→ quotation lock (continuous from sources onwards)
notes + lock → review → style → build → [Word round] → import
import → restore → import → fidelity → import → footnotes → import → glosses → back matter → package
foundations (Step 2) gate every translate; the pilot (Step 3) gates every unit but the pilot
```

### D. Editorial markers

| Marker | Meaning |
| --- | --- |
| `[לבדיקה: …]` | to check; counted by `check` |
| `[תרגום מקובל קיים]` | an existing published translation is used |
| `==…==` | highlight: an original differs from the author |
| `==[…]==` | the author's own insertion inside a quotation |
| `[=…]` | the translator's gloss inside a quotation |
| `^n^` | footnote reference |
| `<!--id:ch05.p0123-->` | stable ID of the block (hidden in previews) |
| `<!--page:57-->` | printed page break in the source |
| `{?…}` | doubtful OCR reading (Step 0 only; resolved or turned into `[לבדיקה]` in Step 1) |
