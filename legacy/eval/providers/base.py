"""Shared behaviour: HTTP with backoff, on-disk cache, failed-output capture.

API keys are read from the environment inside each adapter, sent only as request
headers, and never written to the cache, the logs or any output file.
"""
import hashlib
import os
import json
import random
import re
import time
import urllib.error
import urllib.request

from ..config import EVAL

MAX_OUTPUT = 1500
RETRYABLE = {408, 429, 500, 502, 503, 504, 529}


class ProviderError(Exception):
    pass


class MalformedJSON(ProviderError):
    def __init__(self, raw):
        super().__init__("malformed JSON")
        self.raw = raw


def http_json(url, headers, body=None, method=None, retries=None, timeout=300):
    retries = int(os.environ.get("EVAL_RETRIES", "8")) if retries is None else retries
    data = json.dumps(body).encode("utf-8") if body is not None else None
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, data=data, method=method or ("POST" if data else "GET"),
                                     headers={"Content-Type": "application/json", **headers})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:500]
            if e.code in RETRYABLE and attempt < retries:
                time.sleep(min(90, 3 * 2 ** attempt + random.random() * 3))
                continue
            raise ProviderError(f"HTTP {e.code}: {detail}") from None
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt < retries:
                time.sleep(min(60, 2 ** attempt + random.random()))
                continue
            raise ProviderError(f"network: {e}") from None


def parse_json(text):
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t)
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", t, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
    raise MalformedJSON(text)


def cache_key(provider, model, system, user):
    return hashlib.sha256((provider + "\x00" + model + "\x00" + system + "\x00" + user).encode("utf-8")).hexdigest()


def cached_call(provider, model, system, user, call):
    """call() -> (parsed dict, usage dict). Cached by sha256(provider+model+system+user)."""
    d = EVAL / "cache"
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"{cache_key(provider, model, system, user)}.json"
    if f.exists():
        out = json.loads(f.read_text(encoding="utf-8"))
        out["cached"] = True
        return out
    try:
        parsed, usage = call()
    except MalformedJSON:
        parsed, usage = call()          # retry a malformed response once; a second MalformedJSON propagates
    out = {"provider": provider, "model": model, "response": parsed, "usage": usage}
    f.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    out["cached"] = False
    return out


def save_failed(provider, rid, raw):
    d = EVAL / "failed"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{rid}.{provider}.txt").write_text(raw if isinstance(raw, str) else repr(raw), encoding="utf-8")


def version_key(name):
    """'gemini-3.1-pro' → (3, 1); 'gpt-5.2' → (5, 2). Unknown → ()."""
    m = re.search(r"(\d+(?:\.\d+)*)", name)
    return tuple(int(x) for x in m.group(1).split(".")) if m else ()
