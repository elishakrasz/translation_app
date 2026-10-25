---
description: Step 4 — translate a unit's chunks with sub-agents, from prompts built by the engine
argument-hint: <unit> [--chunks 3,7]
---
Translate `$ARGUMENTS` (a unit id, optionally `--chunks`).

1. Run `{{TRANSLATOR}} translate prompts $ARGUMENTS`. If it refuses (foundations missing, or the unit isn't chunked),
   tell me why and stop.
2. For each prompt in `work/translate/<unit>/prompt_NNNN.md`, start one sub-agent (at most the `agents.parallel` number
   from project.yaml at a time). Its whole instruction: "Read <prompt path> and do exactly what it says. Write only the
   two files it names." Don't paraphrase the prompt; the file is the brief.
3. When all are back, check each chunk's structure: `<python> legacy/tools/check_structure.py units/<unit-folder> <NNNN…>`
   with TRANSLATOR_PROJECT set to this folder (the python and legacy folder are next to {{TRANSLATOR}}). A chunk that
   fails goes back to a new sub-agent once, with the failure added; if it fails again, report it.
4. Report per chunk: blocks, `[לבדיקה]` flags, notes written. Then list, from the notes files, every gloss dropped or
   folded in (style rule 10) and every pun recreated, for my approval.

Don't run anything that writes outside units/<unit>/ and work/translate/. The translation waits for my reading; the
next step is the sources round (/sources), which replaces the provisional quotations.
