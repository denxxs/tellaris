"""Asking a group: put a follow-up question to people from a finished run.

You pick a group (everyone, or any mix of the Where it works breakdowns such as
"Under 30s in India") and a question. Oracle picks people from that group at
random (so smaller countries are heard too), asks each one in character, using
what they decided and remember, and sums the answers up like a small survey: a
chart for multiple choice, number and 0-10 questions, themes and quotes for open
ones, and the answers split by whether people leaned yes or no. The numbers
weight each answer by the real people that person stands for, so they describe
the group, not the sample.
"""

from __future__ import annotations

import asyncio
import hashlib
import time
import uuid
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, Field, field_validator, model_validator

from ..llm import LLMError, llm
from ..population.models import Persona
from ..store import store
from .aggregate import breakdowns

Kind = Literal["open", "choice", "number", "scale"]
MAX_ASK = 200


class InterviewRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    kind: Kind = "open"
    options: list[str] = Field(default_factory=list, max_length=8)
    unit: str | None = Field(default=None, max_length=30)
    group: dict[str, str] = Field(default_factory=dict, description="Breakdown id -> key, e.g. {'age': '18-29', 'country': 'IND'}. Empty = everyone.")
    limit: int = Field(default=40, ge=3, le=MAX_ASK)

    @field_validator("options")
    @classmethod
    def _clean(cls, v: list[str]) -> list[str]:
        return list(dict.fromkeys(o.strip() for o in v if o.strip()))

    @model_validator(mode="after")
    def _check(self) -> "InterviewRequest":
        if self.kind == "choice" and len(self.options) < 2:
            raise ValueError("A multiple-choice question needs at least two options.")
        return self


class Answer(BaseModel):
    answer: str = Field(description="Your answer in your own voice, one to three sentences")
    choice: str | None = Field(default=None, description="For multiple choice: exactly one of the options")
    number: float | None = Field(default=None, description="For a number question: your number")
    scale: int | None = Field(default=None, ge=0, le=10, description="For a 0-10 question: your score")


class Theme(BaseModel):
    label: str = Field(description="A short theme, under 8 words")
    answers: list[int] = Field(default_factory=list, description="Numbers of the answers that express it")


class Digest(BaseModel):
    summary: str = Field(description="Two or three plain sentences on what the group said")
    themes: list[Theme] = Field(default_factory=list, max_length=6)


ANSWER_SYSTEM = """You are a specific person from a simulation, being asked a follow-up question in a short interview.
Stay in character: answer in first person, in your own voice, honestly, in one to three sentences, consistent with
what you decided and what you remember. If you would not know or care, say so plainly.
Fill the structured field that matches the question type too: choice (copy one option exactly), number, or scale (0-10)."""

DIGEST_SYSTEM = """You summarise a small interview of simulated people for a busy reader. Be specific and neutral.
Group the answers into up to six themes, listing which answers (by number) express each. Plain words, no marketing."""


def group_label(group: dict[str, str]) -> str:
    if not group:
        return "Everyone"
    dims = breakdowns()
    parts = [dims[d][2](k) if d in dims else k for d, k in group.items()]
    places = [p for d, p in zip(group, parts) if d in ("country", "region")]
    rest = [p for d, p in zip(group, parts) if d not in ("country", "region")]
    return ", ".join(rest) + (" in " if rest and places else "") + " and ".join(places)


def members(people: list[Persona], group: dict[str, str]) -> list[Persona]:
    dims = breakdowns()
    core = [p for p in people if p.influencer_voice is None]
    return [p for p in core if all(d in dims and str(dims[d][1](p)) == str(k) for d, k in group.items())]


def pick(pool: list[Persona], n: int, seed: str) -> list[Persona]:
    """A plain random sample without repeats, reproducible for the same question. Weighting happens in
    the tally, so sampling by weight here would count big groups twice."""
    if len(pool) <= n:
        return list(pool)
    rng = np.random.default_rng(int(hashlib.sha256(seed.encode()).hexdigest()[:8], 16))
    idx = rng.choice(len(pool), size=n, replace=False)
    return [pool[int(i)] for i in sorted(idx)]


