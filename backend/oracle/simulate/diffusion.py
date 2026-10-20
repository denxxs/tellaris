"""Who knows whom: the contact network the society talks over."""

from __future__ import annotations

import networkx as nx
import numpy as np

from ..population.models import Persona


def build_network(people: list[Persona], k: int = 6, seed: int | None = None) -> nx.Graph:
    rng = np.random.default_rng(seed)
    g = nx.Graph()
    for p in people:
        g.add_node(p.id)
    ids = [p.id for p in people]
    by_country: dict[str, list[Persona]] = {}
    for p in people:
        by_country.setdefault(p.country, []).append(p)
    for p in people:
        same = [q for q in by_country[p.country] if q.id != p.id]
        for _ in range(k // 2):
            r = rng.random()
            if r < 0.75 and same:
                # Prefer people in the same sector or segment.
                close = [q for q in same if q.sector == p.sector or q.segment == p.segment]
                pool = close if close and rng.random() < 0.6 else same
                q = pool[int(rng.integers(len(pool)))]
                g.add_edge(p.id, q.id)
            elif len(ids) > 1:
                q = ids[int(rng.integers(len(ids)))]
                if q != p.id:
                    g.add_edge(p.id, q)
    # Nobody is a hermit: everyone knows at least three people, mostly in their own country.
    for p in people:
        same = [q.id for q in by_country[p.country] if q.id != p.id] or [i for i in ids if i != p.id]
        tries = 0
        while g.degree(p.id) < min(3, len(ids) - 1) and same and tries < 20:
            g.add_edge(p.id, same[int(rng.integers(len(same)))])
            tries += 1
    return g
