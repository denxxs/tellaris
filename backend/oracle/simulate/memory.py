"""Memory and reflection for people in the society.

Each person keeps a short stream of memories as the society runs: what they said
first, posts and replies from their contacts, replies to them, news, the buying
meeting they sat in, and their own one-line takeaway from each round. Every round
they see their most important memories, not just their first quote. At the end each
person reflects once on what they remember and says how they see it now and what
moved them.

Importance is scored without extra model calls: things aimed at you (replies,
your own meeting) and news weigh more; views unlike your own stand out; older
memories fade.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, Field, field_validator

from ..llm import LLMError, llm
from ..research.news import remembered
from ..population.models import Persona
from ..scenario.models import ScenarioSpec

Kind = Literal["said", "saw", "reply", "news", "meeting", "thought"]

KIND_LABEL = {
    "said": "what they said first",
    "saw": "contacts' posts",
    "reply": "replies to them",
    "news": "news",
    "meeting": "their buying meeting",
    "thought": "their own thinking",
}

RECALL = 6


class Memory(BaseModel):
    n: int
    round: int
    kind: Kind
    text: str
    who: str | None = None
    item: str | None = None
    importance: float = Field(ge=0, le=1)


class Mind:
    """One person's memories during a run."""

    def __init__(self) -> None:
        self.memories: list[Memory] = []
        self.trajectory: list[float] = []

    def add(self, rnd: int, kind: Kind, text: str, importance: float, who: str | None = None, item: str | None = None) -> None:
        text = " ".join(text.split())[:240]
        if not text:
            return
        if item and any(m.item == item for m in self.memories):
            return
        self.memories.append(Memory(n=len(self.memories) + 1, round=rnd, kind=kind, text=text, who=who, item=item, importance=round(min(1.0, max(0.0, importance)), 3)))

    def recall(self, now: int, k: int = RECALL) -> list[Memory]:
        """The memories most likely to be on their mind now: important and still remembered. A round
        is a day; how much fades per day follows recall of news events (research/news.remembered)."""
        scored = sorted(self.memories, key=lambda m: -(m.importance * remembered(max(0, now - m.round))))
        return sorted(scored[:k], key=lambda m: m.n)

    def lines(self, now: int, k: int = RECALL) -> str:
        return "\n".join(f"[{m.n}] round {m.round}, {describe(m)}" for m in self.recall(now, k))


def describe(m: Memory) -> str:
    if m.kind == "said":
        return f"you said: \"{m.text}\""
    if m.kind == "saw":
        return f"{m.who} posted: \"{m.text}\""
    if m.kind == "reply":
        return f"{m.who} replied to you: \"{m.text}\""
    if m.kind == "news":
        return f"news: {m.text}"
    if m.kind == "meeting":
        return f"in your company's meeting: {m.text}"
    return f"you thought: {m.text}"


def seen_importance(item_p: float | None, own_p: float, engagement: int) -> float:
    """Posts that disagree with you and posts many people reacted to stick."""
    surprise = abs((item_p if item_p is not None else own_p) - own_p)
    return 0.35 + 0.35 * min(1.0, surprise / 0.5) + 0.2 * min(1.0, engagement / 6)


class Reflection(BaseModel):
    belief: str = Field(description="How you see it now, in one or two sentences, in your own voice")
    juster: int = Field(ge=0, le=10, description="Your view now, on the Juster scale")
    influences: list[int] = Field(default_factory=list, description="Numbers of up to 3 memories that moved you most; empty if nothing did")
    changed_mind: bool = Field(description="True if your view is meaningfully different from where you started")

    @field_validator("influences")
    @classmethod
    def _cap(cls, v: list[int]) -> list[int]:
        return list(dict.fromkeys(v))[:3]


REFLECT_SYSTEM = """You are one specific person. Over the last days you have seen your contacts talk about a topic, maybe some news,
maybe a meeting at work. Below is what you remember. Take a moment and think it over honestly.
Say how you see it now in one or two sentences, in your own voice. Name the memories (by number) that moved you most,
or none if nothing did. Most people only change their minds a little; some not at all.
Give your view on the Juster scale: 0 no chance (1%), 1 very slight (10%), 3 some (30%),
5 fair-good (50%), 7 probable (70%), 9 almost sure (90%), 10 certain (99%)."""


