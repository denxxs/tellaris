"""The society: people post, reply, argue and change their minds on a feed.

Each person is connected to a handful of contacts (mostly same country and
similar work). Round 0 seeds the feed with the takes of people who cared enough
to say something. In each later round every person reads their contacts' recent
posts (and any news), then posts, replies or stays quiet, and updates their view.
Company buying meetings appear in the same feed. The rounds also drive the Bass
projection of adoption over the full time frame.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, Field, field_validator

from ..llm import LLMError, llm
from ..population.models import Persona
from ..scenario.models import ScenarioSpec
from .calibrate import Calibration, apply_array
from .diffusion import bass_projection, build_network
from .memory import Mind, mind_record, reflect_all, seen_importance
from .memory import summarize as summarize_minds
from .reaction import JUSTER, Reaction


class Turn(BaseModel):
    action: Literal["post", "reply", "quiet"] = Field(description="What you do this round. Most people stay quiet most rounds.")
    reply_to: str | None = Field(default=None, description="For a reply: the id of the item you answer, from your feed")
    text: str = Field(default="", description="Your post or reply, in your own voice, at most 280 characters. Empty when quiet.")
    juster: int = Field(ge=0, le=10, description="Your view now, on the Juster scale")
    changed: bool = Field(description="True if your view moved since last round")
    why: str = Field(default="", description="One short sentence on why your view did or didn't move")
    takeaway: str = Field(default="", description="One short sentence: what you will remember from this round. Empty if nothing stuck.")

    @field_validator("text")
    @classmethod
    def _trim(cls, v: str) -> str:
        return v.strip()[:320]


SYSTEM = """You are one specific person scrolling your feed on the network you actually use (LinkedIn, X, WhatsApp groups, Reddit,
a local forum: whatever fits you). You see what your contacts have been saying about a topic, and maybe some news.

