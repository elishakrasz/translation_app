"""Step 2 — the evaluation prompt (identical for both providers), the schema, and validation."""
import json
import re

from .config import EVAL, ROOT

SYSTEM_HEAD = """You are evaluating a published Hebrew translation of an English academic book on Hasidism (Michael Rosen, *The Quest for Authenticity*, on the Yehudi of Przysucha, R. Simhah Bunim and the Kotzker). You are a reviewer, not a translator. Do not rewrite, improve, or propose alternative renderings of whole sentences. Report problems only, as structured findings.

Evaluate three things, and only these:
1. **Fidelity to the English**: meaning shifts, omissions, additions, wrong referent, wrong attribution (who said what), wrong tense/modality (e.g. "could well argue" rendered as a certainty), number/negation errors.
2. **Register and style against the style sheet below**: the translation is deliberately literal in meaning, Torah-scholarly in wording (the Hebrew a talmid hakham or scholar of Hasidism would write, with established rabbinic and Hasidic expressions) and literary in flow. That register is a choice, not an error. Flag only departures *from the style sheet*: calques from English syntax, stilted or unidiomatic Hebrew, unexplained abstractions, loanwords where the glossary fixes a Hebrew term, and any explanatory gloss that is not in the English.
3. **Terminology**: any English term in the glossary rendered differently from its fixed Hebrew.

Do not flag: the author's English metaphors kept in Hebrew (deliberate); Yiddish words kept in Yiddish (deliberate); sentences split or merged (allowed); footnote markers (^12^); bracketed editorial flags or [bracketed words] awaiting checking against a scan.

Severity: `critical` = a reader of the Hebrew would take away a different claim than a reader of the English; `major` = meaning preserved but distorted in emphasis, attribution or nuance, or a glossary term broken; `minor` = wording that a careful editor would change but no reader would be misled.

Names and titles: after a person's first mention a shortened form is house style (e.g. המגיד for "the Maggid of Mezritch", החוזה for "the Seer of Lublin") and is not a terminology error; the required terms list gives the full form.

Answer format — a JSON object: {"id": the paragraph id, "overall": {"fidelity": 1-5, "register": 1-5, "terminology": 1-5}, "findings": [{"category", "severity", "he_span", "en_span", "note"}], "confidence": 0.0-1.0}. Each overall score is an integer from 1 to 5 (5 = no problems, 1 = seriously wrong); never use another scale. `category` is one of meaning-shift, omission, addition, attribution, modality, register, calque, gloss, terminology, other. `note` is one sentence in English stating the problem, with no rewrite.

Answer ONLY with JSON matching the schema. If there are no findings, return an empty `findings` array with `overall` scores. Quote the exact Hebrew span for every finding."""

USER_TMPL = """PARAGRAPH ID: {id}   KIND: {kind}   ALIGNMENT: {align}

REQUIRED TERMS IN THIS PARAGRAPH (English → fixed Hebrew, inflect as grammar requires):
{terms}

ENGLISH SOURCE:
{en}

HEBREW TRANSLATION:
{he}"""

NO_REWRITE = "\n\nDo not propose a rewrite; state the problem only. Every he_span must be copied exactly from the Hebrew above."

CATEGORIES = ["meaning-shift", "omission", "addition", "attribution", "modality", "register", "calque", "gloss", "terminology", "other"]
SEVERITIES = ["critical", "major", "minor"]

SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "overall": {"type": "object", "properties": {k: {"type": "integer", "enum": [1, 2, 3, 4, 5]} for k in ("fidelity", "register", "terminology")},
                    "required": ["fidelity", "register", "terminology"], "additionalProperties": False},
        "findings": {"type": "array", "items": {"type": "object", "properties": {
            "category": {"type": "string", "enum": CATEGORIES},
            "severity": {"type": "string", "enum": SEVERITIES},
            "he_span": {"type": "string"}, "en_span": {"type": "string"}, "note": {"type": "string"}},
            "required": ["category", "severity", "he_span", "en_span", "note"], "additionalProperties": False}},
        "confidence": {"type": "number"},
    },
    "required": ["id", "overall", "findings", "confidence"], "additionalProperties": False,
}

