"""HTTP API (FastAPI)."""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from .. import __version__
from ..backtest.runner import BacktestRequest, builtin_cases, job_view, start_backtest
from ..config import PROVIDER_KEY_ENV, env, settings_store
from ..events import hub
from ..llm import llm
from ..pipeline import STAGES, cancel_run, start_run
from ..population.models import Persona
from ..scenario.compiler import SECTORS, compile_scenario
from ..scenario.levers import apply_lever
from ..scenario.models import RunConfig, RunRequest, ScenarioSpec
from ..simulate.calibrate import DEFAULT_PARAMS
from ..store import store
from ..world.countries import blocs, company_types, countries, occupations
from ..world.influence import InfluenceEdge, anchor, channels, expand, graph_payload

log = logging.getLogger("oracle.api")

MODEL_EXAMPLES = {
    "openai": ["openai/gpt-4o-mini", "openai/gpt-4.1-mini", "openai/gpt-4.1", "openai/o4-mini"],
    "anthropic": ["anthropic/claude-haiku-5-5", "anthropic/claude-sonnet-5-5", "anthropic/claude-opus-5-5"],
    "gemini": ["gemini/gemini-2.5-flash", "gemini/gemini-2.5-pro"],
    "groq": ["groq/llama-3.3-70b-versatile"],
    "deepseek": ["deepseek/deepseek-chat"],
    "mistral": ["mistral/mistral-small-latest", "mistral/mistral-large-latest"],
    "openrouter": ["openrouter/meta-llama/llama-3.3-70b-instruct", "openrouter/qwen/qwen-2.5-72b-instruct"],
    "xai": ["xai/grok-3-mini"],
    "together_ai": ["together_ai/meta-llama/Llama-3.3-70B-Instruct-Turbo"],
    "azure": ["azure/<your-deployment-name>"],
    "ollama": ["ollama/llama3.1", "ollama/qwen2.5"],
    "mock": ["mock/oracle"],
}


@asynccontextmanager
async def lifespan(_: FastAPI):
    await store.open()
    await store.mark_interrupted()
    yield
    await store.close()


app = FastAPI(title="Product Oracle", version=__version__, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=env.cors_origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"]
)


def _uses_mock() -> bool:
    r = settings_store.get().roles
    return any(m.startswith("mock/") for m in [r.planner, r.analyst, *r.crowd])


# ------------------------------------------------------------------ meta

@app.get("/api/health")
async def health() -> dict[str, Any]:
    return {"ok": True, "version": __version__, "mock": _uses_mock()}


@app.get("/api/meta")
async def meta() -> dict[str, Any]:
    return {
        "version": __version__,
        "mock": _uses_mock(),
        "countries": [
            {
                "iso3": c.iso3, "iso_num": c.iso_num, "name": c.name, "region": c.region, "income": c.income, "blocs": c.blocs,
                "population_m": c.population_m, "workforce_m": c.workforce_m, "gdp_pc_usd": c.gdp_pc_usd, "anchor": c.anchor,
                "internet_pct": c.internet_pct, "isco_source": c.isco_source,
            }
            for c in countries().values()
        ],
        "blocs": [{**b.model_dump(), "anchor": anchor(b.id)} for b in blocs().values()],
        "occupations": [{"id": o.id, "title": o.title, "isco": o.isco, "buyer_role": o.buyer_role} for o in occupations().values()],
        "company_types": company_types(),
        "sectors": SECTORS,
        "channels": channels(),
        "stages": [{"id": s[0], "label": s[1]} for s in STAGES],
        "model_examples": MODEL_EXAMPLES,
        "defaults": RunConfig().model_dump(),
    }


# ------------------------------------------------------------------ scenario & world

class PreviewRequest(BaseModel):
    prompt: str = Field(min_length=10, max_length=20000)
    targets: list[str] = Field(default_factory=list)
    influence_threshold: float = 0.25


