"""Turns spoken numbers, weights and relative dates into clean values.

Handles English, Hindi and Kannada number words (Latin and native script), native digits,
and phrases like "do point aath kilo" -> 2.8 or "15 din baad" -> today + 15 days.
"""
import re
from datetime import date, timedelta

NATIVE_DIGITS = str.maketrans("०१२३४५६७८९೦೧೨೩೪೫೬೭೮೯", "01234567890123456789")

NUM_WORDS = {
    # English
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    # Hindi (Latin)
    "shunya": 0, "sunya": 0, "ek": 1, "do": 2, "teen": 3, "char": 4, "chaar": 4,
    "paanch": 5, "panch": 5, "chhe": 6, "chhah": 6, "chah": 6, "saat": 7,
    "aath": 8, "nau": 9, "das": 10,
    # Hindi (Devanagari)
    "शून्य": 0, "एक": 1, "दो": 2, "तीन": 3, "चार": 4, "पांच": 5, "पाँच": 5,
    "छह": 6, "छः": 6, "सात": 7, "आठ": 8, "नौ": 9, "दस": 10,
    # Kannada (Latin)
    "sonne": 0, "ondu": 1, "eradu": 2, "mooru": 3, "naalku": 4, "nalku": 4,
    "aidu": 5, "aaru": 6, "elu": 7, "yelu": 7, "entu": 8, "ombattu": 9, "hattu": 10,
    # Kannada (script)
    "ಸೊನ್ನೆ": 0, "ಒಂದು": 1, "ಎರಡು": 2, "ಮೂರು": 3, "ನಾಲ್ಕು": 4, "ಐದು": 5,
    "ಆರು": 6, "ಏಳು": 7, "ಎಂಟು": 8, "ಒಂಬತ್ತು": 9, "ಹತ್ತು": 10,
}
POINT_WORDS = {"point", "पॉइंट", "पॉइन्ट", "प्वाइंट", "दशमलव", "dashamlav", "ಪಾಯಿಂಟ್", "ದಶಮಾಂಶ"}
PUNCT = ",.?!।;:\"'()"


def _core(tok: str) -> str:
    return tok.strip(PUNCT).lower()


def _is_num_token(core: str) -> bool:
    return core in NUM_WORDS or core in POINT_WORDS or core.isdigit()


def _group_to_str(group: list[str]) -> str:
    """['2'|'do', 'point', 'aath'] -> '2.8';  ['ek','shunya','char','do'] -> '1042'."""
    parts, cur = [], []
    for g in group:
        if g in POINT_WORDS:
            parts.append(cur)
            cur = []
        else:
            cur.append(g)
    parts.append(cur)

    def join(tokens):
        out = ""
        for t in tokens:
            out += t if t.isdigit() else str(NUM_WORDS[t])
        return out

    left = join(parts[0])
    if len(parts) > 1 and parts[1]:
        return f"{left or '0'}.{join(parts[1])}"
    return left


def words_to_digits(text: str) -> str:
    """Replace runs of spoken number words with digits. Keeps all other words."""
    text = text.translate(NATIVE_DIGITS)
    tokens = text.split()
    out, group = [], []
    for tok in tokens:
        core = _core(tok)
        if _is_num_token(core):
            group.append(core)
            continue
        if group:
            out.append(_flush(group))
            group = []
        out.append(tok)
    if group:
        out.append(_flush(group))
    return " ".join(out)


def _flush(group: list[str]) -> str:
    # a lone "point" is a normal word, not a number
    if all(g in POINT_WORDS for g in group):
        return " ".join(group)
    return _group_to_str([g for g in group])


KG_UNITS = r"(?:kgs?|kilos?|kilogram|kilograms|किलो|किलोग्राम|ಕೆಜಿ|ಕಿಲೋ|ಕಿಲೊ)"
GRAM_UNITS = r"(?:g|gm|gms|gram|grams|ग्राम|ಗ್ರಾಂ)"
WEIGHT_WORDS = r"(?:weight|wajan|vajan|vazan|wazan|वज़न|वजन|ತೂಕ|tooka|tuka)"


def parse_weight(text: str) -> float | None:
    t = words_to_digits(text).lower()
    m = re.search(r"(\d+)\s*" + KG_UNITS + r"\s*(\d{1,3})\s*" + GRAM_UNITS + r"(?![a-z])", t)
    if m:  # "2 kilo 800 gram"
        return round(int(m.group(1)) + int(m.group(2)) / 1000, 3)
    m = re.search(r"(\d+(?:\.\d+)?)\s*" + KG_UNITS + r"(?![a-z])", t)
    if m:
        return float(m.group(1))
    m = re.search(r"(\d{3,4})\s*" + GRAM_UNITS + r"(?![a-z])", t)
    if m:
        return int(m.group(1)) / 1000
    m = re.search(WEIGHT_WORDS + r"\D{0,15}?(\d+(?:\.\d+)?)", t)
    if m:
        return float(m.group(1))
    return None


WEIGHT_RANGES = {"newborn": (0.5, 6.0), "child": (1.0, 30.0), "pregnant": (30.0, 150.0)}


def weight_plausible(weight: float, btype: str | None) -> bool:
    lo, hi = WEIGHT_RANGES.get(btype or "", (0.5, 150.0))
    return lo <= weight <= hi


NEXT_CONTEXT = (
    "next", "agla", "agli", "agle", "अगला", "अगली", "अगले", "visit", "विज़िट", "विजिट",
    "aana", "aaungi", "aaenge", "आऊंगी", "आना", "ಮುಂದಿನ", "mundina", "ಭೇಟಿ", "bheti", "baad", "बाद",
)


def parse_next_visit(text: str, today: date) -> date | None:
    """Only reads a date when she is talking about the next visit."""
    t = words_to_digits(text).lower()
    if not any(k in t for k in NEXT_CONTEXT):
        return None
    m = re.search(r"(\d+)\s*(?:din|dino|दिन|dina|dinagalu|ದಿನ|days?)", t)
    if m:
        return today + timedelta(days=int(m.group(1)))
    m = re.search(r"(\d+)\s*(?:hafte|hafta|हफ्ते|हफ़्ते|सप्ताह|weeks?|vaara|ವಾರ)", t)
    if m:
        return today + timedelta(weeks=int(m.group(1)))
    if any(k in t for k in ("agle hafte", "next week", "अगले हफ्ते", "अगले हफ़्ते", "mundina vaara", "ಮುಂದಿನ ವಾರ")):
        return today + timedelta(days=7)
    if any(k in t for k in ("parso", "परसों", "naadiddu", "ನಾಡಿದ್ದು")):
        return today + timedelta(days=2)
    if re.search(r"(?<![a-z])(kal|tomorrow|naale)(?![a-z])", t) or "कल" in t or "ನಾಳೆ" in t:
        return today + timedelta(days=1)
    return None
