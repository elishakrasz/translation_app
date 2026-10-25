# Style pass brief — one pass, proposals only

You are one of five style passes over a Hebrew translation that has already been reviewed for fidelity. Each pass
does one job and stays inside it; the translator decides every proposal. You never rewrite the text: you propose
replacements for exact spans.

## Read first (in the project folder)
- `style/style-sheet.md` — the voice (Nagen's plain, warm, first-person Hebrew; Steinsaltz's clarity; Sabato's pacing in
  memoir) and its rules. It is the authority for every proposal.
- `terms/decided-terms.yaml` and `style/style-checklist.yaml`.
- `work/style/<unit>-pairs.md` — the unit block by block: `EN:` the English, `HE:` the current Hebrew.

## The five passes (do only yours)
1. **structure** — sentences and paragraph flow. The target is about 16 Hebrew words a sentence, a long period set
   against a short verdict; split sentences over ~35 words where the Hebrew allows; merge only fragments the English
   doesn't have. Mark what reads as translated rather than written: English word order, cleft sentences ("it is X
   that…"), sentences mirroring English length.
2. **lexicon** — vocabulary and terminology: the glossary and decided terms, register (no ornate or obscure words, no
   loanword where a plain Hebrew word exists, rule 7), ש not אשר, the feminine demonstrative (rule 3), אבל only in memoir.
3. **voice** — transitions and the movement of the argument: connectives from the style sheet's bank, the first person
   where Polen has it, paragraph openings and the short closing verdict, the memoir passages in Sabato's pacing (rule 9).
4. **fidelity** — style must not shift claims: check every hedge, modality, emphasis and attribution against the
   English, especially in sentences earlier passes would restructure. Quote the English words in your reason.
5. **footnotes** — the notes: consistency of citation form with the house style already applied, short forms, the
   register of argument notes matching the body.

## Never
- Touch anything marked LOCKED (verified verses and sources), `[לבדיקה …]` flags, `^n^` markers, `<!--id-->` comments.
- Explain or replace a metaphor; add a gloss or a synonym; change אלוקים, לעתים, Koren references.
- Propose taste-only changes: each proposal must serve a rule or a clear gain in the style sheet's voice.

## Output: one JSON file (path given to you), nothing else
```json
{"reviewer": "<pass name>", "unit": "<unit>", "findings": [
 {"block": "ch02.p0014", "he_span": "exact Hebrew from the HE line (an exact substring)",
  "proposed": "the Hebrew that replaces exactly that span",
  "reason": "one sentence in English: what it fixes, with the rule or the English words",
  "category": "<your pass name>", "severity": "major|minor", "checklist_rule": "the rule id, or null"}]}
```
Keep spans as short as the change allows, and never let two of your proposals overlap. Check with Python before
finishing that every he_span occurs in its block's HE text. Reply with the number of proposals and, for structure, the
sentences you split.
