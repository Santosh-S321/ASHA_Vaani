"""Fixed rules for vaccines due and next visit date. Never decided by the LLM.

Vaccines: National Immunization Schedule (NIS), MoHFW / NHM.
Newborn visits: HBNC home visits on days 3, 7, 14, 21, 28 and 42.
JE is left out because it is given only in endemic districts.
"""
from datetime import date, timedelta

CHILD_SCHEDULE = [
    (0, ["BCG", "OPV-0", "HepB-0"]),
    (42, ["OPV-1", "Penta-1", "RVV-1", "fIPV-1", "PCV-1"]),        # 6 weeks
    (70, ["OPV-2", "Penta-2", "RVV-2"]),                            # 10 weeks
    (98, ["OPV-3", "Penta-3", "RVV-3", "fIPV-2", "PCV-2"]),         # 14 weeks
    (270, ["MR-1", "PCV-B", "fIPV-3", "VitA-1"]),                   # 9 months
    (480, ["MR-2", "DPT-B1", "OPV-B"]),                             # 16 months
]
PREGNANCY_CODES = ["Td-1", "Td-2", "Td-B"]
ALL_CODES = [c for _, codes in CHILD_SCHEDULE for c in codes] + PREGNANCY_CODES
HBNC_DAYS = [3, 7, 14, 21, 28, 42]

# spoken series name -> code prefix (dose picked by resolve_series)
SERIES = {
    "BCG": "BCG", "OPV": "OPV", "Penta": "Penta", "RVV": "RVV", "fIPV": "fIPV", "PCV": "PCV",
    "MR": "MR", "HepB": "HepB", "Td": "Td", "DPT": "DPT", "VitA": "VitA",
}


def age_days(dob: date, today: date) -> int:
    return (today - dob).days


def due_vaccines(b: dict, today: date) -> list[str]:
    given = b.get("given", {})
    if b["type"] == "pregnant":
        if "Td-1" not in given:
            return ["Td-1"]
        if "Td-2" not in given and "Td-B" not in given and given["Td-1"] + timedelta(days=28) <= today:
            return ["Td-2"]
        return []
    age = age_days(b["dob"], today)
    return [c for day, codes in CHILD_SCHEDULE if day <= age for c in codes if c not in given]


def resolve_series(series: str, b: dict, today: date, dose: int | None = None) -> str | None:
    """'Penta' -> the next Penta dose this beneficiary has not had (or 'Penta-2' if dose=2)."""
    prefix = SERIES.get(series)
    if not prefix:
        return None
    if prefix == "BCG":
        return "BCG"
    if dose is not None:
        code = f"{prefix}-{dose}"
        return code if code in ALL_CODES else None
    codes = PREGNANCY_CODES if b["type"] == "pregnant" else [c for c in ALL_CODES if c not in PREGNANCY_CODES]
    given = b.get("given", {})
    for c in codes:
        if c.startswith(prefix + "-") and c not in given:
            return c
    return None


def next_visit(b: dict, today: date) -> date:
    if b["type"] == "pregnant":
        weeks = (today - b["lmp"]).days // 7
        return today + timedelta(days=7 if weeks >= 36 else 30)
    age = age_days(b["dob"], today)
    if b["type"] == "newborn":
        for d in HBNC_DAYS:
            visit = b["dob"] + timedelta(days=d - 1)   # day of birth counts as day 1
            if visit > today:
                return visit
    if due_vaccines(b, today):
        return today + timedelta(days=7)   # overdue doses: next immunisation session
    for day, _ in CHILD_SCHEDULE:
        if day > age:
            return b["dob"] + timedelta(days=day)
    return today + timedelta(days=90)
