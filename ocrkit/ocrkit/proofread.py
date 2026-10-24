"""
Proofread OCR page records with the Claude API (<dir>/ocr.jsonl -> <dir>/proof.jsonl).

Every response is checked before it is accepted (checks.py). A page that
fails is retried with the reason as feedback; if it still fails, the OCR text
is kept, status "kept_ocr", so a bad response never silently replaces real
text. Every accepted page records what changed, word by word.

Runs are resumable: pages already in proof.jsonl are skipped unless asked for.
"""

import base64
import io
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from . import checks, records as rec, report, textfmt as tf
from .diff import word_changes
from .prompts import system_prompt, user_message

DEFAULT_MODEL = "claude-sonnet-5"
MAX_ATTEMPTS = 3          # model attempts per page (bad responses)
MAX_TRANSPORT = 8         # network/rate-limit retries per attempt (do not use up attempts)
MAX_TOKENS = 16000
CHANGE_FLAG = 0.15        # pages changing more than this share of words are flagged
BATCH_POLL = 60           # seconds between batch status checks

# USD per 1M tokens (input, output). Check against current Anthropic pricing;
# an unknown model prints a warning instead of a wrong cost.
PRICING = {
    "claude-sonnet-5": (2.00, 10.00),
    "claude-opus-5": (5.00, 25.00),
    "claude-haiku-4-5": (1.00, 5.00),
}
MEDIA = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
         ".gif": "image/gif", ".webp": "image/webp"}


class FatalAPIError(Exception):
    """An error that will fail for every page (billing, auth): stop the run."""


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --------------------------------------------------------------------------
# Requests
# --------------------------------------------------------------------------

def image_block(path):
    path = Path(path)
    media = MEDIA.get(path.suffix.lower())
    if media:
        data = path.read_bytes()
    else:   # .tif and others: convert to PNG
        from PIL import Image
        buf = io.BytesIO()
        Image.open(path).convert("RGB").save(buf, "PNG")
        data, media = buf.getvalue(), "image/png"
    return {"type": "image", "source": {"type": "base64", "media_type": media,
                                        "data": base64.b64encode(data).decode()}}


def page_language(ocr_rec, language):
    if language != "auto":
        return language
    return "hebrew" if "heb" in (ocr_rec.get("lang") or "") or ocr_rec.get("script") == "Hebrew" else "english"


def page_image(ocr_rec, out_dir, vision):
    if vision == "off" or not ocr_rec.get("image"):
        return None
    p = Path(out_dir) / ocr_rec["image"]
    return p if p.exists() else None


def build_params(ocr_rec, out_dir, language, model, effort, vision, feedback=""):
    img = page_image(ocr_rec, out_dir, vision)
    text = user_message(ocr_rec["text"], ocr_rec.get("low_conf"), feedback)
    content = [image_block(img), {"type": "text", "text": text}] if img else text
    params = {
        "model": model,
        "max_tokens": MAX_TOKENS,
        "system": system_prompt(page_language(ocr_rec, language), img is not None),
        "messages": [{"role": "user", "content": content}],
    }
    if effort:
        params["output_config"] = {"effort": effort}
    return params, img is not None


def call(client, params, page):
    """One model call with network retries. Returns the response, or None on a non-retryable error."""
    import anthropic
    body = {k: v for k, v in params.items() if k != "output_config"}
    extra = {"extra_body": {"output_config": params["output_config"]}} if "output_config" in params else {}
    for t in range(1, MAX_TRANSPORT + 1):
        try:
            return client.messages.create(**body, **extra)
        except anthropic.RateLimitError as e:
            try:
                wait = float(e.response.headers.get("retry-after", "30"))
            except (TypeError, ValueError):
                wait = 30
            print(f"  ⚠ page {page}: rate limited, waiting {wait:.0f}s")
            time.sleep(wait)
        except anthropic.APIStatusError as e:
            if e.status_code in (401, 402, 403) or "credit balance" in str(e.message).lower():
                raise FatalAPIError(f"{e.status_code}: {e.message}") from e
            if e.status_code >= 500 or e.status_code == 529:
                print(f"  ⚠ page {page}: server error {e.status_code}, retrying")
                time.sleep(min(5 * t, 60))
                continue
            print(f"  ✗ page {page}: API error {e.status_code}: {e.message}")
            return None
        except anthropic.APIConnectionError as e:
            print(f"  ⚠ page {page}: connection error ({e}), retrying")
            time.sleep(min(5 * t, 60))
    print(f"  ✗ page {page}: gave up after {MAX_TRANSPORT} network retries")
    return None


