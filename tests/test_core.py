"""Offline tests: no Gnani or LLM keys needed. Run with:  pytest -q"""
import asyncio
from datetime import date, timedelta

import pytest
from cryptography.fernet import Fernet

from app import beneficiaries, danger, schedule
from app.dialogue import Session
from app.extract import RuleExtractor, is_advice_request
from app.normalize import parse_next_visit, parse_weight, words_to_digits
from app.store import Store

TODAY = date(2026, 11, 13)


# ---------- normaliser ----------
@pytest.mark.parametrize("text,expected", [
    ("vajan do point aath kilo hai", 2.8),
    ("weight 2.8 kg", 2.8),
    ("बच्चे का वज़न दो पॉइंट आठ किलो", 2.8),
    ("2 kilo 800 gram", 2.8),
    ("ತೂಕ ಎರಡು ಪಾಯಿಂಟ್ ಒಂಬತ್ತು ಕಿಲೋ", 2.9),
    ("2900 gram", 2.9),
    ("no, weight is 2.8 kilo", 2.8),
])
def test_parse_weight(text, expected):
    assert parse_weight(text) == pytest.approx(expected)


def test_words_to_digits_id():
    assert "1042" in words_to_digits("ID ek shunya char do")
    assert "1042" in words_to_digits("ಐಡಿ ಒಂದು ಸೊನ್ನೆ ನಾಲ್ಕು ಎರಡು")


def test_next_visit_dates():
    assert parse_next_visit("agli visit 15 din baad", TODAY) == TODAY + timedelta(days=15)
    assert parse_next_visit("next visit agle hafte", TODAY) == TODAY + timedelta(days=7)
    assert parse_next_visit("kal bukhar tha", TODAY) is None   # no next-visit context


# ---------- danger signs ----------
def test_danger_positive_and_negated():
    assert "newborn_fever" in danger.detect("bachche ko tez bukhar hai", "newborn")
    assert danger.detect("bukhar nahi hai, sab theek", "newborn") == []
    assert "bleeding" in danger.detect("pregnancy mein bleeding ho rahi hai", "pregnant")
    assert danger.detect("koi bleeding nahi", "pregnant") == []
    assert "newborn_not_feeding" in danger.detect("baby doodh nahi pee raha", "newborn")
    assert "newborn_fever" in danger.detect("ಮಗುವಿಗೆ ಜ್ವರ ಇದೆ", "newborn")
    assert danger.detect("ಮಗುವಿಗೆ ಜ್ವರ ಇಲ್ಲ", "newborn") == []


def test_danger_list_has_sources():
    assert danger.SOURCES and all(s.get("source") for s in danger.SIGNS)


# ---------- schedule ----------
def test_vaccines_due_and_hbnc():
    reg = beneficiaries.load(TODAY)
    baby = reg["1044"]                       # 2 days old, nothing given
    assert schedule.due_vaccines(baby, TODAY) == ["BCG", "OPV-0", "HepB-0"]
    # born 2 days ago, so today is HBNC day 3 (this visit); the next one is day 7
    assert schedule.next_visit(baby, TODAY) == baby["dob"] + timedelta(days=6)
    kavya = reg["2051"]                      # 45 days, birth doses done
    assert "Penta-1" in schedule.due_vaccines(kavya, TODAY)
    meena = reg["1043"]                      # pregnant, Td-1 given 60 days ago
    assert schedule.due_vaccines(meena, TODAY) == ["Td-2"]


def test_advice_detection():
    assert is_advice_request("bukhar hai, kaun si dawai dein?")
    assert not is_advice_request("IFA goli di")


# ---------- full conversation (rule extractor, no network) ----------
def make_session(tmp_path, lang="hi"):
    store = Store(tmp_path / "r.enc", Fernet.generate_key().decode())
    return Session(lang, RuleExtractor(), store, today=TODAY), store


def run(s, text):
    return asyncio.run(s.handle(text))


def test_full_visit_with_correction(tmp_path):
    s, store = make_session(tmp_path)
    assert "AI" in s.start()[0]                                  # AI disclosure on turn one
    out = run(s, "ID ek shunya char do")
    assert s.state == "DICTATION" and s.b["id"] == "1042"
    out = run(s, "vajan do point aath kilo")
    assert s.state == "READBACK" and s.form["weight_kg"] == 2.8
    assert "1 0 4 2" in out[-1]                                  # ID read digit by digit
    out = run(s, "nahi, weight 2.9 kilo")
    assert s.form["weight_kg"] == 2.9 and "2 पॉइंट 9" in out[-1]
    out = run(s, "haan, save karo")
    assert s.state == "AWAIT_ID"
    rec = store.all()[0]
    assert rec["weight_kg"] == 2.9 and rec["beneficiary_id"] == "1042"
    assert b"1042" not in (tmp_path / "r.enc").read_bytes()      # encrypted at rest


def test_danger_alert_spoken_first_and_saved(tmp_path):
    s, store = make_session(tmp_path)
    run(s, "1044")
    out = run(s, "baby ko tez bukhar hai, vajan 2.6 kilo")
    assert "PHC" in out[0]                                       # alert first
    assert "newborn_fever" in s.form["danger_signs"]
    run(s, "haan save")
    assert store.followups()[0]["danger_signs"]


def test_vaccine_given_today_updates_due(tmp_path):
    s, _ = make_session(tmp_path)
    run(s, "ID 1044")
    run(s, "BCG laga diya, weight 3 kilo")
    assert "BCG" in s.form["vaccines_given_today"]
    assert "BCG" not in s.form["vaccines_due"]


def test_implausible_weight_is_questioned(tmp_path):
    s, _ = make_session(tmp_path)
    run(s, "1042")
    out = run(s, "vajan 28 kilo")
    assert s.form["weight_kg"] is None and "फिर से" in out[-1]


def test_advice_request_refused(tmp_path):
    s, _ = make_session(tmp_path)
    run(s, "1043")
    out = run(s, "kitni goli deni chahiye?")
    assert any("सलाह नहीं" in line for line in out)


def test_llm_merge_rules_win_and_dangers_union():
    from app.extract import Extraction, _merge
    rules = Extraction(weight_kg=2.8, danger_sign_ids=["newborn_fever"])
    llm = {"weight_kg": 28, "visit_type": "HBNC", "vaccines_given": ["BCG", "MADE-UP"],
           "danger_sign_ids": ["newborn_not_feeding", "not_a_sign"], "intent": "confirm",
           "next_visit_date": "2026-11-20"}
    ex = _merge(rules, llm)
    assert ex.weight_kg == 2.8                                  # explicit number from rules wins
    assert ex.vaccines_given == ["BCG"]                         # unknown codes dropped
    assert set(ex.danger_sign_ids) == {"newborn_fever", "newborn_not_feeding"}
    assert ex.intent is None                                    # fields + confirm = an edit


def test_kannada_flow(tmp_path):
    s, _ = make_session(tmp_path, "kn")
    assert "AI" in s.start()[0]
    run(s, "ಐಡಿ ಒಂದು ಸೊನ್ನೆ ನಾಲ್ಕು ಮೂರು")                          # 1043
    out = run(s, "ತೂಕ ಐವತ್ತೆರಡು ಕಿಲೋ 52 kg")
    assert s.form["weight_kg"] == 52 and s.state == "READBACK"
    assert "ಸೇವ್" in out[-1]
