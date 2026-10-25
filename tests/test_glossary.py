"""Step 2b: merging two extractions, the review page, and applying decisions."""

import json

import yaml

from translator import bootstrap, glossary
from translator.project import Project


def make(tmp_path, monkeypatch):
    monkeypatch.delenv("TRANSLATOR_PROJECT", raising=False)
    project, _ = bootstrap.init(tmp_path / "book", title="Test Book")
    ref = tmp_path / "other" / "glossary" / "glossary-book.json"
    ref.parent.mkdir(parents=True)
    ref.write_text(json.dumps({"terms": [{"source": "Baal Shem Tov", "target": "הבעל שם טוב", "aliases": ["Besht"]}]}))
    cfg = yaml.safe_load((project.root / "project.yaml").read_text())
    cfg["reference_glossaries"] = [str(ref)]
    (project.root / "project.yaml").write_text(yaml.safe_dump(cfg, allow_unicode=True))
    w = project.root / "work" / "glossary"
    w.mkdir(parents=True)
    (w / "proposed_a.json").write_text(json.dumps({"terms": [
        {"source": "melakha", "target": "מלאכה", "category": "concept", "count": 30, "units": ["ch02"]},
        {"source": "Besht", "target": "הבעש\"ט", "category": "person", "count": 3, "units": ["ch03"]},
        {"source": "Sforno", "target": "הספורנו", "category": "person", "confidence": "low", "units": ["ch02"]}]}))
    (w / "proposed_b.json").write_text(json.dumps({"terms": [
        {"source": "melakha", "target": "מלאכה", "category": "concept", "count": 28, "units": ["ch02", "ch01"]},
        {"source": "Baal Shem Tov", "target": "הבעל שם טוב", "category": "person", "aliases": ["Besht"], "count": 5}]}))
    return Project(project.root)


def test_merge_page_apply(tmp_path, monkeypatch):
    project = make(tmp_path, monkeypatch)
    labels, merged = glossary.merge(project)
    assert labels == ["a", "b"] and len(merged) == 3
    by = {m["source"]: m for m in merged}
    assert by["melakha"]["agree"] and by["melakha"]["units"] == ["ch01", "ch02"] and by["melakha"]["count"] == 30
    besht = by["Besht"]                                                    # joined through the alias
    assert not besht["agree"] and "Baal Shem Tov" in besht["aliases"]
    assert besht["reference"]["target"] == "הבעל שם טוב"
    assert by["Sforno"]["found_by"] == ["a"]
    assert merged[0]["source"] == "Besht"                                   # disagreements first

    out, s = glossary.page(project)
    text = out.read_text()
    assert "glossary-decisions.json" in text and "הספורנו" in text and s["differ"] == 1

    dec = tmp_path / "glossary-decisions.json"
    dec.write_text(json.dumps({"decisions": {
        "melakha": {"decision": "accept", "target": "מלאכה"},
        "Besht": {"decision": "edit", "target": "הבעל שם טוב", "note": "full form"},
        "Sforno": {"decision": "reject"}}}))
    terms, problems, undecided, resolved = glossary.apply(project, dec, write=True)
    assert not problems and not undecided and len(terms) == 2
    g = json.loads((project.root / "terms" / "glossary.json").read_text())
    assert g["version"] == 2 and {t["source"] for t in g["terms"]} == {"Besht", "melakha"}
    besht = next(t for t in g["terms"] if t["source"] == "Besht")
    assert besht["target"] == "הבעל שם טוב" and besht["aliases"] == ["Baal Shem Tov"]
