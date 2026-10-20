"""Analyst layer: theme extraction and the final report.

Numbers come from the simulation; the analyst model explains them. It is told
never to invent figures that are not in the data it gets.
"""

from __future__ import annotations

import json
import random
from typing import Any, Literal

from pydantic import BaseModel, Field

from ..llm import LLMError, llm
from ..scenario.models import ScenarioSpec


class Theme(BaseModel):
    theme: str = Field(description="Short name, 2-6 words")
    share: float = Field(ge=0, le=1, description="Approximate share of the items in this theme")
    example: str = Field(description="One representative item, verbatim")


class Themes(BaseModel):
    objections: list[Theme] = Field(default_factory=list)
    reasons: list[Theme] = Field(default_factory=list)
    change_mind: list[Theme] = Field(default_factory=list)


THEME_SYSTEM = """You cluster survey answers into themes. Use 3-7 themes per list, ordered by share.
Theme names are short and concrete (e.g. 'Price too high for team size', 'Data residency concerns').
Shares are your estimate of the fraction of items in each theme. Examples must be copied verbatim."""


async def extract_themes(raw: dict[str, list[str]], model: str, seed: int | None = None) -> Themes:
    rng = random.Random(seed)
    sample = {k: rng.sample(v, min(len(v), 160)) for k, v in raw.items()}
    user = "\n\n".join(f"{k.upper()} ({len(raw[k])} items, sample shown):\n" + "\n".join(f"- {x}" for x in sample[k]) for k in sample)
    try:
        return await llm.json(task="themes", model=model, system=THEME_SYSTEM, user=user, schema=Themes, temperature=0.2, mock_ctx={"raw": sample})
    except LLMError:
        return Themes()


class Driver(BaseModel):
    factor: str
    effect: Literal["positive", "negative", "mixed"]
    evidence: str


class Insight(BaseModel):
    title: str
    detail: str


class Recommendation(BaseModel):
    action: str
    why: str
    expected_impact: str
    priority: Literal["high", "medium", "low"]


class Lever(BaseModel):
    label: str = Field(description="Short what-if, e.g. 'Cut price to $29/month'")
    description: str
    changes: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Scenario edits to test it. Allowed keys: price_amount (number), subject_append (text added to the "
            "subject description), assumed_reach (0-1), add_force (object with name, origin, direction, strength, description)"
        ),
    )


class Report(BaseModel):
    headline: str = Field(description="One sentence answer with the key number")
    verdict: Literal["strong", "promising", "uncertain", "weak", "unlikely"]
    summary: str = Field(description="3-5 sentence executive summary")
    drivers: list[Driver] = Field(default_factory=list)
    country_insights: list[Insight] = Field(default_factory=list)
    segment_insights: list[Insight] = Field(default_factory=list)
    influence_insights: list[Insight] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    recommendations: list[Recommendation] = Field(default_factory=list)
    levers: list[Lever] = Field(default_factory=list)
    confidence_note: str = Field(description="How much to trust this and why")


REPORT_SYSTEM = """You are a senior strategy analyst writing the result of a large multi-agent simulation.
Write for a founder or executive who needs to decide what to do next.

Rules:
- Use ONLY numbers present in the data. Quote them as percentages with no false precision.
- Be direct. If the result is weak, say so. No hype.
- Explain WHY using the segment, country, objection and influence data.
- Call out outside influences (e.g. a bloc's regulation affecting a target country) when the data shows an effect.
- Recommendations must be concrete and testable. Levers must be scenario edits that can be re-simulated.
- confidence_note: mention sample size, interval width, model agreement and that simulations are not ground truth."""


def _compact(results: dict[str, Any]) -> dict[str, Any]:
    keep = dict(results)
    for k in ("by_country_segment",):
        keep.pop(k, None)
    if keep.get("diffusion"):
        d = dict(keep["diffusion"])
        d.pop("network", None)
        d["examples"] = d.get("examples", [])[:5]
        if d.get("bass"):
            b = dict(d["bass"])
            curve = b.pop("curve", [])
            b["curve_samples"] = curve[:: max(1, len(curve) // 6)]
            d["bass"] = b
        keep["diffusion"] = d
    if keep.get("wtp"):
        w = dict(keep["wtp"])
        w["curve"] = w.get("curve", [])[::3]
        keep["wtp"] = w
    return keep


async def write_report(spec: ScenarioSpec, results: dict[str, Any], model: str) -> Report:
    payload = json.dumps(_compact(results), default=str)[:60000]
    user = f"SCENARIO:\n{spec.model_dump_json(indent=1)}\n\nSIMULATION RESULTS (JSON):\n{payload}"
    return await llm.json(
        task="report", model=model, system=REPORT_SYSTEM, user=user, schema=Report, temperature=0.3,
        mock_ctx={"spec": spec.model_dump(), "results": results},
    )
