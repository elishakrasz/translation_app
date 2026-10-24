"""Gemini Pro adapter (REST, generativelanguage.googleapis.com)."""
import os
import re

from ..prompts import SCHEMA
from .base import MAX_OUTPUT, ProviderError, cached_call, http_json, parse_json, version_key

NAME = "gemini"
API = "https://generativelanguage.googleapis.com/v1beta"
_model = None


def _headers():
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise ProviderError("GEMINI_API_KEY is not set")
    return {"x-goog-api-key": key}


def pick_model(names):
    """Newest Pro model that can generate content; stable releases before previews."""
    pro = [n.removeprefix("models/") for n in names if re.fullmatch(r"(models/)?gemini-[\d.]+-pro(-preview(-\d{2}-\d{2,4})?|-latest|-\d+)?", n)]
    if not pro:
        raise ProviderError("no Gemini Pro model listed")
    return max(pro, key=lambda n: (version_key(n), "preview" not in n, n))


def model():
    global _model
    if _model is None:
        _model = os.environ.get("EVAL_GEMINI_MODEL")
        if not _model:
            names, url = [], f"{API}/models?pageSize=1000"
            data = http_json(url, _headers())
            names = [m["name"] for m in data.get("models", []) if "generateContent" in m.get("supportedGenerationMethods", [])]
            _model = pick_model(names)
    return _model


def _to_gemini_schema(s):
    """Gemini's responseSchema is an OpenAPI subset: no additionalProperties."""
    if isinstance(s, dict):
        if s.get("type") == "integer" and "enum" in s:      # Gemini enums are string-only: use a range
            return {"type": "integer", "minimum": min(s["enum"]), "maximum": max(s["enum"])}
        return {k: _to_gemini_schema(v) for k, v in s.items() if k != "additionalProperties"}
    if isinstance(s, list):
        return [_to_gemini_schema(v) for v in s]
    return s


def evaluate(system, user, schema=SCHEMA):
    m = model()
    thinking = int(os.environ.get("EVAL_GEMINI_THINKING_TOKENS", "2048"))   # Pro models think; that counts against the output cap

    def call():
        body = {"systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": {"temperature": 0, "maxOutputTokens": MAX_OUTPUT + thinking,
                                     "responseMimeType": "application/json", "responseSchema": _to_gemini_schema(schema)}}
        r = http_json(f"{API}/models/{m}:generateContent", _headers(), body)
        parts = (r.get("candidates") or [{}])[0].get("content", {}).get("parts", [])
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        u = r.get("usageMetadata", {})
        return parse_json(text), {"input": u.get("promptTokenCount", 0),
                                  "output": u.get("candidatesTokenCount", 0) + u.get("thoughtsTokenCount", 0)}

    return cached_call(NAME, m, system, user, call)
