# Evaluation passes (Gemini, GPT, optional DictaLM)

These passes read the translation and never change it. Each evaluator reports findings; none of them rewrites the text.

```
# offline, free: alignment, a sample prompt (eval/aligned/<ch>-sample-prompt.txt), cost estimate
.venv/bin/python -m eval.run --chapter ch02 --dry-run --limit 20

# pilot: 20 paragraphs, both providers (keys come from .env), then read the report
.venv/bin/python -m eval.run --chapter ch02 --providers gemini,openai --limit 20

# rebuild the review page with an Evaluators column and a "⚑ needs a look" filter
python3 tools/build_review.py ch02-holy-rebellion_temp review/ch02 "The Holy Rebellion — chapter 2"
```

Chapters: `ch01` … `ch06`. Verified original sources and headings are skipped. The notes are skipped unless you pass `--include-notes`.

| Variable | Purpose |
|---|---|
| `GEMINI_API_KEY`, `OPENAI_API_KEY` | API keys (read from `.env`; sent only as request headers, never logged or cached) |
| `EVAL_GEMINI_MODEL`, `EVAL_OPENAI_MODEL` | Pin a model. Otherwise the newest Pro / flagship listed by the API is used, and its name goes into every result |
| `EVAL_COST_CAP_USD` | Asks for confirmation above this estimate (default 10). `--yes` skips the question |
| `EVAL_GEMINI_THINKING_TOKENS`, `EVAL_OPENAI_REASONING_TOKENS` | Extra output allowance for models that think before answering (defaults 2048 / 4000) |
| `EVAL_DICTA_MODEL`, `EVAL_DICTA_BACKEND` (`ollama` / `hf`), `EVAL_DICTA_URL`, `HF_TOKEN` | For `--with-dicta` |

Outputs:
- `results/<ch>/` holds one file per paragraph and provider.
- `report/<ch>.html`, `.csv` and `-summary.md` are the reports.
- `findings/<ch>.json` is read by the review page.
- `cache/` means re-runs are free.
- `failed/` holds malformed responses.

Prices in `pricing.json` are placeholders. Check them before a full run.

Tests: `.venv/bin/python -m pytest -q -p no:cacheprovider tests/`

Terms:
- `tools/merge_decided_terms.py` merged `decided-terms.md` into the glossary (already done).
- `tools/conform_terms.py` reports what it would change in the translation. `--apply` makes the changes, with backups.
