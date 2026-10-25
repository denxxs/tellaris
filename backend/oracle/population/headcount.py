"""How many real people a simulated group stands for, from published statistics.

- A job with ISCO-08 codes: employed people in each 2-digit group (ILOSTAT), times the 4-digit
  unit group's share of its 2-digit group (from US occupational data; see build_people.py).
- Business owners, freelancers, students, retirees, the unemployed and people outside the labour
  force come from ILOSTAT and World Bank counts (see realdata.population_count).
- Age and gender filters use the job's real age and gender mix (ILOSTAT), or the country's
  population by age and sex (World Bank) for people outside jobs.
- When no source exists (e.g. "startup founders"), the size is unknown and returned as None:
  Oracle never makes one up.
"""

from __future__ import annotations

from functools import lru_cache

from ..world.countries import Occupation, countries, occupations
from . import realdata

UNKNOWN = None


def _job_codes(o: Occupation) -> list[str]:
    return list(getattr(o, "isco08", None) or [])


@lru_cache(maxsize=20000)
def occupation_headcount(iso: str, occupation_id: str) -> float | None:
    """People doing this job in this country, or None when no source exists."""
    c = countries()[iso]
    o = occupations().get(occupation_id)
    if o is None or not c.simulatable:
        return UNKNOWN
    workforce = c.workforce_m * 1e6
    kind = getattr(o, "population", None)
    if kind:
        n, _ = realdata.population_count(iso, kind)
        return n
    codes = _job_codes(o)
    if not codes:
        return UNKNOWN
    by2, _ = realdata.employed_2digit(iso, workforce, c.isco_shares())
    within = realdata.within_2digit()
    total = 0.0
    for code in codes:
        if len(code) == 2:  # the whole 2-digit group
            total += by2.get(code, 0.0)
        elif code in within:
            total += by2.get(code[:2], 0.0) * within[code]
        else:
            return UNKNOWN  # no detailed split for this unit group (yet)
    return total


def occupation_source(iso: str, occupation_id: str) -> str:
    c = countries()[iso]
    o = occupations().get(occupation_id)
    if o is None or not c.simulatable:
        return "no data"
    kind = getattr(o, "population", None)
    if kind:
        _, src = realdata.population_count(iso, kind)
        return src
    _, src = realdata.employed_2digit(iso, c.workforce_m * 1e6, c.isco_shares())
    return f"{src}; 4-digit split from US occupational data" if realdata.within_2digit() else "no 4-digit split yet"


def _age_fraction_job(iso: str, o: Occupation | None, lo: int, hi: int) -> float:
    """Share of a job's workers aged lo..hi: ILOSTAT age groups by job, spread by the population shape."""
    major = int(_job_codes(o)[0][0]) if o is not None and _job_codes(o) else None
    bands = realdata.job_age_band_weights(iso, major)
    if not bands:
        return _age_fraction_pop(iso, lo, hi)
    total = sum(w for _, w in bands) or 1.0
    got = 0.0
    for (blo, bhi), w in bands:
        a, b = max(lo, blo), min(hi, bhi)
        if a > b:
            continue
        inside = realdata.people_aged(iso, a, b) or 0.0
        whole = realdata.people_aged(iso, blo, bhi) or 1.0
        got += w * inside / whole
    return got / total


def _age_fraction_pop(iso: str, lo: int, hi: int, base_lo: int = 15, base_hi: int = 99) -> float:
    whole = realdata.people_aged(iso, base_lo, base_hi)
    if not whole:
        return 1.0
    return (realdata.people_aged(iso, max(lo, base_lo), min(hi, base_hi)) or 0.0) / whole


_POP_AGES = {"students": (18, 30), "retirees": (65, 99), "unemployed": (15, 64), "outside_labour_force": (15, 99)}


def _filters(iso: str, o: Occupation | None, age_min: int | None, age_max: int | None, gender: str) -> float:
    lo, hi = age_min or 15, age_max or 99
    kind = getattr(o, "population", None) if o is not None else None
    if age_min is None and age_max is None:
        age_f = 1.0
    elif kind in _POP_AGES:
        blo, bhi = _POP_AGES[kind]
        age_f = _age_fraction_pop(iso, lo, hi, blo, bhi)
    else:
        age_f = _age_fraction_job(iso, o, lo, hi)
    if gender not in ("woman", "man"):
        return age_f
    fs = realdata.female_share_job(iso, _job_codes(o)) if o is not None and _job_codes(o) else None
    if fs is None:
        fs = realdata.female_share(iso, lo, hi) or 0.5
    return age_f * (fs if gender == "woman" else 1 - fs)


def segment_headcount(
    iso: str, occupation_ids: list[str], custom: bool = False, age_min: int | None = None, age_max: int | None = None, gender: str = "any"
) -> float | None:
    """People in a segment in one country, or None when any part of it has no source."""
    if custom:
        return UNKNOWN
    if not occupation_ids:
        adults = realdata.people_aged(iso, age_min or 15, age_max or 99, gender if gender in ("woman", "man") else "any")
        if adults is not None:
            return adults
        a = countries()[iso].adults_m
        return a * 1e6 if a is not None else UNKNOWN
    total = 0.0
    for oid in occupation_ids:
        n = occupation_headcount(iso, oid)
        if n is None:
            return UNKNOWN
        total += n * _filters(iso, occupations().get(oid), age_min, age_max, gender)
    return total


def seg_headcount(iso: str, seg) -> float | None:
    """Headcount for a Segment object. A free-text trait narrows it only by a share the user gave."""
    base = segment_headcount(iso, seg.occupations, bool(seg.custom_occupation), seg.age_min, seg.age_max, seg.gender)
    if base is None:
        return None
    if getattr(seg, "trait", None):
        if seg.trait_share is None:
            return None
        base *= seg.trait_share
    return base


def seg_is_estimated(seg) -> bool:
    """True when the size isn't fully backed by data (kept for older callers)."""
    return bool(getattr(seg, "trait", None) or getattr(seg, "custom_occupation", None))
