"""Step 1 on a small made-up book: clean, chunk, IDs, state and gates."""

import json

import pytest
import yaml

from translator import bootstrap, chunk, clean
from translator.project import Project
from translator.state import State

PAGES = {
    # a chapter opening: label, two-line title, a heading, a paragraph broken by a hyphen at the page end
    2: ("Chapter 1\n\nHow to Think\nAbout Shabbos\n\nTHE ORIGINS OF THE WEEK\n\n"
        "The seven-day week is traceable to the Hebrew Bible.^1^ Its spread was slow and its gen-\n"
        "--- notes ---\n1. Nahum Sarna, Genesis, 14. Sarna adds that the"),
    # running head, the paragraph's continuation, a block quote, a margin scrap, the note continued
    3: ("Stop, Look, Listen\n\nerous reach covered the world. A well-\nloved account says so.^2^\n\n"
        "> Why a seven-day week? The ancient Greeks, it seems,\n> had no week.\n\nTh\nno\nsar\nfri\n\n"
        "A new paragraph starts here.\n"
        "--- notes ---\n(cont.) idea is old.\n2. Daniel Boorstin, The Discoverers, 13."),
}


def proof_record(n, text, printed):
    return {"page": n, "status": "ok", "text": text, "printed_page": printed, "model": "test", "mode": "text",
            "language": "english", "attempts": 1, "warnings": [], "usage": {}}


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.delenv("TRANSLATOR_PROJECT", raising=False)
    root = tmp_path / "book"
    bootstrap.init(root, title="Stop, Look, Listen")
    ocr = root / "source" / "ocr" / "part1"
    ocr.mkdir(parents=True)
    with open(ocr / "ocr.jsonl", "w") as f:
        f.write(json.dumps({"page": 1, "text": "x"}) + "\n")             # a blank page, skipped
        for n, t in PAGES.items():
            f.write(json.dumps({"page": n, "text": t}) + "\n")
    with open(ocr / "proof.jsonl", "w") as f:
        for n, t in PAGES.items():
            f.write(json.dumps(proof_record(n, t, str(n - 1))) + "\n")
    cfg = yaml.safe_load((root / "project.yaml").read_text())
    cfg["sources_received"] = [{"file": "Part1.pdf", "ocr": "part1"}]
    cfg["units"] = [{"id": "ch01", "slug": "how-to-think", "title": "How to Think About Shabbos",
                     "start": {"part": "part1", "page": 2}}]
    cfg["running_heads"] = ["Stop, Look, Listen"]
    (root / "project.yaml").write_text(yaml.safe_dump(cfg, allow_unicode=True))
    return Project(root)


def test_clean(project):
    results, report, problems = clean.run(project, project.units, write=True)
    assert not problems and not results[0].errors, (problems, results[0].errors)
    text = project.cleaned_file(project.units[0]).read_text()
    assert text.startswith("<!--page:1-->\n\n# How to Think About Shabbos\n\n## THE ORIGINS OF THE WEEK")
    assert "Chapter 1" not in text and "Stop, Look, Listen" not in text      # label and running head dropped
    assert "its generous<!--page:2--> reach" in text                        # hyphen repaired at the page break
    assert "A well-loved account" in text                                  # a real compound keeps its hyphen
    assert "> Why a seven-day week? The ancient Greeks, it seems, had no week." in text
    assert "Th\nno" not in text and "sar" not in text.split()              # margin scrap dropped
    assert "\n\nA new paragraph starts here." in text
    assert "1\\. Nahum Sarna, Genesis, 14. Sarna adds that the idea is old." in text
    kinds = {e["kind"] for e in json.loads("[" + ",".join((project.records / "edits.jsonl").read_text().split("\n")[:-1]) + "]")}
    assert {"label-dropped", "running-head-dropped", "dehyphenated", "hyphen-kept", "margin-scrap-dropped"} <= kinds


def test_clean_reports_missing_note(project):
    p3 = PAGES[3].replace("2. Daniel Boorstin, The Discoverers, 13.", "")
    lines = (project.root / "source/ocr/part1/proof.jsonl").read_text().splitlines()
    lines[1] = json.dumps(proof_record(3, p3, "2"))
    (project.root / "source/ocr/part1/proof.jsonl").write_text("\n".join(lines) + "\n")
    results, *_ = clean.run(project, project.units, write=True)
    assert any("^2^ has no note" in e for e in results[0].errors)
    assert not project.cleaned_file(project.units[0]).exists()               # nothing written with errors


def test_chunk_ids_and_permanence(project):
    clean.run(project, project.units, write=True)
    unit = project.units[0]
    summary, problem = chunk.run(project, unit, write=True)
    assert problem is None
    rows = [json.loads(l) for l in (project.unit_dir(unit) / "blocks.jsonl").read_text().splitlines()]
    assert [r["id"] for r in rows] == ["ch01.p0001", "ch01.p0002", "ch01.p0003", "ch01.p0004", "ch01.p0005",
                                       "ch01.n001", "ch01.n002"]
    assert rows[2]["page_start"] == "1" and rows[2]["page_end"] == "2"      # the paragraph across the page break
    body = (project.unit_dir(unit) / "chunk0001.md").read_text()
    assert "<!--page:" not in body and body.count("<!--id:") == 5
    notes = (project.unit_dir(unit) / "chunk0002.md").read_text()
    assert notes.startswith("1\\. Nahum Sarna") and "<!--id:ch01.n002-->" in notes
    manifest = json.loads((project.unit_dir(unit) / "manifest.json").read_text())
    assert manifest["chunk_count"] == 2 and manifest["chunks"][1]["output_file"] == "output_chunk0002.md"

    again, problem = chunk.run(project, unit, write=True)                  # same source: nothing to do
    assert again["unchanged"] and problem is None
    f = project.cleaned_file(unit)
    f.write_text(f.read_text().replace("slow", "quick"))
    _, problem = chunk.run(project, unit, write=True)                       # changed source: refused
    assert "IDs are permanent" in problem


def test_state_order(project):
    state = State(project)
    ok, msg = state.can_start("ch01", "chunk")
    assert not ok and "chunk needs clean to pass first" in msg
    state.set("ch01", "clean", "awaiting-gate", report="work/clean/report.md")
    ok, msg = state.can_start("ch01", "chunk")
    assert not ok and "waiting for your decision in work/clean/report.md" in msg
    state.set("ch01", "clean", "passed")
    assert state.can_start("ch01", "chunk") == (True, "")
    state.set("ch01", "chunk", "passed")
    state.set("ch01", "clean", "awaiting-gate")                             # redoing clean makes chunk stale
    assert state.state_of("ch01", "chunk") == "stale"


def test_helpers():
    assert clean.ends_sentence('unique to Israel."^1^')
    assert not clean.ends_sentence("the extractive capitalism of")
    assert clean.is_margin_scrap(["Wh", "Hov", "enh", "in t"])
    assert not clean.is_margin_scrap(["Rabbi Naftali Citron", "October 11, 2021", "The Carlebach Shul"])
    assert clean.is_caps_heading("SHABBOS: THE SMILING FACE OF TIME")
    assert not clean.is_caps_heading("Shabbos in Scripture")
