"""Step 4 — runner.

    python -m eval.run --chapter ch02 --providers gemini,openai [--with-dicta] [--limit 20] [--yes]
    python -m eval.run --chapter ch02 --dry-run        # offline: alignment, prompt sample and estimate, no API calls

Evaluates paragraphs of kind prose/quote (and note with --include-notes); verified
source quotations and headings are skipped. Results: eval/results/<chapter>/<id>.<provider>.json.
"""
import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from . import align, prompts
from .config import CHAPTERS, EVAL, env, load_dotenv
from .providers import PROVIDERS
from .providers.base import MalformedJSON, ProviderError, save_failed

OUT_TOKENS_EST = {"gemini": 600 + 2048, "openai": 600 + 2000, "dicta": 400}


def est_tokens(text):
    heb = sum(1 for c in text if "֐" <= c <= "׿")
    return int(heb / 2.2 + (len(text) - heb) / 3.8)


def price(model_name, provider):
    table = json.loads((EVAL / "pricing.json").read_text(encoding="utf-8"))
    name = model_name or {"gemini": "gemini", "openai": "gpt", "dicta": "dicta"}[provider]
    keys = [k for k in table if not k.startswith("_") and name.startswith(k)]
    return table[max(keys, key=len)] if keys else table.get(provider, {"input": 0, "output": 0})


def estimate(jobs, models):
    total, lines = 0.0, []
    for prov, recs in jobs.items():
        tin = sum(est_tokens(system) + est_tokens(u) for _, system, u in recs)
        tout = OUT_TOKENS_EST[prov] * len(recs)
        p = price(models.get(prov), prov)
        cost = (tin * p["input"] + tout * p["output"]) / 1e6
        total += cost
        lines.append(f"  {prov:7} {models.get(prov) or '(model resolved at run time)'}: {len(recs)} calls, "
                     f"~{tin:,} in / ~{tout:,} out tokens ≈ ${cost:.2f}")
    return total, lines


def evaluate_one(mod, prov, rec, system, user, dicta):
    rid = rec["id"]
    try:
        out = mod.evaluate(system, user)
        problems = prompts.validate(out["response"], rec["he"], dicta)
        if problems:                     # re-ask once, then keep only the valid findings
            out = mod.evaluate(system, user + prompts.NO_REWRITE)
            problems = prompts.validate(out["response"], rec["he"], dicta)
            if problems:
                out["response"] = prompts.drop_invalid(out["response"], rec["he"], dicta)
                out["validation"] = problems
    except MalformedJSON as e:
        save_failed(prov, rid, e.raw)
        return rid, prov, "failed (malformed JSON)"
    except ProviderError as e:
        save_failed(prov, rid, str(e))
        return rid, prov, f"failed ({str(e)[:80]})"
    out.update(id=rid, kind=rec["kind"], chunk=rec["chunk"], para=rec["para"],
               evaluated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    d = EVAL / "results" / rec["chapter"]
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{rid}.{prov}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return rid, prov, "cached" if out.get("cached") else "ok"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--chapter", required=True, choices=sorted(CHAPTERS))
    ap.add_argument("--providers", default="gemini,openai")
    ap.add_argument("--with-dicta", action="store_true")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--include-notes", action="store_true", help="also evaluate the chapter's notes")
    ap.add_argument("--yes", action="store_true", help="skip the cost confirmation")
    ap.add_argument("--dry-run", action="store_true", help="no API calls: alignment, a sample prompt and the estimate")
    a = ap.parse_args(argv)

    records, log = align.align_chapter(a.chapter)
    align.write(a.chapter, records, log)
    kinds = {"prose", "quote"} | ({"note"} if a.include_notes else set())
    todo = [r for r in records if r["kind"] in kinds]
    skipped = {k: sum(1 for r in records if r["kind"] == k) for k in ("source-quote", "heading", "note") if k not in kinds}
    if a.limit:
        todo = todo[:a.limit]
    print(f"to evaluate: {len(todo)} paragraphs; skipped: {skipped}")

    provs = [p for p in a.providers.split(",") if p] + (["dicta"] if a.with_dicta else [])
    for p in provs:
        if p not in PROVIDERS:
            sys.exit(f"unknown provider {p}")
    glossary = prompts.load_glossary()
    system = prompts.system_prompt()
    jobs = {p: [(r, prompts.DICTA_PROMPT, r["he"]) if p == "dicta" else (r, system, prompts.user_prompt(r, glossary))
                for r in todo] for p in provs}

    if a.dry_run:
        models = {p: env({"gemini": "EVAL_GEMINI_MODEL", "openai": "EVAL_OPENAI_MODEL", "dicta": "EVAL_DICTA_MODEL"}[p]) for p in provs}
        total, lines = estimate(jobs, models)
        print("\n".join(lines) + f"\n  total ≈ ${total:.2f} (placeholder prices — verify eval/pricing.json)")
        if todo:
            sample = EVAL / "aligned" / f"{a.chapter}-sample-prompt.txt"
            sample.write_text(f"=== SYSTEM ===\n{system}\n\n=== USER ===\n{prompts.user_prompt(todo[0], glossary)}\n", encoding="utf-8")
            print(f"sample prompt → {sample}")
        print("dry run: no API calls made")
        return

    load_dotenv()
    models = {}
    for p in provs:
        try:
            models[p] = PROVIDERS[p].model()
        except ProviderError as e:
            sys.exit(f"{p}: {e}")
    print("models: " + ", ".join(f"{p} = {m}" for p, m in models.items()))
    total, lines = estimate(jobs, models)
    print("\n".join(lines) + f"\n  total ≈ ${total:.2f}")
    cap = float(env("EVAL_COST_CAP_USD", "10"))
    if total > cap and not a.yes:
        if not sys.stdin.isatty() or input(f"Estimate exceeds EVAL_COST_CAP_USD={cap}. Continue? [y/N] ").lower() != "y":
            sys.exit("stopped before any evaluation call")

    status = {}
    pools = {p: ThreadPoolExecutor(max_workers=4) for p in provs}      # at most 4 in flight per provider
    futs = [pools[p].submit(evaluate_one, PROVIDERS[p], p, r, s, u, p == "dicta") for p in provs for r, s, u in jobs[p]]
    for f in futs:
        rid, p, st = f.result()
        key = st.split(" ")[0]
        status[key] = status.get(key, 0) + 1
        if st.startswith("failed"):
            print(f"  {rid} {p}: {st}")
    for pool in pools.values():
        pool.shutdown()
    print(f"done: {status}")
    meta = {"chapter": a.chapter, "models": models, "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "evaluated": len(todo), "skipped": skipped, "unaligned": sum(1 for l in log if "UNALIGNED" in l)}
    (EVAL / "results" / a.chapter).mkdir(parents=True, exist_ok=True)
    (EVAL / "results" / a.chapter / "_run.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    from . import report
    report.main(["--chapter", a.chapter])


if __name__ == "__main__":
    main()
