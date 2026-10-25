"""Influence map: which countries and blocs the targets are tied to, and through what.

Every tie is measured (see ties.py): who buys a country's goods and services, where its imports
come from, where its people's friends abroad live, where those who left now live, and EU law
for EU members. The largest few per channel are shown. Things the user states are true come in
as scenario edges.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from . import ties as ties_mod
from .countries import blocs, countries
from .ties import CHANNELS

TOP_PER_CHANNEL = 3  # how many partners per kind of tie to show and to tell people about


class InfluenceEdge(BaseModel):
    source: str
    target: str
    channel: str
    strength: float
    sectors: list[str]
    note: str
    origin: str = "data"  # data | scenario


class Influencer(BaseModel):
    """A country or bloc that affects one or more targets."""

    code: str
    name: str
    kind: str  # country | bloc
    total_strength: float
    edges: list[InfluenceEdge] = Field(default_factory=list)
    via: list[str] = Field(default_factory=list)  # unused: only direct, measured ties
    order: int = 1


def channels() -> dict[str, str]:
    return {k: v["about"] for k, v in CHANNELS.items()} | {"scenario": "Something you said is true"}


def node_name(code: str) -> str:
    if code in countries():
        return countries()[code].name
    if code in blocs():
        return blocs()[code].name
    return code


def _pct(x: float) -> str:
    return f"{x:.0%}" if x >= 0.01 else "under 1%"


def measured_edges(target: str) -> list[InfluenceEdge]:
    """The target's largest measured ties, per channel. Only data: shares come straight from the
    sources in ties.py; nothing is weighted or judged."""
    out: list[InfluenceEdge] = []
    tname = node_name(target)
    eu = blocs().get("EU")
    if eu and target in eu.members:
        out.append(InfluenceEdge(source="EU", target=target, channel="regulation", strength=1.0, sectors=["all"],
                                 note=CHANNELS["regulation"]["text"].format(tgt=tname), origin="data"))
    for ch, spec in CHANNELS.items():
        if spec["list"] is None:
            continue
        for src, share, extra in ties_mod.partners(target, ch)[:TOP_PER_CHANNEL]:
            if src == target or (src not in countries() and src not in blocs()):
                continue
            sname = node_name(src)
            if src == "EU":
                sname = "other EU countries" if eu and target in eu.members else "the EU"
            note = spec["text"].format(src=sname, tgt=tname, pct=_pct(share), n=f"{extra.get('n', 0):,}")
            note = note[0].upper() + note[1:]
            src_name = extra.get("source") or ties_mod.SOURCES[ch]
            note += ties_mod.pair_note(target, src) + f". Source: {src_name}" + (f" {extra['year']}" if extra.get("year") and str(extra["year"]) not in src_name else "") + "."
            out.append(InfluenceEdge(source=src, target=target, channel=ch, strength=round(share, 4), sectors=spec["sectors"], note=note, origin="data"))
    return out


def expand(
    targets: list[str],
    extra: list[InfluenceEdge] | None = None,
    threshold: float = 0.0,  # kept for old callers; measured ties aren't cut by a judged strength
    sectors: list[str] | None = None,
) -> list[Influencer]:
    """Countries and blocs tied to the targets, strongest tie first.

    sectors narrows to ties that touch the scenario's sectors (or everyone).
    """
    target_set = set(targets)
    sector_set = set(sectors or [])

    def relevant(e: InfluenceEdge) -> bool:
        if not sector_set:
            return True
        return "all" in e.sectors or bool(set(e.sectors) & sector_set)

    found: dict[str, Influencer] = {}
    edges = [e for t in targets for e in measured_edges(t)] + [e for e in (extra or []) if e.target in target_set]
    for e in edges:
        if e.source in target_set or not relevant(e):
            continue
        kind = "bloc" if e.source in blocs() else "country"
        inf = found.setdefault(e.source, Influencer(code=e.source, name=node_name(e.source), kind=kind, total_strength=0.0))
        inf.edges.append(e)
    for inf in found.values():
        inf.edges.sort(key=lambda e: -e.strength)
        inf.total_strength = round(max(e.strength for e in inf.edges), 4)  # for ordering only
    return sorted(found.values(), key=lambda i: (-len({e.target for e in i.edges}), -i.total_strength))


def anchor(code: str) -> list[float] | None:
    """Where to draw a country or bloc on a map: the capital, or the centre of a bloc's capitals."""
    cs = countries()
    if code in cs:
        return cs[code].anchor
    if code in blocs():
        pts = [cs[m].anchor for m in blocs()[code].members if m in cs and cs[m].anchor]
        if pts:
            return [round(sum(p[0] for p in pts) / len(pts), 2), round(sum(p[1] for p in pts) / len(pts), 2)]
    return None


def graph_payload(targets: list[str], influencers: list[Influencer]) -> dict[str, Any]:
    """Nodes and links for the frontend map."""
    nodes = []
    for t in targets:
        nodes.append({"id": t, "name": node_name(t), "role": "target", "anchor": anchor(t)})
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
                "anchor": anchor(i.code),
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
