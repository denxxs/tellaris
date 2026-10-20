"""Real statistics per country for building people (see scripts/build_people.py).

Everything returned here comes from the World Bank or ILOSTAT, with a stated fallback when a
country lacks a table. Nothing is hand-set.
"""

from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path
from statistics import NormalDist, median
from typing import Any

DATA = Path(__file__).resolve().parents[1] / "data"
BAND_EDGES = [(0, 4), (5, 9), (10, 14), (15, 19), (20, 24), (25, 29), (30, 34), (35, 39), (40, 44), (45, 49), (50, 54), (55, 59), (60, 64), (65, 69), (70, 74), (75, 79), (80, 99)]
JOB_AGE = [(15, 24), (25, 54), (55, 64), (65, 99)]


@lru_cache(maxsize=1)
def _all() -> dict[str, Any]:
    p = DATA / "people.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"countries": {}, "_meta": {}}


def get(iso: str) -> dict[str, Any]:
    return _all()["countries"].get(iso, {})


def meta() -> dict[str, Any]:
    return _all().get("_meta", {})


# ---------------------------------------------------------------- age and sex


def by_age(iso: str, sex: str = "any") -> list[float] | None:
    """People at each single year of age 0..99 (each 5-year band spread evenly over its years)."""
    a = get(iso).get("age_sex")
    if not a:
        return None
    out = [0.0] * 100
    for i, (lo, hi) in enumerate(BAND_EDGES):
        n = (a["female"][i] if sex != "man" else 0) + (a["male"][i] if sex != "woman" else 0)
        span = hi - lo + 1
        for y in range(lo, hi + 1):
            out[y] += n / span
    return out


def people_aged(iso: str, lo: int = 15, hi: int = 99, sex: str = "any") -> float | None:
    ages = by_age(iso, sex)
    if ages is None:
        return None
    return sum(ages[max(0, lo): min(99, hi) + 1])


def age_weights(iso: str, lo: int, hi: int, sex: str = "any") -> list[tuple[int, float]]:
    """(age, weight) over lo..hi following the country's real population shape."""
    ages = by_age(iso, sex)
    if ages is None:
        return [(a, 1.0) for a in range(lo, hi + 1)]
    return [(a, ages[a]) for a in range(lo, min(hi, 99) + 1)]


def female_share(iso: str, lo: int = 15, hi: int = 99) -> float | None:
    f, m = people_aged(iso, lo, hi, "woman"), people_aged(iso, lo, hi, "man")
    return f / (f + m) if f is not None and m is not None and f + m > 0 else None


# ---------------------------------------------------------------- jobs


@lru_cache(maxsize=1)
def _within_major() -> dict[str, dict[str, float]]:
    """For countries without 2-digit data: each 2-digit group's median share of its major group,
    across the countries that have it."""
    shares: dict[str, list[float]] = {}
    for c in _all()["countries"].values():
        oc2 = (c.get("oc2") or {}).get("employed")
        if not oc2:
            continue
        major: dict[str, float] = {}
        for g, n in oc2.items():
            major[g[0]] = major.get(g[0], 0) + n
        for g, n in oc2.items():
            if major[g[0]]:
                shares.setdefault(g, []).append(n / major[g[0]])
    by_major: dict[str, dict[str, float]] = {}
    for g, v in shares.items():
        by_major.setdefault(g[0], {})[g] = median(v)
    for m, gs in by_major.items():  # renormalise so each major group sums to 1
        t = sum(gs.values()) or 1
        by_major[m] = {g: s / t for g, s in gs.items()}
    return by_major


def employed_2digit(iso: str, workforce: float, isco_major_shares: dict[int, float]) -> tuple[dict[str, float], str]:
    """Employed people per 2-digit ISCO group, and where the numbers come from."""
    oc2 = get(iso).get("oc2")
    if oc2:
        return {g: float(n) for g, n in oc2["employed"].items()}, f"ILOSTAT {oc2['year']}"
    wm = _within_major()
    out = {}
    for major, share in isco_major_shares.items():
        for g, s in wm.get(str(major), {}).items():
            out[g] = workforce * share * s
    return out, "ILOSTAT major groups, split by the median 2-digit mix of countries with data"


@lru_cache(maxsize=1)
def within_2digit() -> dict[str, float]:
    """Share of each 4-digit ISCO unit group within its 2-digit group (from US occupational data,
    see scripts/build_people.py). Empty until those files are built."""
    p = DATA / "isco_within.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8")).get("share", {})