def add_usage(total, u, batch=False):
    total["input"] += u.input_tokens
    total["output"] += u.output_tokens
    total["cache_read"] += getattr(u, "cache_read_input_tokens", 0) or 0
    total["cache_write"] += getattr(u, "cache_creation_input_tokens", 0) or 0
    total["batched"] = total.get("batched", False) or batch


def new_usage():
    return {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}


_warned = set()


def cost_usd(model, usage):
    """Cost in USD, or None for a model not in PRICING."""
    if model not in PRICING:
        if model not in _warned:
            print(f"  ⚠ no price for model {model!r} - add it to PRICING to see costs")
            _warned.add(model)
        return None
    i, o = PRICING[model]
    c = (usage["input"] * i + usage["cache_read"] * i * 0.10
         + usage["cache_write"] * i * 1.25 + usage["output"] * o) / 1_000_000
    return c * 0.5 if usage.get("batched") else c


def fmt_cost(c):
    return "unknown" if c is None else f"${c:.3f}"


# --------------------------------------------------------------------------
# Records
# --------------------------------------------------------------------------

def ok_record(ocr_rec, chk, model, mode, language, attempts, usage, change_flag):
    rate, changes = word_changes(ocr_rec["text"], chk["text"])
    warnings = list(chk["warnings"])
    if rate > change_flag and len(ocr_rec["text"].split()) >= 40:
        warnings.append(f"high change rate: {rate:.0%} of words changed")
    return {
        "page": ocr_rec["page"], "status": "ok", "text": chk["text"],
        "printed_page": chk["printed"], "model": model, "mode": mode, "language": language,
        "attempts": attempts, "warnings": warnings,
        "doubtful": tf.doubtful(chk["text"]), "change_rate": rate, "changes": changes,
        "usage": usage, "at": now(),
    }


def kept_record(ocr_rec, reason, model, mode, language, attempts, usage):
    return {
        "page": ocr_rec["page"], "status": "kept_ocr", "text": ocr_rec["text"],
        "printed_page": None, "model": model, "mode": mode, "language": language,
        "attempts": attempts, "reason": reason, "warnings": [f"not proofread: {reason}"],
        "doubtful": [], "change_rate": 0.0, "changes": [], "usage": usage, "at": now(),
    }


def response_text(msg):
    return "".join(b.text for b in msg.content if b.type == "text").strip()


# --------------------------------------------------------------------------
# One page, synchronously
# --------------------------------------------------------------------------

def proofread_page(client, ocr_rec, out_dir, language="auto", model=DEFAULT_MODEL, effort=None,
                   vision="auto", change_flag=CHANGE_FLAG, feedback="", attempts_used=0, usage=None):
    """Returns the page's proof record (status ok or kept_ocr)."""
    n = ocr_rec["page"]
    lang = page_language(ocr_rec, language)
    usage = usage or new_usage()
    mode, reason, attempt = "text", "no response", attempts_used
    while attempt < MAX_ATTEMPTS:
        attempt += 1
        params, is_vision = build_params(ocr_rec, out_dir, language, model, effort, vision, feedback)
        mode = "vision" if is_vision else "text"
        resp = call(client, params, n)
        if resp is None:
            reason = "API error"
            break
        add_usage(usage, resp.usage)
        chk = checks.check_page(ocr_rec["text"], response_text(resp), resp.stop_reason, vision=is_vision)
        if chk["ok"]:
            return ok_record(ocr_rec, chk, model, mode, lang, attempt, usage, change_flag)
        reason = feedback = chk["reason"]
        print(f"  ⚠ page {n}: attempt {attempt}/{MAX_ATTEMPTS} rejected - {reason}")
    print(f"  ✗ page {n}: keeping the OCR text")
    return kept_record(ocr_rec, reason, model, mode, lang, attempt, usage)


