"""How big the places people work at are, and how many work for the state (built by scripts/build_firms.py).

Size comes as a class ("50-99 people"), never an invented exact headcount: below 50 people the
country's own workplace-size shares for the job group (ILOSTAT), above 50 the enterprise split
(OECD / US Census), and the finer classes inside that from the US shape.
"""

from __future__ import annotations

import math
from functools import lru_cache
from typing import Any

from ..config import load_json


@lru_cache(maxsize=1)
def _data() -> dict[str, Any]:
    try:
        return load_json("firms.json")
    except FileNotFoundError:
        return {"_meta": {}, "countries": {}}


def ladder(iso: str, major: int | None) -> list[tuple[int, int | None, float]]:
    """(lo, hi, share of the job group's workers) for every size class, smallest first."""
    d = _data()
    rec = d["countries"].get(iso)
    if not rec:
        return []
    w = rec["workplace"]
    shares = w["groups"].get(str(major)) if major is not None else None
    shares = shares or w["groups"]["all"]
    out = [(lo, hi, p) for (lo, hi), p in zip(w["classes"][:-1], shares[:-1])]
    p50, mid = shares[-1], rec["mid_share_of_50plus"]
    m = d["_meta"]
    out += [(lo, hi, p50 * mid * s) for (lo, hi), s in zip(m["mid_classes"], m["us_mid"])]
    out += [(lo, hi, p50 * (1 - mid) * s) for (lo, hi), s in zip(m["large_classes"], m["us_large"])]
    return out


def source(iso: str) -> str:
    rec = _data()["countries"].get(iso)
    if not rec:
        return "no data"
    return f"{rec['workplace']['source']}; above 50 people: {rec['enterprise_source']}, finer classes from US Census SUSB"


def public_share(iso: str, codes: list[str], employed: dict[str, float] | None = None) -> float | None:
    """Share of people in these ISCO-08 unit groups who work in the public sector (ILOSTAT)."""
    rec = _data()["countries"].get(iso)
    if not rec or not codes:
        return None
    by2 = rec["public"]["by2"]
    groups = sorted({c[:2] for c in codes if c[:2] in by2})
    if not groups:
        return None
    weights = [(employed or {}).get(g, 0.0) for g in groups]
    if sum(weights) <= 0:
        weights = [1.0] * len(groups)  # no counts to weigh them by: each group counts once
    return sum(by2[g] * w for g, w in zip(groups, weights)) / sum(weights)


def _overlap(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Overlap of two people-count ranges on a log scale, as a share of the first."""
    lo, hi = max(a[0], b[0]), min(a[1], b[1])
    if hi <= lo:
        return 0.0
    return math.log(hi / lo) / math.log(a[1] / a[0])


def classes_for(iso: str, major: int | None, types: dict[str, tuple[int, int]]) -> list[tuple[int, int | None, float, str]]:
    """Size classes open to these company types, with their share of workers and the type each falls under.

    A class only partly inside the allowed sizes keeps that part of its share (sizes spread evenly
    on a log scale within a class); its type is the one covering most of it."""
    top = max((hi for _, hi in types.values()), default=1) + 1
    out = []
    for lo, hi, p in ladder(iso, major):
        rng = (float(lo), float((hi if hi is not None else top - 1) + 1))
        best, frac_best, frac_all = None, 0.0, 0.0
        for t, (tlo, thi) in types.items():
            f = _overlap(rng, (float(max(tlo, 1)), float(thi + 1)))
            frac_all = max(frac_all, f)
            if f > frac_best:
                best, frac_best = t, f
        if best and p > 0:
            out.append((lo, hi, p * frac_all, best))
    return out


def size_text(cls: list[int | None] | None) -> str:
    if not cls:
        return ""
    lo, hi = cls
    if hi is None:
        return f"{lo:,}+ people"
    if lo == hi:
        return "1 person" if lo == 1 else f"{lo:,} people"
    return f"{lo:,}-{hi:,} people"
