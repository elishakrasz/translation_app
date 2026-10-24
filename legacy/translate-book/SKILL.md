---
name: translate-book
description: Translate books (PDF/DOCX/EPUB) into any language using parallel sub-agents. Converts input -> Markdown chunks -> translated chunks -> HTML/DOCX/EPUB/PDF.
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, Agent, AskUserQuestion
metadata: {"openclaw":{"requires":{"bins":["python3","pandoc","ebook-convert"],"anyBins":["calibre","ebook-convert"]},"homepage":"https://github.com/deusyu/translate-book"}}
---

# Book Translation Skill

You are a book translation assistant. You translate entire books from one language to another by orchestrating a multi-step pipeline.

## Workflow

### 1. Collect Parameters

Determine the following from the user's message:
- **file_path**: Path to the input file (PDF, DOCX, EPUB, or Markdown) — REQUIRED
- **target_lang**: Target language code (default: `zh`) — e.g. zh, en, ja, ko, fr, de, es, he
- **concurrency**: Number of parallel sub-agents per batch (default: `8`)
- **temp_root**: Optional directory under which `{filename}_temp/` should be created
- **epub_cover**: Optional explicit cover image path for EPUB output
- **export_name**: Optional filename stem for user-facing output aliases
- **custom_instructions**: Any additional translation instructions from the user (optional)

If the file path is not provided, ask the user.

### 2. Preprocess — Convert to Markdown Chunks

Run the conversion script to produce chunks:

```bash
python3 {baseDir}/scripts/convert.py "<file_path>" --olang "<target_lang>"
```

If the user provided `temp_root`, add `--temp-root "<temp_root>"`. The temp
directory leaf name remains `{filename}_temp/`; only the parent directory
changes.

For PDFs, Calibre reflows text by coordinate heuristics, which shatters math
formulas, flattens tables, and interleaves multi-column layouts before
translation starts. If the PDF is an academic or technical document and a
layout-aware parser is already installed — or the user asks for one — extract
the PDF with it first, then pass the resulting Markdown file to `convert.py`
instead of the PDF. Markdown input (`.md` / `.markdown`) skips Calibre:

- MinerU >= 4: `mineru-kit parse "<file_path>" -o "<name>.md"`
- Marker: `marker_single "<file_path>" --output_dir "<dir>"`, then use `<dir>/<name>/<name>.md`

Keep the PDF's file name stem for the Markdown file, because the temp
directory is named after it. These CLIs change between versions; check the
parser's `--help` if a flag is rejected. Do not install a parser without the
user's consent, because they download large models. Images next to the
Markdown file and base64 images inlined in it are copied into the temp
directory. `--strip-page-numbers` does not apply to Markdown input.

This creates a `{filename}_temp/` directory containing:
- `input.html` (Calibre input only), `input.md` — intermediate files
- `chunk0001.md`, `chunk0002.md`, ... — source chunks for translation
- `manifest.json` — chunk manifest for tracking and validation
- `source_fingerprint.json` — SHA-256 identity of the source bytes this temp dir was built from
- `config.txt` — pipeline configuration with metadata

If `convert.py` aborts because the temp dir was created from different source
bytes, do not reuse it — delete the temp directory or pass a fresh
`--temp-root`, then re-run. Temp dirs created before fingerprinting existed
are adopted with a warning and fingerprinted on the next successful run.

### 3. Discover Source Chunks

Use Glob to find all source chunks:

```
Glob: {filename}_temp/chunk*.md
```

Exclude `output_chunk*.md` from the source list. The selective re-translation
plan below decides which chunks actually need work.

### 3.5. Build Glossary (term consistency)

A separate sub-agent translates each chunk with a fresh context. Without shared state, the same proper noun can drift across multiple translations. The glossary makes every sub-agent see the same canonical translation for the terms that appear in its chunk.

If `<temp_dir>/glossary.json` already exists, skip the rebuild — re-running the skill must not overwrite a hand-edited glossary. To force a rebuild, delete the file.

Otherwise:

