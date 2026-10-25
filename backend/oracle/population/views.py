"""Views from real survey respondents (World Values Survey wave 7).

Each simulated person is matched to a real respondent from the same country who is like them in
sex, age, work and income, and carries that respondent's actual answers. Nothing is scored or
invented: the person states what the respondent said. Countries the survey didn't cover get no
views. The pool is built locally by scripts/build_views.py (WVS terms forbid redistribution).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Callable

import numpy as np

from ..config import env

POOL_PATH = env.var_dir / "datasets" / "wvs_pool.json"
MATCH_COLUMNS = ["Q260", "Q262", "Q279", "Q281", "Q288"]  # sex, age, employment, occupation, income step
MIN_CELL = 10  # fewest respondents to draw from before loosening the match

FREQ = {1: "daily", 2: "weekly", 3: "monthly", 4: "less than monthly", 5: "never"}
CONF = {1: "a great deal", 2: "quite a lot", 3: "not very much", 4: "none at all"}
TRUST4 = {1: "completely", 2: "somewhat", 3: "not very much", 4: "not at all"}
IMPORTANCE = {1: "very important", 2: "rather important", 3: "not very important", 4: "not at all important"}


@dataclass(frozen=True)
class Question:
    key: str
    column: str  # WVS wave 7 variable
    text: Callable[[int], str | None]  # the answer in words
    score: Callable[[int], float | None] = lambda v: None  # higher = more of the label, for drivers
    label: str = ""  # driver label
    group: str = "views"


def _scale(lo: str, hi: str, intro: str) -> Callable[[int], str]:
    return lambda v: f"{intro}: {v} on a 1-10 scale (1 = {lo}, 10 = {hi})"


QUESTIONS: list[Question] = [
    Question("trust_people", "Q57",
             lambda v: {1: "Thinks most people can be trusted", 2: "Thinks you need to be very careful with people"}.get(v),
             lambda v: {1: 1.0, 2: 0.0}.get(v), "Trusts most people"),
    Question("trust_strangers", "Q61", lambda v: f"Trusts people they meet for the first time {TRUST4[v]}" if v in TRUST4 else None,
             lambda v: 5.0 - v if v in TRUST4 else None, "Trusts strangers"),
    Question("trust_foreigners", "Q63", lambda v: f"Trusts people of another nationality {TRUST4[v]}" if v in TRUST4 else None,
             lambda v: 5.0 - v if v in TRUST4 else None, "Trusts foreigners"),
    Question("more_technology", "Q44",
             lambda v: {1: "Thinks more emphasis on technology would be a good thing", 2: "Doesn't mind more emphasis on technology",
                        3: "Thinks more emphasis on technology would be a bad thing"}.get(v),
             lambda v: {1: 2.0, 2: 1.0, 3: 0.0}.get(v), "Welcomes more technology"),
    Question("science_easier_life", "Q158",
             _scale("completely disagree", "completely agree", "Agrees science and technology make life healthier, easier and more comfortable"),
             lambda v: float(v), "Thinks science makes life easier"),
    Question("science_world_better", "Q163",
             _scale("a lot worse off", "a lot better off", "Thinks the world is better off because of science and technology"),
             lambda v: float(v), "Thinks science made the world better"),
    Question("society_change", "Q42",
             lambda v: {1: "Wants society changed radically", 2: "Wants society improved by gradual reforms",
                        3: "Wants society defended against subversive forces"}.get(v)),
    Question("confidence_companies", "Q77", lambda v: f"Confidence in major companies: {CONF[v]}" if v in CONF else None,
             lambda v: 5.0 - v if v in CONF else None, "Trusts big companies"),
    Question("confidence_banks", "Q78", lambda v: f"Confidence in banks: {CONF[v]}" if v in CONF else None,
             lambda v: 5.0 - v if v in CONF else None, "Trusts banks"),
    Question("confidence_government", "Q71", lambda v: f"Confidence in the national government: {CONF[v]}" if v in CONF else None,
             lambda v: 5.0 - v if v in CONF else None, "Trusts the government"),
    Question("confidence_press", "Q66", lambda v: f"Confidence in the press: {CONF[v]}" if v in CONF else None,
             lambda v: 5.0 - v if v in CONF else None, "Trusts the press"),
    Question("confidence_tv", "Q67", lambda v: f"Confidence in television: {CONF[v]}" if v in CONF else None,
             lambda v: 5.0 - v if v in CONF else None, "Trusts television"),
    Question("competition", "Q109", _scale("competition is good", "competition is harmful", "On competition"),
             lambda v: 11.0 - v, "Sees competition as good"),
    Question("hard_work", "Q110", _scale("hard work brings a better life", "success is luck and connections", "On getting ahead"),
             lambda v: 11.0 - v, "Believes hard work pays"),
    Question("income_equality", "Q106", _scale("incomes should be made more equal", "bigger income differences are needed as incentives", "On incomes"),
             lambda v: float(v), "Accepts income differences"),
    Question("ownership", "Q107", _scale("more private ownership of business", "more government ownership of business", "On ownership"),
             lambda v: 11.0 - v, "Favours private business"),
    Question("environment_growth", "Q111",
             lambda v: {1: "Puts protecting the environment ahead of economic growth", 2: "Puts economic growth ahead of the environment"}.get(v),
             lambda v: {1: 1.0, 2: 0.0}.get(v), "Puts the environment first"),
    Question("left_right", "Q240", _scale("left", "right", "Politically"), lambda v: float(v), "Leans right politically"),
    Question("religion", "Q6", lambda v: f"Religion is {IMPORTANCE[v]} in their life" if v in IMPORTANCE else None,
             lambda v: 5.0 - v if v in IMPORTANCE else None, "Religious"),
    Question("control_over_life", "Q48", _scale("no choice at all", "a great deal of choice", "Feels in control of their own life"),
             lambda v: float(v), "Feels in control of life"),
    Question("money_satisfaction", "Q50", _scale("completely dissatisfied", "completely satisfied", "Satisfied with their household's finances"),
             lambda v: float(v), "Happy with their finances"),
    *[
        Question(f"news_{k}", col, lambda v, name=name: f"{name}: {FREQ[v]}" if v in FREQ else None,
                 lambda v: 5.0 - v if v in FREQ else None, f"Follows {name.lower()}", "news")
        for k, col, name in [
            ("newspaper", "Q201", "Daily newspaper"), ("tv", "Q202", "TV news"), ("radio", "Q203", "Radio news"),
            ("phone", "Q204", "Mobile phone"), ("email", "Q205", "Email"), ("internet", "Q206", "Internet"),
            ("social", "Q207", "Social media"), ("friends", "Q208", "Talking with friends or colleagues"),
        ]
    ],
]
BY_KEY = {q.key: q for q in QUESTIONS}

# ISCO-08 major group -> WVS "occupational group" (Q281) codes.
ISCO_TO_WVS = {1: {2}, 2: {1}, 3: {1}, 4: {3}, 5: {4, 5}, 6: {9, 10}, 7: {6}, 8: {7}, 9: {8, 9}, 0: {11}}
# Tellaris's non-worker kinds -> WVS employment status (Q279).
WORK_OF = {"retirees": {4}, "outside_labour_force": {5}, "students": {6}, "unemployed": {7}}
WORKING = {1, 2, 3}
SELF_EMPLOYED = {3}


@dataclass
class Match:
    answers: dict[str, int]
    year: int
    matched_on: list[str] = field(default_factory=list)


@lru_cache(maxsize=1)
def pool() -> dict | None:
    if not POOL_PATH.exists():
        return None
    data = json.loads(POOL_PATH.read_text(encoding="utf-8"))
    keys = data["_meta"]["row"][7:]
    out = {}
    for iso, c in data["countries"].items():
        rows = c["rows"]
        out[iso] = {
            "year": c["year"],
            "sex": np.array([r[0] for r in rows]),
            "age": np.array([r[1] for r in rows]),
            "work": np.array([r[2] for r in rows]),
            "occ": np.array([r[3] for r in rows]),
            "inc_lo": np.array([r[4] if r[4] is not None else -1 for r in rows], dtype=float),
            "inc_hi": np.array([r[5] if r[5] is not None else -1 for r in rows], dtype=float),
            "weight": np.array([r[6] for r in rows], dtype=float),
            "answers": [dict((k, v) for k, v in zip(keys, r[7:]) if v is not None) for r in rows],
        }
    return out


def covered(iso: str) -> bool:
    p = pool()
    return bool(p and iso in p)


def _band(age: int) -> tuple[int, int]:
    for lo, hi in ((15, 24), (25, 34), (35, 44), (45, 54), (55, 64)):
        if age <= hi:
            return lo, hi
    return 65, 120


def match(iso: str, rng: np.random.Generator, *, sex: str, age: int, population: str | None,
          isco_major: int | None, self_employed: bool, income_pct: float | None) -> Match | None:
    """Draw one real respondent like this person (survey weights), loosening the match step by step
    until at least MIN_CELL respondents qualify. None when the country wasn't surveyed."""
    p = pool()
    if not p or iso not in p:
        return None
    c = p[iso]
    lo, hi = _band(age)
    sex_m = c["sex"] == (2 if sex == "woman" else 1)
    age_m = (c["age"] >= lo) & (c["age"] <= hi)
    if population in WORK_OF:
        work_exact = np.isin(c["work"], list(WORK_OF[population]))
        work_broad = ~np.isin(c["work"], list(WORKING))
        occ_m = np.ones_like(sex_m)
    else:
        work_exact = np.isin(c["work"], list(SELF_EMPLOYED if self_employed else WORKING))
        work_broad = np.isin(c["work"], list(WORKING))
        has_occ = bool((c["occ"] >= 0).any())  # some surveys (EVS in the joint file) record no occupation
        occ_m = (np.isin(c["occ"], list(ISCO_TO_WVS.get(isco_major, set())))
                 if isco_major is not None and has_occ else np.ones_like(sex_m))
    inc_m = None
    if income_pct is not None:
        inc_m = (c["inc_lo"] <= income_pct) & (income_pct < c["inc_hi"])
    steps = []
    if inc_m is not None:
        steps.append((["sex", "age", "work", "occupation", "income"], sex_m & age_m & work_exact & occ_m & inc_m))
    steps += [
        (["sex", "age", "work", "occupation"], sex_m & age_m & work_exact & occ_m),
        (["sex", "age", "working or not", "occupation"], sex_m & age_m & work_broad & occ_m),
        (["sex", "age", "working or not"], sex_m & age_m & work_broad),
        (["sex", "age"], sex_m & age_m),
        (["sex"], sex_m),
        ([], np.ones_like(sex_m)),
    ]
    for on, mask in steps:
        idx = np.flatnonzero(mask)
        if len(idx) >= MIN_CELL or not on:
            if not len(idx):
                return None
            w = c["weight"][idx]
            pick = int(idx[rng.choice(len(idx), p=w / w.sum())])
            if population in WORK_OF or not bool((c["occ"] >= 0).any()):
                on = [x for x in on if x != "occupation"]
            return Match(answers=dict(c["answers"][pick]), year=c["year"], matched_on=on)
    return None


