"""GPT flagship adapter (REST, Chat Completions with structured outputs)."""
import os
import re

from ..prompts import SCHEMA
from .base import MAX_OUTPUT, ProviderError, cached_call, http_json, parse_json, version_key

NAME = "openai"
API = "https://api.openai.com/v1"
EXCLUDE = re.compile(r"mini|nano|audio|realtime|search|image|transcribe|tts|codex|oss|instruct|chat|embedding|moderation|turbo|preview|pro")
_model = None


def _headers():
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise ProviderError("OPENAI_API_KEY is not set")
    return {"Authorization": f"Bearer {key}"}


def pick_model(models):
    """models: [(id, created)]. Newest flagship gpt-N[.M]; an undated alias beats a dated snapshot."""
    flag = [(i, c) for i, c in models if re.fullmatch(r"gpt-\d+(\.\d+)?(o)?(-\d{4}-\d{2}-\d{2})?", i) and not EXCLUDE.search(i)]
    if not flag:
        raise ProviderError("no GPT flagship model listed")
    return max(flag, key=lambda ic: (version_key(ic[0]), not re.search(r"\d{4}-\d{2}-\d{2}", ic[0]), ic[1]))[0]


def model():
    global _model
    if _model is None:
        _model = os.environ.get("EVAL_OPENAI_MODEL")
        if not _model:
            data = http_json(f"{API}/models", _headers())
            _model = pick_model([(m["id"], m.get("created", 0)) for m in data.get("data", [])])
    return _model


_no_temperature = False


def evaluate(system, user, schema=SCHEMA):
    m = model()
    reasoning = int(os.environ.get("EVAL_OPENAI_REASONING_TOKENS", "4000"))  # reasoning models spend output tokens thinking

    def call():
        global _no_temperature
        body = {"model": m, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "max_completion_tokens": MAX_OUTPUT + reasoning,
                "response_format": {"type": "json_schema", "json_schema": {"name": "evaluation", "strict": True, "schema": schema}}}
        if os.environ.get("EVAL_OPENAI_REASONING_EFFORT"):
            body["reasoning_effort"] = os.environ["EVAL_OPENAI_REASONING_EFFORT"]
        if not _no_temperature:
            body["temperature"] = 0
        try:
            r = http_json(f"{API}/chat/completions", _headers(), body)
        except ProviderError as e:
            if "temperature" not in str(e) or "temperature" not in body:
                raise
            if not _no_temperature:      # reasoning models accept only the default temperature
                _no_temperature = True
                print(f"  note: {m} does not accept temperature 0; using its default")
            body.pop("temperature")
            r = http_json(f"{API}/chat/completions", _headers(), body)
        text = r["choices"][0]["message"].get("content") or ""
        u = r.get("usage", {})
        return parse_json(text), {"input": u.get("prompt_tokens", 0), "output": u.get("completion_tokens", 0)}

    return cached_call(NAME, m, system, user, call)
