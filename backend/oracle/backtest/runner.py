"""Backtests: run the engine on resolved cases and score it.

Each case is a question whose real outcome is known as a rate (vote share,
adoption share). We record the raw stated number and the calibrated number,
score both (mean absolute error, Brier-style squared error), and refit the
calibration per question kind when there are enough cases.
"""

from __future__ import annotations

import asyncio
import re
import time
import uuid
from typing import Any

from pydantic import BaseModel, Field

from ..config import load_json
from ..scenario.models import RunConfig, RunRequest
from ..simulate.calibrate import DEFAULT_PARAMS, Calibration, apply, fit_platt, reliability
from ..store import store

MIN_CASES_TO_FIT = 3


class Case(BaseModel):
    id: str
    kind: str = Field(pattern="^(action|belief)$")
    as_of: str
    targets: list[str]
    actual: float = Field(ge=0, le=1)
    prompt: str
    source: str = ""


class BacktestRequest(BaseModel):
    case_ids: list[str] = Field(default_factory=list, description="Empty = all built-in cases")
    custom_cases: list[Case] = Field(default_factory=list)
    agents: int = Field(default=80, ge=10, le=2000)
    runs_per_agent: int = Field(default=1, ge=1, le=4)
    fit: bool = True


def builtin_cases() -> list[Case]:
    return [Case.model_validate(c) for c in load_json("backtest_cases.json")["cases"]]


_OUTCOMES = re.compile(r"Outcomes:\s*([^.?\n]+)", re.IGNORECASE)

jobs: dict[str, dict[str, Any]] = {}


async def _run_case(case: Case, req: BacktestRequest) -> dict[str, Any]:
    from ..pipeline import start_run, tasks  # local import avoids a cycle

    prompt = (
        f"{case.prompt}\n\nIMPORTANT: Treat {case.as_of} as today. People in the simulation must not know anything "
        "that happened after that date."
    )
    m = _OUTCOMES.search(case.prompt)
    cfg = RunConfig(
        agents=req.agents, runs_per_agent=req.runs_per_agent, committees=0, diffusion_rounds=0,
        influencer_voices=0, research=False, seed=17,
    )
    run_id = await start_run(RunRequest(prompt=prompt, targets=case.targets, config=cfg))
    task = tasks.get(run_id)
    if task:
        try:
            await task
        except BaseException:  # noqa: BLE001
            pass
    run = await store.get_run(run_id) or {}
    results = run.get("results") or {}
    head = results.get("headline") or {}
    spec = run.get("spec") or {}
    expected_first = m.group(1).split(",")[0].strip().lower() if m else None
    first = (spec.get("outcomes") or [""])[0].strip().lower()
    flipped = bool(expected_first and first and expected_first != first)
    stated = head.get("stated")
    calibrated = head.get("calibrated")
    if flipped and stated is not None:
        stated, calibrated = 1 - stated, 1 - (calibrated or 0)
    return {
        "case_id": case.id, "run_id": run_id, "status": run.get("status"), "kind": case.kind,
        "actual": case.actual, "stated": stated, "calibrated": calibrated, "flipped": flipped,
        "error": run.get("error"),
    }


async def run_backtest(job_id: str, req: BacktestRequest) -> None:
    job = jobs[job_id]
    cases = [c for c in builtin_cases() if not req.case_ids or c.id in req.case_ids] + list(req.custom_cases)
    job["total"] = len(cases)
    rows = []
    try:
        for case in cases:
            job["current"] = case.id
            rows.append(await _run_case(case, req))
            job["done"] = len(rows)
            job["rows"] = rows

        ok = [r for r in rows if r["stated"] is not None]
        summary: dict[str, Any] = {"cases": len(rows), "scored": len(ok), "by_kind": {}}
        for kind in ("action", "belief"):
            ks = [r for r in ok if r["kind"] == kind]
            if not ks:
                continue
            act = [r["actual"] for r in ks]
            st = [r["stated"] for r in ks]
            ca = [r["calibrated"] for r in ks]
            entry: dict[str, Any] = {
                "n": len(ks),
                "mae_stated": round(sum(abs(a - b) for a, b in zip(st, act)) / len(ks), 4),
                "mae_calibrated": round(sum(abs(a - b) for a, b in zip(ca, act)) / len(ks), 4),
                "sq_error_calibrated": round(sum((a - b) ** 2 for a, b in zip(ca, act)) / len(ks), 4),
                "reliability": reliability(ca, act),
            }
            if req.fit and len(ks) >= MIN_CASES_TO_FIT:
                cal = fit_platt(st, act, kind)
                await store.save_calibration(kind, cal.model_dump())
                refit = [apply(s, cal) for s in st]
                entry["fitted"] = cal.model_dump()
                entry["mae_refit"] = round(sum(abs(a - b) for a, b in zip(refit, act)) / len(ks), 4)
            else:
                a, b = DEFAULT_PARAMS[kind]
                entry["fitted"] = None
                entry["current"] = Calibration(kind=kind, a=a, b=b, source="default").model_dump()
            summary["by_kind"][kind] = entry
        job["summary"] = summary
        job["status"] = "done"
        await store.save_backtest(job_id, {"status": "done", "rows": rows, "summary": summary, "request": req.model_dump()})
    except Exception as exc:  # noqa: BLE001
        job["status"] = "failed"
        job["error"] = f"{type(exc).__name__}: {exc}"
        await store.save_backtest(job_id, {"status": "failed", "rows": rows, "error": job["error"], "request": req.model_dump()})


def start_backtest(req: BacktestRequest) -> str:
    job_id = "bt_" + uuid.uuid4().hex[:10]
    jobs[job_id] = {"id": job_id, "status": "running", "started": time.time(), "done": 0, "total": 0, "rows": []}
    jobs[job_id]["task"] = asyncio.create_task(run_backtest(job_id, req))
    return job_id


def job_view(job_id: str) -> dict[str, Any] | None:
    j = jobs.get(job_id)
    if not j:
        return None
    return {k: v for k, v in j.items() if k != "task"}
