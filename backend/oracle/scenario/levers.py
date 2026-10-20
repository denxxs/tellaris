"""Apply a what-if lever to a scenario."""

from __future__ import annotations

from typing import Any

from .models import Force, Price, ScenarioSpec


def apply_lever(spec: ScenarioSpec, changes: dict[str, Any]) -> ScenarioSpec:
    s = spec.model_copy(deep=True)
    if "price_amount" in changes and changes["price_amount"] is not None:
        amount = float(changes["price_amount"])
        s.price = (s.price or Price(amount=amount)).model_copy(update={"amount": amount})
    if changes.get("price_period") and s.price:
        s.price.period = str(changes["price_period"])
    if changes.get("subject_append"):
        s.subject = f"{s.subject.rstrip()} {str(changes['subject_append']).strip()}"
    if changes.get("subject"):
        s.subject = str(changes["subject"])
    if changes.get("assumed_reach") is not None:
        s.assumed_reach = max(0.0, min(1.0, float(changes["assumed_reach"])))
    if changes.get("horizon_months"):
        s.horizon_months = int(changes["horizon_months"])
    if isinstance(changes.get("add_force"), dict):
        f = dict(changes["add_force"])
        f.setdefault("origin", "global")
        f.setdefault("name", "New factor")
        s.forces = [*s.forces, Force.model_validate(f)]
    if changes.get("remove_force"):
        s.forces = [f for f in s.forces if f.name != changes["remove_force"]]
    if changes.get("lens") in ("b2b", "consumer", "personal", "opinion", "forecast"):
        s.lens = changes["lens"]
        s.b2b = s.lens == "b2b"
    if changes.get("competitors") is not None:
        s.competitors = list(changes["competitors"])
    return ScenarioSpec.model_validate(s.model_dump())
