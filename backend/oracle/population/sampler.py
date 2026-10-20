"""Population builder: draws a realistic, weighted set of people.

Structure comes from data (country labour mix, income levels, digital maturity,
regulation), so the crowd is not whatever an LLM imagines. The LLM only adds
names and backstories afterwards (see enrich.py).
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass

import numpy as np

from ..scenario.models import Force, ScenarioSpec, Segment
from ..world.countries import Country, Occupation, blocs, company_types, countries, occupations
from ..world.influence import Influencer
from .headcount import seg_headcount
from .models import Exposure, Persona, Traits

SENIORITY = ["junior", "mid", "senior", "executive"]
SENIORITY_INCOME = {"junior": 0.7, "mid": 1.0, "senior": 1.5, "executive": 2.6}
SENIORITY_AGE = {"junior": (21, 30), "mid": (27, 42), "senior": (34, 56), "executive": (38, 66)}
SENIORITY_AUTHORITY = {"junior": 0.05, "mid": 0.2, "senior": 0.5, "executive": 0.85}
OWNER_OCCUPATIONS = {"founder_b2b_saas", "founder_d2c", "smb_owner", "farmer", "freelancer", "electrician"}
NON_WORKERS = {"student", "retiree", "homemaker", "unemployed"}


@dataclass
class _Occ:
    """Occupation used for sampling (catalogue entry or a custom one)."""

    id: str
    title: str
    isco: int
    sectors: list[str]
    company_types: list[str]
    income_mult: float
    tech: float
    buyer_role: str

    @classmethod
    def of(cls, o: Occupation) -> "_Occ":
        return cls(o.id, o.title, o.isco, o.sectors, o.company_types, o.income_mult, o.tech, o.buyer_role)


def _clip(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return float(min(hi, max(lo, x)))


def _allocate(total: int, weights: dict[str, float]) -> dict[str, int]:
    """Largest-remainder allocation that gives every key at least one slot when possible."""
    keys = [k for k, w in weights.items() if w > 0]
    if not keys or total <= 0:
        return {}
    wsum = sum(weights[k] for k in keys)
    raw = {k: total * weights[k] / wsum for k in keys}
    alloc = {k: int(math.floor(v)) for k, v in raw.items()}
    if total >= len(keys):
        for k in keys:
            if alloc[k] == 0:
                alloc[k] = 1
    while sum(alloc.values()) > total:
        k = max(alloc, key=lambda x: alloc[x] - raw[x])
        alloc[k] -= 1
    rem = sorted(keys, key=lambda k: raw[k] - alloc[k], reverse=True)
    i = 0
    while sum(alloc.values()) < total:
        alloc[rem[i % len(rem)]] += 1
        i += 1
    return alloc


class PopulationBuilder:
    def __init__(self, spec: ScenarioSpec, influencers: list[Influencer], seed: int | None = None, weighting: str = "population"):
        self.spec = spec
        self.weighting = weighting
        self.influencers = influencers
        self.rng = np.random.default_rng(seed)
        self.occ = occupations()
        self.ctypes = company_types()
        self._direct_targets: dict[str, set[str]] = {}
        for inf in influencers:
            if inf.order == 1:
                self._direct_targets[inf.code] = {e.target for e in inf.edges}

    # ---------- occupation choice ----------

    def _segment_pool(self, seg: Segment, country: Country) -> list[tuple[_Occ, float]]:
        if seg.occupations:
            shares = country.isco_shares()
            pool = []
            for oid in seg.occupations:
                o = self.occ[oid]
                # Within a segment, lean slightly on how common the job group is in this country.
                group = shares.get(o.isco, 0.1) if o.isco else 0.1
                pool.append((_Occ.of(o), o.weight * (0.5 + group)))
            return pool
        if seg.custom_occupation:
            title = seg.custom_occupation.strip().capitalize()
            sectors = self.spec.sectors[:2] or ["services"]
            ctypes = seg.company_types or ["smb", "midmarket", "enterprise"]
            return [(_Occ(f"custom:{title.lower()}", title, 2, sectors, ctypes, 1.5, 0.6, "champion"), 1.0)]
        return self._general_pool(country)

    def _general_pool(self, country: Country) -> list[tuple[_Occ, float]]:
        """Representative adults: workers by ISCO mix, plus non-workers."""
        shares = country.isco_shares()
        adults = country.population_m * 0.72  # rough share aged 15+
        worker_share = _clip(country.workforce_m / max(adults, 1), 0.3, 0.9)
        by_group: dict[int, list[Occupation]] = {}
        for o in self.occ.values():
            by_group.setdefault(o.isco, []).append(o)
        pool: list[tuple[_Occ, float]] = []
        for g, members in by_group.items():
            gw = worker_share * shares.get(g, 0) if g else (1 - worker_share)
            total_w = sum(m.weight for m in members) or 1
            for m in members:
                pool.append((_Occ.of(m), gw * m.weight / total_w))
        return pool

    @staticmethod
    def _age_ok(o: _Occ, seg: Segment) -> bool:
        lo, hi = seg.age_min or 15, seg.age_max or 100
        if o.id == "retiree":
            return hi >= 58
        if o.id == "student":
            return lo <= 30
        return True

    def _pick(self, pool: list[tuple[_Occ, float]]) -> _Occ:
        w = np.array([max(p[1], 1e-9) for p in pool])
        return pool[int(self.rng.choice(len(pool), p=w / w.sum()))][0]

    # ---------- attributes ----------

    def _seniority(self, o: _Occ) -> str:
        if o.id in OWNER_OCCUPATIONS:
            return "executive"
        if o.id in NON_WORKERS:
            return "junior"
        if o.isco == 1:
            p = [0.0, 0.15, 0.45, 0.40]
        elif o.isco in (2, 3):
            p = [0.3, 0.4, 0.25, 0.05]
        else:
            p = [0.45, 0.4, 0.13, 0.02]
        return SENIORITY[int(self.rng.choice(4, p=p))]

    def _company(self, o: _Occ, seg: Segment) -> tuple[str, int]:
        options = [c for c in (seg.company_types or []) if c in o.company_types] or o.company_types or ["smb"]
        if seg.company_types and not any(c in o.company_types for c in seg.company_types):
            options = seg.company_types
        ctype = options[int(self.rng.integers(len(options)))]
        lo, hi = self.ctypes.get(ctype, {"employees": [1, 100]})["employees"]
        if hi <= 1:
            return ctype, int(hi)
        size = int(round(math.exp(self.rng.uniform(math.log(max(lo, 1)), math.log(hi)))))
        return ctype, size

    def _sector(self, o: _Occ) -> str:
        relevant = [s for s in o.sectors if s in self.spec.sectors]
        if relevant:
            return relevant[int(self.rng.integers(len(relevant)))]
        concrete = [s for s in o.sectors if s not in ("all", "none")]
        if concrete:
            return concrete[int(self.rng.integers(len(concrete)))]
        if "all" in o.sectors and self.spec.sectors:
            return self.spec.sectors[int(self.rng.integers(len(self.spec.sectors)))]
        return "services" if "all" in o.sectors else "none"

    def _age(self, o: _Occ, seniority: str) -> int:
        if o.id == "student":
            return int(self.rng.integers(18, 26))
        if o.id == "retiree":
            return int(self.rng.integers(61, 82))
        lo, hi = SENIORITY_AGE[seniority]
        return int(self.rng.integers(lo, hi + 1))

    def _traits(self, o: _Occ, c: Country, seniority: str, age: int, ctype: str, size: int, income_rel: float) -> Traits:
        r = self.rng
        youth = _clip((45 - age) / 40, -0.5, 0.6)
        tech = _clip(0.55 * o.tech + 0.2 * c.tech_trust + 0.15 * c.digital + 0.12 * youth + r.normal(0, 0.1))
        skeptic = _clip(r.beta(2.6, 2.4) + 0.15 * (1 - c.tech_trust) - 0.1 + (0.05 if age > 50 else 0))
        risk = _clip(r.beta(2.2, 2.8) + (0.25 if o.id.startswith("founder") or o.id == "vc_investor" else 0) + 0.08 * youth)
        price = _clip(0.55 * c.price_sensitivity + 0.3 * (1 - _clip(income_rel / 3)) + r.normal(0, 0.1) + (0.1 if ctype in ("startup", "smb", "self_employed") else 0))
        conformity = _clip(r.beta(2.4, 2.6) + (0.1 if c.region in ("East Asia", "South Asia", "Southeast Asia") else 0))
        openness = _clip(r.beta(2.6, 2.2) + 0.1 * youth)
        authority = SENIORITY_AUTHORITY[seniority]
        if o.buyer_role == "economic_buyer":
            authority += 0.15
        if o.id in OWNER_OCCUPATIONS:
            authority = 0.95
        if ctype == "enterprise" and o.id not in OWNER_OCCUPATIONS:
            authority *= 0.7
        if o.id in NON_WORKERS:
            authority = 0.0
        return Traits(
            tech_affinity=round(tech, 3),
            skepticism=round(skeptic, 3),
            risk_appetite=round(risk, 3),
            price_sensitivity=round(price, 3),
            conformity=round(conformity, 3),
            openness=round(openness, 3),
            budget_authority=round(_clip(authority + r.normal(0, 0.05)), 3),
        )

    def _exposures(self, iso: str, sector: str, o: _Occ, ctype: str) -> list[Exposure]:
        out: list[Exposure] = []
        for inf in self.influencers:
            for e in inf.edges:
                if e.origin == "scenario":
                    continue  # scenario forces are applied below, once, with their direction
                if inf.order == 1:
                    hits_me = e.target == iso
                else:
                    # X -> mid -> me: only if the intermediate actually reaches my country.
                    hits_me = any(iso in self._direct_targets.get(v, set()) for v in inf.via)
                if not hits_me:
                    continue
                specific = sector in e.sectors or any(s in e.sectors for s in o.sectors)
                general = "all" in e.sectors
                if not (specific or general):
                    continue
                # Big companies feel cross-border forces more (they have foreign clients).
                scale = 1.0 if ctype in ("enterprise", "midmarket", "scaleup") else 0.65
                p = _clip(e.strength * (1.25 if specific else 0.55) * scale)
                if self.rng.random() < p:
                    out.append(
                        Exposure(
                            source=e.source, source_name=inf.name, channel=e.channel,
                            strength=e.strength, note=e.note, origin=e.origin,
                        )
                    )
        for f in self.spec.forces:
            if not self._force_applies(f, iso, sector, o):
                continue
            if self.rng.random() < _clip(0.25 + f.strength * 0.85):
                name = f.origin
                if f.origin in countries():
                    name = countries()[f.origin].name
                elif f.origin in blocs():
                    name = blocs()[f.origin].name
                out.append(
                    Exposure(
                        source=f.origin, source_name=name, channel=f.channel, strength=f.strength,
                        note=f"{f.name}: {f.description}".strip(": "), direction=f.direction, origin="scenario",
                    )
                )
        out.sort(key=lambda x: -x.strength)
        return out[:6]

    @staticmethod
    def _force_applies(f: Force, iso: str, sector: str, o: _Occ) -> bool:
        if f.affects and iso not in f.affects:
            return False
        s = set(f.sectors or ["all"])
        return "all" in s or sector in s or bool(s & set(o.sectors))

    # ---------- build ----------

    def _person(self, idx: str, iso: str, seg: Segment, seg_index: int, *, voice: str | None = None) -> Persona:
        c = countries()[iso]
        pool = [(o, w) for o, w in self._segment_pool(seg, c) if self._age_ok(o, seg)] or self._segment_pool(seg, c)
        o = self._pick(pool)
        seniority = self._seniority(o)
        ctype, size = self._company(o, seg)
        sector = self._sector(o)
        age = self._age(o, seniority)
        if seg.age_min is not None or seg.age_max is not None:
            lo, hi = seg.age_min or 15, max(seg.age_min or 15, seg.age_max or 95)
            if not lo <= age <= hi:
                age = int(self.rng.integers(lo, hi + 1))
                # Keep seniority believable for the age we landed on.
                if age < 26 and seniority in ("senior", "executive") and o.id not in OWNER_OCCUPATIONS:
                    seniority = "junior"
        income = c.gdp_pc_usd * o.income_mult * SENIORITY_INCOME[seniority] * float(self.rng.lognormal(0, 0.35))
        if o.id in NON_WORKERS:
            income = c.gdp_pc_usd * o.income_mult * float(self.rng.lognormal(0, 0.4))
        rel = income / max(c.gdp_pc_usd, 1)
        band = "low" if rel < 0.7 else "middle" if rel < 1.6 else "high" if rel < 4 else "very high"
        traits = self._traits(o, c, seniority, age, ctype, size, rel)
        if voice is None:
            exposures = self._exposures(iso, sector, o, ctype)
        else:
            exposures = []
        return Persona(
            id=idx, country=iso, country_name=c.name, segment=seg.name, segment_index=seg_index,
            occupation_id=o.id, occupation=o.title, isco=o.isco, sector=sector, company_type=ctype,
            company_size=size, seniority=seniority, buyer_role=o.buyer_role, age=age,
            gender=seg.gender if seg.gender in ("woman", "man") else str(self.rng.choice(["woman", "man", "non-binary person"], p=[0.475, 0.51, 0.015])),
            income_usd=int(round(income, -2)), income_band=band, traits=traits, exposures=exposures,
            is_buyer=seg.is_buyer if voice is None else False, influencer_voice=voice,
            group_trait=seg.trait if voice is None else None,
        )

    def build(self, n: int, influencer_voices: int = 0) -> list[Persona]:
        spec = self.spec
        segs = list(spec.segments)
        if spec.general_population_share > 0 and not any(not s.occupations and not s.custom_occupation for s in segs):
            buyer_w = sum(s.weight for s in segs) or 1
            share = spec.general_population_share
            segs.append(
                Segment(
                    name="General public",
                    description="Representative adults for broader context",
                    weight=buyer_w * share / max(1 - share, 1e-6),
                    is_buyer=False,
                )
            )
        def segs_in(iso: str) -> dict[str, float]:
            return {str(i): s.weight for i, s in enumerate(segs) if not s.countries or iso in s.countries}

        # Countries with no segment that lives there get no agents.
        country_w = {
            iso: w for iso, w in (spec.target_weights or {t: 1.0 for t in spec.targets}).items() if segs_in(iso)
        }
        people: list[Persona] = []
        counter = 0
        if self.weighting == "population":
            # Automatic sizing: every (country, group) cell gets agents in proportion to the
            # square root of its real headcount. Big groups get more agents, small ones still
            # get enough to say something, and the weights below put everyone back at true scale.
            cell_heads = {
                (iso, i): seg_headcount(iso, s)
                for iso in country_w
                for i, s in enumerate(segs)
                if not s.countries or iso in s.countries
            }
            buyer_cells = {f"{k[0]}|{k[1]}": math.sqrt(max(v, 1.0)) for k, v in cell_heads.items() if segs[k[1]].is_buyer}
            other_cells = {f"{k[0]}|{k[1]}": math.sqrt(max(v, 1.0)) for k, v in cell_heads.items() if not segs[k[1]].is_buyer}
            n_other = round(n * spec.general_population_share) if other_cells and buyer_cells else (n if other_cells else 0)
            alloc = {**_allocate(n - n_other, buyer_cells), **_allocate(n_other, other_cells)}
            for key, k in alloc.items():
                iso, si = key.split("|")
                for _ in range(k):
                    counter += 1
                    people.append(self._person(f"p{counter:05d}", iso, segs[int(si)], int(si)))
        else:
            country_alloc = _allocate(n, country_w)
            for iso, count in country_alloc.items():
                seg_alloc = _allocate(count, segs_in(iso))
                for si, k in seg_alloc.items():
                    seg = segs[int(si)]
                    for _ in range(k):
                        counter += 1
                        people.append(self._person(f"p{counter:05d}", iso, seg, int(si)))

        # How many real people each agent stands for: the cell's estimated headcount
        # split across the agents sampled into it.
        cells = Counter((p.country, p.segment_index) for p in people)
        heads = {
            key: seg_headcount(key[0], segs[key[1]])
            for key in cells
        }
        for p in people:
            p.represents = round(heads[(p.country, p.segment_index)] / cells[(p.country, p.segment_index)], 1)

        if self.weighting == "population":
            # Weight = real people represented, normalised within buyers and within everyone else.
            for group in (True, False):
                members = [p for p in people if p.is_buyer == group]
                total = sum(p.represents for p in members) or 1
                for p in members:
                    p.weight = round(p.represents / total, 10)
        else:
            # Equal: country share x segment share within that country. Sums to 1.
            cw_total = sum(country_w.values()) or 1
            for p in people:
                cw = country_w[p.country] / cw_total
                local = segs_in(p.country)
                sw = segs[p.segment_index].weight / (sum(local.values()) or 1)
                p.weight = round(cw * sw / cells[(p.country, p.segment_index)], 8)

        people.extend(self._voices(influencer_voices, segs, counter))
        return people

    def _voices(self, n: int, segs: list[Segment], start: int) -> list[Persona]:
        """A few people from influencer countries, to hear the outside view."""
        if n <= 0 or not self.influencers:
            return []
        candidates: dict[str, float] = {}
        for inf in self.influencers[:6]:
            if inf.code in countries():
                candidates[inf.code] = candidates.get(inf.code, 0) + inf.total_strength
            elif inf.code in blocs():
                members = [m for m in blocs()[inf.code].members if m in countries() and m not in self.spec.targets]
                big = sorted(members, key=lambda m: -countries()[m].workforce_m * countries()[m].gdp_pc_usd)[:3]
                for m in big:
                    candidates[m] = candidates.get(m, 0) + inf.total_strength / len(big)
        for t in self.spec.targets:
            candidates.pop(t, None)
        if not candidates:
            return []
        buyer_segs = [i for i, s in enumerate(segs) if s.is_buyer] or list(range(len(segs)))
        alloc = _allocate(n, candidates)
        out = []
        counter = start
        source_of = {}
        for inf in self.influencers:
            if inf.code in blocs():
                for m in blocs()[inf.code].members:
                    source_of.setdefault(m, inf.code)
            source_of.setdefault(inf.code, inf.code)
        for iso, k in alloc.items():
            for _ in range(k):
                counter += 1
                si = buyer_segs[int(self.rng.integers(len(buyer_segs)))]
                p = self._person(f"v{counter:05d}", iso, segs[si], si, voice=source_of.get(iso, iso))
                p.weight = 0.0
                out.append(p)
        return out