Decide what you do this round:
- "quiet": read and move on. This is what most people do most of the time.
- "post": share your own take with your network.
- "reply": answer one specific item in your feed, by its id. Disagree when you disagree; people push back.
Write like a real person in your position: specific, short, your own register, no hashtags or marketing language.
Your traits matter: people who follow their peers move with their circle; sceptics want evidence, not enthusiasm.
Then give your current view on the Juster scale: 0 no chance (1%), 1 very slight (10%), 3 some (30%),
5 fair-good (50%), 7 probable (70%), 9 almost sure (90%), 10 certain (99%)."""


def _item(**kw: Any) -> dict[str, Any]:
    base = {"agrees": 0, "disagrees": 0, "parent": None, "author": None, "from_p": None, "to_p": None}
    base.update(kw)
    return base


def _author_fields(p: Persona) -> dict[str, Any]:
    return {
        "author": p.id, "author_name": p.name, "country": p.country, "segment": p.segment,
        "occupation": p.occupation, "tagline": p.tagline,
    }


async def run_society(
    people: list[Persona],
    reactions: list[Reaction],
    spec: ScenarioSpec,
    cal: Calibration,
    models: list[str],
    rounds: int,
    cap: int,
    temperature: float,
    seed: int | None = None,
    initial_items: list[dict[str, Any]] | None = None,
    on_items: Callable[[list[dict[str, Any]]], Awaitable[None]] | None = None,
    on_round: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    memory: bool = True,
    minds_out: dict[str, dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Run the society. With memory on, each person keeps and recalls memories and reflects at the end;
    their memories and reflection are written into minds_out (person id -> record)."""
    rng = np.random.default_rng(seed)
    first: dict[str, Reaction] = {}
    stated: dict[str, list[float]] = {}
    for r in sorted(reactions, key=lambda r: r.run):
        first.setdefault(r.persona_id, r)
        stated.setdefault(r.persona_id, []).append(r.p_stated)

    pool = [p for p in people if p.influencer_voice is None and p.id in first]
    if not pool or rounds <= 0:
        return {"rounds": []}, list(initial_items or [])
    if len(pool) > cap:
        w = np.array([max(p.weight, 1e-9) for p in pool])
        idx = rng.choice(len(pool), size=cap, replace=False, p=w / w.sum())
        pool = [pool[int(i)] for i in idx]
    by_id = {p.id: p for p in pool}
    pids = list(by_id)
    g = build_network(pool, seed=seed)
    weights = np.array([max(by_id[pid].weight, 1e-9) for pid in pids])
    state = {pid: float(np.mean(stated[pid])) for pid in pids}
    minds: dict[str, Mind] = {}
    if memory:
        for pid in pids:
            m = minds[pid] = Mind()
            m.trajectory.append(state[pid])
            m.add(0, "said", first[pid].quote, 0.9)
        for it in initial_items or []:
            if it.get("kind") == "meeting":
                for member in it.get("members", []):
                    mid = member.get("persona_id")
                    if mid in minds:
                        d = it.get("decision") or {}
                        minds[mid].add(0, "meeting", f"the company chose to {d.get('decision', 'decide')}: {it.get('text', '')}", 0.9, item=it["id"])

    feed: list[dict[str, Any]] = list(initial_items or [])
    counter = [len(feed)]
    if on_items and feed:
        await on_items(list(feed))

    def new_id() -> str:
        counter[0] += 1
        return f"f{counter[0]:05d}"

    def snapshot(rnd: int, changed: int = 0, news: str | None = None, posts: int = 0, replies: int = 0) -> dict[str, Any]:
        vals = np.array([state[pid] for pid in pids])
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
            "posts": posts,
            "replies": replies,
            "sharers": posts + replies,
            "news": news,
        }

    def tally(items: list[dict[str, Any]]) -> None:
        """Contacts on the same side agree; on the other side disagree."""
        for it in items:
            a = it.get("author")
            if a not in by_id:
                continue
            side = state[a] >= 0.5
            for n in g.neighbors(a):
                if (state[n] >= 0.5) == side:
                    it["agrees"] += 1
                else:
                    it["disagrees"] += 1

    # Round 0: people who cared enough to say something.
    seeds = []
    for pid in pids:
        r = first[pid]
        p = by_id[pid]
        if r.attention in ("evaluate", "consider") or (p.traits.openness > 0.7 and rng.random() < 0.4):
            seeds.append(pid)
    rng.shuffle(seeds)
    seeds = seeds[: max(3, int(len(pids) * 0.35))]
    round0 = [_item(id=new_id(), round=0, kind="post", text=first[pid].quote, p=round(state[pid], 3), **_author_fields(by_id[pid])) for pid in seeds]
    tally(round0)
    feed.extend(round0)
    history = [snapshot(0, posts=len(round0))]
    if on_items:
        await on_items(round0)
    if on_round:
        await on_round(history[-1])

    news_forces = [f for f in spec.forces if f.strength >= 0.4]
    examples: list[dict[str, Any]] = []
    item_by_id = {it["id"]: it for it in feed}

    for rnd in range(1, rounds + 1):
        news = None
        news_item = None
        if 0 <= rnd - 1 < len(news_forces):
            f = news_forces[rnd - 1]
            news = f"{f.name}: {f.description}".strip(": ")
            news_item = _item(id=new_id(), round=rnd, kind="news", text=news, title=f.name, origin=f.origin, direction=f.direction)
            feed.append(news_item)
            item_by_id[news_item["id"]] = news_item
            if on_items:
                await on_items([news_item])

        recent = [it for it in feed if it["kind"] in ("post", "reply") and it["round"] >= rnd - 2]
        new_state: dict[str, float] = {}
        produced: list[dict[str, Any]] = []
        lock = asyncio.Lock()
        changed_count = 0

        async def act(i: int, pid: str) -> None:
            nonlocal changed_count
            p = by_id[pid]
            contacts = set(g.neighbors(pid))
            visible = [it for it in recent if it["author"] in contacts]
            visible.sort(key=lambda it: (-it["round"], -(it["agrees"] + it["disagrees"])))
            visible = visible[:5]
            if not visible and not news:
                new_state[pid] = state[pid]
                return
            lines = [
                f"[{it['id']}] {it['author_name']}, {it['occupation'].split(' (')[0]} in {p.country_name if it['country'] == p.country else it['country']}"
                f"{' (replying)' if it['kind'] == 'reply' else ''}: \"{it['text']}\""
                for it in visible
            ]
            mind = minds.get(pid)
            past = (
                f"WHAT YOU REMEMBER:\n{mind.lines(rnd)}\n\n" if mind and len(mind.memories) > 1
                else f"What you said before: \"{first[pid].quote}\"\n\n"
            )
            if mind:
                for it in visible:
                    kind = "reply" if it["kind"] == "reply" and item_by_id.get(it.get("parent") or "", {}).get("author") == pid else "saw"
                    imp = 0.85 if kind == "reply" else seen_importance(it.get("p"), state[pid], it["agrees"] + it["disagrees"])
                    mind.add(rnd, kind, it["text"], imp, who=it["author_name"], item=it["id"])
                if news:
                    mind.add(rnd, "news", news, 0.8, item=news_item["id"] if news_item else None)
            user = (
                f"YOU:\n{p.card()}\n\nTHE TOPIC: {spec.subject}\nThe question for you: {spec.persona_question}\n"
                f"Your current view: {state[pid]:.0%}.\n" + past
                + ("YOUR FEED:\n" + "\n".join(lines) + "\n\n" if lines else "")
                + (f"NEWS: {news}\n\n" if news else "")
                + "What do you do?"
            )
            model = models[(i + rnd) % len(models)]
            try:
                t = await llm.json(
                    task="society_turn", model=model, system=SYSTEM, user=user, schema=Turn, temperature=temperature,
                    mock_ctx={"persona": p.model_dump(), "p": state[pid], "visible": visible, "news": news, "spec": spec.model_dump(), "round": rnd},
                )
            except LLMError:
                new_state[pid] = state[pid]
                return
            target = JUSTER.get(t.juster, state[pid])
            p_new = 0.35 * state[pid] + 0.65 * target  # people rarely jump all the way in one round
            new_state[pid] = p_new
            if mind and t.takeaway.strip():
                mind.add(rnd, "thought", t.takeaway, 0.7)
            moved = abs(p_new - state[pid]) > 0.08
            async with lock:
                if moved:
                    changed_count += 1
                    if len(examples) < 40:
                        examples.append({"round": rnd, "persona_id": pid, "name": p.name, "country": p.country, "from": round(state[pid], 3), "to": round(p_new, 3), "why": t.why})
                if t.action != "quiet" and t.text:
                    parent = t.reply_to if t.action == "reply" and t.reply_to in {v["id"] for v in visible} else None
                    it = _item(
                        id=new_id(), round=rnd, kind="reply" if parent else "post", text=t.text, p=round(p_new, 3), parent=parent,
                        from_p=round(state[pid], 3) if moved else None, to_p=round(p_new, 3) if moved else None, why=t.why if moved else None,
                        **_author_fields(p),
                    )
                    produced.append(it)
                elif moved:
                    produced.append(_item(id=new_id(), round=rnd, kind="shift", text=t.why, p=round(p_new, 3), from_p=round(state[pid], 3), to_p=round(p_new, 3), **_author_fields(p)))

        await asyncio.gather(*(act(i, pid) for i, pid in enumerate(pids)))
        state.update(new_state)
        for pid, mind in minds.items():
            mind.trajectory.append(state[pid])
        tally([it for it in produced if it["kind"] in ("post", "reply")])
        produced.sort(key=lambda it: it["id"])
        feed.extend(produced)
        for it in produced:
            item_by_id[it["id"]] = it
            if it.get("parent") and it["parent"] in item_by_id:
                item_by_id[it["parent"]]["replies"] = item_by_id[it["parent"]].get("replies", 0) + 1
        if on_items and produced:
            await on_items(produced)
        posts = sum(1 for it in produced if it["kind"] == "post")
        replies = sum(1 for it in produced if it["kind"] == "reply")
        history.append(snapshot(rnd, changed_count, news, posts, replies))
        if on_round:
            await on_round(history[-1])

    # Reflection: each person thinks over what they remember. Kept apart from the rounds, so the
    # word-of-mouth numbers and the Bass projection mean the same as before.
    reflection_summary: dict[str, Any] = {"people": 0}
    if minds:
        reflections = await reflect_all(by_id, minds, state, spec, models, temperature, JUSTER, rounds + 1)
        reflection_summary = summarize_minds(
            minds, reflections, state, {pid: by_id[pid].weight for pid in pids}, lambda v: apply_array(v, cal),
        )
        reflection_summary["examples"] = [
            {"persona_id": pid, "name": by_id[pid].name, "country": by_id[pid].country, "occupation": by_id[pid].occupation,
             "from": round(minds[pid].trajectory[0], 3), "to": r["p"], "belief": r["belief"]}
            for pid, r in sorted(reflections.items(), key=lambda kv: -abs(kv[1]["p"] - minds[kv[0]].trajectory[0]))[:8]
        ]
        if minds_out is not None:
            for pid, mind in minds.items():
                minds_out[pid] = mind_record(mind, reflections.get(pid))

    # Bass projection from the observed social pull.
    start, end = history[0]["calibrated"], history[-1]["calibrated"]
    m = max(0.0, min(1.0, end * spec.assumed_reach))
    enthusiasts = sum(weights[i] for i, pid in enumerate(pids) if state[pid] >= 0.7 and by_id[pid].traits.risk_appetite >= 0.6) / weights.sum()
    p_innov = float(np.clip(0.005 + 0.08 * enthusiasts, 0.003, 0.06))
    pull = (end - start) / max(start, 0.02)
    active = sum(h["sharers"] for h in history[1:]) / max(len(pids) * max(rounds, 1), 1)
    q_imit = float(np.clip(0.15 + 0.6 * active + 0.8 * pull, 0.05, 0.7))

    talk = [it for it in feed if it["kind"] in ("post", "reply")]
    voices: dict[str, dict[str, Any]] = {}
    for it in talk:
        v = voices.setdefault(it["author"], {"persona_id": it["author"], "name": it["author_name"], "country": it["country"], "occupation": it["occupation"], "items": 0, "agrees": 0, "p": state.get(it["author"])})
        v["items"] += 1
        v["agrees"] += it["agrees"]
    threads = sorted((it for it in talk if it["kind"] == "post"), key=lambda it: -(it.get("replies", 0) * 3 + it["agrees"] + it["disagrees"]))[:5]

    summary = {
        "agents": len(pids),
        "edges": g.number_of_edges(),
        "rounds": history,
        "examples": examples,
        "reflection": reflection_summary,
        "social_pull": round(end - start, 4),
        "bass": {"m": round(m, 4), "p": round(p_innov, 4), "q": round(q_imit, 4), "curve": bass_projection(m, p_innov, q_imit, spec.horizon_months)},
        "network": {
            "nodes": [{"id": pid, "country": by_id[pid].country, "p": round(state[pid], 3), "name": by_id[pid].name} for pid in pids],
            "links": [{"source": a, "target": b} for a, b in g.edges()],
        },
        "society": {
            "posts": sum(1 for it in talk if it["kind"] == "post"),
            "replies": sum(1 for it in talk if it["kind"] == "reply"),
            "shifts": len(examples),
            "news": sum(1 for it in feed if it["kind"] == "news"),
            "meetings": sum(1 for it in feed if it["kind"] == "meeting"),
            "top_voices": sorted(voices.values(), key=lambda v: -(v["agrees"] + v["items"]))[:6],
            "hot_threads": [{"id": t["id"], "author_name": t["author_name"], "text": t["text"], "replies": t.get("replies", 0), "agrees": t["agrees"], "disagrees": t["disagrees"]} for t in threads],
        },
    }
    return summary, feed


def meeting_items(committees: list[Any], start: int = 0) -> list[dict[str, Any]]:
    """Each buying committee as one feed item holding its meeting."""
    out = []
    for i, c in enumerate(committees):
        if not c.decision:
            continue
        out.append(
            _item(
                id=f"m{start + i + 1:04d}", round=0, kind="meeting", text=c.decision.summary, country=c.country,
                company_type=c.company_type, company_size=c.company_size, decision=c.decision.model_dump(),
                transcript=c.transcript, members=c.members, committee_id=c.id,
            )
        )
    return out
