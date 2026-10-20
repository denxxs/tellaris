"""Individual reactions: each person, in character, decides what THEY would do.

Every agent is sampled `runs_per_agent` times, rotating across the crowd models,
so results average over model biases and sampling noise.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from ..llm import LLMError, llm
from ..population.models import Persona
from ..research.search import Fact
from ..scenario.models import ScenarioSpec

# Juster scale: verbal probability anchors that predict real purchases better
# than "would you buy?" questions.
JUSTER = {0: 0.01, 1: 0.10, 2: 0.20, 3: 0.30, 4: 0.40, 5: 0.50, 6: 0.60, 7: 0.70, 8: 0.80, 9: 0.90, 10: 0.99}
JUSTER_TEXT = (
    "10 Certain, practically certain (99 in 100) | 9 Almost sure (9 in 10) | 8 Very probable (8 in 10) | "
    "7 Probable (7 in 10) | 6 Good possibility (6 in 10) | 5 Fairly good possibility (5 in 10) | "
    "4 Fair possibility (4 in 10) | 3 Some possibility (3 in 10) | 2 Slight possibility (2 in 10) | "
    "1 Very slight possibility (1 in 10) | 0 No chance, almost no chance (1 in 100)"
)


class ReactionOut(BaseModel):
    attention: Literal["ignore", "skim", "consider", "evaluate"] = Field(
        description="How much attention you would realistically give this"
    )
    juster: int = Field(ge=0, le=10, description="Juster scale answer to the question")
    likelihood: float = Field(ge=0, le=1, description="Your probability for the first outcome / doing it")
    choice: str = Field(description="The outcome you pick, exactly as written in the options")
    option_probs: dict[str, float] | None = Field(default=None, description="Categorical only: probability per option")
    estimate: float | None = Field(default=None, description="Numeric only: your estimate")
    willingness_to_pay: float | None = Field(
        default=None, description="Max you'd pay in USD for the stated period, if a price is relevant; null otherwise"
    )
    reasons: list[str] = Field(default_factory=list, description="Up to 3 reasons, in your words")
    objections: list[str] = Field(default_factory=list, description="Up to 3 objections or blockers")
    change_mind: list[str] = Field(default_factory=list, description="Up to 2 things that would change your answer")
    influences: list[str] = Field(
        default_factory=list, description="Codes of outside forces that affected your answer (from your list)"
    )
    quote: str = Field(description="1-2 sentences, how you'd actually say it")
    confidence: float = Field(ge=0, le=1, default=0.6)

    @field_validator("reasons", "objections", "change_mind", "influences")
    @classmethod
    def _cap(cls, v: list[str]) -> list[str]:
        return [str(x)[:240] for x in v[:3]]


class Reaction(ReactionOut):
    persona_id: str
    run: int
    model: str
    p_stated: float


SYSTEM = """You are role-playing ONE specific real person in a world simulation used to forecast real outcomes.
Stay fully in character. Decide as this person would actually BEHAVE, not how they would like to look.

Realism rules (critical):
- Most people ignore most new products, campaigns and announcements. Busy, sceptical or price-sensitive people say no often.
- Your traits are real constraints: high scepticism means you need proof; high price sensitivity means price dominates; low tech affinity means friction; low budget authority means you can only suggest, and the answer is about whether it actually happens for you.
- Compare against what you use today (including doing nothing, spreadsheets, or an existing vendor). Switching has a cost.
- Outside forces listed for you are real pressures in your work. Weigh them only if they matter to this decision.
- Use only the facts given and your own life. Don't invent statistics.
- Be honest and specific in your own voice. No marketing language.

