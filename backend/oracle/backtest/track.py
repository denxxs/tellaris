"""Track record: predictions made before the outcome was known, scored once it is.

Backtests replay famous past events that models may already know, so their scores
flatter Tellaris. The track record is the honest test. You save a finished run's
headline with the date the real answer will be known, then enter what really
happened. Each prediction is frozen when it is saved, so it cannot be tuned after
the fact.
"""

from __future__ import annotations

import time
import uuid
from datetime import date, datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from ..simulate.calibrate import apply, fit_platt, reliability
from ..store import store

MIN_TO_FIT = 3


class TrackRequest(BaseModel):
    resolves_on: date
    note: str = Field(default="", max_length=500)


class ResolveRequest(BaseModel):
    actual: float = Field(ge=0, le=1, description="What really happened, as a share from 0 to 1")
    source: str = Field(default="", max_length=500)


class PredictionError(ValueError):
    pass


def _today() -> date:
    return datetime.now(timezone.utc).date()


def freeze(run: dict[str, Any], req: TrackRequest) -> dict[str, Any]:
    """Copy everything needed to score the prediction later, so later edits to the run change nothing."""
    if run.get("status") != "done":
        raise PredictionError("Only finished simulations can be tracked.")
    spec = run.get("spec") or {}
    head = (run.get("results") or {}).get("headline") or {}
    if spec.get("outcome_type") == "numeric" or head.get("value") is None:
        raise PredictionError("Only questions answered as a share can be tracked for now.")
    if req.resolves_on <= _today():
        raise PredictionError("Pick a date in the future, when the real answer will be known.")
    outcomes = spec.get("outcomes") or ["Yes"]
    # With a given awareness, the prediction is for the whole audience; otherwise for those who hear of it.
    wa = head.get("with_awareness")
    predicted, ci, reach = (wa["value"], wa["ci"], head["awareness"]) if wa else (head["value"], head.get("ci"), 1.0)
    return {
        "id": uuid.uuid4().hex[:12],
        "run_id": run["id"],
        "created_at": time.time(),
        "made_on": _today().isoformat(),
        "resolves_on": req.resolves_on.isoformat(),
        "note": req.note.strip(),
        "title": spec.get("title") or run.get("title") or "",
        "question": spec.get("question") or "",
        "measure": (f"Share of the whole audience, if {round(head['awareness'] * 100, 1):g}% hear about it" if wa else head.get("label")) or f"Share choosing {outcomes[0]}",
        "outcome": outcomes[0],
        "targets": spec.get("targets") or [],
        "lens": head.get("lens"),
        "kind": head.get("kind") or "belief",
        "predicted": predicted,
        "ci": ci,
        "stated": head.get("stated"),
        "reach": reach,
        "calibration": head.get("calibration"),
        "status": "open",
        "actual": None,
        "source": "",
        "resolved_at": None,
    }


def resolve(pred: dict[str, Any], req: ResolveRequest) -> dict[str, Any]:
    now = time.time()
    return {
        **pred,
        "status": "resolved",
        "actual": req.actual,
        "source": req.source.strip(),
        "resolved_at": now,
        # True when the outcome was entered after the prediction was frozen, which is
        # what makes it an honest test.
        "blind": now > pred["created_at"],
        "error": round(pred["predicted"] - req.actual, 4),
        "within_range": bool(pred.get("ci") and pred["ci"][0] <= req.actual <= pred["ci"][1]),
    }


def _intent(p: dict[str, Any], value: float) -> float:
    """For adoption questions the headline is reach x intent; the say/do correction works on intent."""
    if p["kind"] == "action" and p.get("reach"):
        return min(1.0, value / p["reach"])
    return value


def summary(preds: list[dict[str, Any]]) -> dict[str, Any]:
    done = [p for p in preds if p["status"] == "resolved"]
    today = _today().isoformat()
    out: dict[str, Any] = {
        "total": len(preds),
        "open": sum(1 for p in preds if p["status"] == "open"),
        "due": sum(1 for p in preds if p["status"] == "open" and p["resolves_on"] <= today),
        "resolved": len(done),
        "by_kind": {},
    }
    if not done:
        return out
    out["mae"] = round(sum(abs(p["predicted"] - p["actual"]) for p in done) / len(done), 4)
    out["within_range"] = round(sum(1 for p in done if p.get("within_range")) / len(done), 4)
    out["points"] = [{"id": p["id"], "title": p["title"], "predicted": p["predicted"], "actual": p["actual"], "kind": p["kind"]} for p in done]
    for kind in ("action", "belief"):
        ks = [p for p in done if p["kind"] == kind and p.get("stated") is not None]
        if not ks:
            continue
        stated = [_intent(p, p["stated"]) for p in ks]
        actual = [_intent(p, p["actual"]) for p in ks]
        out["by_kind"][kind] = {
            "n": len(ks),
            "mae": round(sum(abs(p["predicted"] - p["actual"]) for p in ks) / len(ks), 4),
            "mae_stated": round(sum(abs(s - a) for s, a in zip(stated, actual)) / len(ks), 4),
            "reliability": reliability([p["predicted"] for p in ks], [p["actual"] for p in ks]),
            "can_fit": len(ks) >= MIN_TO_FIT,
        }
    return out


async def fit(kind: str) -> dict[str, Any]:
    """Fit the say/do correction for one kind from resolved predictions and save it."""
    done = [p for p in await store.predictions() if p["status"] == "resolved" and p["kind"] == kind and p.get("stated") is not None]
    if len(done) < MIN_TO_FIT:
        raise PredictionError(f"Needs at least {MIN_TO_FIT} resolved predictions of this kind; there are {len(done)}.")
    stated = [_intent(p, p["stated"]) for p in done]
    actual = [_intent(p, p["actual"]) for p in done]
    cal = fit_platt(stated, actual, kind)
    cal.source = "track record"
    await store.save_calibration(kind, cal.model_dump())
    before = sum(abs(_intent(p, p["predicted"]) - a) for p, a in zip(done, actual)) / len(done)
    after = sum(abs(apply(s, cal) - a) for s, a in zip(stated, actual)) / len(done)
    return {"calibration": cal.model_dump(), "n": len(done), "mae_before": round(before, 4), "mae_after": round(after, 4)}
