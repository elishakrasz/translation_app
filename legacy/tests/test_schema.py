"""Validation of evaluator responses, provider plumbing and report logic — all mocked, no network."""
import json

import pytest

from eval import prompts, report, run
from eval.providers import base, gemini, openai

HE = "ר' בונים אמר שהאמת היא העיקר, ולא הפנייה החיצונית של האדם."


def valid():
    return {"id": "ch02-0001-2", "overall": {"fidelity": 4, "register": 5, "terminology": 5},
            "findings": [{"category": "modality", "severity": "major", "he_span": "האמת היא העיקר",
                          "en_span": "truth may be the essence", "note": "The English hedges; the Hebrew states it as certain."}],
            "confidence": 0.8}


def test_valid_response_passes():
    assert prompts.validate(valid(), HE) == []


def test_rewrite_in_note_is_rejected():
    r = valid()
    r["findings"][0]["note"] = "Better: ר' בונים אמר שייתכן שהאמת היא העיקר ולא הפנייה החיצונית של האדם"
    assert any("rewrite" in p for p in prompts.validate(r, HE))


def test_invented_span_is_rejected():
    r = valid()
    r["findings"][0]["he_span"] = "האמת היא הכול"
    assert any("substring" in p for p in prompts.validate(r, HE))


def test_bad_enums_and_scores_rejected():
    r = valid()
    r["findings"][0]["category"] = "tone"
    r["overall"]["fidelity"] = 7
    probs = prompts.validate(r, HE)
    assert any("category" in p for p in probs) and any("fidelity" in p for p in probs)


def test_drop_invalid_keeps_good_findings():
    r = valid()
    r["findings"].append(dict(r["findings"][0], he_span="לא קיים"))
    out = prompts.drop_invalid(r, HE)
    assert len(out["findings"]) == 1 and out["dropped_findings"] == 1


def test_dicta_validation():
    assert prompts.validate({"findings": [{"he_span": "הפנייה החיצונית", "type": "צירוף", "severity": "קלה", "note": ""}],
                             "naturalness": 4}, HE, dicta=True) == []
    assert prompts.validate({"findings": [], "naturalness": 9}, HE, dicta=True)


def test_system_prompt_has_style_and_terms_not_steinsaltz():
    s = prompts.system_prompt()
    assert "Torah-scholarly" in s and "פשיסחא" in s and "Steinsaltz" not in s


def test_required_terms_from_glossary():
    g = prompts.load_glossary()
    t = prompts.required_terms("The Yehudi of Przysucha spoke of truthfulness.", g)
    assert "פשיסחא" in t and "אמתיות" in t


def test_parse_json_variants():
    assert base.parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert base.parse_json('Here: {"a": 1} done') == {"a": 1}
    with pytest.raises(base.MalformedJSON):
        base.parse_json("no json")


def test_model_picking():
    assert gemini.pick_model(["models/gemini-2.5-pro", "models/gemini-2.5-flash", "models/gemini-3-pro-preview",
                              "models/gemini-3-pro", "models/gemini-embedding-001"]) == "gemini-3-pro"
    assert openai.pick_model([("gpt-4o", 1), ("gpt-5", 2), ("gpt-5-mini", 3), ("gpt-5.2", 4),
                              ("gpt-5.2-2025-12-11", 5), ("gpt-5.2-pro", 6), ("gpt-realtime", 7)]) == "gpt-5.2"


def test_cache_and_malformed_retry(tmp_path, monkeypatch):
    monkeypatch.setattr(base, "EVAL", tmp_path)
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) == 1:
            raise base.MalformedJSON("oops")
        return {"ok": True}, {"input": 10, "output": 5}

    out = base.cached_call("gemini", "m", "sys", "user", flaky)
    assert out["response"] == {"ok": True} and not out["cached"] and len(calls) == 2
    again = base.cached_call("gemini", "m", "sys", "user", flaky)
    assert again["cached"] and len(calls) == 2
    cached_text = next((tmp_path / "cache").glob("*.json")).read_text()
    assert set(json.loads(cached_text)) == {"provider", "model", "response", "usage"}   # response and usage only


