"""Social spread: people talk to their contacts and update their views.

We build a homophilous small-world network (people mostly know people in their
country and line of work), then run rounds where every agent sees what their
contacts said and decides whether to change their mind. Optional news events
(scenario forces) land mid-simulation. The observed social pull is used to
project adoption over the full horizon with a Bass diffusion model.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import networkx as nx
import numpy as np
from pydantic import BaseModel, Field

from ..llm import LLMError, llm
from ..population.models import Persona
from ..scenario.models import ScenarioSpec
from .calibrate import Calibration, apply_array
from .reaction import JUSTER, Reaction


class Update(BaseModel):
    juster: int = Field(ge=0, le=10)
    changed: bool
    why: str = Field(description="One sentence on why you did or didn't change your mind")
    quote: str = Field(description="What you'd say to your contacts now, 1-2 sentences")
    share: bool = Field(description="Would you actively mention this to others?")


SYSTEM = """You are role-playing one specific person who has been hearing what their contacts think.
Update your view the way this person really would. People with high 'follows peers' scores move with their circle;
sceptics need evidence, not enthusiasm. Most people don't change their minds much in a few weeks.
Juster scale: 0 no chance (1%), 1 very slight (10%), 3 some (30%), 5 fair-good (50%), 7 probable (70%), 9 almost sure (90%), 10 certain (99%)."""


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


def bass_projection(m: float, p: float, q: float, months: int) -> list[dict[str, float]]:
    """Cumulative adoption share by month for market potential m."""
    out = []
    cum = 0.0
    for t in range(1, months + 1):
        f = cum / m if m > 0 else 0
        new = (p + q * f) * (m - cum) if m > 0 else 0
        cum = min(m, cum + max(new, 0))
        out.append({"month": t, "adoption": round(cum, 5)})
    return out


async def run_diffusion(
    people: list[Persona],
    reactions: list[Reaction],
    spec: ScenarioSpec,
    cal: Calibration,
    models: list[str],
    rounds: int,
    cap: int,
    temperature: float,
    seed: int | None = None,
    on_round: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
) -> dict[str, Any]:
    rng = np.random.default_rng(seed)
    first: dict[str, Reaction] = {}
    for r in sorted(reactions, key=lambda r: r.run):
        first.setdefault(r.persona_id, r)
    pool = [p for p in people if p.influencer_voice is None and p.id in first]
    if not pool or rounds <= 0:
        return {"rounds": []}
    if len(pool) > cap:
        w = np.array([max(p.weight, 1e-9) for p in pool])
        idx = rng.choice(len(pool), size=cap, replace=False, p=w / w.sum())
        pool = [pool[int(i)] for i in idx]
    by_id = {p.id: p for p in pool}
    g = build_network(pool, seed=seed)

    stated: dict[str, list[float]] = {}
    for r in reactions:
        stated.setdefault(r.persona_id, []).append(r.p_stated)
    state = {
        pid: {"p": float(np.mean(stated[pid])), "quote": first[pid].quote, "share": first[pid].attention in ("consider", "evaluate")}
        for pid in by_id
    }
    weights = np.array([max(by_id[pid].weight, 1e-9) for pid in by_id])
    pids = list(by_id)

    def snapshot(rnd: int, changed: int = 0, news: str | None = None) -> dict[str, Any]:
        vals = np.array([state[pid]["p"] for pid in pids])
        cal_vals = apply_array(vals, cal)
        by_c = {}
        for c in sorted({by_id[pid].country for pid in pids}):
            mask = np.array([by_id[pid].country == c for pid in pids])
            by_c[c] = round(float((cal_vals[mask] * weights[mask]).sum() / weights[mask].sum()), 4)
        return {
            "round": rnd,
            "stated": round(float((vals * weights).sum() / weights.sum()), 4),
            "calibrated": round(float((cal_vals * weights).sum() / weights.sum()), 4),
            "by_country": by_c,
            "changed": changed,
            "sharers": int(sum(1 for pid in pids if state[pid]["share"])),
            "news": news,
        }

    history = [snapshot(0)]
    if on_round:
        await on_round(history[-1])

    # Strong outside forces arrive as news from round 2 on, one per round.
    news_forces = [f for f in spec.forces if f.strength >= 0.4]
    examples: list[dict[str, Any]] = []

    for rnd in range(1, rounds + 1):
        news = None
        if 0 <= rnd - 2 < len(news_forces):
            f = news_forces[rnd - 2]
            news = f"{f.name}: {f.description}"
        new_state: dict[str, dict[str, Any]] = {}

        async def update(i: int, pid: str) -> None:
            p = by_id[pid]
            neighbors = list(g.neighbors(pid))
            talkers = [n for n in neighbors if state[n]["share"]] or neighbors
            heard = talkers[:5]
            if not heard and not news:
                new_state[pid] = dict(state[pid])
                return
            lines = [
                f"- {by_id[n].name}, {by_id[n].occupation} in {by_id[n].country_name} (leaning {state[n]['p']:.0%}): \"{state[n]['quote']}\""
                for n in heard
            ]
            user = (
                f"YOU:\n{p.card()}\n\nTHE SUBJECT: {spec.subject}\nQuestion: {spec.persona_question}\n"
                f"Your current view: {state[pid]['p']:.0%} likely. You said: \"{state[pid]['quote']}\"\n\n"
                + (f"WHAT YOUR CONTACTS SAY:\n" + "\n".join(lines) + "\n\n" if lines else "")
                + (f"NEWS THIS WEEK: {news}\n\n" if news else "")
                + "Has your view changed?"
            )
            model = models[(i + rnd) % len(models)]
            try:
                u = await llm.json(
                    task="diffuse_update", model=model, system=SYSTEM, user=user, schema=Update, temperature=temperature,
                    mock_ctx={"persona": p.model_dump(), "p": state[pid]["p"], "neighbors": [state[n]["p"] for n in heard], "news": news, "spec": spec.model_dump()},
                )
            except LLMError:
                new_state[pid] = dict(state[pid])
                return
            p_new = JUSTER.get(u.juster, state[pid]["p"])
            # Small anchoring: people rarely jump all the way in one round.
            p_new = 0.35 * state[pid]["p"] + 0.65 * p_new
            new_state[pid] = {"p": p_new, "quote": u.quote, "share": u.share}
            if u.changed and len(examples) < 30:
                examples.append({"round": rnd, "persona_id": pid, "name": p.name, "country": p.country, "from": round(state[pid]["p"], 3), "to": round(p_new, 3), "why": u.why})

        await asyncio.gather(*(update(i, pid) for i, pid in enumerate(pids)))
        changed = sum(1 for pid in pids if abs(new_state[pid]["p"] - state[pid]["p"]) > 0.05)
        state.update(new_state)
        history.append(snapshot(rnd, changed, news))
        if on_round:
            await on_round(history[-1])

    # Bass projection: market potential from the final calibrated view x reach,
    # imitation (q) from the social pull we observed, innovation (p) from early enthusiasts.
    start, end = history[0]["calibrated"], history[-1]["calibrated"]
    reach = spec.assumed_reach
    m = max(0.0, min(1.0, end * reach))
    enthusiasts = sum(weights[i] for i, pid in enumerate(pids) if state[pid]["p"] >= 0.7 and by_id[pid].traits.risk_appetite >= 0.6) / weights.sum()
    p_innov = float(np.clip(0.005 + 0.08 * enthusiasts, 0.003, 0.06))
    pull = (end - start) / max(start, 0.02)
    sharers = history[-1]["sharers"] / max(len(pids), 1)
    q_imit = float(np.clip(0.15 + 0.6 * sharers + 0.8 * pull, 0.05, 0.7))
    return {
        "agents": len(pids),
        "edges": g.number_of_edges(),
        "rounds": history,
        "examples": examples,
        "social_pull": round(end - start, 4),
        "bass": {"m": round(m, 4), "p": round(p_innov, 4), "q": round(q_imit, 4), "curve": bass_projection(m, p_innov, q_imit, spec.horizon_months)},
        "network": {
            "nodes": [{"id": pid, "country": by_id[pid].country, "p": round(state[pid]["p"], 3), "name": by_id[pid].name} for pid in pids],
            "links": [{"source": a, "target": b} for a, b in g.edges()],
        },
    }