# Survey channel behind each news medium (Q201-Q208).
MEDIUM_KEYS = {"newspaper": ["news_newspaper"], "tv": ["news_tv"], "radio": ["news_radio"],
               "internet": ["news_internet", "news_phone", "news_email"], "social": ["news_social"], "friends": ["news_friends"]}
# Days in a month each answer means at least (the answer's lower edge, so nothing is guessed in between).
DAYS_AT_LEAST = {1: 30.0, 2: 4.0, 3: 1.0, 4: 0.0, 5: 0.0}


def _days(answers: dict[str, int], media: tuple[str, ...]) -> float | None:
    """Days a month, at least, they get news from the most-used of these media."""
    keys = [k for m in media for k in MEDIUM_KEYS.get(m, [])]
    vals = [DAYS_AT_LEAST[answers[k]] for k in keys if answers.get(k) in DAYS_AT_LEAST]
    return max(vals) if vals else None


@lru_cache(maxsize=4096)
def _country_days(iso: str, media: tuple[str, ...]) -> float | None:
    p = pool()
    if not p or iso not in p:
        return None
    c = p[iso]
    pairs = [(d, w) for a, w in zip(c["answers"], c["weight"]) if (d := _days(a, media)) is not None]
    total = sum(w for _, w in pairs)
    return sum(d * w for d, w in pairs) / total if total else None


def news_attention(iso: str, answers: dict[str, int], media: list[str]) -> float:
    """How often this person gets news from these media relative to their country's (weighted)
    average: 1 = average, 0 = never. 1 when there is no survey data."""
    mine = _days(answers or {}, tuple(media))
    avg = _country_days(iso, tuple(media))
    if mine is None or not avg:
        return 1.0
    return mine / avg


def lines(views: dict[str, int], group: str | None = None) -> list[str]:
    out = []
    for k, v in views.items():
        q = BY_KEY.get(k)
        if q and (group is None or q.group == group):
            t = q.text(v)
            if t:
                out.append(t)
    return out


def scores(views: dict[str, int]) -> dict[str, float]:
    out = {}
    for k, v in views.items():
        q = BY_KEY.get(k)
        s = q.score(v) if q else None
        if s is not None:
            out[k] = s
    return out
