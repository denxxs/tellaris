"""Who knows whom: the contact network the society talks over.

How often a contact lives in another country comes from Meta's Social Connectedness Index: the
share of a country's friendships that are with each country, itself included. Within a country,
contacts are picked evenly (no data says who befriends whom by job). k, the number of contacts
each person starts from, is a simulation setting, not a claim about the world.
"""

from __future__ import annotations

import networkx as nx
import numpy as np

from ..population.models import Persona
from ..world.ties import friend_share


def country_mix(home: str, present: list[str]) -> dict[str, float]:
    """Where a person from `home` finds contacts, among the countries in this run. A country with
    no friendship data keeps its contacts at home rather than guessing ties."""
    shares = {c: friend_share(home, c) for c in present}
    if shares.get(home) is None:
        return {home: 1.0}
    shares = {c: v for c, v in shares.items() if v}
    total = sum(shares.values())
    return {c: v / total for c, v in shares.items()} if total else {home: 1.0}


def build_network(people: list[Persona], k: int = 6, seed: int | None = None) -> nx.Graph:
    rng = np.random.default_rng(seed)
    g = nx.Graph()
    for p in people:
        g.add_node(p.id)
    by_country: dict[str, list[Persona]] = {}
    for p in people:
        by_country.setdefault(p.country, []).append(p)
    present = sorted(by_country)
    mix = {c: country_mix(c, present) for c in present}
    for p in people:
        countries_, probs = zip(*mix[p.country].items())
        for _ in range(k // 2):
            c = countries_[int(rng.choice(len(countries_), p=np.array(probs) / sum(probs)))]
            pool = [q for q in by_country[c] if q.id != p.id]
            if pool:
                g.add_edge(p.id, pool[int(rng.integers(len(pool)))].id)
    # Nobody is a hermit: everyone knows at least three people, drawn the same way.
    ids = [p.id for p in people]
    for p in people:
        countries_, probs = zip(*mix[p.country].items())
        tries = 0
        while g.degree(p.id) < min(3, len(ids) - 1) and tries < 20:
            tries += 1
            c = countries_[int(rng.choice(len(countries_), p=np.array(probs) / sum(probs)))]
            pool = [q for q in by_country[c] if q.id != p.id]
            if pool:
                g.add_edge(p.id, pool[int(rng.integers(len(pool)))].id)
    return g
