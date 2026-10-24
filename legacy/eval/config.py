"""Paths, chapter map and environment for the evaluation passes."""
import sys
import os
from pathlib import Path

ROOT = (Path(os.environ["TRANSLATOR_PROJECT"]).expanduser().resolve() if os.environ.get("TRANSLATOR_PROJECT")
        else sys.exit("Set TRANSLATOR_PROJECT to the book folder, e.g. TRANSLATOR_PROJECT=~/the_translator"))
EVAL = ROOT / "eval"

CHAPTERS = {
    "ch01": ("ch01-introduction_temp", "Introduction"),
    "ch02": ("ch02-holy-rebellion_temp", "The Holy Rebellion"),
    "ch03": ("ch03-biographical-sketch_temp", "Biographical Sketch"),
    "ch04": ("ch04-torah-and-theology_temp", "Torah and Theology"),
    "ch05": ("ch05-zaddik-and-leadership_temp", "Zaddik and Leadership"),
    "ch06": ("ch06-quest-for-truth_temp", "The Quest for Truth"),
    "ch07": ("ch07-torat-ha-adam-human-psychology_temp", "Torat ha-Adam: Human Psychology"),
    "ch08": ("ch08-torat-ha-adam-psychology-of-the-soul_temp", "Torat ha-Adam: The Psychology of the Soul"),
    "ch09": ("ch09-torat-ha-adam-psychology-of-service_temp", "Torat ha-Adam: The Psychology of Service"),
    "ch10": ("ch10-prayer_temp", "Prayer"),
    "ch11": ("ch11-reaction-against-przysucha_temp", "The Reaction against Przysucha"),
    "ch12": ("ch12-end-of-the-holy-rebellion_temp", "The End of the Holy Rebellion"),
}


def load_dotenv(path=ROOT / ".env"):
    """Put KEY=value lines from .env into os.environ (existing variables win). Values are never printed."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.removeprefix("export ").strip()
        os.environ.setdefault(k, v.strip().strip("'\""))


def env(name, default=None):
    return os.environ.get(name, default)
