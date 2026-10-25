"""A knowledge graph for each simulation.

Before anyone is simulated, the orchestrator maps the topic: the product or idea,
competitors, companies, regulators and rules, technologies, customer types, places
and events, and how they relate ("competes with", "regulates", "used by"). It
works from the question, the setup, the user's files and the web research, and
every link cites the facts it came from. Things only the user's files reveal stay
private: they are drawn for the user but never reach simulated people.

The graph is used three ways:
1. Each person is told the few links that touch them (their country, their kind
   of work, the product itself), not the whole graph.
2. After the run, Tellaris counts which entities people brought up in their answers
   and posts, and how those people leaned.
3. The run page draws it as an interactive map.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from ..llm import llm
from ..population.models import Persona
from ..scenario.models import ScenarioSpec
from .search import Fact

EntityType = Literal["product", "competitor", "company", "regulator", "policy", "technology", "customer", "place", "event", "concept"]
TYPES = ("product", "competitor", "company", "regulator", "policy", "technology", "customer", "place", "event", "concept")
MAX_ENTITIES = 30
MAX_RELATIONS = 60


class GEntity(BaseModel):
    id: str = Field(description="Short lowercase id, letters, digits and dashes, unique")
    name: str = Field(description="The name people would use")
    type: EntityType
    summary: str = Field(default="", description="One plain sentence on what it is and why it matters here")
    aliases: list[str] = Field(default_factory=list, description="Other words people might use for it, e.g. 'price', 'cost' for a price concept")
    countries: list[str] = Field(default_factory=list, description="ISO3 codes it mainly applies to; empty = everywhere")
    facts: list[int] = Field(default_factory=list, description="Numbers of the facts it comes from, if any")

    @field_validator("aliases")
    @classmethod
    def _aliases(cls, v: list[str]) -> list[str]:
        return [a.strip() for a in v if 2 < len(a.strip()) < 40][:6]


class GRelation(BaseModel):
    source: str = Field(description="Entity id")
    target: str = Field(description="Entity id")
    label: str = Field(description="A short verb phrase, at most 4 words, e.g. 'competes with', 'regulates', 'used by'")
    detail: str = Field(default="", description="One sentence stating the fact behind the link")
    facts: list[int] = Field(default_factory=list, description="Numbers of the facts it comes from, if any")


class KnowledgeGraph(BaseModel):
    entities: list[GEntity] = Field(default_factory=list)
    relations: list[GRelation] = Field(default_factory=list)


SYSTEM = """You map the world around a question as a small knowledge graph, so that simulated people can be grounded in it
and a reader can see what the question touches.

Entities (at most 30): the product or idea itself (type "product", exactly one), competitors and alternatives people use
today, other companies involved, regulators and laws or policies, technologies, kinds of customers or people affected,
places that matter, events, and a few concepts people will argue about (price, trust, privacy, habit...). Give concepts
aliases: the everyday words people use for them.
Relations (at most 60): short verb phrases between entity ids ("competes with", "regulates", "used by", "costs more than",
"partners with", "applies in", "worries"). Each one states its fact in one sentence.