# --------------------------------------------------------------------------
# Many pages through the Message Batches API (half price, results within 24 h)
# --------------------------------------------------------------------------

def run_batch(client, todo, ocr, out_dir, language, model, effort, vision, change_flag, proof_path):
    """
    Submit all pages as one batch, wait, record the pages that pass, and
    return [(page, feedback, attempts_used)] to retry one by one.
    The batch id is saved, so an interrupted run picks up the same batch.
    """
    state_path = Path(out_dir) / "proof-batch.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else None
    modes = {}
    if state and state.get("model") == model:
        batch_id = state["batch_id"]
        print(f"✓ Resuming batch {batch_id} ({len(state['pages'])} pages)")
        for n in state["pages"]:
            modes[n] = build_params(ocr[n], out_dir, language, model, effort, vision)[1]
    else:
        requests = []
        for n in todo:
            params, modes[n] = build_params(ocr[n], out_dir, language, model, effort, vision)
            requests.append({"custom_id": f"page-{n}", "params": params})
        batch = client.messages.batches.create(requests=requests)
        batch_id = batch.id
        state_path.write_text(json.dumps({"batch_id": batch_id, "model": model,
                                          "pages": list(todo), "created": now()}, indent=2))
        print(f"✓ Submitted batch {batch_id} with {len(requests)} pages")

    while True:
        b = client.messages.batches.retrieve(batch_id)
        if b.processing_status == "ended":
            break
        c = b.request_counts
        print(f"  batch {batch_id}: {c.succeeded} done, {c.processing} processing - "
              f"checking again in {BATCH_POLL}s")
        time.sleep(BATCH_POLL)

    retry, total = [], new_usage()
    for result in client.messages.batches.results(batch_id):
        n = int(result.custom_id.split("-", 1)[1])
        outcome = result.result
        if outcome.type != "succeeded":
            retry.append((n, "", 0))
            print(f"  ⚠ page {n}: batch request {outcome.type}, will retry")
            continue
        msg = outcome.message
        usage = new_usage()
        add_usage(usage, msg.usage, batch=True)
        add_usage(total, msg.usage, batch=True)
        chk = checks.check_page(ocr[n]["text"], response_text(msg), msg.stop_reason, vision=modes.get(n, False))
        if chk["ok"]:
            rec.append_record(proof_path, ok_record(ocr[n], chk, model, "vision" if modes.get(n) else "text",
                                                    page_language(ocr[n], language), 1, usage, change_flag))
        else:
            print(f"  ⚠ page {n}: batch response rejected - {chk['reason']}")
            retry.append((n, chk["reason"], 1))
    state_path.unlink()
    print(f"✓ Batch finished: {len(todo) - len(retry)} pages accepted, {len(retry)} to retry one by one. "
          f"Batch cost {fmt_cost(cost_usd(model, total))}")
    return retry, total


# --------------------------------------------------------------------------
# Run
# --------------------------------------------------------------------------

def parse_pages(s):
    """'1,7-9,31' -> {1, 7, 8, 9, 31}"""
    out = set()
    for part in s.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-")
            out.update(range(int(a), int(b) + 1))
        elif part:
            out.add(int(part))
    return out


def finish(out_dir, proof_path, ocr, change_flag):
    proof = rec.compact(proof_path) if proof_path.exists() else {}
    pages = {n: (proof[n]["text"] if n in proof else ocr[n]["text"]) for n in ocr}
    printed = {n: proof[n].get("printed_page") for n in proof}
    (out_dir / "proof.txt").write_text(rec.render_pages(pages, printed), encoding="utf-8")
    path = report.write_report(out_dir, ocr, proof, cost_usd)
    return proof, path


