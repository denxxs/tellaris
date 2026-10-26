"""Memory and reflection for people in the society.

Each person keeps a short stream of memories as the society runs: what they said
first, posts and replies from their contacts, replies to them, news, the buying
meeting they sat in, and their own one-line takeaway from each round. Every round
they see everything they still remember, not just their first quote. At the end each
person reflects once on what they remember and says how they see it now and what
moved them.

What is still remembered follows recall of news events (a round is a day; research/news.remembered):
each memory is kept or forgotten by a fixed draw against that curve. Nothing is ranked by a
made-up importance score; the person (the model) decides what matters to them.
"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Callable
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, Field, field_validator

from ..llm import LLMError, llm
from ..research.news import remembered
from .reaction import juster_point
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



class Memory(BaseModel):
    n: int
    round: int
    kind: Kind
    text: str
    who: str | None = None
    item: str | None = None
    importance: float | None = None  # older runs only


class Mind:
    """One person's memories during a run."""

    def __init__(self) -> None:
        self.memories: list[Memory] = []
        self.trajectory: list[float] = []

    def add(self, rnd: int, kind: Kind, text: str, who: str | None = None, item: str | None = None) -> None:
        text = " ".join(text.split())[:240]
        if not text:
            return
        if item and any(m.item == item for m in self.memories):
            return
        self.memories.append(Memory(n=len(self.memories) + 1, round=rnd, kind=kind, text=text, who=who, item=item))

    def recall(self, now: int, key: str = "") -> list[Memory]:
        """Everything they still remember now, in the order it happened. A round is a day; each
        memory survives with the share of people who still recall a news event that old."""
        return [m for m in self.memories if kept(key, m, now)]

    def lines(self, now: int, key: str = "") -> str:
        return "\n".join(f"[{m.n}] round {m.round}, {describe(m)}" for m in self.recall(now, key))


def kept(key: str, m: Memory, now: int) -> bool:
    """A fixed draw, so reruns agree, against the measured recall curve."""
    h = hashlib.sha256(f"{key}|{m.n}|{m.round}".encode()).digest()
    return int.from_bytes(h[:8], "big") / 2**64 < remembered(max(0, now - m.round))


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
        recalled = mind.recall(now, pid)
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
        p_after = juster.get(r.juster, state[pid])  # their view is what they answer
        out[pid] = {
            "belief": r.belief.strip()[:400],
            "p": round(p_after, 4),
            "influences": [n for n in r.influences if n in valid],
            "changed_mind": r.changed_mind and juster_point(p_after) != juster_point(mind.trajectory[0]),
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