def _forces_as_edges(spec: ScenarioSpec) -> list[InfluenceEdge]:
    return [
        InfluenceEdge(source=f.origin, target=t, channel=f.channel, strength=f.strength, sectors=f.sectors or ["all"], note=f"{f.name}: {f.description}", origin="scenario")
        for f in spec.forces
        if f.origin and f.origin != "global"
        for t in (f.affects or spec.targets)
        if t != f.origin
    ]


@app.post("/api/scenario/preview")
async def preview(req: PreviewRequest) -> dict[str, Any]:
    from ..llm import Usage, current_usage

    usage = Usage()
    token = current_usage.set(usage)
    try:
        spec = await compile_scenario(req.prompt, settings_store.get().roles.planner, req.targets or None)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"Scenario builder failed: {exc}") from exc
    finally:
        current_usage.reset(token)
    infl = expand(spec.targets, _forces_as_edges(spec), req.influence_threshold, spec.sectors or None)
    return {"spec": spec.model_dump(), "world": graph_payload(spec.targets, infl), "usage": usage.to_dict()}


class HeadcountRequest(BaseModel):
    spec: ScenarioSpec


@app.post("/api/scenario/headcount")
async def headcount(req: HeadcountRequest) -> dict[str, Any]:
    """Estimated real people behind each group, per country."""
    from ..population.headcount import segment_headcount

    spec = req.spec
    out = []
    for seg in spec.segments:
        where = [c for c in (seg.countries or spec.targets) if c in countries()]
        per = {c: round(segment_headcount(c, seg.occupations, custom=bool(seg.custom_occupation))) for c in where}
        out.append({"name": seg.name, "total": sum(per.values()), "by_country": per})
    return {"segments": out, "total": sum(s["total"] for s in out)}


class WorldRequest(BaseModel):
    targets: list[str]
    sectors: list[str] = Field(default_factory=list)
    threshold: float = 0.25
    spec: ScenarioSpec | None = None


@app.post("/api/world/influence")
async def world(req: WorldRequest) -> dict[str, Any]:
    extra = _forces_as_edges(req.spec) if req.spec else []
    infl = expand(req.targets, extra, req.threshold, req.sectors or None)
    return graph_payload(req.targets, infl)


# ------------------------------------------------------------------ runs

@app.post("/api/runs")
async def create_run(req: RunRequest) -> dict[str, str]:
    run_id = await start_run(req)
    return {"id": run_id}


@app.get("/api/runs")
async def list_runs(limit: int = 50) -> list[dict[str, Any]]:
    return await store.list_runs(limit)


