"""init, upgrade and doctor: making a project folder, keeping its Claude Code files current, checking the Mac."""

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

from . import __version__, generate
from .project import ENGINE, TRANSLATOR_BIN, Project

FOLDERS = ["source/original", "source/ocr", "source/cleaned", "units", "style/corpus", "style/profiles", "terms",
           "records", "review", "work", "drafts/koren", "drafts/word", "index", "out"]
PROJECT_GITIGNORE = "work/\nreview/**/*.html\n~$*\n.DS_Store\n"


def init(path, title=None, house="koren"):
    root = Path(path).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    made = []
    for f in FOLDERS:
        if not (root / f).exists():
            (root / f).mkdir(parents=True)
            made.append(f + "/")
    pj = root / "project.yaml"
    if not pj.exists():
        cfg = yaml.safe_load((ENGINE / "templates" / "project.yaml").read_text(encoding="utf-8"))
        cfg["book"]["title"] = title or root.name
        cfg["house"] = house
        pj.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
        made.append("project.yaml")
    if not (root / ".gitignore").exists():
        (root / ".gitignore").write_text(PROJECT_GITIGNORE, encoding="utf-8")
        made.append(".gitignore")
    project = Project(root)
    if generate.claude_md(project):
        made.append("CLAUDE.md")
    generate.state_md(project)
    made += upgrade(project)
    return project, made


def upgrade(project):
    """Copy the engine's slash commands and VS Code settings into the project, with this engine's path."""
    made = []
    cmd_dir = project.root / ".claude" / "commands"
    cmd_dir.mkdir(parents=True, exist_ok=True)
    for src in sorted((ENGINE / "commands").glob("*.md")):
        text = src.read_text(encoding="utf-8").replace("{{TRANSLATOR}}", str(TRANSLATOR_BIN))
        dst = cmd_dir / src.name
        if not dst.exists() or dst.read_text(encoding="utf-8") != text:
            dst.write_text(text, encoding="utf-8")
            made.append(f".claude/commands/{src.name}")
    (cmd_dir / ".engine-version").write_text(__version__ + "\n", encoding="utf-8")

    vs = project.root / ".vscode"
    vs.mkdir(exist_ok=True)
    for name in ("settings.json", "tasks.json"):
        text = (ENGINE / "templates" / "vscode" / name).read_text(encoding="utf-8").replace("{{TRANSLATOR}}", str(TRANSLATOR_BIN))
        if not (vs / name).exists():
            (vs / name).write_text(text, encoding="utf-8")
            made.append(f".vscode/{name}")
    return made


def commands_version(project):
    p = project.root / ".claude" / "commands" / ".engine-version"
    return p.read_text(encoding="utf-8").strip() if p.exists() else None


# ---------------------------------------------------------------------------
# doctor
# ---------------------------------------------------------------------------

def _run(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=20).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _key_present(name):
    for f in (Path.home() / ".config" / "translator" / ".env", ENGINE / ".env"):
        if f.exists() and any(l.split("=", 1)[0].strip() == name and l.split("=", 1)[1].strip()
                              for l in f.read_text(encoding="utf-8").splitlines() if "=" in l and not l.startswith("#")):
            return f
    return None


def doctor(project=None):
    """[(ok, what, detail)] for every prerequisite; ok is True, False or None (optional and missing)."""
    out = []
    add = lambda ok, what, detail="": out.append((ok, what, detail))
    add(sys.version_info >= (3, 12), "Python 3.12+", sys.version.split()[0])
    add(importlib.util.find_spec("ocrkit") is not None, "ocrkit installed", "pip install -e ./ocrkit")
    tess = shutil.which("tesseract")
    langs = set(_run([tess, "--list-langs"]).split()) if tess else set()
    add(bool(tess) and {"eng", "heb", "osd"} <= langs, "Tesseract with eng, heb, osd",
        "missing: " + ", ".join(sorted({"eng", "heb", "osd"} - langs)) if tess else "brew install tesseract tesseract-lang")
    add(bool(shutil.which("pdftoppm")), "Poppler (pdftoppm)", "brew install poppler")
    soffice = shutil.which("soffice") or ("/Applications/LibreOffice.app/Contents/MacOS/soffice"
                                          if Path("/Applications/LibreOffice.app").exists() else None)
    add(bool(soffice), "LibreOffice", soffice or "for the Koren PDF drafts")
    add(bool(shutil.which("node")), "Node", "for the Word builder")
    add(bool(shutil.which("pandoc")), "Pandoc")
    add(Path("/Applications/Microsoft Word.app").exists(), "Word", "for the translator's edit round")
    add(Path("/Applications/calibre.app").exists() or None, "Calibre (optional)", "only for publisher EPUB/DOCX")
    nd = ENGINE / "legacy" / "tools" / "node_docx" / "node_modules"
    add(nd.exists() or None, "docx package for the Word builders", "cd legacy/tools/node_docx && npm ci")
    k = _key_present("ANTHROPIC_API_KEY")
    add(bool(k), "ANTHROPIC_API_KEY (for ocrkit)", str(k) if k else "add it to ~/.config/translator/.env")
    for name in ("GEMINI_API_KEY", "OPENAI_API_KEY"):
        add(bool(_key_present(name)) or None, f"{name} (optional, outside evaluation)")
    skill = Path.home() / ".claude" / "skills" / "book-translator"
    add(skill.exists() and skill.resolve() == ENGINE, "skill linked into ~/.claude/skills/",
        f"ln -s {ENGINE} {skill}")
    if project:
        v = commands_version(project)
        add(v == __version__, "project's slash commands current", f"project {v}, engine {__version__}: run `translator upgrade`"
            if v != __version__ else __version__)
    return out
