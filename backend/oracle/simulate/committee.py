"""B2B buying committees: a champion, a budget owner, a technical evaluator and a
risk/security voice debate the purchase over a few rounds, then decide.

Most B2B deals die in committee, not with the first enthusiastic user, so this
is the number that matters for B2B products.
"""

from __future__ import annotations

import asyncio
from collections import Counter
from collections.abc import Awaitable, Callable
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, Field, field_validator

from ..llm import LLMError, llm
from ..population.models import Persona
from ..research.search import Fact
from ..scenario.models import ScenarioSpec

ROLE_LABEL = {
    "champion": "Champion (would use it and pushes for it)",
    "economic_buyer": "Budget owner (signs off on spend)",
    "technical": "Technical evaluator (integration, reliability)",
    "security_legal": "Security / legal / compliance reviewer",
    "procurement": "Procurement (vendor terms and price)",
    "end_user": "Day-to-day user",
}

B2B_COMPANY_TYPES = {"startup", "scaleup", "smb", "midmarket", "enterprise", "government"}


class Statement(BaseModel):
    stance: float = Field(ge=-1, le=1, description="-1 strongly against, +1 strongly for")
    statement: str = Field(description="What you say in the meeting, 1-3 sentences, in character")
    conditions: list[str] = Field(default_factory=list, description="Conditions for your yes, up to 2")
    concerns: list[str] = Field(default_factory=list, description="Your main concerns, up to 2")


class Decision(BaseModel):
    decision: Literal["buy", "pilot", "defer", "reject"]
    probability_of_purchase: float = Field(ge=0, le=1, description="Chance this company pays within the horizon")
    deal_cycle_months: float = Field(ge=0, le=36)
    decisive_factor: str
    blockers: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
    summary: str


class Committee(BaseModel):
    id: str
    country: str
    company_type: str
    company_size: list[int | None] | None = None
    company_size_text: str = ""
    sector: str
    members: list[dict[str, Any]]
    transcript: list[dict[str, Any]] = Field(default_factory=list)
    decision: Decision | None = None

    @field_validator("company_size", mode="before")
    @classmethod
    def _old_size(cls, v):
        return v if isinstance(v, list) or v is None else None  # runs saved before sizes became classes


MEMBER_SYSTEM = """You are in a real internal buying meeting at your company, role-playing the person described.
Speak as that person would in front of colleagues: specific, political, protective of budget and risk.
Be realistic: most proposals get deferred or rejected. You must weigh your role's concerns."""

DECISION_SYSTEM = """You are an experienced B2B sales analyst observing a buying committee.
Based ONLY on the meeting transcript and the company profile, predict what this company actually does.
Typical B2B base rates: most evaluations end in 'defer' or 'reject'; a paid pilot is a common middle ground.
Return a calibrated probability, not an opinion about the product."""


def _pick_members(spec: ScenarioSpec, pool: list[Persona], anchor: Persona, rng: np.random.Generator) -> list[tuple[str, Persona]]:
    members: list[tuple[str, Persona]] = []
    used = {anchor.id}
    anchor_role = anchor.buyer_role if anchor.buyer_role in spec.committee_roles else "champion"
    members.append((anchor_role, anchor))
    for role in spec.committee_roles:
        if role == anchor_role:
            continue
        same_country = [p for p in pool if p.country == anchor.country and p.id not in used]
        cands = [p for p in same_country if p.buyer_role == role] or [
            p for p in same_country if p.isco in (1, 2) and p.buyer_role not in ("none",)
        ]
        if not cands:
            continue
        # Prefer people from the same kind of company.
        same_type = [p for p in cands if p.company_type == anchor.company_type]
        chosen = (same_type or cands)[int(rng.integers(len(same_type or cands)))]
        used.add(chosen.id)
        members.append((role, chosen))
    return members


def form_committees(spec: ScenarioSpec, people: list[Persona], n: int, seed: int | None = None) -> list[Committee]:
    rng = np.random.default_rng(seed)
    core = [p for p in people if p.influencer_voice is None]
    anchors = [p for p in core if p.is_buyer and p.company_type in B2B_COMPANY_TYPES and p.buyer_role != "none"]
    if not anchors:
        return []
    w = np.array([max(p.weight, 1e-9) for p in anchors])
    picks = rng.choice(len(anchors), size=min(n, len(anchors)), replace=False, p=w / w.sum())
    out = []
    for i, idx in enumerate(picks):
        anchor = anchors[int(idx)]
        members = _pick_members(spec, core, anchor, rng)
        if len(members) < 2:
            continue
        out.append(
            Committee(
                id=f"c{i + 1:03d}",
                country=anchor.country,
                company_type=anchor.company_type,
                company_size=anchor.company_size,
                company_size_text=anchor.company_size_text,
                sector=anchor.sector,
                members=[
                    {
                        "role": role, "role_label": ROLE_LABEL.get(role, role), "persona_id": p.id, "name": p.name,
                        "occupation": p.occupation, "seniority": p.seniority,
                    }
                    for role, p in members
                ],
            )
        )
    return out


def _company_line(c: Committee, people: dict[str, Persona]) -> str:
    anchor = people[c.members[0]["persona_id"]]
    return (
        f"Company: a {c.company_type.replace('_', ' ')} in {anchor.country_name}{f' ({c.company_size_text})' if c.company_size_text else ''}, sector {c.sector.replace('_', ' ')}."
    )