Use only what the description, the setup and the numbered facts support, plus widely known facts. Cite fact numbers where
they apply. Prefer specific names to generic ones. Do not invent figures."""


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:40] or "x"


def _user_prompt(spec: ScenarioSpec, facts: list[Fact]) -> str:
    lines = [
        f"TITLE: {spec.title}",
        f"QUESTION: {spec.question}",
        f"WHAT PEOPLE SEE: {spec.subject}",
        f"COUNTRIES: {', '.join(spec.targets)}",
    ]
    if spec.competitors:
        lines.append(f"KNOWN ALTERNATIVES: {', '.join(spec.competitors)}")
    if spec.segments:
        lines.append("GROUPS: " + "; ".join(f"{s.name} ({s.description})" if s.description else s.name for s in spec.segments))
    if spec.forces:
        lines.append("OUTSIDE FACTORS: " + "; ".join(f"{f.name} from {f.origin}: {f.description}" for f in spec.forces))
    if facts:
        lines.append("\nFACTS:")
        lines += [f"[{i}] {f.statement}" + ("" if f.public else " (internal)") for i, f in enumerate(facts, 1)]
    return "\n".join(lines)


def clean(kg: KnowledgeGraph, spec: ScenarioSpec, facts: list[Fact]) -> dict[str, Any]:
    """Unique ids, one product node, links only between known entities, sources and privacy attached."""
    entities: dict[str, dict[str, Any]] = {}
    by_name: dict[str, str] = {}
    id_map: dict[str, str] = {}
    for e in kg.entities[: MAX_ENTITIES + 10]:
        name = e.name.strip()
        if not name:
            continue
        key = name.lower()
        if key in by_name:
            id_map[e.id] = by_name[key]
            continue
        eid = base = _slug(e.id or name)
        n = 2
        while eid in entities:
            eid, n = f"{base}-{n}", n + 1
        id_map[e.id] = eid
        by_name[key] = eid
        entities[eid] = {
            "id": eid, "name": name[:80], "type": e.type, "summary": e.summary.strip()[:300],
            "aliases": e.aliases, "countries": [c for c in e.countries if len(c) == 3][:10], "fact_ids": [i for i in e.facts if 1 <= i <= len(facts)],
        }
        if len(entities) >= MAX_ENTITIES:
            break

    products = [e for e in entities.values() if e["type"] == "product"]
    if not products:
        pid = _slug(spec.title) or "product"
        entities[pid] = {"id": pid, "name": spec.title[:80], "type": "product", "summary": spec.subject[:300], "aliases": [], "countries": [], "fact_ids": []}
        products = [entities[pid]]
    for extra in products[1:]:
        extra["type"] = "company"
    product_id = products[0]["id"]

    relations = []
    seen = set()
    for r in kg.relations:
        s, t = id_map.get(r.source, r.source), id_map.get(r.target, r.target)
        if s not in entities or t not in entities or s == t or (s, t, r.label.lower()) in seen:
            continue
        seen.add((s, t, r.label.lower()))
        fids = [i for i in r.facts if 1 <= i <= len(facts)]
        relations.append({"source": s, "target": t, "label": r.label.strip()[:40] or "relates to", "detail": r.detail.strip()[:300], "fact_ids": fids})
        if len(relations) >= MAX_RELATIONS:
            break

    def sources(fids: list[int]) -> tuple[list[dict[str, Any]], bool]:
        out, public = [], True
        for i in fids:
            f = facts[i - 1]
            public = public and f.public
            out.append({"statement": f.statement, "urls": f.source_urls[:2], "public": f.public})
        return out, public

    for e in entities.values():
        e["sources"], _ = sources(e.pop("fact_ids"))
        # An entity is private only when everything known about it comes from internal facts.
        # The product is always public: people are shown what it is.
        # Private sources stay listed for the user (marked); simulated people only ever get public links.
        e["public"] = e["id"] == product_id or not e["sources"] or any(s["public"] for s in e["sources"])
    for r in relations:
        r["sources"], pub = sources(r.pop("fact_ids"))
        r["public"] = pub and entities[r["source"]]["public"] and entities[r["target"]]["public"]

    # Drop entities nothing connects to, except the product.
    linked = {r["source"] for r in relations} | {r["target"] for r in relations} | {product_id}
    entities = {k: v for k, v in entities.items() if k in linked}
    return {"product": product_id, "entities": list(entities.values()), "relations": relations}


async def build_graph(spec: ScenarioSpec, facts: list[Fact], model: str) -> dict[str, Any]:
    kg = await llm.json(
        task="knowledge_graph", model=model, system=SYSTEM, user=_user_prompt(spec, facts), schema=KnowledgeGraph, temperature=0.2,
        mock_ctx={"spec": spec.model_dump(), "facts": [f.model_dump() for f in facts]},
    )
    return clean(kg, spec, facts)


# ---------- grounding people ----------

def _words(*texts: str) -> set[str]:
    return {w for t in texts for w in re.findall(r"[a-z]{4,}", (t or "").lower())}


def context_for(graph: dict[str, Any], countries: dict[str, str], k: int = 4) -> Callable[[Persona], list[str]]:
    """Returns a function giving each person the few public links that touch them."""
    ents = {e["id"]: e for e in graph.get("entities", [])}
    product = graph.get("product")
    rels = [r for r in graph.get("relations", []) if r.get("public")]

    def for_person(p: Persona) -> list[str]:
        mine = _words(p.segment, p.occupation, p.sector, p.company_type)
        scored = []
        for r in rels:
            pair = [ents[r["source"]], ents[r["target"]]]
            if any(e["countries"] and p.country not in e["countries"] for e in pair):
                continue
            s = 0.0
            for e in pair:
                if e["id"] == product:
                    s += 2
                if e["type"] == "place" and e["name"].lower() == countries.get(p.country, "").lower():
                    s += 2.5
                if e["countries"] and p.country in e["countries"]:
                    s += 1.5
                if e["type"] in ("customer", "company") and mine & _words(e["name"], e["summary"]):
                    s += 2
                if e["type"] in ("competitor", "regulator", "policy"):
                    s += 0.75
            scored.append((s, r))
        scored.sort(key=lambda x: -x[0])
        out = []
        for _, r in scored[:k]:
            a, b = ents[r["source"]]["name"], ents[r["target"]]["name"]
            out.append(r["detail"] or f"{a} {r['label']} {b}.")
        return out

    return for_person


# ---------- what people talked about ----------

def _pattern(e: dict[str, Any]) -> re.Pattern[str] | None:
    names = [e["name"], *e.get("aliases", [])]
    names = [n for n in names if len(n) >= 3]
    if not names:
        return None
    return re.compile(r"\b(" + "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True)) + r")\b", re.IGNORECASE)


def mentions(graph: dict[str, Any], reactions: list[Any], feed: list[dict[str, Any]], people: dict[str, Persona]) -> dict[str, Any]:
    """Which entities people brought up, how often, how those people leaned, and examples."""
    texts: list[tuple[str, str, str, float]] = []  # persona id, kind, text, leaning
    first: dict[str, Any] = {}
    lean: dict[str, list[float]] = {}
    for r in reactions:
        first.setdefault(r.persona_id, r)
        lean.setdefault(r.persona_id, []).append(r.p_stated)
    for pid, r in first.items():
        p = sum(lean[pid]) / len(lean[pid])
        parts = [x.strip().rstrip(".") for x in [r.quote, *r.reasons, *r.objections] if x and x.strip()]
        texts.append((pid, "answer", ". ".join(parts) + ".", p))
    for it in feed:
        if it.get("kind") in ("post", "reply") and it.get("author"):
            texts.append((it["author"], "post", it.get("text", ""), it.get("p") if it.get("p") is not None else 0.5))

    out: dict[str, Any] = {}
    for e in graph.get("entities", []):
        pat = _pattern(e)
        if not pat:
            continue
        who: dict[str, float] = {}
        samples = []
        for pid, kind, text, p in texts:
            m = pat.search(text)
            if not m:
                continue
            who.setdefault(pid, p)
            if len(samples) < 6 and pid in people and not any(s["persona_id"] == pid for s in samples):
                start = max(0, m.start() - 90)
                end = min(len(text), m.end() + 110)
                if start:  # snap to whole words
                    start = text.find(" ", start) + 1 or start
                if end < len(text):
                    end = text.rfind(" ", m.end(), end) if text.rfind(" ", m.end(), end) > 0 else end
                snippet = ("…" if start else "") + text[start:end].strip() + ("…" if end < len(text) else "")
                pp = people[pid]
                samples.append({"persona_id": pid, "name": pp.name, "country": pp.country, "occupation": pp.occupation, "kind": kind, "text": snippet, "p": round(p, 3)})
        if who:
            out[e["id"]] = {
                "people": len(who),
                "lean": round(sum(who.values()) / len(who), 4),
                "samples": samples,
            }
    return out
