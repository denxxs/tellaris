"""The timeline: real calendar time from today to the end of the question's time frame.

The society's rounds become periods of real time (with a 12-month question and 3 rounds,
each round is four months). Events land in the period they fall in:
- scheduled: real upcoming events announced in the news (a rule taking effect, a launch date);
- assumed: what-if events the user placed on the timeline.
Each person hears an event or not by the same rules as news (see research/news.py).
"""

from __future__ import annotations

import calendar
from datetime import date
from typing import Any

from ..research.news import NewsItem
from ..scenario.models import ScenarioSpec


def add_months(d: date, months: float) -> date:
    whole = int(months)
    y, m = divmod(d.month - 1 + whole, 12)
    year, month = d.year + y, m + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    out = date(year, month, day)
    frac = months - whole
    if frac:
        out = date.fromordinal(out.toordinal() + round(frac * 30))
    return out


def months_between(a: date, b: date) -> float:
    return (b.year - a.year) * 12 + (b.month - a.month) + (b.day - a.day) / 30


def unit_for(horizon: int) -> str:
    """How to label time: months for short questions, quarters for medium, years for long."""
    return "month" if horizon <= 18 else "quarter" if horizon <= 48 else "year"


def label(as_of: date, months: float, unit: str) -> str:
    d = add_months(as_of, months)
    if unit == "year":
        return str(d.year)
    if unit == "quarter":
        return f"Q{(d.month - 1) // 3 + 1} {d.year}"
    return d.strftime("%b %Y")


def when(months: float, unit: str) -> str:
    """Relative label, e.g. 'Month 3' or 'Year 2'."""
    if unit == "year":
        return f"Year {max(1, int(-(-months // 12)))}"
    if unit == "quarter":
        return f"Quarter {max(1, int(-(-months // 3)))}"
    return f"Month {max(1, round(months))}"


def periods(as_of: date, horizon: int, rounds: int) -> list[dict[str, Any]]:
    """Round r covers months ((r-1)*step, r*step]."""
    unit = unit_for(horizon)
    step = horizon / max(rounds, 1)
    out = []
    for r in range(1, rounds + 1):
        a, b = (r - 1) * step, r * step
        start, end = label(as_of, a, unit), label(as_of, b, unit)
        out.append({"round": r, "start_month": round(a, 2), "end_month": round(b, 2), "label": start if start == end else f"{start} to {end}"})
    return out


def round_of(at_month: float, horizon: int, rounds: int) -> int | None:
    if at_month > horizon or rounds <= 0:
        return None
    step = horizon / rounds
    return min(rounds, max(1, int(-(-at_month // step)) if at_month > 0 else 1))


def events_for(spec: ScenarioSpec, news: list[NewsItem], as_of: date) -> list[dict[str, Any]]:
    """Every event on the timeline: real scheduled ones from the news, then the user's what-ifs."""
    unit = unit_for(spec.horizon_months)
    out: list[dict[str, Any]] = []
    for it in news:
        if not it.upcoming:
            continue
        at = months_between(as_of, date.fromisoformat(it.upcoming))
        if 0 < at <= spec.horizon_months:
            out.append({
                "id": f"s{len(out) + 1:02d}", "kind": "scheduled", "name": it.headline, "description": it.summary,
                "at_month": round(at, 2), "date": it.upcoming, "countries": it.countries, "reach": it.reach,
                "audiences": it.audiences, "direction": {"helps": "helps", "hurts": "hurts"}.get(it.stance, "mixed"),
                "source": it.source, "url": it.url, "news_id": it.id,
            })
    for i, e in enumerate(spec.events):
        if e.at_month > spec.horizon_months:
            continue
        out.append({
            "id": f"a{i + 1:02d}", "kind": "assumed", "name": e.name, "description": e.description, "at_month": e.at_month,
            "date": add_months(as_of, e.at_month).isoformat(), "countries": e.countries, "reach": e.reach,
            "audiences": e.audiences, "direction": e.direction,
        })
    for e in out:
        e["when"] = when(e["at_month"], unit)
        e["label"] = label(as_of, e["at_month"], unit)
    out.sort(key=lambda e: e["at_month"])
    return out