async def run_committees(
    committees: list[Committee],
    people: list[Persona],
    spec: ScenarioSpec,
    facts: list[Fact],
    models: list[str],
    decision_model: str,
    rounds: int,
    temperature: float,
    on_committee: Callable[[Committee], Awaitable[None]] | None = None,
) -> list[Committee]:
    by_id = {p.id: p for p in people}
    fact_lines = "\n".join(f"- {f.statement}" for f in facts[:8])

    async def run_one(ci: int, c: Committee) -> None:
        company = _company_line(c, by_id)
        situation = (
            f"PROPOSAL ON THE TABLE: {spec.subject}\n"
            + (f"Price: {spec.price.amount:g} {spec.price.currency} per {spec.price.period}\n" if spec.price else "")
            + (f"Alternatives: {', '.join(spec.competitors[:6])}\n" if spec.competitors else "")
            + (f"Known facts:\n{fact_lines}\n" if fact_lines else "")
            + f"Horizon: {spec.horizon_months} months."
        )
        for rnd in range(rounds):
            said_before = "\n".join(f"[{t['round'] + 1}] {t['name']} ({t['role']}): {t['statement']}" for t in c.transcript)

            async def speak(mi: int, m: dict[str, Any]) -> dict[str, Any] | None:
                p = by_id[m["persona_id"]]
                exp = "\n".join(f"- {e.source} [{e.channel}]: {e.note}" for e in p.exposures[:4])
                user = (
                    f"YOU:\n{p.card()}\nYour role in this decision: {m['role_label']}\n"
                    + (f"Outside pressures on you:\n{exp}\n" if exp else "")
                    + f"\n{company}\n{situation}\n\n"
                    + (f"MEETING SO FAR:\n{said_before}\n\n" if said_before else "")
                    + ("Give your opening position." if rnd == 0 else "React to your colleagues and state your current position.")
                )
                model = models[(ci + mi + rnd) % len(models)]
                try:
                    s = await llm.json(
                        task="committee_turn", model=model, system=MEMBER_SYSTEM, user=user, schema=Statement,
                        temperature=temperature, mock_ctx={"persona": p.model_dump(), "role": m["role"], "round": rnd, "spec": spec.model_dump()},
                    )
                except LLMError:
                    return None
                return {"round": rnd, "persona_id": p.id, "name": p.name, "role": m["role"], **s.model_dump()}

            turns = await asyncio.gather(*(speak(i, m) for i, m in enumerate(c.members)))
            c.transcript.extend(t for t in turns if t)

        transcript = "\n".join(
            f"[round {t['round'] + 1}] {t['name']} — {t['role']} (stance {t['stance']:+.1f}): {t['statement']}"
            + (f" Conditions: {'; '.join(t['conditions'])}" if t["conditions"] else "")
            for t in c.transcript
        )
        try:
            c.decision = await llm.json(
                task="committee_decision", model=decision_model, system=DECISION_SYSTEM,
                user=f"{company}\n{situation}\n\nTRANSCRIPT:\n{transcript}",
                schema=Decision, temperature=0.2,
                mock_ctx={"transcript": c.transcript, "spec": spec.model_dump()},
            )
        except LLMError:
            c.decision = None
        if on_committee:
            await on_committee(c)

    await asyncio.gather(*(run_one(i, c) for i, c in enumerate(committees)))
    return committees


def summarize(committees: list[Committee], spec: ScenarioSpec) -> dict[str, Any]:
    decided = [c for c in committees if c.decision]
    if not decided:
        return {"n": 0}
    counts = Counter(c.decision.decision for c in decided)
    probs = np.array([c.decision.probability_of_purchase for c in decided])
    cycles = np.array([c.decision.deal_cycle_months for c in decided if c.decision.decision in ("buy", "pilot")])
    blockers = Counter(b.strip().rstrip(".").lower() for c in decided for b in c.decision.blockers)
    factors = Counter(c.decision.decisive_factor.strip().rstrip(".") for c in decided)
    by_country = []
    for country in sorted({c.country for c in decided}):
        cs = [c for c in decided if c.country == country]
        by_country.append({
            "country": country, "n": len(cs),
            "purchase_probability": round(float(np.mean([c.decision.probability_of_purchase for c in cs])), 4),
            "buy_or_pilot": round(sum(c.decision.decision in ("buy", "pilot") for c in cs) / len(cs), 4),
        })
    by_type = []
    for t in sorted({c.company_type for c in decided}):
        cs = [c for c in decided if c.company_type == t]
        by_type.append({
            "company_type": t, "n": len(cs),
            "purchase_probability": round(float(np.mean([c.decision.probability_of_purchase for c in cs])), 4),
        })
    # Which role most often argued against the deal?
    role_stance: dict[str, list[float]] = {}
    for c in decided:
        for t in c.transcript:
            role_stance.setdefault(t["role"], []).append(t["stance"])
    return {
        "n": len(decided),
        "decisions": {k: round(counts.get(k, 0) / len(decided), 4) for k in ["buy", "pilot", "defer", "reject"]},
        "purchase_probability": round(float(probs.mean()), 4),
        "purchase_ci": [round(float(np.percentile(probs, 10)), 4), round(float(np.percentile(probs, 90)), 4)],
        "median_cycle_months": round(float(np.median(cycles)), 1) if len(cycles) else None,
        "top_blockers": [{"blocker": b, "count": n} for b, n in blockers.most_common(8)],
        "decisive_factors": [{"factor": f, "count": n} for f, n in factors.most_common(6)],
        "by_country": by_country,
        "by_company_type": by_type,
        "role_stance": {r: round(float(np.mean(v)), 3) for r, v in role_stance.items()},
    }
