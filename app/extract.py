"""Turns one utterance into field updates.

RuleExtractor works offline and handles the common phrasings. LLMExtractor asks an LLM for
strict JSON and merges it with the rules: rules win for explicit numbers, the LLM fills gaps,
and danger signs from both are kept (union).
"""
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date

from . import config, danger, schedule
from .normalize import parse_next_visit, parse_weight, words_to_digits

log = logging.getLogger("extract")
PUNCT = ",.?!।;:\"'()"


@dataclass
class Extraction:
    weight_kg: float | None = None
    visit_type: str | None = None
    vaccines_given: list[str] = field(default_factory=list)
    vaccines_removed: list[str] = field(default_factory=list)
    next_visit_date: date | None = None
    notes: list[str] = field(default_factory=list)
    danger_sign_ids: list[str] = field(default_factory=list)
    intent: str | None = None   # confirm | reject | advice_request

    def has_fields(self) -> bool:
        return any([self.weight_kg is not None, self.visit_type, self.vaccines_given,
                    self.vaccines_removed, self.next_visit_date, self.notes])


VACCINE_PATTERNS = [
    ("BCG", r"bcg|बीसीजी|ಬಿಸಿಜಿ"),
    ("OPV", r"opv|bopv|polio|पोलियो|ಪೋಲಿಯೋ|ಪೋಲಿಯೊ"),
    ("Penta", r"pentavalent|penta|पेंटा|ಪೆಂಟಾ"),
    ("RVV", r"rotavirus|rota|rvv|रोटा|ರೋಟಾ"),
    ("fIPV", r"fipv|ipv"),
    ("PCV", r"pcv"),
    ("MR", r"measles|khasra|mr|खसरा|ದಡಾರ"),
    ("HepB", r"hepatitis\s*b|hep\s*b|हेपेटाइटिस"),
    ("Td", r"tetanus|tt|td|टीटी|ಟಿಟಿ"),
    ("DPT", r"dpt"),
    ("VitA", r"vitamin\s*a|विटामिन ए"),
]
GIVEN_WORDS = ["laga", "lagaya", "lagi", "lag gaya", "lag gayi", "diya", "de diya", "given", "gave", "done",
               "लगा", "लगाया", "लगी", "दिया", "दी", "ಹಾಕಿದೆ", "ಹಾಕಿದ್ದೇವೆ", "ಹಾಕಲಾಗಿದೆ", "ಕೊಟ್ಟಿದೆ",
               "ಕೊಟ್ಟೆ", "haakide", "kottide"]
NOT_GIVEN = ["nahi laga", "nahin laga", "nahi lagaya", "nahi diya", "not given", "नहीं लगा", "नहीं दिया",
             "ಹಾಕಿಲ್ಲ", "ಕೊಟ್ಟಿಲ್ಲ", "haakilla"]
VISIT_TYPE_WORDS = [
    ("ANC", ["anc", "antenatal", "एएनसी", "ಎಎನ್‌ಸಿ"]),
    ("HBNC", ["hbnc", "newborn visit", "नवजात विज़िट", "नवजात विजिट", "ನವಜಾತ ಶಿಶು ಭೇಟಿ"]),
    ("PNC", ["pnc", "postnatal", "delivery ke baad", "प्रसव के बाद", "ಹೆರಿಗೆ ನಂತರ"]),
    ("IMMUNISATION", ["immunisation", "immunization", "vaccination visit", "टीकाकरण", "ಲಸಿಕಾ ಭೇಟಿ"]),
]
YES = {"haan", "haa", "han", "ha", "हाँ", "हां", "हा", "sahi", "सही", "save", "सेव", "theek", "ठीक",
       "ok", "okay", "yes", "correct", "houdu", "haudu", "ಹೌದು", "sari", "ಸರಿ", "ಸೇವ್"}
NO = {"nahi", "nahin", "nhi", "नहीं", "नही", "no", "illa", "ಇಲ್ಲ", "galat", "गलत", "wrong", "ತಪ್ಪು", "tappu"}
MEDICINE = ["dawai", "dawa", "davai", "दवा", "दवाई", "medicine", "tablet", "goli", "गोली", "dose", "खुराक",
            "ilaj", "ilaaj", "इलाज", "treatment", "ಔಷಧಿ", "ಮಾತ್ರೆ", "ಚಿಕಿತ್ಸೆ", "syrup", "सिरप"]
QUESTION = ["kya", "kaun", "kitni", "kitna", "kaise", "should", "what", "which", "how much", "क्या", "कौन",
            "कितनी", "कितना", "कैसे", "ಏನು", "ಎಷ್ಟು", "ಯಾವ", "?"]


def _tokens(text: str) -> set[str]:
    return {t.strip(PUNCT) for t in text.lower().split()}


def is_advice_request(text: str) -> bool:
    t = text.lower()
    return any(m in t for m in MEDICINE) and any(q in t for q in QUESTION)


def confirm_intent(text: str) -> str | None:
    toks = _tokens(text)
    if toks & NO:
        return "reject"
    if toks & YES or "save karo" in text.lower():
        return "confirm"
    return None


def _vaccines(t: str, b: dict, today: date) -> list[str]:
    found = []
    for series, pat in VACCINE_PATTERNS:
        for m in re.finditer(r"(?<![a-z])(?:" + pat + r")(?![a-z])(?:\s*-?\s*(\d))?", t):
            dose = int(m.group(1)) if m.group(1) and series != "BCG" else None
            code = schedule.resolve_series(series, b, today, dose)
            if code and code not in found:
                found.append(code)
    return found


