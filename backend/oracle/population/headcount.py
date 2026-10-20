"""How many real people a simulated group stands for.

A job's headcount in a country = employed workforce x the job's baseline share of a
US-like workforce x (how big its ISCO group is in this country / in the reference)
x a sector factor (startup density for founders, software spend for tech jobs, the
size of the IT-services industry for IT-services roles). Non-workers are shares of
adults. These are order-of-magnitude estimates, labelled as such in the UI.
"""

from __future__ import annotations

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


def segment_headcount(iso: str, occupation_ids: list[str], custom: bool = False) -> float:
    """People in a segment in one country. Empty list = all adults."""
    c = countries()[iso]
    if not occupation_ids:
        if custom:
            return c.workforce_m * 1e6 * DEFAULT_CUSTOM_SHARE
        return c.adults_m * 1e6
    return sum(occupation_headcount(iso, oid) for oid in occupation_ids)
