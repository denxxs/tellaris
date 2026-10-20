"""Scenario builder: turns any paragraph into a ScenarioSpec."""

from __future__ import annotations

import math
from datetime import date

from ..llm import llm
from ..world.countries import blocs, company_types, countries, expand_codes, find_mentions, global_sample, occupations, resolve
from pydantic import BaseModel

from .lenses import default_lens
from .models import Force, ScenarioSpec, Segment

SECTORS = [
    "software", "it_services", "finance", "retail", "healthcare", "education", "manufacturing",
    "agriculture", "energy", "media", "telecom", "logistics", "construction", "hospitality",
    "real_estate", "public_sector", "services",
]

SYSTEM = """You are the scenario architect of a world-simulation prediction engine.
Your job: turn the user's description into a precise, simulatable scenario.

Oracle answers ANY question about people: launches and pricing, but also opinions, culture, habits, preferences, hypotheticals,
politics, food, dating, trends and silly questions. Take every question seriously and simulate it properly.

Rules:
- Find the real question. For a product it is usually whether the target buyers adopt or buy it within a time horizon. For anything
  else, ask what the user actually wants to know about people.
- subject_kind: product/feature/pricing/campaign/company/market for offers people might take up; personal or habit for choices about
  their own life (would you move abroad, try a 4-day week, eat bugs); opinion/preference/culture/hypothetical/policy/event for what
  people think, prefer or would choose.
- outcome_type: binary for yes/no; categorical for "which one" or attitude scales (e.g. "Love it, It's fine, Hate it", or the options
  the user lists, 2-6 short labels in their words); numeric when the answer is a number (how much would you pay, how many hours).
  For categorical, outcomes[0] is the most interesting option to track.
- lens (decides how the question is treated):
  b2b = companies deciding to buy (software, services, tools for work). Use it whenever the buyer is a business.
  consumer = people buying or using something for themselves (apps, food, subscriptions, gadgets, events with a ticket price).
  personal = choices about their own life (move abroad, quit a job, try a 4-day week, eat bugs, get a pet).
  opinion = what people think, prefer, find funny or would pick (pizza toppings, names, ads, slogans, culture, hypotheticals).
  forecast = something that will happen and people take part in or expect (votes, referendums, tours selling out, results).
- scope: "global" when the question is about the world or "everywhere", otherwise "countries".
- Groups (segments) can be anything, combining filters: occupations from the catalogue (or custom_occupation), countries,
  age_min/age_max (Gen Z adults 18-28, millennials 29-44, Gen X 45-60, boomers 61-80), gender (only if the question is about one),
  company_types, and a free-text trait for anything else ("own a dog", "go to the gym weekly", "have used a dating app",
  "Taylor Swift fans", "earn over $100k"). With a trait, set trait_share to your best estimate of the share of the group's base
  population (same countries, ages and jobs) who have that trait, 0-1. Leave occupations empty for the general public.
- persona_question must be about each simulated person's OWN behaviour or belief, answerable from their point of view (e.g. "Would you start paying for X within 12 months?"). Never ask a person to predict society.
- Pick segments that decide the outcome (buyers, users, voters, blockers) AND segments that shape it (influencers, gatekeepers). Use occupation ids from the catalogue; use custom_occupation only when nothing fits. Weights reflect how many agents each segment should get.
- If the user ties a segment to specific countries (e.g. "founders in the USA, analysts at Infosys in India"), set that segment's countries. Leave countries empty when a segment exists in every target.
- Set b2b=true only for the b2b lens; buying committees are simulated then.
- Add "diffusion" to modes when word of mouth, virality or public opinion matters.
- Targets: ISO3 codes. If the user names none, choose the most relevant markets (max 3), unless scope is global.
- forces: outside pressures that change the outcome, especially ones from countries/blocs that are NOT targets (e.g. EU AI Act and GDPR affecting Indian IT firms with EU clients; US interest rates; Chinese competitors). Be concrete.
- assumed_reach: realistic share of the WHOLE target audience (all the people in the segments, often millions) that will even hear about this within the horizon. A new or little-known company with no big launch budget usually reaches 0.2-2% of a national market in a year; a well-funded launch maybe 5%; a household brand or a law in the news 30-90%.
- price: when there are several plans, use the plan a typical buyer in the main segment would start on (usually the cheapest paid plan), name the other plans in the subject, and keep the unit exactly as written (per workspace, per seat, per month). Never use the top tier as the price unless the user says so.
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


def normalize(spec: ScenarioSpec, prompt: str, overrides: list[str] | None = None, global_depth: str = "quick") -> ScenarioSpec:
    """Make an LLM-produced (or user-edited) spec safe to simulate."""
    cs = countries()

    if spec.scope == "global" and not overrides:
        overrides = global_sample(global_depth)

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
    spec.targets = targets[: 40 if spec.scope == "global" else 12]

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
    for seg in spec.segments:
        if seg.age_min is not None and seg.age_max is not None and seg.age_max < seg.age_min:
            seg.age_min, seg.age_max = seg.age_max, seg.age_min
    if spec.lens is None:
        spec.lens = default_lens(spec.subject_kind, spec.b2b)
    if spec.lens == "b2b":
        spec.b2b = True
        if "committee" not in spec.modes:
            spec.modes.append("committee")
    else:
        spec.b2b = False
        spec.modes = [m for m in spec.modes if m != "committee"]
    return spec


async def compile_scenario(
    prompt: str, model: str, overrides: list[str] | None = None, context: str = "",
    lens: str | None = None, scope: str | None = None, global_depth: str = "quick",
) -> ScenarioSpec:
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
    if lens:
        spec.lens = lens  # the user's choice wins
    if scope:
        spec.scope = scope
    spec = normalize(spec, prompt, overrides, global_depth)
    if "diffusion" not in spec.modes:
        spec.modes.append("diffusion")
    if context:
        spec.subject = await public_brief(spec, prompt, context, model)
    return spec


BRIEF_SYSTEM = """You write what a prospective customer in the target market would actually see about this offer:
the website, the pricing page, a sales demo and the first days of a free trial. Write 4-8 plain sentences.
Include: what it is and does, who it is for, the price and plans as a customer would see them, notable features and claims,
and anything a customer would directly notice while using it.
Leave out internal details a customer cannot see: hosting and architecture, internal providers and integrations being
wired up, internal credit mechanics, costs, roadmaps, targets, team. Do not argue for or against it."""


class _Brief(BaseModel):
    description: str


async def public_brief(spec: ScenarioSpec, prompt: str, context: str, model: str) -> str:
    """The scenario's description, stripped of internals a customer could not know."""
    user = (
        f"Target market: {', '.join(spec.targets)}. Question: {spec.question}\n"
        + (f"Price as the scenario has it: {spec.price.amount:g} {spec.price.currency} per {spec.price.period}\n" if spec.price else "")
        + f"\nUSER DESCRIPTION:\n{prompt}\n\nDOCUMENTS:\n{context[:30000]}"
    )
    try:
        out = await llm.json(task="public_brief", model=model, system=BRIEF_SYSTEM, user=user, schema=_Brief, temperature=0.2, mock_ctx={"subject": spec.subject})
        return out.description.strip() or spec.subject
    except Exception:  # noqa: BLE001 - keep the planner's description if this step fails
        return spec.subject
