"""Turn individual reactions into weighted, calibrated results with uncertainty."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

import numpy as np

from ..population.models import Persona
from ..scenario.models import ScenarioSpec
from .calibrate import Calibration, apply_array, kind_for
from .reaction import Reaction

BOOTSTRAP = 1000


def _wmean(x: np.ndarray, w: np.ndarray) -> float:
    s = w.sum()
    return float((x * w).sum() / s) if s > 0 else float("nan")


def _wquantile(x: np.ndarray, w: np.ndarray, q: float) -> float:
    if len(x) == 0:
        return float("nan")
    order = np.argsort(x)
    xs, ws = x[order], w[order]
    cw = np.cumsum(ws)
    if cw[-1] <= 0:
        return float(np.quantile(xs, q))
    return float(xs[np.searchsorted(cw, q * cw[-1], side="left").clip(0, len(xs) - 1)])


class Aggregator:
    def __init__(self, people: list[Persona], reactions: list[Reaction], spec: ScenarioSpec, cal: Calibration, seed: int | None = None):
        self.spec = spec
        self.cal = cal
        self.rng = np.random.default_rng(seed)
        self.by_person: dict[str, list[Reaction]] = defaultdict(list)
        for r in reactions:
            self.by_person[r.persona_id].append(r)
        self.people = [p for p in people if p.id in self.by_person]
        self.core = [p for p in self.people if p.influencer_voice is None]
        buyers = [p for p in self.core if p.is_buyer]
        self.focus = buyers or self.core
        self.action = kind_for(spec.subject_kind) == "action"
        self.reach = spec.assumed_reach if self.action else 1.0
        self.max_runs = max((len(v) for v in self.by_person.values()), default=1)

    # ---------- per-person numbers ----------

    def _p(self, pid: str) -> float:
        return float(np.mean([r.p_stated for r in self.by_person[pid]]))

    def _p_cal(self, pid: str) -> float:
        return float(apply_array(np.array([self._p(pid)]), self.cal)[0])

    def _matrix(self, people: list[Persona]) -> np.ndarray:
        m = np.full((len(people), self.max_runs), np.nan)
        for i, p in enumerate(people):
            vals = [r.p_stated for r in self.by_person[p.id]]
            m[i, : len(vals)] = vals
        return m

    def _weights(self, people: list[Persona]) -> np.ndarray:
        w = np.array([p.weight for p in people], dtype=float)
        if w.sum() <= 0:
            w = np.ones(len(people))
        return w

    def _summary(self, people: list[Persona]) -> dict[str, Any]:
        if not people:
            return {"n": 0}
        m = self._matrix(people)
        w = self._weights(people)
        stated = np.nanmean(m, axis=1)
        cal = apply_array(stated, self.cal)
        point = _wmean(cal, w) * self.reach
        # Bootstrap over people and over which ensemble sample we trust.
        n = len(people)
        boots = np.empty(BOOTSTRAP)
        valid_counts = (~np.isnan(m)).sum(axis=1)
        for b in range(BOOTSTRAP):
            idx = self.rng.integers(0, n, n)
            pick = (self.rng.random(n) * valid_counts[idx]).astype(int)
            vals = m[idx, pick]
            boots[b] = _wmean(apply_array(vals, self.cal), w[idx]) * self.reach
        lo, hi = np.nanpercentile(boots, [5, 95])
        heads = float(sum(p.represents for p in people))
        return {
            "n": n,
            "people": round(heads),
            "adopters": round(point * heads),
            "stated": round(_wmean(stated, w), 4),
            "calibrated": round(_wmean(cal, w), 4),
            "value": round(point, 4),
            "ci": [round(float(lo), 4), round(float(hi), 4)],
        }

    # ---------- breakdowns ----------

    def _group(self, key, label=None, min_n: int = 1, limit: int | None = None) -> list[dict[str, Any]]:
        groups: dict[str, list[Persona]] = defaultdict(list)
        for p in self.focus:
            groups[key(p)].append(p)
        out = []
        for k, members in groups.items():
            if len(members) < min_n:
                continue
            s = self._summary(members)
            s.update({"key": k, "label": label(members[0]) if label else k, "share": round(sum(m.weight for m in members), 4)})
            s["top_objection"] = self._top([o for m in members for r in self.by_person[m.id] for o in r.objections], 1)
            out.append(s)
        out.sort(key=lambda x: -x["n"])
        return out[:limit] if limit else out

    @staticmethod
    def _top(items: list[str], k: int) -> list[str]:
        norm = Counter(i.strip().rstrip(".").lower() for i in items if i.strip())
        return [t for t, _ in norm.most_common(k)]

    def influence_effects(self) -> list[dict[str, Any]]:
        """For each outside force: do exposed people answer differently?"""
        sources: dict[tuple[str, str], str] = {}
        for p in self.focus:
            for e in p.exposures:
                sources[(e.source, e.channel)] = e.source_name
        out = []
        for (src, ch), name in sources.items():
            exposed = [p for p in self.focus if any(e.source == src and e.channel == ch for e in p.exposures)]
            others = [p for p in self.focus if p not in exposed]
            if not exposed:
                continue
            pe = np.array([self._p_cal(p.id) for p in exposed])
            we = self._weights(exposed)
            em = _wmean(pe, we)
            if others:
                po = np.array([self._p_cal(p.id) for p in others])
                om = _wmean(po, self._weights(others))
            else:
                om = float("nan")
            # Mentions: answers from people who feel this force that name its source.
            mentions = sum(1 for p in exposed for r in self.by_person[p.id] if any(c.strip().upper() == src.upper() for c in r.influences))
            note = next(e.note for p in exposed for e in p.exposures if e.source == src and e.channel == ch)
            direction = next(e.direction for p in exposed for e in p.exposures if e.source == src and e.channel == ch)
            out.append(
                {
                    "source": src, "source_name": name, "channel": ch, "note": note, "direction": direction,
                    "exposed_n": len(exposed), "others_n": len(others),
                    "exposed_value": round(em * self.reach, 4),
                    "others_value": None if np.isnan(om) else round(om * self.reach, 4),
                    "delta": None if np.isnan(om) else round((em - om) * self.reach, 4),
                    "mentions": mentions,
                    "countries": sorted({p.country for p in exposed}),
                }
            )
        out.sort(key=lambda x: -(abs(x["delta"] or 0) * x["exposed_n"] + x["mentions"]))
        return out

    def voices(self) -> list[dict[str, Any]]:
        groups: dict[str, list[Persona]] = defaultdict(list)
        for p in self.people:
            if p.influencer_voice:
                groups[p.influencer_voice].append(p)
        out = []
        for code, members in groups.items():
            vals = np.array([self._p_cal(m.id) for m in members])
            out.append(
                {
                    "source": code,
                    "n": len(members),
                    "value": round(float(vals.mean()) * self.reach, 4),
                    "countries": sorted({m.country for m in members}),
                    "quotes": [
                        {"persona_id": m.id, "name": m.name, "country": m.country, "occupation": m.occupation, "quote": self.by_person[m.id][0].quote}
                        for m in members[:4]
                    ],
                }
            )
        return sorted(out, key=lambda x: -x["n"])

    def drivers(self) -> list[dict[str, Any]]:
        """Weighted correlation of each trait with the outcome."""
        if len(self.focus) < 8:
            return []
        y = np.array([self._p(p.id) for p in self.focus])
        w = self._weights(self.focus)
        out = []
        for trait in ["tech_affinity", "skepticism", "risk_appetite", "price_sensitivity", "conformity", "openness", "budget_authority"]:
            x = np.array([getattr(p.traits, trait) for p in self.focus])
            mx, my = _wmean(x, w), _wmean(y, w)
            cov = _wmean((x - mx) * (y - my), w)
            sx = np.sqrt(_wmean((x - mx) ** 2, w))
            sy = np.sqrt(_wmean((y - my) ** 2, w))
            r = cov / (sx * sy) if sx > 0 and sy > 0 else 0.0
            out.append({"trait": trait, "correlation": round(float(r), 3)})
        out.sort(key=lambda d: -abs(d["correlation"]))
        return out

    def wtp(self) -> dict[str, Any] | None:
        if not self.spec.price:
            return None
        vals, ws, countries_ = [], [], []
        for p in self.focus:
            ps = [r.willingness_to_pay for r in self.by_person[p.id] if r.willingness_to_pay is not None and r.willingness_to_pay >= 0]
            if ps:
                vals.append(float(np.median(ps)))
                ws.append(p.weight or 1.0)
                countries_.append(p.country)
        if not vals:
            return None
        v, w = np.array(vals), np.array(ws)
        price = self.spec.price.amount
        top = max(price * 3, _wquantile(v, w, 0.95))
        grid = sorted({round(x, 2) for x in np.linspace(0, top, 25)} | {price})
        curve = [{"price": g, "share": round(float(w[v >= g].sum() / w.sum()), 4)} for g in grid]
        by_c = []
        for c in sorted(set(countries_)):
            mask = np.array([x == c for x in countries_])
            by_c.append({"country": c, "median": round(_wquantile(v[mask], w[mask], 0.5), 2), "n": int(mask.sum())})
        return {
            "currency": "USD",
            "period": self.spec.price.period,
            "price": price,
            "median": round(_wquantile(v, w, 0.5), 2),
            "p25": round(_wquantile(v, w, 0.25), 2),
            "p75": round(_wquantile(v, w, 0.75), 2),
            "share_at_price": round(float(w[v >= price].sum() / w.sum()), 4),
            "curve": curve,
            "by_country": by_c,
        }

    def outcome_distribution(self) -> list[dict[str, Any]] | dict[str, Any] | None:
        spec = self.spec
        w = self._weights(self.focus)
        if spec.outcome_type == "categorical":
            out = []
            for o in spec.outcomes:
                vals = np.array([np.mean([(r.option_probs or {}).get(o, 0.0) for r in self.by_person[p.id]]) for p in self.focus])
                out.append({"option": o, "share": round(_wmean(vals, w), 4)})
            return out
        if spec.outcome_type == "numeric":
            vals = np.array([np.nanmean([r.estimate if r.estimate is not None else np.nan for r in self.by_person[p.id]]) for p in self.focus])
            mask = ~np.isnan(vals)
            if not mask.any():
                return None
            v, ww = vals[mask], w[mask]
            return {
                "unit": spec.numeric_unit,
                "median": round(_wquantile(v, ww, 0.5), 4),
                "p10": round(_wquantile(v, ww, 0.1), 4),
                "p90": round(_wquantile(v, ww, 0.9), 4),
                "mean": round(_wmean(v, ww), 4),
            }
        yes = np.array([np.mean([1.0 if r.choice == spec.outcomes[0] else 0.0 for r in self.by_person[p.id]]) for p in self.focus])
        return [
            {"option": spec.outcomes[0], "share": round(_wmean(yes, w), 4)},
            {"option": spec.outcomes[1], "share": round(1 - _wmean(yes, w), 4)},
        ]

    def model_agreement(self) -> list[dict[str, Any]]:
        by_model: dict[str, list[float]] = defaultdict(list)
        focus_ids = {p.id for p in self.focus}
        for pid, rs in self.by_person.items():
            if pid in focus_ids:
                for r in rs:
                    by_model[r.model].append(r.p_stated)
        return [
            {"model": m, "n": len(v), "stated": round(float(np.mean(v)), 4), "calibrated": round(float(apply_array(np.array([np.mean(v)]), self.cal)[0]) * self.reach, 4)}
            for m, v in sorted(by_model.items())
        ]

    def attention(self) -> dict[str, float]:
        c: Counter[str] = Counter()
        for p in self.focus:
            for r in self.by_person[p.id]:
                c[r.attention] += 1
        total = sum(c.values()) or 1
        return {k: round(c.get(k, 0) / total, 4) for k in ["ignore", "skim", "consider", "evaluate"]}

    def quotes(self, k: int = 6) -> dict[str, list[dict[str, Any]]]:
        rows = []
        for p in self.focus:
            r = self.by_person[p.id][0]
            rows.append((self._p(p.id), p, r))
        rows.sort(key=lambda x: -x[0])

        def fmt(item):
            pv, p, r = item
            return {"persona_id": p.id, "name": p.name, "country": p.country, "occupation": p.occupation, "segment": p.segment, "p": round(pv, 3), "quote": r.quote}

        pos = [fmt(x) for x in rows[:k] if x[0] >= 0.5]
        neg = [fmt(x) for x in reversed(rows[-k:]) if x[0] < 0.5]
        mid = len(rows) // 2
        middle = [fmt(x) for x in rows[max(0, mid - k // 2) : mid + k // 2]]
        return {"positive": pos, "negative": neg, "undecided": middle}

    def raw_lists(self) -> dict[str, list[str]]:
        reasons, objections, change = [], [], []
        for p in self.focus:
            for r in self.by_person[p.id]:
                reasons += r.reasons
                objections += r.objections
                change += r.change_mind
        return {"reasons": reasons, "objections": objections, "change_mind": change}

    def results(self) -> dict[str, Any]:
        head = self._summary(self.focus)
        label = (
            f"Realistic share who {self.spec.outcomes[0].lower()} within {self.spec.horizon_months} months"
            if self.action and self.spec.outcome_type != "numeric"
            else f"Probability: {self.spec.outcomes[0]}"
        )
        return {
            "headline": {
                **head,
                "label": label,
                "reach": self.reach,
                "if_aware": head.get("calibrated"),
                "kind": "action" if self.action else "belief",
                "calibration": self.cal.model_dump(),
                "samples": sum(len(self.by_person[p.id]) for p in self.focus),
                "agents_total": len(self.people),
            },
            "outcomes": self.outcome_distribution(),
            "attention": self.attention(),
            "by_country": self._group(lambda p: p.country, lambda p: p.country_name),
            "by_segment": self._group(lambda p: p.segment),
            "by_occupation": self._group(lambda p: p.occupation_id, lambda p: p.occupation, min_n=2, limit=20),
            "by_seniority": self._group(lambda p: p.seniority),
            "by_company_type": self._group(lambda p: p.company_type),
            "by_country_segment": self._group(lambda p: f"{p.country}|{p.segment}", lambda p: f"{p.country_name}, {p.segment}"),
            "influence_effects": self.influence_effects(),
            "influencer_voices": self.voices(),
            "drivers": self.drivers(),
            "wtp": self.wtp(),
            "model_agreement": self.model_agreement(),
            "quotes": self.quotes(),
        }
