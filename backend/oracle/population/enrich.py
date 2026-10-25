"""Give each sampled person a name, backstory and point of view."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from pydantic import BaseModel

from ..llm import LLMError, llm
from .models import Persona

BATCH = 8

SYSTEM = """You give simulated people a human face, using ONLY the facts you are given (country, age, gender, job,
company, sector, income, traits and any extra trait).
For each person write: a culturally appropriate full name for their country and gender (avoid the most stereotypical
names), a one-line tagline (who they are, like a social media bio), a 1-2 sentence backstory in third person, a
1-2 sentence typical day, and a one-line description of how they talk.
Restate the given facts in human words; do NOT add new facts. In particular, never invent which products, apps or
brands they use, where they get news, their values, opinions, priorities, problems, family or anything about the
topic being simulated. Those would change how they answer, and Oracle only lets real data do that."""


class Enriched(BaseModel):
    id: str
    name: str
    bio: str
    voice: str = ""
    tagline: str = ""
    typical_day: str = ""


class EnrichedBatch(BaseModel):
    people: list[Enriched]


def _brief(p: Persona) -> str:
    return (
        f"id={p.id} | {p.age} {p.gender} | {p.country_name} | {p.occupation} ({p.seniority}) | "
        f"{p.company_type}{f' ({p.company_size_text})' if p.company_size_text else ''} | sector {p.sector} | "
        + (f"${p.income_usd:,}/yr ({p.income_band})" if p.income_usd is not None else "earnings: none or no data")
        + (f" | {', '.join(k for k, v in p.facts.items() if v)}" if p.facts else "")
        + (f" | also: {p.group_trait}" if p.group_trait else "")
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
            if len(batch) > 1:
                # One bad reply shouldn't leave eight people nameless: retry in halves.
                for half in (batch[: len(batch) // 2], batch[len(batch) // 2 :]):
                    try:
                        part = await llm.json(
                            task="enrich_personas", model=model, system=SYSTEM,
                            user=f"Simulation context (for flavour only, do not mention it): {context}\n\nPeople:\n" + "\n".join(_brief(p) for p in half),
                            schema=EnrichedBatch, temperature=0.9, mock_ctx={"people": [p.model_dump() for p in half]},
                        )
                        out.people.extend(part.people)
                    except LLMError:
                        pass
        for e in out.people:
            p = by_id.get(e.id)
            if p is None:
                continue
            p.name = e.name.strip()[:80]
            p.bio = e.bio.strip()[:600]
            p.voice = e.voice.strip()[:200]
            p.tagline = e.tagline.strip()[:120]
            p.typical_day = e.typical_day.strip()[:400]
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
