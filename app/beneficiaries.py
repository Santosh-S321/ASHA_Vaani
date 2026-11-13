"""Synthetic beneficiary register and lookup by spoken ID or name."""
import json
import re
from datetime import date, timedelta
from pathlib import Path

from .normalize import words_to_digits

_RAW = json.loads((Path(__file__).parent / "data" / "beneficiaries.json").read_text(encoding="utf-8"))["beneficiaries"]


def load(today: date | None = None) -> dict[str, dict]:
    today = today or date.today()
    out = {}
    for r in _RAW:
        b = {
            "id": r["id"],
            "type": r["type"],
            "name": r["name"],
            "aliases": [a.lower() for a in r["aliases"]],
            "given": {code: today - timedelta(days=d) for code, d in r["given"].items()},
        }
        if "dob_days_ago" in r:
            b["dob"] = today - timedelta(days=r["dob_days_ago"])
        if "lmp_days_ago" in r:
            b["lmp"] = today - timedelta(days=r["lmp_days_ago"])
        out[b["id"]] = b
    return out


def find(text: str, register: dict[str, dict]) -> dict | None:
    t = words_to_digits(text).lower()
    compact = re.sub(r"(?<=\d)[\s\-]+(?=\d)", "", t)   # "1 0 4 2" -> "1042"
    for num in re.findall(r"\d{3,6}", compact):
        if num in register:
            return register[num]
    for b in register.values():
        if any(a in t for a in b["aliases"]):
            return b
    return None


def public_view(b: dict, lang: str) -> dict:
    return {"id": b["id"], "type": b["type"], "name": b["name"].get(lang) or b["name"]["en"]}
