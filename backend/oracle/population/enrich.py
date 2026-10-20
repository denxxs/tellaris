"""Give each sampled person a name, backstory and point of view."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from pydantic import BaseModel, Field

from ..llm import LLMError, llm
from .models import Persona

BATCH = 8

SYSTEM = """You write realistic, specific people for a social simulation.
For each person you get fixed facts (country, job, age, income, traits). Keep every fact.
Add: a culturally appropriate full name for their country that matches their gender (avoid the most stereotypical names),
a one-line tagline (who they are in a few words, like a social media bio), a 2-3 sentence backstory in third person,
3 values they live by, 3 current priorities, 2 frustrations, a 1-2 sentence typical day, 2-4 tools, products or services
they already use for their work or life, their household in a few words, 3 information sources they actually use
(specific publications, communities, people, apps), and a one-line description of how they talk.
Make people different from each other. Include ordinary, busy, distracted, sceptical people - not just enthusiasts.
Skeptical traits must show up as scepticism. Low budget authority means they cannot buy on their own."""


class Enriched(BaseModel):
    id: str
    name: str
    bio: str
    priorities: list[str] = Field(default_factory=list)
    frustrations: list[str] = Field(default_factory=list)
    info_sources: list[str] = Field(default_factory=list)
    voice: str = ""
    tagline: str = ""
    values: list[str] = Field(default_factory=list)
    typical_day: str = ""
    tools_today: list[str] = Field(default_factory=list)
    household: str = ""


class EnrichedBatch(BaseModel):
    people: list[Enriched]


def _brief(p: Persona) -> str:
    t = p.traits
    return (
        f"id={p.id} | {p.age} {p.gender} | {p.country_name} | {p.occupation} ({p.seniority}) | "
        f"{p.company_type} ~{p.company_size} staff | sector {p.sector} | ${p.income_usd:,}/yr ({p.income_band}) | "
        f"tech {t.tech_affinity:.2f} skeptic {t.skepticism:.2f} risk {t.risk_appetite:.2f} "
        f"price-sens {t.price_sensitivity:.2f} authority {t.budget_authority:.2f}"
    )


async def enrich(
    people: list[Persona],
    model: str,
    context: str,
    on_batch: Callable[[list[Persona]], Awaitable[None]] | None = None,
) -> int:
    """Enrich in batches. Returns how many people were enriched."""
    by_id = {p.id: p for p in people}
    batches = [people[i : i + BATCH] for i in range(0, len(people), BATCH)]
    done = 0

    async def one(batch: list[Persona]) -> None:
        nonlocal done
        user = (
            f"Simulation context (for flavour only, do not mention it): {context}\n\n"
            "People:\n" + "\n".join(_brief(p) for p in batch)
        )
        try:
            out = await llm.json(
                task="enrich_personas",
                model=model,
                system=SYSTEM,
                user=user,
                schema=EnrichedBatch,
                temperature=0.95,
                mock_ctx={"people": [p.model_dump() for p in batch]},
            )
        except LLMError:
            out = EnrichedBatch(people=[])
        for e in out.people:
            p = by_id.get(e.id)
            if p is None:
                continue
            p.name = e.name.strip()[:80]
            p.bio = e.bio.strip()[:600]
            p.priorities = [x[:160] for x in e.priorities[:4]]
            p.frustrations = [x[:160] for x in e.frustrations[:3]]
            p.info_sources = [x[:80] for x in e.info_sources[:4]]
            p.voice = e.voice.strip()[:200]
            p.tagline = e.tagline.strip()[:120]
            p.values = [x[:60] for x in e.values[:3]]
            p.typical_day = e.typical_day.strip()[:400]
            p.tools_today = [x[:60] for x in e.tools_today[:4]]
            p.household = e.household.strip()[:100]
            done += 1
        for p in batch:
            if not p.name:
                p.name = f"{p.occupation.split('(')[0].strip()} from {p.country_name}"
        if on_batch:
            await on_batch(batch)

    await asyncio.gather(*(one(b) for b in batches))

    # Names are unique within a simulation: on a clash, add a middle initial.
    seen: set[str] = set()
    letters = "ABCDEFGHJKLMNPRSTVW"
    for p in people:
        if p.name in seen:
            parts = p.name.split(" ")
            for k in range(len(letters)):
                letter = letters[(sum(map(ord, p.id)) + k) % len(letters)]
                candidate = " ".join([parts[0], f"{letter}.", *parts[1:]]) if len(parts) > 1 else f"{p.name} {letter}."
                if candidate not in seen:
                    p.name = candidate
                    break
        seen.add(p.name)
    return done