DICTA_PROMPT = """לפניך פסקה מתוך ספר עיון בעברית. אל תתקן ואל תנסח מחדש. ציין רק: (א) משפטים שאינם נשמעים כעברית טבעית (תחביר מתורגם, סדר מילים זר, צירופים שאינם בשימוש); (ב) מילים לא ברורות לקורא משכיל שאינו מומחה. לכל פריט: הציטוט המדויק, סוג הבעיה (תחביר / מילה / צירוף), וחומרה (קלה / בינונית / חמורה). השב ב-JSON בלבד לפי המבנה: {"findings":[{"he_span":"","type":"","severity":"","note":""}],"naturalness":1-5}"""

DICTA_SCHEMA = {
    "type": "object",
    "properties": {"findings": {"type": "array", "items": {"type": "object", "properties": {
        "he_span": {"type": "string"}, "type": {"type": "string"}, "severity": {"type": "string"}, "note": {"type": "string"}},
        "required": ["he_span", "type", "severity", "note"]}}, "naturalness": {"type": "integer"}},
    "required": ["findings", "naturalness"],
}

HEB_WORD = re.compile(r"[א-ת][א-ת֑-ׇ\"'׳״]*")


def system_prompt():
    style = (EVAL / "style-sheet.md").read_text(encoding="utf-8")
    terms = (EVAL / "decided-terms.md").read_text(encoding="utf-8")
    return f"{SYSTEM_HEAD}\n\n---\n\n{terms}\n\n---\n\n{style}"


def load_glossary():
    g = json.loads((ROOT / "glossary" / "glossary-book.json").read_text(encoding="utf-8"))
    out = []
    for t in g["terms"]:
        for s in [t["source"]] + t.get("aliases", []):
            if len(s) > 2:
                out.append((re.compile(r"(?<![\w-])" + re.escape(s) + r"(?![\w-])", re.I), t["source"], t["target"]))
    return out


def required_terms(en, glossary):
    seen, rows = set(), []
    for pat, src, tgt in glossary:
        if src not in seen and pat.search(en):
            seen.add(src)
            rows.append(f"- {src} → {tgt}")
    return "\n".join(rows) or "(none)"


def user_prompt(rec, glossary):
    return USER_TMPL.format(id=rec["id"], kind=rec["kind"], align=rec["align"],
                            terms=required_terms(rec["en"], glossary), en=rec["en"], he=rec["he"])


def _norm(s):
    return re.sub(r"\s+", " ", s).strip()


def validate(resp, he, dicta=False):
    """Return a list of problems (empty = valid). A note with more than 8 Hebrew words is a rewrite;
    a he_span not present in the paragraph is invented."""
    problems = []
    if not isinstance(resp, dict) or not isinstance(resp.get("findings"), list):
        return ["response is not an object with a findings array"]
    if dicta:
        if not isinstance(resp.get("naturalness"), int) or not 1 <= resp["naturalness"] <= 5:
            problems.append("naturalness must be an integer 1–5")
    else:
        ov = resp.get("overall") or {}
        for k in ("fidelity", "register", "terminology"):
            if not isinstance(ov.get(k), int) or not 1 <= ov[k] <= 5:
                problems.append(f"overall.{k} must be an integer 1–5")
    text = _norm(he)
    for i, f in enumerate(resp["findings"]):
        span = _norm(f.get("he_span", ""))
        if not span or span not in text:
            problems.append(f"finding {i}: he_span is not an exact substring of the Hebrew")
        if len(HEB_WORD.findall(f.get("note", ""))) > 8:
            problems.append(f"finding {i}: note contains a Hebrew rewrite")
        if not dicta:
            if f.get("category") not in CATEGORIES:
                problems.append(f"finding {i}: unknown category {f.get('category')!r}")
            if f.get("severity") not in SEVERITIES:
                problems.append(f"finding {i}: unknown severity {f.get('severity')!r}")
    return problems


def drop_invalid(resp, he, dicta=False):
    """After the one re-ask: keep the valid findings, record how many were dropped."""
    text = _norm(he)
    keep = [f for f in resp.get("findings", [])
            if _norm(f.get("he_span", "")) and _norm(f.get("he_span", "")) in text
            and len(HEB_WORD.findall(f.get("note", ""))) <= 8
            and (dicta or (f.get("category") in CATEGORIES and f.get("severity") in SEVERITIES))]
    if not dicta:
        ov = resp.get("overall") or {}
        resp["overall"] = {k: (ov.get(k) if isinstance(ov.get(k), int) and 1 <= ov[k] <= 5 else None)
                           for k in ("fidelity", "register", "terminology")}
    resp["dropped_findings"] = len(resp.get("findings", [])) - len(keep)
    resp["findings"] = keep
    return resp
