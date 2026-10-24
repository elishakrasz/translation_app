"""DictaLM adapter — Hebrew naturalness only.

Backend (EVAL_DICTA_BACKEND):
  ollama (default) — local, http://localhost:11434 (EVAL_DICTA_URL), model EVAL_DICTA_MODEL
  hf               — Hugging Face router (OpenAI-compatible), token HF_TOKEN, model EVAL_DICTA_MODEL
"""
import os

from ..prompts import DICTA_SCHEMA
from .base import MAX_OUTPUT, ProviderError, cached_call, http_json, parse_json

NAME = "dicta"


def model():
    m = os.environ.get("EVAL_DICTA_MODEL")
    if not m:
        raise ProviderError("set EVAL_DICTA_MODEL (e.g. the DictaLM model name in Ollama or on Hugging Face)")
    return m


def evaluate(system, user, schema=DICTA_SCHEMA):
    m = model()
    backend = os.environ.get("EVAL_DICTA_BACKEND", "ollama")

    def call():
        msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        if backend == "hf":
            tok = os.environ.get("HF_TOKEN")
            if not tok:
                raise ProviderError("HF_TOKEN is not set")
            r = http_json("https://router.huggingface.co/v1/chat/completions", {"Authorization": f"Bearer {tok}"},
                          {"model": m, "messages": msgs, "temperature": 0, "max_tokens": MAX_OUTPUT,
                           "response_format": {"type": "json_object"}})
            u = r.get("usage", {})
            return parse_json(r["choices"][0]["message"]["content"]), {"input": u.get("prompt_tokens", 0), "output": u.get("completion_tokens", 0)}
        url = os.environ.get("EVAL_DICTA_URL", "http://localhost:11434")
        r = http_json(f"{url}/api/chat", {}, {"model": m, "messages": msgs, "stream": False, "format": schema,
                                               "options": {"temperature": 0, "num_predict": MAX_OUTPUT}})
        return parse_json(r["message"]["content"]), {"input": r.get("prompt_eval_count", 0), "output": r.get("eval_count", 0)}

    return cached_call(NAME, f"{backend}:{m}", system, user, call)
