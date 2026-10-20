"""How many real people a simulated group stands for.

A job's headcount in a country = employed workforce x the job's baseline share of a
US-like workforce x (how big its ISCO group is in this country / in the reference)
x a sector factor (startup density for founders, software spend for tech jobs, the
size of the IT-services industry for IT-services roles). Non-workers are shares of
adults. These are order-of-magnitude estimates, labelled as such in the UI.
"""

from __future__ import annotations

import math
from functools import lru_cache

from ..world.countries import Country, Occupation, countries, occupation_meta, occupations

TECH_SECTORS = {"software", "it_services", "finance"}
DEFAULT_CUSTOM_SHARE = 0.002  # a niche job we know nothing about: 0.2% of the workforce


def _sector_factor(o: Occupation, c: Country) -> float:
    if o.id.startswith("founder") or o.id == "vc_investor":
        return max(0.05, c.startups / 0.95) ** 1.5
    if o.id.startswith("it_services") or o.id == "bpo_agent":
        hub = occupation_meta()["it_services_hubs"].get(c.iso3, 0.6)
        return hub
    if set(o.sectors) & TECH_SECTORS and o.isco in (1, 2, 3):
        return max(0.1, c.saas) ** 0.6
    return 1.0


@lru_cache(maxsize=20000)
def occupation_headcount(iso: str, occupation_id: str) -> float:
    """People (not millions) doing this job in this country."""
    c = countries()[iso]
    o = occupations().get(occupation_id)
    adults = c.adults_m * 1e6
    workforce = c.workforce_m * 1e6
    if o is None:
        return workforce * DEFAULT_CUSTOM_SHARE
    if o.adult_share is not None or o.isco == 0:
        if o.id == "retiree":
            return c.population_m * 1e6 * (c.pop65 if c.pop65 is not None else 0.08) * 0.9
        if o.id == "unemployed":
            return max(0.0, adults * 0.62 - workforce) * 0.25 + workforce * 0.03
        return adults * (o.adult_share or 0.05)
    ref = occupation_meta()["reference_isco"]
    group_ratio = c.isco_shares().get(o.isco, 0.1) / max(ref[o.isco - 1], 0.005)
    return workforce * (o.base_share or DEFAULT_CUSTOM_SHARE) * group_ratio * _sector_factor(o, c)


def age_share(iso: str, lo: int | None, hi: int | None) -> float:
    """Share of adults (15+) aged lo..hi, from an age curve fitted to the country's median age
    and share over 65. An approximation, but it gets young and old countries the right way round."""
    if lo is None and hi is None:
        return 1.0
    c = countries()[iso]
    lo, hi = max(15, lo or 15), min(100, hi or 100)
    if hi < lo:
        return 0.0
    # Exponential decline in cohort size with age; steeper in young countries.
    tau = max(18.0, (c.median_age - 10) * 1.6)
    weights = [math.exp(-(a - 15) / tau) for a in range(15, 101)]
    total = sum(weights)
    return sum(weights[a - 15] for a in range(lo, hi + 1)) / total


def segment_headcount(
    iso: str, occupation_ids: list[str], custom: bool = False, age_min: int | None = None, age_max: int | None = None, gender: str = "any"
) -> float:
    """People in a segment in one country. Empty list = all adults. Age and gender narrow it."""
    c = countries()[iso]
    if not occupation_ids:
        base = c.workforce_m * 1e6 * DEFAULT_CUSTOM_SHARE if custom else c.adults_m * 1e6
    else:
        base = sum(occupation_headcount(iso, oid) for oid in occupation_ids)
    base *= age_share(iso, age_min, age_max)
    if gender in ("woman", "man"):
        base *= 0.5
    return base


def seg_headcount(iso: str, seg) -> float:
    """Headcount for a Segment object. A free-text trait narrows it by the model's estimated share."""
    base = segment_headcount(iso, seg.occupations, bool(seg.custom_occupation), seg.age_min, seg.age_max, seg.gender)
    if getattr(seg, "trait", None):
        base *= seg.trait_share if seg.trait_share is not None else 0.1
    return base


def seg_is_estimated(seg) -> bool:
    """True when the headcount rests on a model estimate rather than World Bank / ILO data."""
    return bool(getattr(seg, "trait", None) or getattr(seg, "custom_occupation", None))
