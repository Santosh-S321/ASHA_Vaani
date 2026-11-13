"""Conversation state machine: AWAIT_ID -> DICTATION -> READBACK -> (save) -> AWAIT_ID.

Every reply is a fixed template. Danger signs are checked on every utterance, in every state,
and the alert is always spoken first.
"""
import uuid
from datetime import date, datetime

from . import beneficiaries, danger, schedule
from .extract import Extraction, is_advice_request
from .normalize import weight_plausible
from .templates import say, spoken_date, spoken_id, spoken_vaccines, spoken_weight, word

REQUIRED = ["visit_type", "weight_kg"]
DEFAULT_VISIT = {"newborn": "HBNC", "pregnant": "ANC", "child": "IMMUNISATION"}


def blank_form() -> dict:
    return {"visit_type": None, "weight_kg": None, "vaccines_given_today": [], "vaccines_due": [],
            "next_visit_date": None, "danger_signs": [], "notes": []}


class Session:
    def __init__(self, lang: str, extractor, store, today: date | None = None):
        self.lang = lang
        self.extractor = extractor
        self.store = store
        self.today = today or date.today()
        self.register = beneficiaries.load(self.today)
        self.state = "AWAIT_ID"
        self.b: dict | None = None
        self.form = blank_form()
        self.next_spoken = False
        self.pending_signs: list[str] = []
        self.last_saved: dict | None = None

    # ---------- helpers ----------
    def t(self, key: str, **kw) -> str:
        return say(self.lang, key, **kw)

    def _ctx(self) -> dict:
        return {"beneficiary": self._b_with_today(), "today": self.today, "state": self.state, "form": self.form}

    def _b_with_today(self) -> dict:
        b = dict(self.b)
        b["given"] = {**self.b["given"], **{c: self.today for c in self.form["vaccines_given_today"]}}
        return b

    def _recompute(self):
        b = self._b_with_today()
        self.form["vaccines_due"] = schedule.due_vaccines(b, self.today)
        if not self.next_spoken:
            self.form["next_visit_date"] = schedule.next_visit(b, self.today)

    def _load(self, b: dict):
        self.b = b
        self.form = blank_form()
        self.form["visit_type"] = DEFAULT_VISIT.get(b["type"])
        self.form["danger_signs"] = list(self.pending_signs)
        self.pending_signs = []
        self.next_spoken = False
        self._recompute()

    def _alert(self, signs: list[str]) -> str:
        labels = word(self.lang, "and").join(danger.label(s, self.lang) for s in signs)
        return self.t("danger_alert", signs=labels)

    # ---------- public ----------
    def start(self) -> list[str]:
        return [self.t("greet")]

    def snapshot(self) -> dict:
        f = dict(self.form)
        f["next_visit_date"] = f["next_visit_date"].isoformat() if f["next_visit_date"] else None
        f["danger_labels"] = [danger.label(s, "en") for s in f["danger_signs"]]
        return {"state": self.state,
                "beneficiary": beneficiaries.public_view(self.b, self.lang) if self.b else None,
                "form": f}

    async def handle(self, text: str) -> list[str]:
        text = (text or "").strip()
        out: list[str] = []
        self.last_saved = None
        if not text:
            return out

        just_found = False
        if self.state == "AWAIT_ID":
            b = beneficiaries.find(text, self.register)
            if not b:
                signs = [s for s in danger.detect(text) if s not in self.pending_signs]
                if signs:
                    self.pending_signs += signs
                    out.append(self._alert(signs))
                out.append(self.t("advice") if is_advice_request(text) else self.t("not_found"))
                return out
            self._load(b)
            name = b["name"].get(self.lang) or b["name"]["en"]
            out.append(self.t("found", name=name, id=spoken_id(b["id"]), btype=word(self.lang, "btype")[b["type"]]))
            self.state = "DICTATION"
            just_found = True

        ex: Extraction = await self.extractor.extract(text, self._ctx())

        signs = list(dict.fromkeys(danger.detect(text, self.b["type"]) + ex.danger_sign_ids))
        new = [s for s in signs if s in danger.BY_ID and s not in self.form["danger_signs"]]
        if new:
            self.form["danger_signs"] += new
            out.insert(0, self._alert(new))   # the alert is always spoken first

        advice = ex.intent == "advice_request" or is_advice_request(text)
        if advice:
            out.append(self.t("advice"))

        changes, problem = self._apply(ex)

        if self.state == "DICTATION":
            if problem:
                out.append(problem)
                return out
            missing = [f for f in REQUIRED if self.form[f] is None]
            if missing:
                if not (just_found and not changes) and not advice:
                    out.append(self.t("ask_" + missing[0]))
            else:
                out.append(self._readback())
                self.state = "READBACK"
        elif self.state == "READBACK":
            if problem:
                out.append(problem)
            elif changes:
                out.append(self._updated(changes))
            elif ex.intent == "confirm":
                out.append(self._save())
            elif ex.intent == "reject":
                out.append(self.t("what_wrong"))
            elif not new and not advice:
                out.append(self.t("repeat"))
        return out

    # ---------- steps ----------
    def _apply(self, ex: Extraction) -> tuple[list[tuple[str, str]], str | None]:
        changes, problem = [], None
        L = self.lang
        if ex.weight_kg is not None:
            if not weight_plausible(ex.weight_kg, self.b["type"]):
                problem = self.t("weight_check", w=spoken_weight(ex.weight_kg, L))
            elif ex.weight_kg != self.form["weight_kg"]:
                self.form["weight_kg"] = ex.weight_kg
                changes.append(("weight_kg", spoken_weight(ex.weight_kg, L) + (" किलो" if L == "hi" else " ಕಿಲೋ")))
        if ex.visit_type and ex.visit_type != self.form["visit_type"]:
            self.form["visit_type"] = ex.visit_type
            changes.append(("visit_type", word(L, "visit")[ex.visit_type]))
        vacc = list(self.form["vaccines_given_today"])
        vacc += [c for c in ex.vaccines_given if c not in vacc]
        vacc = [c for c in vacc if c not in ex.vaccines_removed]
        if vacc != self.form["vaccines_given_today"]:
            self.form["vaccines_given_today"] = vacc
            changes.append(("vaccines_given_today", spoken_vaccines(vacc, L)))
        if ex.next_visit_date and ex.next_visit_date != self.form["next_visit_date"]:
            self.form["next_visit_date"] = ex.next_visit_date
            self.next_spoken = True
            changes.append(("next_visit_date", spoken_date(ex.next_visit_date, L)))
        for n in ex.notes:
            if n not in self.form["notes"]:
                self.form["notes"].append(n)
        self._recompute()
        return changes, problem

    def _readback(self) -> str:
        L, f = self.lang, self.form
        danger_txt = ""
        if f["danger_signs"]:
            danger_txt = say(L, "readback_danger",
                             signs=word(L, "and").join(danger.label(s, L) for s in f["danger_signs"]))
        return self.t(
            "readback",
            id=spoken_id(self.b["id"]),
            visit_type=word(L, "visit").get(f["visit_type"], word(L, "missing")),
            weight=spoken_weight(f["weight_kg"], L) if f["weight_kg"] is not None else word(L, "missing"),
            given=spoken_vaccines(f["vaccines_given_today"], L),
            due=spoken_vaccines(f["vaccines_due"], L),
            next=spoken_date(f["next_visit_date"], L),
            danger=danger_txt,
        )

    def _updated(self, changes: list[tuple[str, str]]) -> str:
        fields = word(self.lang, "fields")
        items = ", ".join(self.t("change_item", field=fields[k], value=v) for k, v in changes)
        return self.t("updated", changes=items)

    def _save(self) -> str:
        f = self.form
        record = {
            "record_id": uuid.uuid4().hex[:12],
            "beneficiary_id": self.b["id"],
            "beneficiary_name": self.b["name"]["en"],
            "beneficiary_type": self.b["type"],
            "visit_type": f["visit_type"],
            "weight_kg": f["weight_kg"],
            "vaccines_given_today": f["vaccines_given_today"],
            "vaccines_due": f["vaccines_due"],
            "next_visit_date": f["next_visit_date"].isoformat(),
            "danger_signs": f["danger_signs"],
            "danger_labels": [danger.label(s, "en") for s in f["danger_signs"]],
            "notes": f["notes"],
            "language": self.lang,
            "saved_at": datetime.now().isoformat(timespec="seconds"),
        }
        self.store.save(record)
        self.last_saved = record
        msg = self.t("saved", next=spoken_date(f["next_visit_date"], self.lang),
                     flag=word(self.lang, "saved_flag") if f["danger_signs"] else "")
        self.state, self.b, self.form = "AWAIT_ID", None, blank_form()
        return msg
