"""The project folder of one book: finding it, its settings, and where things live in it."""

import os
import sys
from pathlib import Path

import yaml

ENGINE = Path(__file__).resolve().parent.parent
# The translator command in this engine's virtual environment; written into hooks and slash commands.
TRANSLATOR_BIN = Path(sys.executable).parent / "translator"


class ProjectError(Exception):
    """A problem with the project folder or its settings, reported to the user as a plain message."""


def find_root(start=None):
    """The project folder: $TRANSLATOR_PROJECT, else the nearest folder upwards holding project.yaml."""
    env = os.environ.get("TRANSLATOR_PROJECT")
    if env:
        root = Path(env).expanduser().resolve()
        if not (root / "project.yaml").exists():
            raise ProjectError(f"TRANSLATOR_PROJECT={env} has no project.yaml")
        return root
    here = Path(start or Path.cwd()).resolve()
    for d in (here, *here.parents):
        if (d / "project.yaml").exists():
            return d
    raise ProjectError("not in a project folder (no project.yaml here or above). "
                       "Run this from the book's folder, or create one with `translator init`.")


class Project:
    def __init__(self, root=None):
        self.root = Path(root).resolve() if root else find_root()
        self.cfg = yaml.safe_load((self.root / "project.yaml").read_text(encoding="utf-8")) or {}
        self.units = self.cfg.get("units") or []
        ids = [u["id"] for u in self.units]
        if len(ids) != len(set(ids)):
            raise ProjectError("project.yaml: two units have the same id")

    # ---- settings -------------------------------------------------------
    @property
    def title(self):
        return (self.cfg.get("book") or {}).get("title") or self.root.name

    def unit(self, uid):
        for u in self.units:
            if u["id"] == uid:
                return u
        raise ProjectError(f"no unit {uid!r} in project.yaml (units: {', '.join(u['id'] for u in self.units)})")

    def select(self, spec):
        """Units named by 'ch01', 'ch01,ch02', 'ch01-ch03', 'all' or None (= all), in book order."""
        if not spec or spec == "all":
            return list(self.units)
        ids = [u["id"] for u in self.units]
        chosen = []
        for part in spec.split(","):
            part = part.strip()
            if "-" in part and part not in ids:
                a, b = part.split("-", 1)
                if a not in ids or b not in ids:
                    raise ProjectError(f"unknown unit range {part!r}")
                chosen += ids[ids.index(a):ids.index(b) + 1]
            else:
                self.unit(part)
                chosen.append(part)
        return [u for u in self.units if u["id"] in chosen]

    # ---- paths ----------------------------------------------------------
    def unit_name(self, u):
        return f"{u['id']}-{u['slug']}"

    def ocr_dir(self, part):
        return self.root / "source" / "ocr" / part

    def cleaned_file(self, u):
        return self.root / "source" / "cleaned" / f"{self.unit_name(u)}.md"

    def unit_dir(self, u):
        return self.root / "units" / self.unit_name(u)

    @property
    def records(self):
        return self.root / "records"

    def work(self, step):
        return self.root / "work" / step
