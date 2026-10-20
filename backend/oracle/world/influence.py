"""Influence map: who shapes decisions in the target countries, and through what.

The graph has countries and blocs as nodes and directed, typed edges
(regulation, outsourcing, capital, ...). Given target countries we pull in
direct influencers, plus second-order influencers whose effect survives decay,
and scenario-specific forces the scenario builder discovered.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import networkx as nx
from pydantic import BaseModel, Field

from ..config import load_json
from .countries import blocs, countries

SECOND_ORDER_DECAY = 0.5


class InfluenceEdge(BaseModel):
    source: str
    target: str
    channel: str
    strength: float
    sectors: list[str]
    note: str
    origin: str = "map"  # map | scenario


class Influencer(BaseModel):
    """A country or bloc that affects one or more targets."""

    code: str
    name: str
    kind: str  # country | bloc
    total_strength: float
    edges: list[InfluenceEdge] = Field(default_factory=list)
    via: list[str] = Field(default_factory=list)  # for second-order effects
    order: int = 1


@lru_cache
def base_edges() -> list[InfluenceEdge]:
    return [InfluenceEdge.model_validate(e) for e in load_json("influence.json")["edges"]]


@lru_cache
def channels() -> dict[str, str]:
    return load_json("influence.json")["_meta"]["channels"]


def node_name(code: str) -> str:
    if code in countries():
        return countries()[code].name
    if code in blocs():
        return blocs()[code].name
    return code


def build_graph(extra: list[InfluenceEdge] | None = None) -> nx.MultiDiGraph:
    g = nx.MultiDiGraph()
    for code, c in countries().items():
        g.add_node(code, name=c.name, kind="country", region=c.region)
    for code, b in blocs().items():
        g.add_node(code, name=b.name, kind="bloc", region="bloc")
    for e in [*base_edges(), *(extra or [])]:
        g.add_edge(e.source, e.target, key=f"{e.channel}:{e.origin}", **e.model_dump())
    return g


def expand(
    targets: list[str],
    extra: list[InfluenceEdge] | None = None,
    threshold: float = 0.25,
    sectors: list[str] | None = None,
) -> list[Influencer]:
    """Influencers of the targets, strongest first.

    sectors narrows to edges that touch the scenario's sectors (or 'all').
    Blocs that targets belong to still count: EU rules matter to Germany.
    """
    g = build_graph(extra)
    target_set = set(targets)
    sector_set = set(sectors or [])

    def relevant(data: dict[str, Any]) -> bool:
        if not sector_set:
            return True
        s = set(data["sectors"])
        return "all" in s or bool(s & sector_set)

    found: dict[str, Influencer] = {}

    for t in targets:
        if t not in g:
            continue
        for src, _, data in g.in_edges(t, data=True):
            if src in target_set or not relevant(data):
                continue
            inf = found.setdefault(
                src,
                Influencer(code=src, name=node_name(src), kind=g.nodes[src]["kind"], total_strength=0.0),
            )
            inf.edges.append(InfluenceEdge.model_validate(data))
            inf.total_strength += data["strength"]

    # Second order: X -> I -> T where I is a direct influencer.
    direct = list(found.keys())
    for mid in direct:
        mid_strength = max(e.strength for e in found[mid].edges)
        for src, _, data in g.in_edges(mid, data=True):
            if src in target_set or src in found or not relevant(data):
                continue
            eff = data["strength"] * mid_strength * SECOND_ORDER_DECAY
            if eff < threshold * 0.6:
                continue
            inf = Influencer(
                code=src,
                name=node_name(src),
                kind=g.nodes[src]["kind"],
                total_strength=eff,
                edges=[InfluenceEdge.model_validate({**data, "strength": round(eff, 3)})],
                via=[mid],
                order=2,
            )
            prev = found.get(src)
            if prev is None or prev.total_strength < eff:
                found[src] = inf

    result = [i for i in found.values() if max(e.strength for e in i.edges) >= threshold or i.order == 2]
    for i in result:
        i.total_strength = round(i.total_strength, 3)
        i.edges.sort(key=lambda e: -e.strength)
    result.sort(key=lambda i: -i.total_strength)
    return result


def graph_payload(targets: list[str], influencers: list[Influencer]) -> dict[str, Any]:
    """Nodes and links for the frontend map."""
    nodes = []
    for t in targets:
        nodes.append({"id": t, "name": node_name(t), "role": "target"})
    for i in influencers:
        nodes.append(
            {
                "id": i.code,
                "name": i.name,
                "role": "influencer",
                "kind": i.kind,
                "strength": i.total_strength,
                "order": i.order,
                "members": blocs()[i.code].members if i.code in blocs() else [],
            }
        )
    links = []
    for i in influencers:
        for e in i.edges:
            links.append(
                {
                    "source": e.source,
                    "target": e.target,
                    "channel": e.channel,
                    "strength": e.strength,
                    "note": e.note,
                    "origin": e.origin,
                    "via": i.via,
                }
            )
    return {"nodes": nodes, "links": links, "channels": channels()}
