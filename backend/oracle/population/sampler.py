"""Population builder: draws a realistic, weighted set of people from published statistics.

Who they are comes from data: which jobs exist and how many people do them, their gender and age
mix, earnings and spread, and digital and money facts (ILOSTAT, World Bank, Global Findex; see
realdata.py). Where no data exists, the attribute is left out rather than made up. The model
only adds names and a short story afterwards (see enrich.py).
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from statistics import NormalDist

import numpy as np

from ..scenario.models import Force, ScenarioSpec, Segment
from ..world.countries import Country, Occupation, blocs, company_types, countries, occupations
from ..world import ties as ties_mod
from ..world.influence import Influencer
from . import firms, realdata, views
from .headcount import _POP_AGES, occupation_headcount, seg_headcount
from .models import Exposure, Persona, Traits

# Seniority is part of the job's definition, not drawn at random.
EXECUTIVE_JOBS = {"founder_b2b_saas", "founder_d2c", "smb_owner", "ceo_enterprise", "cfo", "cto", "cio", "ciso", "vp_sales", "vc_investor"}
OWNER_OCCUPATIONS = {"founder_b2b_saas", "founder_d2c", "smb_owner", "freelancer"}
NON_WORKERS = {"student", "retiree", "homemaker", "unemployed"}
FACT_GROUPS = ("female", "male", "young", "older", "poorest40", "richest60", "out_lf", "in_lf")


def _logit(p: float) -> float:
    p = min(max(p, 1e-4), 1 - 1e-4)
    return math.log(p / (1 - p))


@dataclass
class _Occ:
    """Occupation used for sampling (catalogue entry or a custom one)."""

    id: str
    title: str
    isco: int
    sectors: list[str]
    company_types: list[str]
    buyer_role: str
    isco08: list[str] = field(default_factory=list)
    population: str | None = None

    @classmethod
    def of(cls, o: Occupation) -> "_Occ":
        return cls(o.id, o.title, o.isco, o.sectors, o.company_types, o.buyer_role, list(o.isco08), o.population)

    @property
    def major(self) -> int | None:
        return int(self.isco08[0][0]) if self.isco08 else None


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
        self.unknown_sizes: set[str] = set()
        self.spec = spec
        self.weighting = weighting
        self.influencers = influencers
        self.rng = np.random.default_rng(seed)
        # Own stream for survey matching, so people are the same with or without the survey pool.
        self.vrng = np.random.default_rng(None if seed is None else [seed, 7])
        self.occ = occupations()
        self.ctypes = company_types()

    # ---------- occupation choice ----------

    def _segment_pool(self, seg: Segment, country: Country) -> list[tuple[_Occ, float]]:
        if seg.occupations:
            pool = []
            for oid in seg.occupations:
                o = self.occ[oid]
                n = occupation_headcount(country.iso3, oid)
                pool.append((_Occ.of(o), n))
            if any(n is None for _, n in pool):
                # No real size for some job: pick among them evenly and say so.
                self.unknown_sizes.add(seg.name)
                return [(o, 1.0) for o, _ in pool]
            return [(o, max(n, 1e-9)) for o, n in pool]
        if seg.custom_occupation:
            title = seg.custom_occupation.strip().capitalize()
            sectors = self.spec.sectors[:2] or ["services"]
            ctypes = seg.company_types or ["smb", "midmarket", "enterprise"]
            self.unknown_sizes.add(seg.name)
            return [(_Occ(f"custom:{title.lower()}", title, 2, sectors, ctypes, "champion"), 1.0)]
        return self._general_pool(country)

    def _general_pool(self, country: Country) -> list[tuple[_Occ, float]]:
        """Representative adults in their real proportions: the employed by occupation group (each
        group voiced by the catalogue jobs in it), plus students, retirees, the unemployed and others
        outside the labour force."""
        iso = country.iso3
        by2, _ = realdata.employed_2digit(iso, country.workforce_m * 1e6, country.isco_shares())
        major_counts: dict[int, float] = {}
        for g, n in by2.items():
            major_counts[int(g[0])] = major_counts.get(int(g[0]), 0.0) + n
        jobs_in: dict[int, list[Occupation]] = {}
        for o in self.occ.values():
            if o.isco08:
                jobs_in.setdefault(int(o.isco08[0][0]), []).append(o)
        pool: list[tuple[_Occ, float]] = []
        for g, n in major_counts.items():
            members = jobs_in.get(g) or []
            if not members:
                continue
            sizes = [occupation_headcount(iso, m.id) for m in members]
            if all(x is not None for x in sizes) and sum(sizes) > 0:
                rel = [x / sum(sizes) for x in sizes]
            else:
                rel = [1 / len(members)] * len(members)  # which job title voices the group, not how big it is
            pool += [(_Occ.of(m), n * r) for m, r in zip(members, rel)]
        for o in self.occ.values():
            if o.population in ("students", "retirees", "unemployed", "outside_labour_force"):
                n, _ = realdata.population_count(iso, o.population)
                if n:
                    pool.append((_Occ.of(o), n))
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
        if o.id in EXECUTIVE_JOBS:
            return "executive"
        if o.id in NON_WORKERS:
            return "none"
        if o.major == 1:
            return "senior"
        return "staff"

    def _company(self, iso: str, o: _Occ, seg: Segment) -> tuple[str, list[int | None] | None]:
        """Company type and size class. Which types are possible comes from the job and the group
        (definitions); how likely each size is comes from data: the public-sector share of the job
        (ILOSTAT) and the share of its workers at each size of workplace or enterprise."""
        options = [c for c in (seg.company_types or []) if c in o.company_types] or o.company_types or ["smb"]
        if seg.company_types and not any(c in o.company_types for c in seg.company_types):
            options = seg.company_types
        fixed = [c for c in options if self.ctypes.get(c, {}).get("employees", [1, 1])[1] <= 1]
        if fixed and len(fixed) == len(options):  # not employed, or working alone: nothing to draw
            lo, hi = self.ctypes.get(fixed[0], {"employees": [0, 0]})["employees"]
            return fixed[0], ([1, 1] if hi == 1 else None)
        if "government" in options:
            others = [c for c in options if c != "government"]
            if not others:
                return "government", None
            share = firms.public_share(iso, o.isco08, realdata.oc2_employed(iso))  # None: job has no ISCO code
            if share is not None and self.rng.random() < share:
                return "government", None
            options = others
        types = {c: tuple(self.ctypes[c]["employees"]) for c in options if c in self.ctypes}
        cls = firms.classes_for(iso, o.major, types)
        total = sum(p for *_, p, _ in cls)
        if not cls or total <= 0:
            return options[0], None
        i = int(self.rng.choice(len(cls), p=np.array([c[2] for c in cls]) / total))
        lo, hi, _, t = cls[i]
        return t, [lo, hi]

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

    def _sex(self, iso: str, o: _Occ, seg: Segment, lo: int, hi: int) -> str:
        if seg.gender in ("woman", "man"):
            return seg.gender
        fs = realdata.female_share_job(iso, o.isco08) if o.isco08 else None
        if fs is None:
            fs = realdata.female_share(iso, lo, hi) or 0.5
        return "woman" if self.rng.random() < fs else "man"

    def _age(self, iso: str, o: _Occ, sex: str, seg: Segment) -> int:
        """Age band from the job's real age mix (ILOSTAT), year within it from the population shape."""
        lo, hi = seg.age_min or 15, seg.age_max or 99
        if o.population in _POP_AGES:
            plo, phi = _POP_AGES[o.population]
            lo, hi = max(lo, plo), min(hi, phi)
            bands = [((lo, hi), 1.0)]
        else:
            bands = realdata.job_age_band_weights(iso, o.major) or [((15, 64), 1.0)]
        cand = [((max(a, lo), min(b, hi)), w) for (a, b), w in bands if max(a, lo) <= min(b, hi) and w > 0]
        if not cand:
            cand = [((lo, max(lo, hi)), 1.0)]
        weights = []
        for (a, b), w in cand:
            ages = realdata.age_weights(iso, a, b, sex)
            band_total = realdata.people_aged(iso, a, b, sex) or 1.0
            weights += [(age, w * n / band_total) for age, n in ages]
        ws = np.array([max(x, 0.0) for _, x in weights]) + 1e-12
        return int(weights[int(self.rng.choice(len(weights), p=ws / ws.sum()))][0])

    def _income(self, iso: str, o: _Occ, c: Country) -> tuple[int | None, float | None, str]:
        """Yearly earnings (USD) from ILOSTAT means and the country's Gini spread; None when no data
        covers them (the self-employed, and people without a job)."""
        if o.population or not o.isco08:
            return None, None, "none" if o.id in NON_WORKERS else "unknown"
        mean, _ = realdata.monthly_earnings(iso, o.major, c.gdp_pc_usd)
        sigma, _ = realdata.income_sigma(iso)
        x = mean * 12 * float(self.rng.lognormal(-sigma**2 / 2, sigma))  # mean-preserving
        # Where they stand among all employees in the country.
        national, _ = realdata.monthly_earnings(iso, None, c.gdp_pc_usd)
        pct = NormalDist().cdf((math.log(max(x, 1) / (national * 12)) + sigma**2 / 2) / sigma)
        band = "bottom 40% of earners" if pct < 0.4 else "middle 40% of earners" if pct < 0.8 else "top 20% of earners" if pct < 0.95 else "top 5% of earners"
        return int(round(x, -2)), pct, band

    def _facts(self, iso: str, sex: str, age: int, pct: float | None, working: bool) -> dict[str, bool]:
        """Digital and money facts drawn from Global Findex rates for people like them."""
        out: dict[str, bool] = {}
        for fact, rates in (realdata.get(iso).get("findex") or {}).items():
            base = rates.get("all")
            if base is None:
                continue
            groups = ["female" if sex == "woman" else "male", "young" if age < 25 else "older", "in_lf" if working else "out_lf"]
            if pct is not None:
                groups.append("poorest40" if pct < 0.4 else "richest60")
            z = _logit(base) + sum(_logit(rates[g]) - _logit(base) for g in groups if g in rates)
            out[fact] = bool(self.rng.random() < 1 / (1 + math.exp(-z)))
        return out

    def _exposures(self, iso: str, sector: str, o: _Occ, ctype: str) -> list[Exposure]:
        """The measured ties of their country that touch their work (who buys what their industry
        sells, where its inputs come from) or everyone (EU law for EU members). Same for everyone in
        that line of work: no odds. Friendships and diaspora are country facts on the card instead."""
        out: list[Exposure] = []
        for inf in self.influencers:
            for e in inf.edges:
                if e.origin == "scenario" or e.target != iso or e.channel in ("friends", "diaspora"):
                    continue  # scenario forces are applied below, once, with their direction
                if not ("all" in e.sectors or sector in e.sectors or any(s_ in e.sectors for s_ in o.sectors)):
                    continue
                out.append(Exposure(source=e.source, source_name=inf.name, channel=e.channel, strength=e.strength, note=e.note, origin=e.origin))
        # Factors the user stated as true reach everyone they apply to: no odds, no guessed strength.
        for f in self.spec.forces:
            if not self._force_applies(f, iso, sector, o):
                continue
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
        out.sort(key=lambda x: (x.origin != "scenario", -x.strength))  # what the user stated always stays
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
        ctype, size = self._company(iso, o, seg)
        sector = self._sector(o)
        sex = self._sex(iso, o, seg, seg.age_min or 15, seg.age_max or 99)
        age = self._age(iso, o, sex, seg)
        income, pct, band = self._income(iso, o, c)
        working = o.id not in NON_WORKERS or o.id == "unemployed"
        facts = self._facts(iso, sex, age, pct, working)
        exposures = self._exposures(iso, sector, o, ctype) if voice is None else []
        m = views.match(
            iso, self.vrng, sex=sex, age=age, population=o.population, isco_major=o.major,
            self_employed=o.id in OWNER_OCCUPATIONS or o.population in ("employers", "own_account"), income_pct=pct,
        )
        return Persona(
            id=idx, country=iso, country_name=c.name, segment=seg.name, segment_index=seg_index,
            occupation_id=o.id, occupation=o.title, isco=o.isco, sector=sector, company_type=ctype,
            company_size=size, seniority=seniority, buyer_role=o.buyer_role, age=age, gender=sex,
            income_usd=income, income_band=band, traits=Traits(), facts=facts, exposures=exposures,
            views=m.answers if m else {}, views_from={"year": m.year, "source": m.source, "matched_on": m.matched_on} if m else {},
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
        sizes = {
            (iso, i): seg_headcount(iso, s)
            for iso in country_w
            for i, s in enumerate(segs)
            if not s.countries or iso in s.countries
        }
        missing = {segs[k[1]].name for k, v in sizes.items() if v is None and segs[k[1]].is_buyer}
        if self.weighting == "population" and missing:
            # Some group has no published size: weight groups equally rather than invent one.
            self.unknown_sizes |= missing
            self.weighting = "equal"
        if self.weighting == "population":
            # Automatic sizing: every (country, group) cell gets agents in proportion to the
            # square root of its real headcount. Big groups get more agents, small ones still
            # get enough to say something, and the weights below put everyone back at true scale.
            cell_heads = {k: v for k, v in sizes.items() if v is not None}
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
            # Equal: every country, and every group within it, counts the same.
            country_w = {iso: 1.0 for iso in country_w}
            country_alloc = _allocate(n, country_w)
            for iso, count in country_alloc.items():
                seg_alloc = _allocate(count, segs_in(iso))  # how many to simulate; weights below are equal
                for si, k in seg_alloc.items():
                    seg = segs[int(si)]
                    for _ in range(k):
                        counter += 1
                        people.append(self._person(f"p{counter:05d}", iso, seg, int(si)))

        # How many real people each agent stands for: the cell's estimated headcount
        # split across the agents sampled into it.
        cells = Counter((p.country, p.segment_index) for p in people)
        for p in people:
            h = sizes.get((p.country, p.segment_index))
            p.represents = round(h / cells[(p.country, p.segment_index)], 1) if h is not None else 0.0  # 0 = unknown

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
                sw = 1 / (len(segs_in(p.country)) or 1)
                p.weight = cw * sw / cells[(p.country, p.segment_index)]
            # Buyers and everyone else each sum to 1, as with population weighting.
            for group in (True, False):
                members = [p for p in people if p.is_buyer == group]
                total = sum(p.weight for p in members) or 1
                for p in members:
                    p.weight = round(p.weight / total, 10)

        people.extend(self._voices(influencer_voices, segs, counter))
        return people

    def _voices(self, n: int, segs: list[Segment], start: int) -> list[Persona]:
        """A few people from influencer countries, to hear the outside view."""
        if n <= 0:
            return []
        # Outside voices come from where the targets' friends abroad actually live (Meta SCI),
        # each target counted equally.
        candidates: dict[str, float] = {}
        for t in self.spec.targets:
            f = ties_mod.of(t).get("friendships") or {}
            abroad = f.get("abroad_share") or 0
            for code, share in (f.get("abroad") or {}).items():
                if code in countries() and code not in self.spec.targets and abroad:
                    candidates[code] = candidates.get(code, 0.0) + share / abroad / len(self.spec.targets)
        if not candidates:
            return []
        buyer_segs = [i for i, s in enumerate(segs) if s.is_buyer] or list(range(len(segs)))
        alloc = _allocate(n, candidates)
        out = []
        counter = start
        for iso, k in alloc.items():
            for _ in range(k):
                counter += 1
                si = buyer_segs[int(self.rng.integers(len(buyer_segs)))]
                p = self._person(f"v{counter:05d}", iso, segs[si], si, voice=iso)
                p.weight = 0.0
                out.append(p)
        return out
