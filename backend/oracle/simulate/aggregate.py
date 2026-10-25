"""Turn individual reactions into weighted, calibrated results with uncertainty."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

import math

import numpy as np

from ..population.models import Persona
from ..world.countries import blocs, countries
from ..scenario.models import ScenarioSpec
from ..scenario.lenses import lens_of
from .calibrate import Calibration, apply_array
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
        for r in sorted(reactions, key=lambda r: (r.persona_id, r.run)):  # stable order, reproducible ranges
            self.by_person[r.persona_id].append(r)
        self.people = [p for p in people if p.id in self.by_person]
        self.core = [p for p in self.people if p.influencer_voice is None]
        buyers = [p for p in self.core if p.is_buyer]
        self.focus = buyers or self.core
        self.lens = lens_of(spec)
        self.action = self.lens.say_do
        # The headline is what people answered. Awareness (how many will even hear of it) is only
        # applied when the user gave it; Tellaris never guesses it.
        self.reach = 1.0
        self.awareness = spec.assumed_reach if self.lens.reach and spec.assumed_reach is not None else None
        # Turns a share into people: everyone for opinion questions, the aware for adoption questions.
        self.aw = 1.0 if not self.lens.reach else self.awareness
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

    def _summary(self, people: list[Persona], boots_n: int = BOOTSTRAP) -> dict[str, Any]:
        if not people:
            return {"n": 0}
        m = self._matrix(people)
        w = self._weights(people)
        stated = np.nanmean(m, axis=1)
        cal = apply_array(stated, self.cal)
        point = _wmean(cal, w) * self.reach
        # Bootstrap over people and over which ensemble sample we trust.
        n = len(people)
        boots = np.empty(boots_n)
        valid_counts = (~np.isnan(m)).sum(axis=1)
        for b in range(boots_n):
            idx = self.rng.integers(0, n, n)
            pick = (self.rng.random(n) * valid_counts[idx]).astype(int)
            vals = m[idx, pick]
            boots[b] = _wmean(apply_array(vals, self.cal), w[idx]) * self.reach
        lo, hi = np.nanpercentile(boots, [5, 95])
        heads = float(sum(p.represents for p in people))
        known = all(p.represents > 0 for p in people)  # 0 = no published size for their group
        return {
            "n": n,
            "people": round(heads) if known else None,
            "adopters": round(point * heads * self.aw) if self.aw is not None and known else None,
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
        """Weighted correlation of each measured attribute with the outcome."""
        if len(self.focus) < 8:
            return []
        y = np.array([self._p(p.id) for p in self.focus])
        w = self._weights(self.focus)
        out = []
        # Survey traits where present, the person's Findex facts (yes = 1), and age.
        candidates: dict[str, list[float | None]] = {}
        for trait in ["tech_affinity", "skepticism", "risk_appetite", "price_sensitivity", "conformity", "openness"]:
            candidates[trait] = [getattr(p.traits, trait) for p in self.focus]
        for fact in sorted({k for p in self.focus for k in p.facts}):
            candidates[fact] = [(1.0 if p.facts[fact] else 0.0) if fact in p.facts else None for p in self.focus]
        candidates["age"] = [float(p.age) for p in self.focus]
        # Answers of the matched real survey respondents (higher = more of the label).
        from ..population.views import BY_KEY, scores

        sc = [scores(p.views) for p in self.focus]
        for key in sorted({k for s_ in sc for k in s_}):
            candidates[key] = [s_.get(key) for s_ in sc]
        for trait, vals in candidates.items():
            if sum(v is not None for v in vals) < 0.8 * len(vals):
                continue  # too few people have it to compare
            keep = np.array([v is not None for v in vals])
            x = np.array([v for v in vals if v is not None], dtype=float)
            ww, yy = w[keep], y[keep]
            mx, my = _wmean(x, ww), _wmean(yy, ww)
            cov = _wmean((x - mx) * (yy - my), ww)
            sx = np.sqrt(_wmean((x - mx) ** 2, ww))
            sy = np.sqrt(_wmean((yy - my) ** 2, ww))
            r = cov / (sx * sy) if sx > 0 and sy > 0 else 0.0
            row = {"trait": trait, "correlation": round(float(r), 3)}
            if trait in BY_KEY:
                row["label"] = BY_KEY[trait].label
            out.append(row)
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

    def _option_ci(self, option: str) -> list[float]:
        """Likely range for one option's share, by resampling people."""
        if not self.focus:
            return [0.0, 0.0]
        vals = np.array([np.mean([(r.option_probs or {}).get(option, 0.0) for r in self.by_person[p.id]]) for p in self.focus])
        w = self._weights(self.focus)
        n = len(vals)
        boots = np.empty(400)
        for b in range(400):
            idx = self.rng.integers(0, n, n)
            boots[b] = _wmean(vals[idx], w[idx])
        lo, hi = np.nanpercentile(boots, [5, 95])
        return [round(float(lo), 4), round(float(hi), 4)]

    # ---------- where it works and where it doesn't ----------

    @staticmethod
    def _age_band(age: int) -> str:
        return "18-29" if age < 30 else "30-44" if age < 45 else "45-59" if age < 60 else "60+"

    @classmethod
    def _dims(cls) -> dict[str, tuple[str, Any, Any]]:
        """Dimension id -> (label, key function, display function)."""
        cs = countries()
        age_label = {"18-29": "Under 30s", "30-44": "30 to 44 year olds", "45-59": "45 to 59 year olds", "60+": "Over 60s"}
        income_label = {"low": "Lower incomes", "middle": "Middle incomes", "high": "Higher incomes", "very high": "Top earners"}
        gender_label = {"woman": "Women", "man": "Men", "non-binary person": "Non-binary people"}
        isco = ["", "Managers and owners", "Professionals", "Technicians", "Clerical workers", "Service and sales workers",
                "Farmers", "Trades workers", "Machine operators", "Elementary jobs"]

        def region(p: Persona) -> str:
            c = cs.get(p.country)
            if not c:
                return "Other"
            if c.region.startswith("Europe"):
                eu = set(blocs()["EU"].members) | {"GBR", "CHE", "NOR"} if "EU" in blocs() else set()
                return "Western Europe" if p.country in eu else "Eastern Europe and Central Asia"
            return c.region.replace("Middle East, North Africa, Afghanistan & Pakistan", "Middle East, North Africa and Pakistan")

        return {
            "country": ("Country", lambda p: p.country, lambda k: cs[k].name if k in cs else k),
            "region": ("Region", region, lambda k: k),
            "age": ("Age", lambda p: cls._age_band(p.age), lambda k: age_label.get(k, k)),
            "gender": ("Gender", lambda p: p.gender, lambda k: gender_label.get(k, k)),
            "income": ("Income", lambda p: p.income_band, lambda k: income_label.get(k, k)),
            "work": ("Type of work", lambda p: "Not working" if p.isco == 0 else isco[p.isco], lambda k: k),
            "segment": ("Group", lambda p: p.segment, lambda k: k),
            "company": ("Company", lambda p: p.company_type, lambda k: k.replace("_", " ").capitalize()),
        }

    def splits(self, head: dict[str, Any]) -> dict[str, Any]:
        """Breakdowns on every dimension, and the cells that really differ from the overall answer."""
        dims = self._dims()
        focus = self.focus
        if len(focus) < 20:
            return {"dimensions": {}, "hot": [], "cold": []}
        overall = head.get("value", 0.0)
        o_lo, o_hi = head.get("ci", [overall, overall])
        min_n = 12

        def cells(keyfn) -> dict[str, list[Persona]]:
            out: dict[str, list[Persona]] = defaultdict(list)
            for p in focus:
                out[keyfn(p)].append(p)
            return out

        dimensions: dict[str, Any] = {}
        for dim_id, (label, keyfn, show) in dims.items():
            groups = cells(keyfn)
            if len(groups) < 2:
                continue
            rows = []
            for k, members in groups.items():
                if len(members) < min_n:
                    continue
                s = self._summary(members, boots_n=300)
                rows.append({"key": k, "label": show(k), "n": s["n"], "value": s["value"], "ci": s["ci"], "people": s.get("people")})
            if len(rows) >= 2:
                rows.sort(key=lambda r: -r["value"])
                dimensions[dim_id] = {"label": label, "rows": rows, "hidden": sum(1 for v in groups.values() if len(v) < min_n)}

        # Pairs that tend to tell a story ("Under 30s in India").
        pairs = [("age", "country"), ("age", "region"), ("gender", "country"), ("income", "country"), ("age", "gender"), ("work", "country")]
        # The same people can turn up under two names (Italy and Western Europe when Italy is the
        # only Western European country). Keep the first, simplest name for each set of people.
        candidates = []
        seen: set[frozenset[str]] = set()

        def add(cell: dict[str, Any], members: list[Persona]) -> None:
            key = frozenset(p.id for p in members)
            if key not in seen:
                seen.add(key)
                candidates.append(cell)

        for dim_id, (label, keyfn, show) in dims.items():
            if dim_id in dimensions:
                groups = cells(keyfn)
                for r in dimensions[dim_id]["rows"]:
                    add({"label": r["label"], "dims": [dim_id], "keys": {dim_id: r["key"]}, **{k: r[k] for k in ("n", "value", "ci", "people")}}, groups[r["key"]])
        for a, b in pairs:
            if a not in dimensions or b not in dimensions:
                continue
            la, ka, sa = dims[a]
            lb, kb, sb = dims[b]
            groups = cells(lambda p: (ka(p), kb(p)))
            for (va, vb), members in groups.items():
                if len(members) < min_n:
                    continue
                s = self._summary(members, boots_n=300)
                joiner = " in " if b in ("country", "region") else ", "
                add({"label": f"{sa(va)}{joiner}{sb(vb)}", "dims": [a, b], "keys": {a: va, b: vb}, **{k: s[k] for k in ("n", "value", "ci")}, "people": s.get("people")}, members)

        def score(c: dict[str, Any]) -> float:
            return abs(c["value"] - overall) * math.sqrt(c["n"])

        hot = [c for c in candidates if c["ci"][0] > o_hi]
        cold = [c for c in candidates if c["ci"][1] < o_lo]
        for c in hot + cold:
            c["vs_overall"] = round(c["value"] - overall, 4)
        hot.sort(key=lambda c: -score(c))
        cold.sort(key=lambda c: -score(c))
        return {"dimensions": dimensions, "hot": hot[:8], "cold": cold[:8], "overall": overall, "min_n": min_n}

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
        first = self.spec.outcomes[0].strip().lower()
        verb = "say yes" if first in ("yes", "y", "true", "agree") else first
        label = (
            f"Share who would {verb} once they hear about it"
            if self.action and self.spec.outcome_type != "numeric"
            else f"Probability: {self.spec.outcomes[0]}"
        )
        heads = float(head.get("people") or 0)
        # Without a given awareness, scale is stated per 1% of the audience who hears about it.
        per_point = round(head["value"] * heads / 100) if self.lens.reach and head.get("value") is not None and heads else None
        revenue = None
        price = self.spec.price
        if price and self.lens.revenue and head.get("value") is not None and heads:
            per_month = {"month": 1.0, "per-seat-month": 1.0, "year": 1 / 12, "usage": 1.0}.get(price.period)
            if per_month is not None:
                unit = price.amount * per_month
                aw = self.aw
                revenue = {
                    "customers": head.get("adopters"),
                    "monthly": round(head["adopters"] * unit, 2) if head.get("adopters") is not None else None,
                    "monthly_ci": [round(x * heads * aw * unit, 2) for x in head["ci"]] if aw is not None else None,
                    "per_point_monthly": round(head["value"] * heads / 100 * unit, 2) if self.lens.reach else None,
                    "currency": price.currency,
                    "note": "Customers times the list price, one seat each.",
                }
        leading = None
        dist = self.outcome_distribution()
        if self.spec.outcome_type == "categorical" and isinstance(dist, list) and dist:
            top = max(dist, key=lambda d: d["share"])
            leading = {"option": top["option"], "share": top["share"], "ci": self._option_ci(top["option"])}
            # The value still measures the first option; the leading option travels separately.
            label = f"Share choosing “{self.spec.outcomes[0]}”"
        elif self.spec.outcome_type == "numeric" and isinstance(dist, dict):
            unit = dist.get("unit")
            label = f"Typical answer ({unit})" if unit else "Typical answer"
        elif not self.action:
            first = self.spec.outcomes[0]
            label = f"Share who say “{first}”" if first.lower() not in ("yes", "y") else "Share who say yes"
        return {
            "headline": {
                **head,
                "leading": leading,
                "label": label,
                "reach": self.reach,
                "if_aware": head.get("calibrated"),
                "awareness": self.awareness,
                "per_point_adopters": per_point,
                "with_awareness": (
                    {"value": round(head["value"] * self.awareness, 4), "ci": [round(x * self.awareness, 4) for x in head["ci"]]}
                    if self.awareness is not None and head.get("value") is not None else None
                ),
                "kind": "action" if self.action else "belief",
                "lens": self.lens.id,
                "lens_label": self.lens.label,
                "calibration": self.cal.model_dump(),
                "samples": sum(len(self.by_person[p.id]) for p in self.focus),
                "agents_total": len(self.people),
                "revenue": revenue,
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
            "splits": self.splits(head),
        }


def breakdowns() -> dict[str, tuple[str, Any, Any]]:
    """The breakdown dimensions used by Where it works: id -> (label, key function, display function)."""
    return Aggregator._dims()
