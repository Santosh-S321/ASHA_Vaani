"""Danger-sign check 1 of 2: keyword list with simple negation handling.

The second check is the LLM (app/extract.py), which may only answer with IDs from this list.
A sign is flagged if EITHER check finds it, because a missed sign costs double.
"""
import json
import re
from pathlib import Path

_DATA = json.loads((Path(__file__).parent / "data" / "danger_signs.json").read_text(encoding="utf-8"))
SIGNS: list[dict] = _DATA["signs"]
SOURCES: list[str] = _DATA["sources"]
BY_ID = {s["id"]: s for s in SIGNS}

NEGATIONS = {"nahi", "nahin", "nhi", "नहीं", "नही", "no", "not", "illa", "ಇಲ್ಲ", "ಇಲ್ಲಾ", "without", "bina", "बिना"}
PUNCT = ",.?!।;:\"'()"


def _is_latin(s: str) -> bool:
    return bool(re.fullmatch(r"[a-z0-9 \-]+", s))


def _matches(text: str, kw: str):
    if _is_latin(kw):
        return [m.span() for m in re.finditer(r"(?<![a-z])" + re.escape(kw) + r"(?![a-z])", text)]
    return [m.span() for m in re.finditer(re.escape(kw), text)]


def _negated(text: str, start: int, end: int, kw: str) -> bool:
    kw_tokens = set(kw.split())
    before = [t.strip(PUNCT) for t in text[:start].split()[-2:]]
    rest = text[end:]
    glued = re.match(r"\S*", rest).group().strip(PUNCT)   # e.g. Kannada "ಜ್ವರವಿಲ್ಲ"
    if glued.endswith(("illa", "ಇಲ್ಲ", "ಿಲ್ಲ")):
        return True
    after = [t.strip(PUNCT) for t in rest.split()[:3]]
    return any(t in NEGATIONS and t not in kw_tokens for t in before + after)


def detect(text: str, btype: str | None = None) -> list[str]:
    """Return danger-sign IDs mentioned (and not negated) in the text."""
    t = text.lower()
    found = []
    for sign in SIGNS:
        if btype and btype not in sign["applies_to"]:
            continue
        for kw in sign["keywords"]:
            kwl = kw.lower()
            if any(not _negated(t, s, e, kwl) for s, e in _matches(t, kwl)):
                found.append(sign["id"])
                break
    return found


def label(sign_id: str, lang: str) -> str:
    sign = BY_ID.get(sign_id)
    if not sign:
        return sign_id
    return sign["label"].get(lang) or sign["label"]["en"]