def _context(p: Persona, spec: dict[str, Any], reactions: list[dict[str, Any]], mind: dict[str, Any] | None) -> str:
    out = f"WHO YOU ARE:\n{p.card()}\n\nTHE TOPIC: {spec.get('subject', '')}\nYou were asked: {spec.get('persona_question', '')}\n"
    if reactions:
        r = reactions[0]
        mean = sum(x["p_stated"] for x in reactions) / len(reactions)
        out += f"You answered: \"{r['quote']}\" (leaning {mean:.0%}). Your reasons: {'; '.join(r.get('reasons', []))}. Your doubts: {'; '.join(r.get('objections', []))}.\n"
    ref = (mind or {}).get("reflection")
    if ref:
        out += f"After talking it over with people you know, you said: \"{ref['belief']}\"\n"
    return out


def _match_choice(raw: str | None, options: list[str]) -> str | None:
    if not raw:
        return None
    low = raw.strip().lower()
    for o in options:
        if o.lower() == low:
            return o
    for o in options:
        if low.startswith(o.lower()) or o.lower().startswith(low):
            return o
    return None


def _wquantile(values: np.ndarray, weights: np.ndarray, q: float) -> float:
    order = np.argsort(values)
    v, w = values[order], weights[order]
    cum = np.cumsum(w) / w.sum()
    return float(v[min(np.searchsorted(cum, q), len(v) - 1)])


