"""A reviewer from another model family, called through its API (OpenAI so far), writing the same findings file as
the Claude reviewers: work/review/<unit>-findings-<name>.json.

It gets the same brief (briefs/review.md), style sheet, decided terms and checklist, and the unit's pairs in batches
of blocks. Responses are cached in work/review/cache/ by a hash of model and prompt, so a rerun costs nothing. Keys are
read from ~/.config/translator/.env or the engine's .env, never printed.
"""

import hashlib
import json
import re
import urllib.request
from pathlib import Path

from .project import ENGINE

URL = {"openai": "https://api.openai.com/v1/chat/completions"}
KEY = {"openai": "OPENAI_API_KEY"}


def api_key(provider):
    name = KEY[provider]
    for f in (Path.home() / ".config" / "translator" / ".env", ENGINE / ".env"):
        if f.exists():
            for line in f.read_text(encoding="utf-8").splitlines():
                if line.startswith(name + "=") and line.split("=", 1)[1].strip():
                    return line.split("=", 1)[1].strip().strip("'\"")
    raise RuntimeError(f"{name} not found in ~/.config/translator/.env or {ENGINE}/.env")


def system_prompt(project, name):
    parts = [(ENGINE / "briefs" / "review.md").read_text(encoding="utf-8"),
             f"\nYour reviewer name is \"{name}\". The project files are given below instead of on disk.",
             "\n# style/style-sheet.md\n" + (project.root / "style" / "style-sheet.md").read_text(encoding="utf-8"),
             "\n# terms/decided-terms.yaml\n" + (project.root / "terms" / "decided-terms.yaml").read_text(encoding="utf-8"),
             "\n# style/style-checklist.yaml\n" + (project.root / "style" / "style-checklist.yaml").read_text(encoding="utf-8"),
             "\nAnswer with the JSON object only: {\"reviewer\": ..., \"unit\": ..., \"findings\": [...]}. "
             "You can't run Python here: copy every he_span character for character from the HE line."]
    return "\n".join(parts)


def batch_text(items):
    lines = []
    for it in items:
        lines += [f"## {it['id']}", "", "EN: " + it["english"], "", "HE: " + it["hebrew"]]
        for q in it["locked"]:
            lines.append(f"LOCKED ({q['qid']}, {q['locator']}) — do not review these words: {q['text']}")
        lines.append("")
    return "\n".join(lines)


def call(provider, model, system, user, cache_dir):
    h = hashlib.sha256(f"{provider}|{model}|{system}|{user}".encode("utf-8")).hexdigest()[:24]
    f = cache_dir / f"{h}.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8")), True
    body = {"model": model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "response_format": {"type": "json_object"}}
    req = urllib.request.Request(URL[provider], data=json.dumps(body).encode("utf-8"),
                                 headers={"Authorization": f"Bearer {api_key(provider)}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        data = json.loads(r.read().decode("utf-8"))
    out = {"model": data.get("model", model), "usage": data.get("usage", {}),
           "content": data["choices"][0]["message"]["content"]}
    cache_dir.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return out, False


def review(project, unit, provider="openai", model="gpt-6.1-sol", name="openai", batch=40, progress=print):
    from . import review as rv
    items = rv.gather(project, unit)
    system = system_prompt(project, name)
    cache = project.work("review") / "cache"
    findings, usage, bad = [], {"prompt_tokens": 0, "completion_tokens": 0}, 0
    he = {it["id"]: it["hebrew"] for it in items}
    for i in range(0, len(items), batch):
        part = items[i:i + batch]
        user = f"Unit {unit['id']} ({unit.get('title', '')}), blocks {part[0]['id']} to {part[-1]['id']}:\n\n" + batch_text(part)
        out, cached = call(provider, model, system, user, cache)
        for k in usage:
            usage[k] += (out.get("usage") or {}).get(k, 0)
        try:
            got = json.loads(re.sub(r"^```(?:json)?|```$", "", out["content"].strip(), flags=re.M)).get("findings", [])
        except json.JSONDecodeError:
            got, bad = [], bad + 1
        ok = [x for x in got if x.get("block") in he and x.get("he_span") and x["he_span"] in he[x["block"]]]
        findings += ok
        progress(f"  blocks {part[0]['id']}–{part[-1]['id']}: {len(ok)} finding(s)"
                 + (f", {len(got) - len(ok)} with a span not in the text" if len(got) > len(ok) else "")
                 + (" (cached)" if cached else ""))
    path = project.work("review") / f"{unit['id']}-findings-{name}.json"
    path.write_text(json.dumps({"reviewer": name, "unit": unit["id"], "model": out.get("model", model),
                                "findings": findings}, ensure_ascii=False, indent=1), encoding="utf-8")
    return path, findings, usage, bad