def test_keys_never_reach_cache_or_results(tmp_path, monkeypatch):
    monkeypatch.setattr(base, "EVAL", tmp_path)
    monkeypatch.setattr(run, "EVAL", tmp_path)
    monkeypatch.setenv("GEMINI_API_KEY", "SECRET-KEY-123")
    seen = {}

    def fake_http(url, headers, body=None, **kw):
        seen["url"], seen["headers"] = url, headers
        return {"candidates": [{"content": {"parts": [{"text": json.dumps(valid())}]}}], "usageMetadata": {}}

    monkeypatch.setattr(gemini, "http_json", fake_http)
    monkeypatch.setattr(gemini, "_model", "gemini-test-pro")
    rec = {"id": "ch02-0001-2", "chapter": "ch02", "chunk": "0001", "para": 2, "kind": "prose", "he": HE, "en": "x", "align": "1:1"}
    rid, prov, st = run.evaluate_one(gemini, "gemini", rec, "sys", "user", False)
    assert st == "ok" and "SECRET" not in seen["url"]
    for f in tmp_path.rglob("*.json"):
        assert "SECRET-KEY-123" not in f.read_text()


def test_reask_once_then_drop(tmp_path, monkeypatch):
    monkeypatch.setattr(run, "EVAL", tmp_path)
    bad = valid()
    bad["findings"][0]["he_span"] = "invented"
    asked = []

    class Fake:
        @staticmethod
        def evaluate(system, user):
            asked.append(user)
            return {"response": json.loads(json.dumps(bad)), "model": "fake"}

    rec = {"id": "ch02-0001-2", "chapter": "ch02", "chunk": "0001", "para": 2, "kind": "prose", "he": HE, "en": "x", "align": "1:1"}
    _, _, st = run.evaluate_one(Fake, "openai", rec, "sys", "user", False)
    out = json.loads((tmp_path / "results" / "ch02" / "ch02-0001-2.openai.json").read_text())
    assert len(asked) == 2 and asked[1] == "user" + prompts.NO_REWRITE
    assert out["response"]["findings"] == [] and out["response"]["dropped_findings"] == 1 and out["validation"]


def test_agreement_and_human_look():
    f = lambda span, sev="minor", cat="register": {"category": cat, "severity": sev, "he_span": span, "en_span": "", "note": ""}
    g = {"overall": {"fidelity": 4, "register": 4, "terminology": 5}, "findings": [f("האמת היא העיקר"), f("החיצונית")]}
    o = {"overall": {"fidelity": 4, "register": 4, "terminology": 5}, "findings": [f("האמת היא")]}
    assert report.agreement(HE, g["findings"], o["findings"]) == pytest.approx(0.5)
    assert report.human_look(HE, {"gemini": g, "openai": o}) == []
    o["overall"]["fidelity"] = 2
    assert "fidelity 4 vs 2" in report.human_look(HE, {"gemini": g, "openai": o})
    o["overall"]["fidelity"] = 4
    g["findings"].append(f("של האדם", "major"))
    assert "gemini: major not seen by openai" in report.human_look(HE, {"gemini": g, "openai": o})
    assert report.human_look(HE, {"gemini": {"overall": g["overall"], "findings": [f("האדם", "critical")]}}) == ["gemini: critical"]
    assert report.human_look(HE, {"dicta": {"findings": [{"he_span": "האדם", "severity": "חמורה"}], "naturalness": 2}}) == ["dicta: חמורה"]


def test_off_scale_scores_rejected_and_nulled():
    r = valid()
    r["overall"]["fidelity"] = 95
    assert any("fidelity" in p for p in prompts.validate(r, HE))
    assert prompts.drop_invalid(r, HE)["overall"]["fidelity"] is None


def test_gemini_skips_special_variants_and_gets_range_schema():
    assert gemini.pick_model(["models/gemini-3.1-pro-preview", "models/gemini-3.1-pro-preview-customtools"]) == "gemini-3.1-pro-preview"
    sch = gemini._to_gemini_schema(prompts.SCHEMA)
    assert sch["properties"]["overall"]["properties"]["fidelity"] == {"type": "integer", "minimum": 1, "maximum": 5}