1. **Sample chunks**: read `chunk0001.md`, the last chunk, and 3 evenly-spaced middle chunks. If `chunk_count < 5`, sample all of them.
2. **Extract terms**: from the samples, identify proper nouns and recurring domain terms that need consistent translation across the book — typically people, places, organizations, technical concepts. Translate each into the target language. Skip generic vocabulary that any translator would render the same way.
3. **Write `glossary.json`** in the temp dir, matching this v2 schema:

   ```json
   {
     "version": 2,
     "terms": [
       {"id": "Manhattan", "source": "Manhattan", "target": "曼哈顿",
        "category": "place", "aliases": [], "gender": "unknown",
        "confidence": "medium", "frequency": 0,
        "evidence_refs": [], "notes": ""}
     ],
     "high_frequency_top_n": 20,
     "applied_meta_hashes": {}
   }
   ```

   Existing v1 `glossary.json` files are auto-upgraded to v2 on first load. v2 forbids the same surface form (source or alias) appearing in two different terms; if a v1 file has polysemous duplicate sources, the upgrade aborts with a disambiguation message.

4. **Count frequencies** by running:

   ```bash
   python3 {baseDir}/scripts/glossary.py count-frequencies "<temp_dir>"
   ```

   This scans every `chunk*.md` (excluding `output_chunk*.md`), updates each term's `frequency` field, and writes back atomically.

The glossary is hand-editable. If the user edits a `target`, `aliases`, or
`category` field after a partial run, the run-state planner in the next step
will re-translate only chunks whose recorded term set or term hashes are
affected.

### 3.7. Plan Selective Re-translation

Run:

```bash
python3 {baseDir}/scripts/run_state.py plan "<temp_dir>"
```

If the user explicitly asks to apply glossary edits to outputs produced before
`run_state.json` existed, add `--retranslate-untracked`; otherwise keep the
default so old temp dirs remain resumable without mass re-translation.

Capture stdout JSON:
- `translation_chunk_ids` — chunks to translate in this run.
- `record_only_chunk_ids` — existing valid outputs that need `run_state.json`
  records but do not need translation.
- `unchanged_chunk_ids` — existing outputs already consistent with the current
  source chunks and glossary.

If `record_only_chunk_ids` is non-empty, record them before launching
sub-agents:

```bash
python3 {baseDir}/scripts/run_state.py record "<temp_dir>" chunk0001 chunk0002 ...
```

Use `translation_chunk_ids` as the work queue for Step 4. If it is empty, skip
to Step 5.

### 4. Parallel Translation with Sub-Agents

**Each chunk gets its own independent sub-agent** (1 chunk = 1 sub-agent = 1 fresh context). This prevents context accumulation and output truncation.

Launch chunks in batches to respect API rate limits:
- Each batch: up to `concurrency` sub-agents in parallel (default: 8)
- Wait for the current batch to complete before launching the next

**Spawn each sub-agent with the following task.** Use whatever sub-agent/background-agent mechanism your runtime provides (e.g. the Agent tool, sessions_spawn, or equivalent).

The output file is `output_` prefixed to the source filename: `chunk0001.md` → `output_chunk0001.md`.

> Translate the file `<temp_dir>/chunk<NNNN>.md` to {TARGET_LANGUAGE} and write the result to `<temp_dir>/output_chunk<NNNN>.md`. Follow the translation rules below. Output only the translated content — no commentary.

Each sub-agent receives:
- The single chunk file it is responsible for
- The temp directory path
- The target language
- The translation prompt (see below)
- A per-chunk term table (see "Term table assembly" below)
- Read-only neighboring chunk excerpts (see "Neighbor context assembly" below)
- Any custom instructions

**Term table assembly** — before spawning a sub-agent, run:

```bash
python3 {baseDir}/scripts/glossary.py print-terms-for-chunk "<temp_dir>" "chunk<NNNN>.md"
```

Capture stdout. The CLI emits a 3-column markdown table (`原文 | 别名 | 译文`) of every term that either appears in this chunk (by source OR any alias) OR is in the top-N most-frequent terms book-wide. Inject the table as `{TERM_TABLE}` in the Terminology section of the translation prompt. **If stdout is empty (no glossary, or no relevant terms), omit the Terminology section from this chunk's prompt entirely** — do not leave a dangling `{TERM_TABLE}` placeholder.

**Neighbor context assembly** — before spawning a sub-agent, run:

```bash
python3 {baseDir}/scripts/chunk_context.py "<temp_dir>" "chunk<NNNN>.md"
```