def run(out_dir, language="auto", model=DEFAULT_MODEL, effort="low", vision="auto",
        repair=False, pages=None, redo_all=False, batch=False, change_flag=CHANGE_FLAG, client=None):
    out_dir = Path(out_dir)
    ocr_path, proof_path = out_dir / "ocr.jsonl", out_dir / "proof.jsonl"
    if not ocr_path.exists():
        sys.exit(f"{ocr_path} not found - run the OCR step first (or import-txt)")
    ocr = rec.latest_by_page(rec.load_records(ocr_path))
    proof = rec.latest_by_page(rec.load_records(proof_path))

    print("=" * 70 + "\nOCR proofreading with the Claude API\n" + "=" * 70)
    print(f"\nFolder:   {out_dir}/\nModel:    {model}" + (f"  (effort={effort})" if effort else ""))
    print(f"Language: {language}   vision: {vision}   batch: {'yes' if batch else 'no'}")

    if pages:
        todo = sorted(pages & set(ocr))
    elif redo_all:
        todo = sorted(ocr)
    elif repair:
        todo = sorted(n for n in ocr if n not in proof or proof[n]["status"] != "ok")
    else:
        todo = sorted(n for n in ocr if n not in proof)
        if proof:
            print(f"✓ {len(proof)} pages already proofread - continuing with the rest")
    if not todo:
        print("\nNothing to do.")
        finish(out_dir, proof_path, ocr, change_flag)
        return

    if client is None:
        if not os.getenv("ANTHROPIC_API_KEY"):
            sys.exit("ANTHROPIC_API_KEY not set - add it to .env")
        import anthropic
        client = anthropic.Anthropic()

    print(f"\nProofreading {len(todo)} pages...\n")
    total, start = new_usage(), time.time()
    try:
        queue = [(n, "", 0) for n in todo]
        if batch:
            queue, btotal = run_batch(client, todo, ocr, out_dir, language, model, effort,
                                      vision, change_flag, proof_path)
            for k in ("input", "output", "cache_read", "cache_write"):
                total[k] += btotal[k]
        seq_usage = new_usage()
        for i, (n, feedback, used) in enumerate(queue, 1):
            usage = new_usage()
            r = proofread_page(client, ocr[n], out_dir, language, model, effort, vision,
                               change_flag, feedback, used, usage)
            rec.append_record(proof_path, r)
            for k in ("input", "output", "cache_read", "cache_write"):
                seq_usage[k] += usage[k]
            if i % 5 == 0 or i == len(queue):
                eta = (len(queue) - i) * (time.time() - start) / i
                print(f"  Page {i}/{len(queue)} - ETA {eta / 60:.1f} min - "
                      f"cost so far {fmt_cost(cost_usd(model, seq_usage))}")
    except FatalAPIError as e:
        proof, path = finish(out_dir, proof_path, ocr, change_flag)
        left = len([n for n in todo if n not in proof])
        print(f"\n✗ Stopping: {e}\n  {left} page(s) not proofread yet. "
              "Fix the account issue and run again - finished pages are kept.")
        sys.exit(1)

    proof, path = finish(out_dir, proof_path, ocr, change_flag)
    done = [proof[n] for n in todo if n in proof]
    kept = [r["page"] for r in done if r["status"] != "ok"]
    flagged = [r["page"] for r in done if r["warnings"]]
    seq_cost = cost_usd(model, seq_usage)
    batch_cost = cost_usd(model, {**total, "batched": True}) if batch else 0
    cost = None if seq_cost is None or batch_cost is None else seq_cost + batch_cost
    print("\n" + "=" * 70)
    print("✓ PROOFREADING COMPLETE" if not kept else "⚠ PROOFREADING COMPLETE WITH PAGES KEPT AS OCR")
    print("=" * 70)
    print(f"Pages: {len(done)}   time: {(time.time() - start) / 60:.1f} min   cost: {fmt_cost(cost)}")
    if kept:
        print(f"⚠ OCR text kept (not proofread): {kept} - run again with --repair")
    print(f"Pages to review: {len(flagged)} - see {path}")
    print(f"Text: {out_dir / 'proof.txt'}\nRecords: {proof_path}")
    print("=" * 70)