async def reflect_all(
    people: dict[str, Persona],
    minds: dict[str, Mind],
    state: dict[str, float],
    spec: ScenarioSpec,
    models: list[str],
    temperature: float,
    juster: dict[int, float],
    now: int,
) -> dict[str, dict[str, Any]]:
    """One reflection per person. Returns per-person results; failures keep their last view."""
    out: dict[str, dict[str, Any]] = {}

    async def one(i: int, pid: str) -> None:
        p, mind = people[pid], minds[pid]
        if not mind.memories:
            return
        recalled = mind.recall(now, k=8)
        user = (
            f"YOU:\n{p.card()}\n\nTHE TOPIC: {spec.subject}\nThe question for you: {spec.persona_question}\n"
            f"Where you started: {mind.trajectory[0]:.0%}. Your view now: {state[pid]:.0%}.\n\n"
            "WHAT YOU REMEMBER:\n" + "\n".join(f"[{m.n}] round {m.round}, {describe(m)}" for m in recalled) + "\n\nThink it over."
        )
        try:
            r = await llm.json(
                task="reflect", model=models[i % len(models)], system=REFLECT_SYSTEM, user=user, schema=Reflection, temperature=temperature,
                mock_ctx={"persona": p.model_dump(), "p": state[pid], "start": mind.trajectory[0], "memories": [m.model_dump() for m in recalled]},
            )
        except LLMError:
            return
        valid = {m.n for m in mind.memories}
        target = juster.get(r.juster, state[pid])
        p_after = 0.5 * state[pid] + 0.5 * target
        out[pid] = {
            "belief": r.belief.strip()[:400],
            "p": round(p_after, 4),
            "influences": [n for n in r.influences if n in valid],
            "changed_mind": r.changed_mind and abs(p_after - mind.trajectory[0]) > 0.08,
        }

    await asyncio.gather(*(one(i, pid) for i, pid in enumerate(minds)))
    return out


def summarize(
    minds: dict[str, Mind],
    reflections: dict[str, dict[str, Any]],
    state: dict[str, float],
    weights: dict[str, float],
    calibrate: Callable[[np.ndarray], np.ndarray],
) -> dict[str, Any]:
    """Where people ended up after reflecting, and which kinds of memory moved them."""
    if not reflections:
        return {"people": 0}
    pids = list(minds)
    before = np.array([state[p] for p in pids])
    after = np.array([reflections.get(p, {}).get("p", state[p]) for p in pids])
    w = np.array([max(weights[p], 1e-9) for p in pids])
    cb, ca = calibrate(before), calibrate(after)
    counts: dict[str, float] = {}
    for pid, r in reflections.items():
        by_n = {m.n: m for m in minds[pid].memories}
        for n in r["influences"]:
            m = by_n.get(n)
            if m:
                counts[m.kind] = counts.get(m.kind, 0) + 1
    total = sum(counts.values()) or 1
    return {
        "people": len(reflections),
        "changed_mind": sum(1 for r in reflections.values() if r["changed_mind"]),
        "before": round(float((cb * w).sum() / w.sum()), 4),
        "after": round(float((ca * w).sum() / w.sum()), 4),
        "moved_by": sorted(
            ({"kind": k, "label": KIND_LABEL[k], "share": round(v / total, 4)} for k, v in counts.items()),
            key=lambda x: -x["share"],
        ),
        "nothing_moved": sum(1 for r in reflections.values() if not r["influences"]),
    }


def mind_record(mind: Mind, reflection: dict[str, Any] | None) -> dict[str, Any]:
    """What is saved on the person: their memories, how their view moved, and their reflection."""
    return {
        "memories": [m.model_dump() for m in mind.memories],
        "trajectory": [round(x, 4) for x in mind.trajectory],
        "reflection": reflection,
    }