Capture stdout. The CLI emits prompt-ready read-only excerpts: the last ~300
characters of the previous chunk and the first ~300 characters of the next
chunk when those files exist. Inject this block as `{NEIGHBOR_CONTEXT}`. If
stdout is empty, omit the neighbor-context block entirely. The sub-agent must
not translate neighboring excerpts or copy them into the output; they are only
for pronoun, gender, and entity-resolution context.

**Each sub-agent's task**:
1. Read the source chunk file (e.g. `chunk0001.md`)
2. Translate the content following the translation rules below
3. Write the translated content to `output_chunk0001.md`
4. Write observations to `output_chunk0001.meta.json` matching the schema below. **Non-blocking** — leave fields empty if unsure; do not invent entities. Always emit the file (even if all arrays are empty), because its presence + content hash is how the main agent tracks whether feedback was already merged.

**Sub-agent meta schema** (`output_chunk<NNNN>.meta.json`):

```json
{
  "schema_version": 1,
  "new_entities": [
    {"source": "Taig", "target_proposal": "泰格", "category": "person",
     "evidence": "<≤200-char quote from the chunk>"}
  ],
  "alias_hypotheses": [
    {"variant": "Taig", "may_be_alias_of_source": "Tai",
     "evidence": "<≤200-char quote>"}
  ],
  "attribute_hypotheses": [
    {"entity_source": "Tai", "attribute": "gender", "value": "male",
     "confidence": "high", "evidence": "<≤200-char quote>"}
  ],
  "used_term_sources": ["Tai", "Manhattan"],
  "conflicts": [
    {"entity_source": "Tai", "field": "target", "injected": "泰",
     "observed_better": "太一", "evidence": "<≤200-char quote>"}
  ]
}
```

**Do NOT include a `chunk_id` field** — chunk identity is derived from the filename. Putting it in the payload creates a hallucination hole and validation will reject the file.

The meta file is read by the main agent later and merged into `glossary.json` (see `merge_meta.py`). Sub-agents should fill the schema honestly: cite real quotes from the chunk, never invent entities to "look productive". An empty meta is a perfectly valid output.

**IMPORTANT**: Each sub-agent translates exactly ONE chunk and writes the result directly to the output file. No START/END markers needed.

#### Translation Prompt for Sub-Agents

Include this translation prompt in each sub-agent's instructions. Replace `{TARGET_LANGUAGE}` with the actual language name (e.g. "Hebrew", "Chinese"). Sections marked *(conditional)* are included only when their condition holds; otherwise omit the whole section, including its heading — never leave an empty section or a dangling placeholder.

---

You are an expert literary translator. Translate the Markdown file below into {TARGET_LANGUAGE} for readers who will read it as a book in their own language.

## Translation

- Be faithful to meaning, tone, voice, register, rhythm, and stylistic effect. Fidelity means preserving what the text does to its reader, not its surface structure.
- Write natural, idiomatic {TARGET_LANGUAGE}. Do not carry over source syntax, word order, idioms, or collocations when that produces calque or translationese; use the equivalent {TARGET_LANGUAGE} means instead.
- Match the source's level of style. If the prose is plain, terse, rough, or deliberately awkward, keep it that way — do not polish it into something more elegant or lyrical than the author wrote. If it is dense or ornate, do not simplify it.
- Keep the rhythm where {TARGET_LANGUAGE} allows: long sentences stay long, fragments stay fragments, and paragraph breaks stay where they are.
- Dialogue must sound like people speaking {TARGET_LANGUAGE}. Each character keeps their own voice (age, background, formality, verbal habits), and the narrator's voice stays distinct from the characters'.
- Preserve ambiguity, irony, subtext, and wordplay. When a pun or allusion cannot carry over directly, recreate its effect in {TARGET_LANGUAGE} rather than explaining it. Never add translator's notes.
- Translate everything, in order. Do not skip, summarize, merge, or add sentences; the translation should be proportionate in length to the source.
- Output only the translated text — no preamble, commentary, or notes.

## Format

