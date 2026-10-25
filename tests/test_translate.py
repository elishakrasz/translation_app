"""Step 4 prompts: the foundations gate, term matching, and translator-facing notes."""

import pytest

from translator import bootstrap, translate


def test_foundations_required(tmp_path, monkeypatch):
    monkeypatch.delenv("TRANSLATOR_PROJECT", raising=False)
    project, _ = bootstrap.init(tmp_path / "book", title="Test")
    with pytest.raises(translate.FoundationsMissing, match="style sheet"):
        translate.foundations(project)
    for p, text in {"style/translation-brief.md": "brief", "style/style-sheet.md": "sheet",
                    "terms/glossary.json": '{"version": 2, "terms": []}',
                    "terms/decided-terms.yaml": "status: draft\ngroups: []\n"}.items():
        (project.root / p).parent.mkdir(parents=True, exist_ok=True)
        (project.root / p).write_text(text)
    with pytest.raises(translate.FoundationsMissing, match="draft"):
        translate.foundations(project)
    (project.root / "terms/decided-terms.yaml").write_text("status: decided\ngroups: []\n")
    assert translate.foundations(project)["brief"] == "brief"


def test_occurs_and_table():
    text = "Robert Moses built roads. The exodus began; vayekhulu is read."
    assert translate.occurs("Moses", text, "person")
    assert not translate.occurs("Exodus", text, "work")           # names and works are case-sensitive
    assert translate.occurs("Exodus", text, "concept")
    glossary = [{"source": "vayekhulu", "target": "וַיְכֻלּוּ", "aliases": [], "category": "concept", "notes": ""},
                {"source": "Sforno", "target": "הספורנו", "aliases": [], "category": "person", "notes": ""}]
    assert [r[0] for r in translate.term_table(glossary, text)] == ["vayekhulu"]


def test_usage_note():
    rec = ("recommended (three reviews): Fresh assessment and my first pass: the narrative as a text → סיפור הבריאה; "
           "creation itself → מעשה בראשית. · b: Proposed.")
    assert translate.usage_note(rec) == "the narrative as a text → סיפור הבריאה; creation itself → מעשה בראשית."
    assert translate.usage_note("no recommendation; proposed form (extractors differed) · Space missions.") == "Space missions."
