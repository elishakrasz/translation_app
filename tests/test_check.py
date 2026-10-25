"""translator check: the quotation lock and the forbidden forms."""

import yaml

from translator import bootstrap, check, records
from translator.project import Project


def make(tmp_path, monkeypatch, hebrew):
    monkeypatch.delenv("TRANSLATOR_PROJECT", raising=False)
    project, _ = bootstrap.init(tmp_path / "book", title="T")
    cfg = yaml.safe_load((project.root / "project.yaml").read_text())
    cfg["units"] = [{"id": "ch01", "slug": "one", "title": "One", "start": {"part": "p", "page": 1}}]
    (project.root / "project.yaml").write_text(yaml.safe_dump(cfg, allow_unicode=True))
    project = Project(project.root)
    d = project.unit_dir(project.units[0]); d.mkdir(parents=True)
    (d / "chunk0001.md").write_text('Rashi says "as if all your work were done."^1^ <!--id:ch01.p0001-->\n')
    (d / "output_chunk0001.md").write_text(hebrew + " <!--id:ch01.p0001-->\n")
    (project.root / "style" / "style-checklist.yaml").write_text(yaml.safe_dump({"rules": [
        {"id": "divine-name", "forbid": ["אלוהים"], "severity": "error"}]}, allow_unicode=True))
    records.append(project, "quotations", [{"unit": "ch01", "block": "ch01.p0001", "text": "כאלו כל מלאכתך עשויה",
                                            "locator": "Rashi on Exodus 20:9"}], by="test")
    return project


def test_lock_holds(tmp_path, monkeypatch):
    project = make(tmp_path, monkeypatch, 'רש"י אומר: "כאלו כל מלאכתך עשויה".^1^ ואמר אלוקים')
    assert check.errors(check.run(project, project.units), "ch01") == []


def test_lock_breaks(tmp_path, monkeypatch):
    project = make(tmp_path, monkeypatch, 'רש"י אומר: "כאילו כל מלאכתך עשויה".^1^ ואמר אלוהים')
    errs = check.errors(check.run(project, project.units), "ch01")
    assert {e[1] for e in errs} == {"quotations", "style"}


def test_markers(tmp_path, monkeypatch):
    project = make(tmp_path, monkeypatch, 'רש"י אומר: "כאלו כל מלאכתך עשויה".')    # ^1^ dropped
    assert any(e[1] == "structure" for e in check.errors(check.run(project, project.units), "ch01"))