def female_share_job(iso: str, codes: list[str]) -> float | None:
    fs = (get(iso).get("oc2") or {}).get("female_share") or {}
    vals = [fs[c[:2]] for c in codes if c[:2] in fs]
    return sum(vals) / len(vals) if vals else None


def job_age_band_weights(iso: str, major: int | None) -> list[tuple[tuple[int, int], float]] | None:
    """How the employed in an ISCO major group (or all employed) split across ILO's age groups."""
    a = get(iso).get("age_by_group")
    if not a:
        return None
    groups = a["groups"]
    if major is not None and str(major) in groups:
        counts = groups[str(major)]
    else:
        counts = [sum(v[i] for v in groups.values()) for i in range(len(JOB_AGE))]
    return list(zip(JOB_AGE, counts))


# ---------------------------------------------------------------- earnings


@lru_cache(maxsize=1)
def _earnings_ratio() -> dict[str, float]:
    """Median ratio of each group's earnings to the national mean, across countries with data."""
    ratios: dict[str, list[float]] = {}
    for c in _all()["countries"].values():
        e = (c.get("earnings_usd_month") or {}).get("groups")
        if not e or not e.get("TOTAL"):
            continue
        for g, v in e.items():
            if g != "TOTAL":
                ratios.setdefault(g, []).append(v / e["TOTAL"])
    return {g: median(v) for g, v in ratios.items()}


def monthly_earnings(iso: str, major: int | None, gdp_pc_usd: float) -> tuple[float, str]:
    """Mean monthly earnings (USD) for an ISCO major group (None = all employees), and the source."""
    e = get(iso).get("earnings_usd_month")
    key = str(major) if major is not None else "TOTAL"
    if e and key in e["groups"]:
        return e["groups"][key], f"ILOSTAT mean earnings {e['year']}"
    if e and "TOTAL" in e["groups"]:
        return e["groups"]["TOTAL"] * _earnings_ratio().get(key, 1.0), f"ILOSTAT national mean earnings {e['year']}, group ratio from other countries"
    # No earnings survey: national income per person, with the typical group ratio.
    return gdp_pc_usd / 12 * _earnings_ratio().get(key, 1.0), "World Bank GDP per person, group ratio from ILOSTAT countries"


@lru_cache(maxsize=1)
def _median_gini() -> float:
    vals = [c["gini"]["value"] for c in _all()["countries"].values() if c.get("gini")]
    return median(vals) if vals else 38.0


def income_sigma(iso: str) -> tuple[float, str]:
    """Spread of a lognormal income distribution with the country's Gini: G = 2*Phi(sigma/sqrt(2)) - 1."""
    g = get(iso).get("gini")
    gini, src = (g["value"], f"World Bank Gini {g['year']}") if g else (_median_gini(), "median Gini of countries with data")
    sigma = math.sqrt(2) * NormalDist().inv_cdf((gini / 100 + 1) / 2)
    return sigma, src


# ---------------------------------------------------------------- people outside regular jobs


def population_count(iso: str, kind: str) -> tuple[float | None, str]:
    """Headcount for a group defined by status rather than occupation."""
    c = get(iso)
    lab = c.get("labour") or {}
    labour_force, unemployment_pct = lab.get("force"), lab.get("unemployment_pct")
    if kind == "employers" and c.get("status"):
        return float(c["status"]["employers"]), f"ILOSTAT employers {c['status']['year']}"
    if kind == "own_account" and c.get("status"):
        return float(c["status"]["own_account"]), f"ILOSTAT own-account workers {c['status']['year']}"
    if kind == "unemployed" and labour_force and unemployment_pct is not None:
        return labour_force * unemployment_pct / 100, f"World Bank labour force x unemployment rate {lab['year']}"
    if kind == "students":
        t = c.get("tertiary_enrolment")
        pop = people_aged(iso, 20, 24)
        if t and pop:
            return pop * t["value"] / 100, f"World Bank tertiary enrolment {t['year']} x people aged 20-24"
    if kind == "retirees":
        lf = c.get("participation")
        old = people_aged(iso, 65, 99)
        if lf and old is not None:
            return old * (1 - lf["65+"]), f"People 65+ not in the labour force (ILOSTAT {lf['year']})"
    if kind == "outside_labour_force":
        lf = c.get("participation")
        adults = people_aged(iso, 15, 99)
        if lf and adults is not None:
            students, _ = population_count(iso, "students")
            retirees, _ = population_count(iso, "retirees")
            outside = adults * (1 - lf["15+"]) - (students or 0) - (retirees or 0)
            return max(0.0, outside), f"People 15+ outside the labour force, not studying or retired (ILOSTAT {lf['year']})"
    return None, "no data"