- Keep all Markdown structure intact: headings, emphasis, lists, blockquotes, links, footnote markers, horizontal rules, and the blank lines between paragraphs.
- Keep existing heading levels. Add a heading mark only to text that is clearly a chapter or section title (e.g. "Chapter Three", a numbered part title). Never turn short prose lines, dialogue, epigraphs, or letter salutations into headings.
- Math (`$...$`, `$$...$$`): copy the LaTeX exactly. Tables (Markdown `| ... |` or HTML `<table>`): keep the row and column structure and translate only the cell text. Code blocks: leave unchanged.
- Images: keep every `![alt](path)` reference. You may translate the alt text, but never change the path — e.g. `![Figure 1: Data Flow](media/image-001.png)` → `![<translated alt>](media/image-001.png)`.
- Raw HTML tags: translate only visible-text attributes (`alt`, `title`), never `src` or `href`. Inside those attribute values, `"`, `'`, `<`, `>` and `&` break the HTML — replace them with the target language's typographic equivalents or with `&quot;`, `&#39;`, `&lt;`, `&gt;`, `&amp;`. This applies only inside raw HTML attribute values, not to ordinary text, code, or URLs.
- Remove empty links and stray conversion artifacts such as a trailing `\` at the end of a line. Page numbers were already removed upstream: do not delete standalone number lines, which may be years, chapter numbers, or citation numbers.

## Terminology *(conditional: only when the term table is non-empty)*

These translations are required. Columns: 原文 = source term, 别名 = aliases and variant spellings, 译文 = required translation. Whenever the source term or any of its aliases appears, use the 译文 form (inflected as {TARGET_LANGUAGE} grammar requires) and do not vary it.

{TERM_TABLE}

## Hebrew conventions *(conditional: only when {TARGET_LANGUAGE} is Hebrew)*

- Narration: contemporary literary Hebrew. Dialogue: natural spoken Hebrew suited to each character — do not raise casual speech to a formal or archaic register unless the source character speaks that way.
- No niqqud, except where a word would otherwise be genuinely ambiguous, or the source is verse or written for young children.
- Hebrew marks gender on verbs, adjectives, and second-person forms. Determine each person's gender from the text, the term table, and the neighbor context. When an addressee's gender truly cannot be determined, choose the reading most consistent with context and keep it consistent. Report any gender you determine for a named character in the meta file's `attribute_hypotheses`.
- Mark dialogue with quotation marks as Hebrew books do, not with the source's single quotes or dashes — unless unusual dialogue punctuation is a deliberate stylistic choice of the author. Use geresh and gershayim in acronyms and transliterations (e.g. צה״ל), and use ״ rather than an ASCII `"` inside raw HTML attribute values.
- Transliterate names that are not in the term table using standard Hebrew transliteration conventions, and keep each one consistent throughout the chunk.
- Leave numerals, URLs, and names conventionally kept in Latin script as they are. Do not insert Unicode direction marks.

## Torah-scholarship register *(conditional: only when {TARGET_LANGUAGE} is Hebrew and the user asks for a Torah-scholarly register)*

The translation should combine three qualities. When they conflict, meaning wins over register, and register wins over flow.

- **Literal in meaning.** Render the author's argument, claims, qualifications, and technical terms exactly. Do not paraphrase, soften, or sharpen interpretive statements, and do not add explanations.
- **Torah-scholarly in wording.** Write as a Hebrew-writing talmid hakham or scholar of Hasidism would, not as a calque of English academic prose. Prefer established concepts and expressions (e.g. ספרות חז"ל or הספרות התורנית rather than "הטקסטים הרבניים"; עבודה שבלב; לימוד תורה; דרך חדשה), the customary forms of names and honorifics the source uses (ר', הקב"ה), and rabbinic Hebrew or Aramaic phrasing where it is natural and clear.
- **Literary in flow.** Natural Hebrew word order, varied sentence rhythm, and cohesive transitions. Avoid English constructions such as "במונחים של", "באופן ש…", "מה שמעניין הוא", stacked "כאשר" clauses, and passive "נעשה על ידי".
- **Quotations translated from English.** When the source quotes a Hasidic or rabbinic work in English translation, write the Hebrew in the style of that literature (e.g. "אמר", "והנה", "דהיינו", "כי"), not in modern Hebrew, while keeping the English meaning exactly. Biblical, Talmudic, and liturgical quotations keep their original wording.

## Custom instructions *(conditional: only when the user gave any)*

These take precedence over the rules above where they conflict.

{CUSTOM_INSTRUCTIONS}

## Neighbor context *(conditional: only when non-empty)*

