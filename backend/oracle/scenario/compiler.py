"""Scenario builder: turns any paragraph into a ScenarioSpec."""

from __future__ import annotations

import math
from datetime import date

from ..llm import llm
from ..world.countries import blocs, company_types, countries, expand_codes, find_mentions, occupations, resolve
from .models import Force, ScenarioSpec, Segment

SECTORS = [
    "software", "it_services", "finance", "retail", "healthcare", "education", "manufacturing",
    "agriculture", "energy", "media", "telecom", "logistics", "construction", "hospitality",
    "real_estate", "public_sector", "services",
]

SYSTEM = """You are the scenario architect of a world-simulation prediction engine.
Your job: turn the user's description into a precise, simulatable scenario.

Rules:
- Find the real question. If the user describes a product, the question is usually whether the target buyers adopt/buy it within a time horizon. If they describe an event, policy or market, ask what they actually want to know.
- persona_question must be about each simulated person's OWN behaviour or belief, answerable from their point of view (e.g. "Would you start paying for X within 12 months?"). Never ask a person to predict society.
- Pick segments that decide the outcome (buyers, users, voters, blockers) AND segments that shape it (influencers, gatekeepers). Use occupation ids from the catalogue; use custom_occupation only when nothing fits. Weights reflect how many agents each segment should get.
- If the user ties a segment to specific countries (e.g. "founders in the USA, analysts at Infosys in India"), set that segment's countries. Leave countries empty when a segment exists in every target.
- For B2B products set b2b=true; committee simulation will model the buying group.
- Add "diffusion" to modes when word of mouth, virality or public opinion matters.
- Targets: ISO3 codes. If the user names none, choose the most relevant markets (max 3).
- forces: outside pressures that change the outcome, especially ones from countries/blocs that are NOT targets (e.g. EU AI Act and GDPR affecting Indian IT firms with EU clients; US interest rates; Chinese competitors). Be concrete.
- assumed_reach: realistic share of the target audience that will even hear about this within the horizon. New startups usually reach well under 30% of a market.
- research_queries: 3-6 web searches that would ground the simulation in current facts (competitors, prices, regulations, recent news).
- Be neutral. Do not assume success.
- Society (word of mouth) is always simulated, so always include "diffusion" in modes.
- When context files are attached (pitch decks, product docs, pricing pages, research), use them to get the product, price, audience, markets and competitors right. The subject must describe what a member of the public or a buyer would actually see (the offer, the price, the claims), never internal plans, targets or confidential numbers."""


def _catalogue() -> str:
    occ = "\n".join(f"- {o.id}: {o.title}" for o in occupations().values())
    ctypes = ", ".join(company_types().keys())
    ctry = "; ".join(f"{c.iso3} {c.name}" for c in countries().values())
    bl = ", ".join(f"{b.id} ({b.name})" for b in blocs().values())
    return (
        f"Occupation catalogue:\n{occ}\n\nCompany types: {ctypes}\n\n"
        f"Countries: {ctry}\nBlocs (valid as force origins): {bl}\n\nSectors: {', '.join(SECTORS)}"
    )


def default_weights(targets: list[str], b2b: bool) -> dict[str, float]:
    cs = countries()
    raw: dict[str, float] = {}
    for t in targets:
        c = cs[t]
        # Business scenarios weight by economic weight of the market; consumer ones by people.
        raw[t] = math.sqrt(c.workforce_m * (c.gdp_pc_usd / 10000)) if b2b else math.sqrt(c.population_m)
    total = sum(raw.values()) or 1
    return {k: round(v / total, 4) for k, v in raw.items()}


def normalize(spec: ScenarioSpec, prompt: str, overrides: list[str] | None = None) -> ScenarioSpec:
    """Make an LLM-produced (or user-edited) spec safe to simulate."""
    cs = countries()

    # Targets: explicit user choice wins, then the model, then mentions in the text.
    targets: list[str] = []
    if overrides:
        targets = expand_codes([resolve(t) or t for t in overrides])
    if not targets:
        targets = expand_codes([resolve(t) or t for t in spec.targets])
    if not targets:
        targets = expand_codes(find_mentions(prompt))
    if not targets:
        targets = ["USA"]
    spec.targets = targets[:12]

    weights = {k: v for k, v in (spec.target_weights or {}).items() if k in spec.targets and v > 0}
    if overrides or len(weights) != len(spec.targets):
        weights = default_weights(spec.targets, spec.b2b)
    total = sum(weights.values()) or 1
    spec.target_weights = {k: round(v / total, 4) for k, v in weights.items()}

    occ = occupations()
    ctypes = company_types()
    cleaned: list[Segment] = []
    for seg in spec.segments:
        valid = [o for o in seg.occupations if o in occ]
        unknown = [o for o in seg.occupations if o not in occ]
        if unknown and not seg.custom_occupation:
            seg.custom_occupation = unknown[0].replace("_", " ")
        seg.occupations = valid
        seg.company_types = [c for c in seg.company_types if c in ctypes]
        wanted = expand_codes([resolve(x) or x for x in seg.countries])
        seg.countries = [c for c in wanted if c in spec.targets]
        if wanted and not seg.countries:
            continue  # tied to countries that are not being simulated
        if seg.weight <= 0:
            continue
        cleaned.append(seg)
    if not cleaned:
        cleaned = [Segment(name="General public", description="Representative working-age adults", weight=1.0)]
    spec.segments = cleaned[:10]

    forces: list[Force] = []
    for f in spec.forces:
        origin = resolve(f.origin) or ("global" if f.origin.lower() in {"global", "world", "worldwide"} else f.origin)
        affects = [a for a in (resolve(x) for x in f.affects) if a in cs] or []
        forces.append(f.model_copy(update={"origin": origin, "affects": affects}))
    spec.forces = forces[:12]

    spec.sectors = [s for s in spec.sectors if s in SECTORS]
    return spec


async def compile_scenario(prompt: str, model: str, overrides: list[str] | None = None, context: str = "") -> ScenarioSpec:
    user = (
        f"Today is {date.today().isoformat()}.\n\n{_catalogue()}\n\n"
        f"User-selected target countries: {', '.join(overrides) if overrides else 'none - choose'}\n\n"
        + (f"CONTEXT FILES FROM THE USER:\n{context}\n\n" if context else "")
        + f"USER DESCRIPTION:\n\"\"\"\n{prompt}\n\"\"\""
    )
    spec = await llm.json(
        task="compile_scenario",
        model=model,
        system=SYSTEM,
        user=user,
        schema=ScenarioSpec,
        temperature=0.3,
        mock_ctx={"prompt": prompt, "context": context[:3000], "targets": overrides or []},
    )
    spec = normalize(spec, prompt, overrides)
    if "diffusion" not in spec.modes:
        spec.modes.append("diffusion")
    return spec
