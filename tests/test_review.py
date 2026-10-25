"""Step 8: validating findings, pairing the two reviewers, applying only what is accepted, keeping the lock."""

import json

import yaml

from translator import bootstrap, records, review
from translator.project import Project

HE = 'הרב אמר את הדברים האלה בצורה מעניינת: "כאלו כל מלאכתך עשויה". <!--id:ch01.p0001-->\n'


def make(tmp_path, monkeypatch):
    monkeypatch.delenv("TRANSLATOR_PROJECT", raising=False)
    project, _ = bootstrap.init(tmp_path / "book", title="T")
    cfg = yaml.safe_load((project.root / "project.yaml").read_text())
    cfg["units"] = [{"id": "ch01", "slug": "one", "title": "One", "start": {"part": "p", "page": 1}}]
    (project.root / "project.yaml").write_text(yaml.safe_dump(cfg, allow_unicode=True))
    project = Project(project.root)
    d = project.unit_dir(project.units[0]); d.mkdir(parents=True)
    (d / "chunk0001.md").write_text('The rabbi said this in an interesting way: "as if all your work were done." <!--id:ch01.p0001-->\n')
    (d / "output_chunk0001.md").write_text(HE)
    records.append(project, "quotations", [{"unit": "ch01", "block": "ch01.p0001", "text": "כאלו כל מלאכתך עשויה",
                                            "locator": "Rashi on Exodus 20:9"}], by="test")
    w = project.work("review"); w.mkdir(parents=True)
    find = lambda span, prop: {"block": "ch01.p0001", "he_span": span, "proposed": prop, "reason": "r",
                                "category": "register", "severity": "minor"}
    (w / "ch01-findings-fable.json").write_text(json.dumps({"findings": [
        find("בצורה מעניינת", "באופן מעניין"), find("not in the text", "x")]}, ensure_ascii=False))
    (w / "ch01-findings-opus.json").write_text(json.dumps({"findings": [
        find("מעניינת", "מאלפת"), find("כאלו כל", "כאילו כל")]}, ensure_ascii=False))
    return project


def test_findings_and_apply(tmp_path, monkeypatch):
    project = make(tmp_path, monkeypatch)
    found, problems = review.load_findings(project, project.units[0])
    assert len(found["fable"]) == 1 and len(found["opus"]) == 1          # bad span dropped, locked span dropped
    assert len(problems) == 2
    assert found["fable"][0]["agreed_with"] == ["opus-1"]                 # overlapping spans pair up
    dec = tmp_path / "dec.json"
    dec.write_text(json.dumps({"decisions": {"fable-1": {"decision": "accept"}, "opus-1": {"decision": "reject"}}}))
    applied, problems = review.apply(project, project.units[0], dec, write=True)
    assert applied == ["fable-1"] and not problems
    out = (project.unit_dir(project.units[0]) / "output_chunk0001.md").read_text()
    assert "באופן מעניין" in out and "כאלו כל מלאכתך עשויה" in out
    rows = records.load(project, "findings")
    assert {(r["reviewer"], r["decision"]) for r in rows} == {("fable", "accept"), ("opus", "reject")}
    assert review.stats(project)["fable"]["register"] == {"accept": 1}


def test_lock_refused(tmp_path, monkeypatch):
    """A span reaching into a locked quotation passes the first filter; applying it is refused."""
    project = make(tmp_path, monkeypatch)
    w = project.work("review")
    (w / "ch01-findings-opus.json").write_text(json.dumps({"findings": [
        {"block": "ch01.p0001", "he_span": "מעניינת: \"כאלו", "proposed": "מעניינת: \"כאילו", "reason": "r", "category": "typo",
         "severity": "minor"}]}, ensure_ascii=False))
    dec = tmp_path / "dec.json"
    dec.write_text(json.dumps({"decisions": {"opus-1": {"decision": "accept"}}}))
    applied, problems = review.apply(project, project.units[0], dec, write=True)
    assert not applied and "locked" in problems[0]