Juster scale for the 'juster' field: """ + JUSTER_TEXT


def _facts_for(p: Persona, facts: list[Fact]) -> list[Fact]:
    return [f for f in facts if not f.countries or p.country in f.countries][:8]


def build_prompt(p: Persona, spec: ScenarioSpec, facts: list[Fact]) -> str:
    lines = ["WHO YOU ARE:", p.card(), ""]
    if p.exposures:
        lines.append("OUTSIDE FORCES IN YOUR WORLD (code: description):")
        for e in p.exposures:
            arrow = {"helps": " (+)", "hurts": " (-)"}.get(e.direction, "")
            lines.append(f"- {e.source} [{e.channel}]{arrow}: {e.note}")
        lines.append("")
    lines += ["THE SITUATION:", spec.subject]
    if spec.price:
        lines.append(f"Price: {spec.price.amount:g} {spec.price.currency} per {spec.price.period}")
    if spec.competitors:
        lines.append(f"Alternatives you may know: {', '.join(spec.competitors[:8])}")
    rel = _facts_for(p, facts)
    if rel:
        lines.append("Known facts:")
        lines += [f"- {f.statement}" for f in rel]
    lines += [
        "",
        f"Time frame: the next {spec.horizon_months} months.",
        f"QUESTION FOR YOU: {spec.persona_question}",
    ]
    if spec.outcome_type == "numeric":
        unit = f" ({spec.numeric_unit})" if spec.numeric_unit else ""
        lines.append(f"Give your numeric estimate{unit} in 'estimate'. Set choice to 'value'.")
        lines.append("Use 'likelihood'/'juster' for how confident you are that it lands in the upper half of plausible values.")
    else:
        lines.append(f"Options: {' | '.join(spec.outcomes)}")
        lines.append(f"'likelihood' and 'juster' are about: {spec.outcomes[0]}")
        if spec.outcome_type == "categorical":
            lines.append("Fill option_probs with a probability for every option (summing to 1).")
    if spec.price:
        lines.append(f"Give willingness_to_pay in USD per {spec.price.period}.")
    return "\n".join(lines)


def stated_probability(r: ReactionOut) -> float:
    """Blend the Juster answer with the stated probability, and respect attention."""
    p = 0.6 * JUSTER.get(r.juster, 0.5) + 0.4 * r.likelihood
    if r.attention == "ignore":
        p = min(p, 0.08)
    elif r.attention == "skim":
        p = min(p, 0.35)
    return round(max(0.0, min(1.0, p)), 4)


def _normalize(r: ReactionOut, spec: ScenarioSpec) -> ReactionOut:
    if spec.outcome_type != "numeric":
        match = next((o for o in spec.outcomes if o.lower() == r.choice.strip().lower()), None)
        if match is None:
            match = next((o for o in spec.outcomes if o.lower() in r.choice.lower()), None)
        r.choice = match or (spec.outcomes[0] if r.likelihood >= 0.5 else spec.outcomes[-1])
    if spec.outcome_type == "categorical":
        probs = {o: float((r.option_probs or {}).get(o, 0.0)) for o in spec.outcomes}
        s = sum(probs.values())
        r.option_probs = {k: v / s for k, v in probs.items()} if s > 0 else {o: (1.0 if o == r.choice else 0.0) for o in spec.outcomes}
    return r


async def react_all(
    people: list[Persona],
    spec: ScenarioSpec,
    facts: list[Fact],
    models: list[str],
    runs_per_agent: int,
    temperature: float,
    on_reaction: Callable[[Reaction, Persona], Awaitable[None]] | None = None,
) -> list[Reaction]:
    if not models:
        raise ValueError("no crowd models configured")
    results: list[Reaction] = []
    lock = asyncio.Lock()

    async def one(idx: int, p: Persona, run: int) -> None:
        model = models[(idx + run) % len(models)]
        user = build_prompt(p, spec, facts)
        try:
            out = await llm.json(
                task="react",
                model=model,
                system=SYSTEM,
                user=user,
                schema=ReactionOut,
                temperature=temperature,
                mock_ctx={"persona": p.model_dump(), "spec": spec.model_dump(), "run": run},
            )
        except LLMError:
            # Try once on another model before giving up on this sample.
            if len(models) == 1:
                return
            model = models[(idx + run + 1) % len(models)]
            try:
                out = await llm.json(
                    task="react", model=model, system=SYSTEM, user=user, schema=ReactionOut,
                    temperature=temperature, mock_ctx={"persona": p.model_dump(), "spec": spec.model_dump(), "run": run},
                )
            except LLMError:
                return
        out = _normalize(out, spec)
        r = Reaction(**out.model_dump(), persona_id=p.id, run=run, model=model, p_stated=stated_probability(out))
        async with lock:
            results.append(r)
        if on_reaction:
            await on_reaction(r, p)

    await asyncio.gather(*(one(i, p, run) for i, p in enumerate(people) for run in range(runs_per_agent)))
    return results
