"""Turn what simulated people SAY into what people are likely to DO.

Two corrections:
1. Intent-to-behaviour: stated intentions overstate action (well documented in
   purchase-intent research). We shrink in log-odds space with a Platt-style map
   logit(p') = a * logit(p) + b. Defaults depend on the kind of question and are
   replaced by parameters fitted from backtests once you have them.
2. Reach: people can only act on what they hear about. For adoption-style
   questions the realistic number is reach x calibrated intent.
"""

from __future__ import annotations

import math

import numpy as np
from pydantic import BaseModel

ACTION_KINDS = {"product", "feature", "pricing", "campaign", "company", "market"}

DEFAULT_PARAMS = {
    # (a, b) for logit(p') = a * logit(p) + b
    "action": (0.85, -0.55),  # buying, switching, signing up: big say/do gap
    "belief": (0.9, 0.0),     # opinions about events or policies: mild shrink toward 50%
}


class Calibration(BaseModel):
    kind: str
    a: float
    b: float
    source: str  # default | backtest
    n_cases: int = 0


def _logit(p: float) -> float:
    p = min(max(p, 1e-4), 1 - 1e-4)
    return math.log(p / (1 - p))


def _sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-x))


def kind_for(subject_kind: str) -> str:
    return "action" if subject_kind in ACTION_KINDS else "belief"


def default_calibration(subject_kind: str) -> Calibration:
    k = kind_for(subject_kind)
    a, b = DEFAULT_PARAMS[k]
    return Calibration(kind=k, a=a, b=b, source="default")


def apply(p: float, cal: Calibration) -> float:
    return _sigmoid(cal.a * _logit(p) + cal.b)


def apply_array(p: np.ndarray, cal: Calibration) -> np.ndarray:
    q = np.clip(p, 1e-4, 1 - 1e-4)
    return 1 / (1 + np.exp(-(cal.a * np.log(q / (1 - q)) + cal.b)))


def fit_platt(predicted: list[float], actual: list[float], kind: str) -> Calibration:
    """Fit (a, b) by logistic regression on log-odds of the raw prediction.

    `actual` may be 0/1 outcomes or observed rates in [0, 1]. Uses a light prior
    toward the defaults so a handful of cases cannot produce wild parameters."""
    x = np.array([_logit(p) for p in predicted])
    y = np.clip(np.array(actual, dtype=float), 0, 1)
    a0, b0 = DEFAULT_PARAMS[kind]
    a, b = a0, b0
    lam = 1.0
    for _ in range(500):
        z = a * x + b
        s = 1 / (1 + np.exp(-z))
        ga = np.sum((s - y) * x) + lam * (a - a0)
        gb = np.sum(s - y) + lam * (b - b0)
        w = s * (1 - s)
        haa = np.sum(w * x * x) + lam
        hbb = np.sum(w) + lam
        hab = np.sum(w * x)
        det = haa * hbb - hab * hab
        if abs(det) < 1e-9:
            break
        da = (hbb * ga - hab * gb) / det
        db = (haa * gb - hab * ga) / det
        a, b = a - da, b - db
        if abs(da) + abs(db) < 1e-7:
            break
    return Calibration(kind=kind, a=float(round(a, 4)), b=float(round(b, 4)), source="backtest", n_cases=len(predicted))


def brier(predicted: list[float], actual: list[float]) -> float:
    p = np.array(predicted)
    y = np.array(actual, dtype=float)
    return float(np.mean((p - y) ** 2)) if len(p) else float("nan")


def log_loss(predicted: list[float], actual: list[float]) -> float:
    p = np.clip(np.array(predicted), 1e-4, 1 - 1e-4)
    y = np.array(actual, dtype=float)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))) if len(p) else float("nan")


def reliability(predicted: list[float], actual: list[float], bins: int = 5) -> list[dict[str, float]]:
    out = []
    edges = np.linspace(0, 1, bins + 1)
    p = np.array(predicted)
    y = np.array(actual, dtype=float)
    for lo, hi in zip(edges[:-1], edges[1:]):
        mask = (p >= lo) & (p < hi if hi < 1 else p <= hi)
        if mask.any():
            out.append({"bin": f"{lo:.1f}-{hi:.1f}", "predicted": float(p[mask].mean()), "actual": float(y[mask].mean()), "n": int(mask.sum())})
    return out
