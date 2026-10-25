"""Who knows whom: the contact network the society talks over.

How many people someone talks to, of what ages and where (home, work, school, elsewhere) comes
from the contact surveys extended to 177 countries by Prem et al. (2021): a person aged 30 in
India has about 11 daily contacts with other adults. How unequal that is between people (some meet
3 people a day, some 40) comes from diary surveys in ten countries (negative binomial dispersion;
countries without a survey use the median). Which country a contact lives in comes from
Meta's Social Connectedness Index (the share of a country's friendships with each country, itself
included). Work contacts are people who also work, in the same sector where there are any; the
rest are picked evenly among people of the right age in that country.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import networkx as nx
import numpy as np

from ..config import load_json
from ..population.models import Persona
from ..world.ties import friend_share


@lru_cache(maxsize=1)
def _contacts() -> dict[str, Any]:
    try:
        return load_json("contacts.json")
    except FileNotFoundError:
        return {"_meta": {"bands": [], "settings": []}, "countries": {}}


def band(age: int) -> int:
    return max(0, min(12, (age - 15) // 5))


def daily_contacts(iso: str, age: int) -> dict[str, list[float]] | None:
    """Mean daily contacts by setting with each adult age band (None = no data)."""
    rec = _contacts()["countries"].get(iso)
    if not rec:
        return None
    r = band(age)
    return {s: rec[s][r] for s in _contacts()["_meta"]["settings"]}


def dispersion(iso: str) -> float | None:
    """Negative binomial dispersion k of contacts per person (variance = mean + mean^2/k), from the
    country's own diary survey, else the median of surveyed countries. None = no survey data at all."""
    d = _contacts().get("dispersion") or {}
    own = (d.get("countries") or {}).get(iso)
    return own["k"] if own else d.get("median_k")


def _ties_to_start(mean: float, k: float | None, rng: np.random.Generator) -> int:
    """How many ties a person starts. Each tie has two ends: a person starts about half their
    contacts and gets the rest from people who pick them (roughly Poisson). For the total to have the
    measured spread (variance mean + mean^2/k), the half they start needs dispersion k/4."""
    half = mean / 2
    if not k or half <= 0:
        return int(half + rng.random())  # no survey data: same expected number for everyone
    k_out = k / 4
    return int(rng.negative_binomial(k_out, k_out / (k_out + half)))


def country_mix(home: str, present: list[str]) -> dict[str, float]:
    """Where a person from `home` finds contacts, among the countries in this run. A country with
    no friendship data keeps its contacts at home rather than guessing ties."""
    shares = {c: friend_share(home, c) for c in present}
    if shares.get(home) is None:
        return {home: 1.0}
    shares = {c: v for c, v in shares.items() if v}
    total = sum(shares.values())
    return {c: v / total for c, v in shares.items()} if total else {home: 1.0}


def _working(p: Persona) -> bool:
    return p.seniority != "none"


def build_network(people: list[Persona], seed: int | None = None) -> nx.Graph:
    rng = np.random.default_rng(seed)
    g = nx.Graph()
    for p in people:
        g.add_node(p.id)
    by_country: dict[str, list[Persona]] = {}
    for p in people:
        by_country.setdefault(p.country, []).append(p)
    present = sorted(by_country)
    mix = {c: country_mix(c, present) for c in present}
    # People per (country, age band), and per (country, age band, sector) for work contacts.
    by_band: dict[tuple[str, int], list[Persona]] = {}
    by_work: dict[tuple[str, int], list[Persona]] = {}
    by_sector: dict[tuple[str, int, str], list[Persona]] = {}
    for p in people:
        k = (p.country, band(p.age))
        by_band.setdefault(k, []).append(p)
        if _working(p):
            by_work.setdefault(k, []).append(p)
            by_sector.setdefault((*k, p.sector), []).append(p)

    def nearest(pools: dict, country: str, b: int, *extra: str) -> list[Persona]:
        for d in range(13):  # the closest age band that has anyone
            for bb in (b - d, b + d):
                pool = pools.get((country, bb, *extra))
                if pool:
                    return pool
        return []

    for p in people:
        rows = daily_contacts(p.country, p.age)
        if rows is None:
            continue
        cells = [(s, b, m) for s, row in rows.items() for b, m in enumerate(row) if m > 0]
        total = sum(m for *_, m in cells)
        n = _ties_to_start(total, dispersion(p.country), rng)
        if not n or not cells:
            continue
        probs = np.array([m for *_, m in cells]) / total
        countries_, cprobs = zip(*mix[p.country].items())
        cprobs = np.array(cprobs) / sum(cprobs)
        for _ in range(n):
            s, b, _m = cells[int(rng.choice(len(cells), p=probs))]
            c = countries_[int(rng.choice(len(countries_), p=cprobs))]
            pool: list[Persona] = []
            if s == "work" and _working(p):
                pool = nearest(by_sector, c, b, p.sector) or nearest(by_work, c, b)
            pool = [q for q in (pool or nearest(by_band, c, b)) if q.id != p.id]
            if pool:
                g.add_edge(p.id, pool[int(rng.integers(len(pool)))].id)
    return g