Read-only: do not translate it or copy it into your output. Use it only to resolve pronouns, gender, speaker identity, and sentences that continue across the chunk boundary, and to keep the tone continuous.

{NEIGHBOR_CONTEXT}

## Source text

The full contents of your assigned chunk file follow.

---

### 4.5. Merge Sub-Agent Meta Into Glossary (after each batch)

Each sub-agent emitted an `output_chunk<NNNN>.meta.json` alongside its translated chunk. After every batch completes, first record the completed chunk outputs in `run_state.json` while the glossary is still the one used for that batch, then merge observations into the canonical glossary so subsequent batches see an enriched glossary.

1. Record successfully translated chunks from this batch before mutating the glossary:

   ```bash
   python3 {baseDir}/scripts/run_state.py record "<temp_dir>" chunk0001 chunk0002 ...
   ```

   If this fails, fix the missing/empty output or state error before continuing.

2. Run prepare-merge:

   ```bash
   python3 {baseDir}/scripts/merge_meta.py prepare-merge "<temp_dir>"
   ```

   Capture stdout JSON. It contains four arrays:
   - `auto_apply` — new entities with no glossary collision and unanimous (target, category) across all proposing chunks.
   - `decisions_needed` — items requiring main-agent judgment. Each has `id`, `kind`, an `options` array, and the data needed to pick. Kinds:
     - `alias` — `{variant, candidate_source, evidence}`. Choices: `yes_alias` / `no_separate_entity` / `skip`.
     - `conflict` — `{entity_source, field, current, proposed, evidence}`. Choices: `keep_current` / `accept_proposed` / `record_in_notes`.
     - `new_entity_existing_alias` — sub-agents propose `proposed_source` as a new entity, but it's already someone's alias. `{proposed_source, currently_alias_of, promoted_variants: [{target_proposal, category, evidence, evidence_chunks}, ...]}`. Choices: one `use_variant_N` per distinct (target, category) promotion variant (promote `proposed_source` to standalone with that target+category, removing it from the host's aliases) / `keep_as_alias` / `skip`.
     - `existing_entity_conflict` — sub-agents proposed a (target, category) for `entity_source` that differs from the canonical. Multiple distinct differing proposals all get exposed. `{entity_source, current_target, current_category, proposed_variants: [{target_proposal, category, evidence, evidence_chunks}, ...]}`. Choices: `keep_current` / one `use_variant_N` per competing proposal (overwrites both target AND category, stamps the prior values into notes) / `record_in_notes` (canonical unchanged; every proposed variant gets logged to notes).
     - `alias_or_new_entity` — `variant` has multiple competing options that can't all coexist under v2's surface-form uniqueness rule. Triggered when (a) `variant` was proposed both as a new standalone entity AND as an alias of one or more candidates, OR (b) `variant` was proposed as an alias of two or more different candidates with no standalone competitor. `{variant, alias_candidates: [{candidate_source, evidence, evidence_chunks}, ...], standalone_variants: [{target_proposal, category, evidence, evidence_chunks}, ...]}`. Choices: one `use_alias_N` per candidate (attach as alias of that candidate), one `use_standalone_N` per competing standalone proposal (add as standalone with that target+category), or `skip`.
     - `conflicting_new_entity_proposals` — `{source, variants: [{target_proposal, category, evidence, evidence_chunks}, ...]}`. Choices: `use_variant_0`, `use_variant_1`, ..., `skip`.
   - `consumed_chunk_ids` — every meta file scanned this round (regardless of whether it produced a finding). These hashes get recorded in `applied_meta_hashes` on apply.
   - `malformed_meta_chunk_ids` — meta files that failed validation. Quarantined: not consumed, not crashing the run. Surface them in your batch progress.

3. **If `consumed_chunk_ids` is empty** → nothing was scanned; skip to Step 5.

4. **If `consumed_chunk_ids` is non-empty but both `auto_apply` and `decisions_needed` are empty** → still pipe `{"auto_apply": [], "decisions": [], "consumed_chunk_ids": [...]}` into `apply-merge` so the hashes get recorded. **Skipping this is the bug** — no-op metas would re-scan forever otherwise.

5. **Otherwise, resolve each decision**:
   - Read its evidence quotes inline.
   - Pick one option from its `options` array.
   - Build a `decisions` entry that round-trips the original decision plus your choice. The entry MUST include the original `kind` and (for `conflicting_new_entity_proposals`) the `variants` array, so apply-merge can validate and act:

     ```json
     {"id": "d1", "kind": "alias", "variant": "Taig", "candidate_source": "Tai", "choice": "yes_alias"}
     ```

6. Pipe the decisions JSON into apply-merge:

   ```bash
   echo '{"auto_apply": [...], "decisions": [...], "consumed_chunk_ids": [...]}' \
     | python3 {baseDir}/scripts/merge_meta.py apply-merge "<temp_dir>"
   ```

   Surface the summary JSON (`auto_applied`, `decisions_resolved`, `consumed_chunks`, `errors`) in your batch progress message.

   **apply-merge is transactional.** If any decision is malformed (wrong choice for kind, missing fields, references a non-existent entity), the entire batch aborts with a non-zero exit and stderr details — no glossary mutation, no hashes recorded. On non-zero exit, fix the offending decision and re-pipe; `prepare-merge` will surface the same proposals because nothing was consumed.

   **Decision order in the input list is not significant.** `apply-merge` internally dispatches entity-creating decisions before alias-attaching ones, so `yes_alias` decisions whose candidate is created by another decision in the same batch (a `use_standalone_N`, `use_variant_N`, or `promote_to_separate_entity`) succeed regardless of the order you pass them in. Alias chains (e.g. `Taighi → Taig` where `Taig → Tai` is also a pending alias decision) resolve via a fixed-point loop within the alias-attacher pass — you don't need to topo-sort or sequence chained aliases manually.

On a fresh run after a previous interrupted batch, `prepare-merge` will pick up any meta files left behind. Don't manually delete them.

### 5. Verify Completeness and Retry

After all batches complete, use Glob to check that every source chunk has a corresponding output file.

If any are missing, retry them — each missing chunk as its own sub-agent. Maximum 2 attempts per chunk (initial + 1 retry).

Also read `manifest.json` and verify:
- Every chunk id has a corresponding output file
- No output file is empty (0 bytes) or blank (whitespace-only)

Then run the meta-merge observability snapshot:

```bash
python3 {baseDir}/scripts/merge_meta.py status "<temp_dir>"
```

Also run the selective re-translation state snapshot:

```bash
python3 {baseDir}/scripts/run_state.py status "<temp_dir>"
```

Surface a one-line summary in the verification report:

> Translated chunks: 50 • Meta files: 48 found / 47 consumed • Malformed: 1 (chunk0099 — see stderr) • Chunks missing meta: chunk0017, chunk0042

Severity rules (none of these fail the run — meta is non-blocking):

- `unmerged_meta_files > 0` after Step 4.5 ran → bug, flag prominently. Resume should have caught this.
- `malformed_meta_files > 0` → sub-agent emitted invalid meta; print chunk_ids and a "fix the file by hand and re-run if you want this chunk's feedback merged" note.
- `meta_files_found < translated_chunks` → sub-agent-compliance issue (some chunks didn't emit meta at all). Print missing chunk_ids.

Report any chunks that failed translation after retry.

### 6. Translate Book Title

Read `config.txt` from the temp directory to get the `original_title` field.
If it is missing (e.g. Markdown input with neither front matter nor a leading
`#` title), use the source file name instead.

Translate the title to the target language. For Chinese, wrap in 书名号: `《translated_title》`.

### 7. Post-process — Merge and Build

Run the build script with the translated title:

```bash
python3 {baseDir}/scripts/merge_and_build.py --temp-dir "<temp_dir>" --title "<translated_title>" --cleanup
```

If the user provided `epub_cover`, add `--cover "<epub_cover>"`. If the user
provided `export_name`, add `--export-name "<export_name>"`.

The `--cleanup` flag removes intermediate files (chunks, input.html, etc.) after a fully successful build. If the user asked to keep intermediates, omit `--cleanup`.

The script reads `output_lang` from `config.txt` automatically. Optional overrides: `--lang`, `--author`.

This produces in the temp directory:
- `output.md` — merged translated markdown
- `book.html` — web version with floating TOC
- `book_doc.html` — ebook version
- `book.docx`, `book.epub`, `book.pdf` — format conversions (requires Calibre)

### 8. Report Results

Tell the user:
- Where the output files are located
- How many chunks were translated
- The translated title
- List generated output files with sizes
- Any format generation failures