@app.get("/api/runs/{run_id}")
async def get_run(run_id: str) -> dict[str, Any]:
    run = await store.get_run(run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    run["live"] = hub.get(run_id) is not None
    return run


@app.delete("/api/runs/{run_id}")
async def delete_run(run_id: str) -> dict[str, bool]:
    await cancel_run(run_id)
    await store.delete_run(run_id)
    return {"ok": True}


@app.post("/api/runs/{run_id}/cancel")
async def cancel(run_id: str) -> dict[str, bool]:
    return {"ok": await cancel_run(run_id)}


@app.get("/api/runs/{run_id}/events")
async def events(run_id: str, request: Request, after: int = -1):
    if not await store.get_run(run_id):
        raise HTTPException(404, "Run not found")
    last_id = request.headers.get("last-event-id")
    if last_id and last_id.isdigit():
        after = max(after, int(last_id))

    async def gen():
        ch = hub.get(run_id)
        q: asyncio.Queue | None = None
        if ch is not None:
            q = asyncio.Queue()
            ch.listeners.add(q)
        try:
            sent = after
            for evt in await store.events(run_id, after):
                sent = evt["seq"]
                yield {"id": str(evt["seq"]), "event": "message", "data": json.dumps(evt)}
            if q is None:
                yield {"event": "end", "data": "{}"}
                return
            while True:
                if await request.is_disconnected():
                    return
                try:
                    evt = await asyncio.wait_for(q.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": "{}"}
                    continue
                if evt is None:
                    yield {"event": "end", "data": "{}"}
                    return
                if evt["seq"] <= sent:
                    continue
                sent = evt["seq"]
                yield {"id": str(evt["seq"]), "event": "message", "data": json.dumps(evt, default=str)}
        finally:
            if ch is not None and q is not None:
                ch.listeners.discard(q)

    return EventSourceResponse(gen())


def _person_summary(p: dict[str, Any], rs: list[dict[str, Any]]) -> dict[str, Any]:
    ps = [r["p_stated"] for r in rs]
    return {
        "id": p["id"], "name": p.get("name"), "country": p["country"], "country_name": p["country_name"],
        "segment": p["segment"], "occupation": p["occupation"], "seniority": p["seniority"], "age": p["age"],
        "company_type": p["company_type"], "voice": p.get("influencer_voice"), "is_buyer": p.get("is_buyer"),
        "weight": p.get("weight"), "represents": p.get("represents", 0), "exposures": [e["source"] for e in p.get("exposures", [])],
        "p": round(sum(ps) / len(ps), 4) if ps else None,
        "choice": rs[0]["choice"] if rs else None,
        "quote": rs[0]["quote"] if rs else None,
        "attention": rs[0]["attention"] if rs else None,
    }


@app.get("/api/runs/{run_id}/personas")
async def personas(run_id: str) -> list[dict[str, Any]]:
    people = await store.personas(run_id)
    reactions = await store.reactions(run_id)
    by: dict[str, list[dict[str, Any]]] = {}
    for r in reactions:
        by.setdefault(r["persona_id"], []).append(r)
    return [_person_summary(p, by.get(p["id"], [])) for p in people]


@app.get("/api/runs/{run_id}/personas/{pid}")
async def persona(run_id: str, pid: str) -> dict[str, Any]:
    p = await store.persona(run_id, pid)
    if not p:
        raise HTTPException(404, "Persona not found")
    return {"persona": p, "reactions": await store.reactions(run_id, pid), "chat": await store.chat(run_id, pid)}


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


CHAT_SYSTEM = """You are role-playing a specific person from a simulation. Stay in character, answer in first person,
in your own voice, briefly (2-6 sentences). You remember how you reacted earlier. Be honest, including doubts.
If asked something your character wouldn't know, say so. Never mention being an AI or a simulation."""


@app.post("/api/runs/{run_id}/personas/{pid}/chat")
async def chat(run_id: str, pid: str, req: ChatRequest) -> dict[str, Any]:
    p = await store.persona(run_id, pid)
    run = await store.get_run(run_id)
    if not p or not run:
        raise HTTPException(404, "Persona not found")
    persona_obj = Persona.model_validate(p)
    reactions = await store.reactions(run_id, pid)
    history = await store.chat(run_id, pid)
    spec = run.get("spec") or {}
    earlier = reactions[0] if reactions else None
    context = (
        f"WHO YOU ARE:\n{persona_obj.card()}\n\nTHE TOPIC: {spec.get('subject', '')}\n"
        + (
            f"Earlier you said: \"{earlier['quote']}\" (leaning {earlier['p_stated']:.0%}). "
            f"Your reasons: {'; '.join(earlier['reasons'])}. Your objections: {'; '.join(earlier['objections'])}."
            if earlier else ""
        )
    )
    messages = [{"role": "system", "content": f"{CHAT_SYSTEM}\n\n{context}"}, *history[-20:], {"role": "user", "content": req.message}]
    model = (settings_store.get().roles.crowd or [settings_store.get().roles.planner])[0]
    try:
        reply = await llm.text(
            task="persona_chat", model=model, messages=messages,
            mock_ctx={**p, "stance": earlier["p_stated"] if earlier else None},
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"Chat failed: {exc}") from exc
    history = [*history, {"role": "user", "content": req.message}, {"role": "assistant", "content": reply}]
    await store.save_chat(run_id, pid, history)
    return {"reply": reply, "chat": history}


@app.get("/api/runs/{run_id}/committees")
async def committees(run_id: str) -> list[dict[str, Any]]:
    return await store.committees(run_id)


class WhatIfRequest(BaseModel):
    label: str = Field(default="What-if", max_length=120)
    changes: dict[str, Any] = Field(default_factory=dict)
    config: RunConfig | None = None


@app.post("/api/runs/{run_id}/whatif")
async def whatif(run_id: str, req: WhatIfRequest) -> dict[str, str]:
    run = await store.get_run(run_id)
    if not run or not run.get("spec"):
        raise HTTPException(404, "Run not found or has no scenario yet")
    spec = apply_lever(ScenarioSpec.model_validate(run["spec"]), req.changes)
    spec.title = f"{spec.title} · {req.label}"[:120]
    prev = RunRequest.model_validate(run["request"])
    cfg = req.config or prev.config
    new_id = await start_run(
        RunRequest(prompt=run["prompt"], targets=spec.targets, config=cfg, spec=spec, parent_id=run_id)
    )
    return {"id": new_id}


@app.get("/api/runs/{run_id}/export")
async def export(run_id: str) -> JSONResponse:
    run = await store.get_run(run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    payload = {
        "run": run,
        "personas": await store.personas(run_id),
        "reactions": await store.reactions(run_id),
        "committees": await store.committees(run_id),
    }
    return JSONResponse(payload, headers={"Content-Disposition": f'attachment; filename="oracle-{run_id}.json"'})


# ------------------------------------------------------------------ settings

@app.get("/api/settings")
async def get_settings() -> dict[str, Any]:
    return {**settings_store.public(), "providers": list(PROVIDER_KEY_ENV.keys()), "model_examples": MODEL_EXAMPLES}


class SettingsPatch(BaseModel):
    roles: dict[str, Any] | None = None
    keys: dict[str, str | None] | None = None
    extra: dict[str, str | None] | None = None
    search_provider: str | None = None
    max_concurrency: int | None = Field(default=None, ge=1, le=256)
    request_timeout_s: int | None = Field(default=None, ge=5, le=600)


@app.put("/api/settings")
async def put_settings(patch: SettingsPatch) -> dict[str, Any]:
    data = patch.model_dump(exclude_none=True)
    if "roles" in data:
        roles = {**settings_store.get().roles.model_dump(), **data["roles"]}
        data["roles"] = roles
        crowd = roles.get("crowd")
        if isinstance(crowd, str):
            roles["crowd"] = [c.strip() for c in crowd.split(",") if c.strip()]
        if not roles.get("crowd"):
            roles["crowd"] = settings_store.get().roles.crowd
    if data.get("search_provider") not in (None, "duckduckgo", "tavily", "none"):
        raise HTTPException(400, "search_provider must be duckduckgo, tavily or none")
    settings_store.update(data)
    return await get_settings()


class TestRequest(BaseModel):
    model: str


@app.post("/api/settings/test")
async def test_model(req: TestRequest) -> dict[str, Any]:
    return await llm.ping(req.model)


# ------------------------------------------------------------------ backtests & calibration

@app.get("/api/backtest/cases")
async def cases() -> list[dict[str, Any]]:
    return [c.model_dump() for c in builtin_cases()]


@app.post("/api/backtest")
async def backtest(req: BacktestRequest) -> dict[str, str]:
    return {"id": start_backtest(req)}


@app.get("/api/backtest/{job_id}")
async def backtest_status(job_id: str) -> dict[str, Any]:
    view = job_view(job_id)
    if view:
        return view
    for b in await store.backtests(100):
        if b["id"] == job_id:
            return b
    raise HTTPException(404, "Backtest not found")


@app.get("/api/backtests")
async def backtests() -> list[dict[str, Any]]:
    return await store.backtests()


@app.get("/api/calibration")
async def calibration() -> dict[str, Any]:
    out = {}
    for kind, (a, b) in DEFAULT_PARAMS.items():
        saved = await store.calibration(kind)
        out[kind] = saved or {"kind": kind, "a": a, "b": b, "source": "default", "n_cases": 0}
    return out


@app.delete("/api/calibration/{kind}")
async def reset_calibration(kind: str) -> dict[str, bool]:
    await store.delete_calibration(kind)
    return {"ok": True}