def tally(req: InterviewRequest, answers: list[dict[str, Any]]) -> dict[str, Any]:
    """Numbers for the chart, overall and split by whether people leaned yes."""

    def one(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
        if req.kind == "choice":
            rows = [a for a in rows if a.get("choice")]
            if not rows:
                return None
            total = sum(a["weight"] for a in rows)
            return {
                "n": len(rows),
                "options": [
                    {"option": o, "share": round(sum(a["weight"] for a in rows if a["choice"] == o) / total, 4), "n": sum(1 for a in rows if a["choice"] == o)}
                    for o in req.options
                ],
            }
        if req.kind in ("number", "scale"):
            key = req.kind
            rows = [a for a in rows if a.get(key) is not None]
            if not rows:
                return None
            v = np.array([float(a[key]) for a in rows])
            w = np.array([a["weight"] for a in rows])
            out = {
                "n": len(rows),
                "mean": round(float((v * w).sum() / w.sum()), 3),
                "median": round(_wquantile(v, w, 0.5), 3),
                "p10": round(_wquantile(v, w, 0.1), 3),
                "p90": round(_wquantile(v, w, 0.9), 3),
            }
            if req.kind == "scale":
                out["counts"] = [sum(1 for a in rows if a["scale"] == s) for s in range(11)]
            return out
        return None

    yes = [a for a in answers if a["leaning"] >= 0.5]
    no = [a for a in answers if a["leaning"] < 0.5]
    return {"all": one(answers), "leaning_yes": one(yes) if len(yes) >= 3 else None, "leaning_no": one(no) if len(no) >= 3 else None}


async def run_interview(iv_id: str, run: dict[str, Any], req: InterviewRequest, crowd: list[str], analyst: str, temperature: float = 0.7) -> None:
    rec = await store.interview(iv_id)
    assert rec is not None
    try:
        rows = await store.personas(run["id"])
        people = [Persona.model_validate(r) for r in rows]
        mind_of = {r["id"]: r.get("mind") for r in rows}
        pool = members(people, req.group)
        chosen = pick(pool, req.limit, f"{run['id']}|{req.question}|{sorted(req.group.items())}")
        by_person: dict[str, list[dict[str, Any]]] = {}
        for r in await store.reactions(run["id"]):
            by_person.setdefault(r["persona_id"], []).append(r)
        spec = run.get("spec") or {}
        rec.update({"pool": len(pool), "asked": len(chosen)})
        await store.save_interview(rec)

        if req.kind == "choice":
            how = "Options (choose exactly one): " + " | ".join(req.options)
        elif req.kind == "number":
            how = f"Answer with a number{f' in {req.unit}' if req.unit else ''}."
        elif req.kind == "scale":
            how = "Answer with a score from 0 (not at all) to 10 (completely)."
        else:
            how = "Answer in your own words."

        answers: list[dict[str, Any]] = []
        lock = asyncio.Lock()

        async def ask(i: int, p: Persona) -> None:
            rs = by_person.get(p.id, [])
            user = _context(p, spec, rs, mind_of.get(p.id)) + f"\nINTERVIEW QUESTION: {req.question}\n{how}"
            try:
                a = await llm.json(
                    task="interview_answer", model=crowd[i % len(crowd)], system=ANSWER_SYSTEM, user=user, schema=Answer, temperature=temperature,
                    mock_ctx={"persona": p.model_dump(), "p": rs[0]["p_stated"] if rs else 0.5, "kind": req.kind, "options": req.options, "question": req.question, "unit": req.unit},
                )
            except LLMError:
                return
            leaning = sum(x["p_stated"] for x in rs) / len(rs) if rs else 0.5
            row = {
                "persona_id": p.id, "name": p.name, "country": p.country, "occupation": p.occupation, "age": p.age,
                "segment": p.segment, "weight": p.weight, "leaning": round(leaning, 4), "answer": a.answer.strip()[:600],
                "choice": _match_choice(a.choice, req.options) if req.kind == "choice" else None,
                "number": a.number if req.kind == "number" else None,
                "scale": a.scale if req.kind == "scale" else None,
            }
            async with lock:
                answers.append(row)
                if len(answers) % 5 == 0:
                    rec["done"] = len(answers)
                    await store.save_interview(rec)

        await asyncio.gather(*(ask(i, p) for i, p in enumerate(chosen)))
        # Interleave countries so the first quotes show the spread, not one country.
        by_country: dict[str, list[dict[str, Any]]] = {}
        for a in sorted(answers, key=lambda a: a["persona_id"]):
            by_country.setdefault(a["country"], []).append(a)
        queues = sorted(by_country.values(), key=len, reverse=True)
        answers = [q[i] for i in range(max((len(q) for q in queues), default=0)) for q in queues if i < len(q)]
        for n, a in enumerate(answers, 1):
            a["n"] = n
        rec.update({"done": len(answers), "answers": answers, "results": tally(req, answers)})

        if answers:
            listing = "\n".join(f"[{a['n']}] {a['occupation'].split(' (')[0]}, {a['country']}: {a['answer']}" for a in answers)
            try:
                d = await llm.json(
                    task="interview_digest", model=analyst, system=DIGEST_SYSTEM,
                    user=f"QUESTION: {req.question}\nGROUP: {rec['group_label']}\n\nANSWERS:\n{listing}", schema=Digest, temperature=0.2,
                    mock_ctx={"answers": answers, "question": req.question, "kind": req.kind},
                )
                valid = {a["n"] for a in answers}
                rec["digest"] = {
                    "summary": d.summary.strip(),
                    "themes": [
                        {"label": t.label, "answers": ids, "share": round(len(ids) / len(answers), 4)}
                        for t in d.themes
                        if (ids := [i for i in dict.fromkeys(t.answers) if i in valid])
                    ],
                }
            except LLMError as exc:
                rec["digest"] = {"summary": "", "themes": [], "error": str(exc)[:200]}
        rec["status"] = "done" if answers else "failed"
        if not answers:
            rec["error"] = "Nobody could be asked. Check that the crowd model works on the Models page."
    except Exception as exc:  # noqa: BLE001 - the record must always end
        rec.update({"status": "failed", "error": str(exc)[:300]})
    rec["finished_at"] = time.time()
    await store.save_interview(rec)


def new_record(run_id: str, req: InterviewRequest) -> dict[str, Any]:
    return {
        "id": uuid.uuid4().hex[:12],
        "run_id": run_id,
        "created_at": time.time(),
        "status": "running",
        "question": req.question.strip(),
        "kind": req.kind,
        "options": req.options,
        "unit": req.unit,
        "group": req.group,
        "group_label": group_label(req.group),
        "limit": req.limit,
        "pool": 0,
        "asked": 0,
        "done": 0,
        "answers": [],
        "results": None,
        "digest": None,
    }