class RuleExtractor:
    async def extract(self, text: str, ctx: dict) -> Extraction:
        return self.extract_sync(text, ctx)

    def extract_sync(self, text: str, ctx: dict) -> Extraction:
        b, today = ctx["beneficiary"], ctx["today"]
        t = words_to_digits(text).lower()
        ex = Extraction()
        ex.weight_kg = parse_weight(text)
        ex.next_visit_date = parse_next_visit(text, today)
        for vt, words in VISIT_TYPE_WORDS:
            if any(re.search(r"(?<![a-z])" + re.escape(w) + r"(?![a-z])", t) for w in words):
                ex.visit_type = vt
                break
        codes = _vaccines(t, b, today)
        if codes:
            if any(n in t for n in NOT_GIVEN):
                ex.vaccines_removed = codes
            elif any(g in t for g in GIVEN_WORDS):
                ex.vaccines_given = codes
        if re.search(r"(?<![a-z])ifa(?![a-z])|आयरन|iron|ಕಬ್ಬಿಣ", t):
            ex.notes.append("IFA tablets given" if any(g in t for g in GIVEN_WORDS) else "IFA tablets discussed")
        ex.danger_sign_ids = danger.detect(text, b["type"])
        if is_advice_request(text):
            ex.intent = "advice_request"
        elif not ex.has_fields():
            ex.intent = confirm_intent(text)
        return ex


SYSTEM_PROMPT = """You extract structured data from an ASHA health worker's spoken home-visit notes.
Speech may mix Hindi or Kannada with English and may contain speech-recognition errors.
Return ONLY one JSON object with exactly these keys:
- "weight_kg": number or null. Convert spoken numbers ("do point aath kilo" = 2.8; "2 kilo 800 gram" = 2.8).
- "visit_type": "ANC", "HBNC", "PNC", "IMMUNISATION" or null. Only if she states the visit type.
- "vaccines_given": codes given TODAY, only from: {codes}. If she names a vaccine without a dose, use the first matching code from the doses still due: {due}.
- "vaccines_removed": codes she says were NOT given, same code list.
- "next_visit_date": "YYYY-MM-DD" or null. Today is {today}. Convert relative dates ("15 din baad").
- "notes": short English notes for other stated facts (e.g. "IFA tablets given"). Never add advice.
- "danger_sign_ids": ids from this list that she reports as PRESENT now. Ignore negated ones ("bukhar nahi hai"). {signs}
- "intent": "confirm" if she confirms the read-back is correct or asks to save; "reject" if she says it is wrong without giving the fix; "advice_request" if she asks what medicine, dose or treatment to give; else null.
Never diagnose or suggest treatment. Never invent values that were not said."""


class LLMExtractor:
    def __init__(self):
        from openai import AsyncOpenAI
        self.client = AsyncOpenAI(api_key=config.LLM_API_KEY, base_url=config.LLM_BASE_URL,
                                  timeout=config.LLM_TIMEOUT_S, max_retries=0)
        self.rules = RuleExtractor()

    async def extract(self, text: str, ctx: dict) -> Extraction:
        rules = self.rules.extract_sync(text, ctx)
        try:
            data = await self._ask(text, ctx)
        except Exception as e:  # noqa: BLE001 - any LLM failure falls back to rules
            log.warning("LLM extraction failed, using rules only: %s", e)
            return rules
        return _merge(rules, data)

    async def _ask(self, text: str, ctx: dict) -> dict:
        b, today = ctx["beneficiary"], ctx["today"]
        signs = "; ".join(f'{s["id"]} = {s["label"]["en"]}' for s in danger.SIGNS)
        system = SYSTEM_PROMPT.format(codes=", ".join(schedule.ALL_CODES),
                                      due=", ".join(schedule.due_vaccines(b, today)) or "none",
                                      today=today.isoformat(), signs=signs)
        user = json.dumps({"beneficiary_type": b["type"], "stage": ctx["state"],
                           "current_record": ctx["form"], "utterance": text}, ensure_ascii=False, default=str)
        resp = await self.client.chat.completions.create(
            model=config.LLM_MODEL,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            response_format={"type": "json_object"},
            temperature=0,
        )
        content = resp.choices[0].message.content or "{}"
        content = content.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
        return json.loads(content)


def _merge(rules: Extraction, d: dict) -> Extraction:
    ex = rules
    if ex.weight_kg is None and isinstance(d.get("weight_kg"), (int, float)):
        ex.weight_kg = float(d["weight_kg"])
    if ex.visit_type is None and d.get("visit_type") in ("ANC", "HBNC", "PNC", "IMMUNISATION"):
        ex.visit_type = d["visit_type"]
    valid = set(schedule.ALL_CODES)
    for key in ("vaccines_given", "vaccines_removed"):
        for c in d.get(key) or []:
            if c in valid and c not in getattr(ex, key):
                getattr(ex, key).append(c)
    if ex.next_visit_date is None and d.get("next_visit_date"):
        try:
            ex.next_visit_date = date.fromisoformat(d["next_visit_date"])
        except (TypeError, ValueError):
            pass
    for n in d.get("notes") or []:
        if isinstance(n, str) and n and n not in ex.notes:
            ex.notes.append(n[:120])
    for s in d.get("danger_sign_ids") or []:
        if s in danger.BY_ID and s not in ex.danger_sign_ids:
            ex.danger_sign_ids.append(s)
    if ex.intent is None and d.get("intent") in ("confirm", "reject", "advice_request"):
        ex.intent = d["intent"]
    if ex.intent == "confirm" and ex.has_fields():
        ex.intent = None   # a fix in the same breath is an edit, not a confirmation
    return ex


def make_extractor():
    return LLMExtractor() if config.llm_enabled() else RuleExtractor()
