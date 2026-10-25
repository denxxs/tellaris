"""Country, bloc and occupation reference data (every country, from World Bank + ILO)."""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache
from typing import Any

from pydantic import BaseModel, Field

from ..config import load_json

ISCO_GROUPS = [
    "managers",
    "professionals",
    "technicians",
    "clerical",
    "service_sales",
    "skilled_agri",
    "craft",
    "operators",
    "elementary",
]


class Country(BaseModel):
    iso3: str
    iso_num: str | None = None
    name: str
    aliases: list[str]
    region: str
    income: str = ""
    capital: str = ""
    anchor: list[float] | None = None
    blocs: list[str]
    population_m: float
    workforce_m: float | None = None  # None: no labour-force data, so the country can't be simulated
    gdp_pc_usd: float
    internet_pct: float | None = None
    pop65: float | None = None
    pop014: float | None = None
    sector_shares: list[float | None] = Field(default_factory=list)
    isco: list[float] | None = None
    isco_source: str = ""
    names: dict[str, list[str]]
    curated: bool = False

    @property
    def simulatable(self) -> bool:
        return self.workforce_m is not None and self.isco is not None

    def isco_shares(self) -> dict[int, float]:
        if not self.isco:
            return {}
        total = sum(self.isco) or 1.0
        return {i + 1: v / total for i, v in enumerate(self.isco)}

    @property
    def adults_m(self) -> float | None:
        """People aged 15+, in millions (None when the age structure isn't published)."""
        return self.population_m * (1 - self.pop014) if self.pop014 is not None else None

    def summary(self) -> dict[str, Any]:
        return self.model_dump(exclude={"names", "aliases"})


class Bloc(BaseModel):
    id: str
    name: str
    members: list[str]
    description: str


class Occupation(BaseModel):
    id: str
    title: str
    isco: int
    sectors: list[str]
    company_types: list[str]
    buyer_role: str
    isco08: list[str] = Field(default_factory=list)  # official ISCO-08 unit groups
    population: str | None = None  # employers | own_account | students | retirees | unemployed | outside_labour_force | unknown


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9 ]+", " ", text.lower()).strip()


@lru_cache
def _world() -> dict[str, Any]:
    return load_json("countries.json")


@lru_cache
def countries() -> dict[str, Country]:
    return {c["iso3"]: Country.model_validate(c) for c in _world()["countries"]}


@lru_cache
def blocs() -> dict[str, Bloc]:
    return {b["id"]: Bloc.model_validate(b) for b in _world()["blocs"]}


@lru_cache
def occupations() -> dict[str, Occupation]:
    data = load_json("occupations.json")
    return {o["id"]: Occupation.model_validate(o) for o in data["occupations"]}


@lru_cache
def company_types() -> dict[str, dict[str, Any]]:
    return load_json("occupations.json")["company_types"]


# Words that are also country aliases but usually mean something else in a sentence.
_AMBIGUOUS = {"us", "chad", "jordan", "georgia", "turkey", "niger", "guinea", "india ink", "china", "japan"}
_CASE_SENSITIVE_CODES = {"US": "USA", "UK": "GBR", "EU": "EU", "UAE": "ARE", "USA": "USA", "KSA": "SAU", "DRC": "COD"}


@lru_cache
def _alias_index() -> dict[str, str]:
    index: dict[str, str] = {}
    for iso, c in countries().items():
        index[_norm(iso)] = iso
        index[_norm(c.name)] = iso
        for a in c.aliases:
            n = _norm(a)
            if n:
                index.setdefault(n, iso)
    for bid, b in blocs().items():
        index[_norm(bid)] = bid
        index[_norm(b.name)] = bid
    index.update({"europe": "EU", "european union": "EU", "the eu": "EU", "gulf": "GCC", "the gulf": "GCC", "southeast asia": "ASEAN"})
    return index


def resolve(name: str) -> str | None:
    """Map a country/bloc name, alias or code to its ISO3 / bloc id."""
    if not name:
        return None
    raw = name.strip()
    if raw.upper() in countries() or raw.upper() in blocs():
        return raw.upper()
    key = _norm(raw)
    idx = _alias_index()
    if key in idx:
        return idx[key]
    if raw.upper() in _CASE_SENSITIVE_CODES:
        return _CASE_SENSITIVE_CODES[raw.upper()]
    if len(key) == 2:
        import pycountry

        try:
            c = pycountry.countries.get(alpha_2=key.upper())
            if c and c.alpha_3 in countries():
                return c.alpha_3
        except (KeyError, LookupError):
            pass
    return None


def find_mentions(text: str) -> list[str]:
    """Countries and blocs mentioned in free text, in order of appearance.

    Longest names match first and claim their words, so "South Africa" never also
    counts as "Africa", and short codes only count in capitals ("US", not "us")."""
    norm = f" {_norm(text)} "
    taken = [False] * len(norm)
    hits: list[tuple[int, str]] = []
    for alias, code in sorted(_alias_index().items(), key=lambda kv: -len(kv[0])):
        if len(alias) < 4 or alias in _AMBIGUOUS:
            continue
        start = 0
        needle = f" {alias} "
        while (pos := norm.find(needle, start)) >= 0:
            span = range(pos + 1, pos + 1 + len(alias))
            if not any(taken[i] for i in span):
                for i in span:
                    taken[i] = True
                hits.append((pos, code))
            start = pos + 1
    # Short codes and ambiguous names only when written as a proper noun.
    for m in re.finditer(r"\b(US|USA|UK|EU|UAE|KSA|DRC)\b", text):
        hits.append((int(m.start() * len(norm) / max(len(text), 1)), _CASE_SENSITIVE_CODES[m.group(1)]))
    for word in ("China", "Japan", "Jordan", "Chad", "Georgia", "Niger", "Guinea", "Turkey"):
        for m in re.finditer(rf"\b{word}\b", text):
            code = _alias_index().get(_norm(word))
            if code:
                hits.append((int(m.start() * len(norm) / max(len(text), 1)), code))
    seen: list[str] = []
    for _, code in sorted(hits):
        if code not in seen:
            seen.append(code)
    return seen


def expand_codes(codes: list[str]) -> list[str]:
    """Turn bloc ids into member countries; keep countries; drop unknowns."""
    out: list[str] = []
    for code in codes:
        if code in countries():
            out.append(code)
        elif code in blocs():
            out.extend(m for m in blocs()[code].members if m in countries())
    return list(dict.fromkeys(out))


def country_blocs(iso: str) -> list[str]:
    return [bid for bid, b in blocs().items() if iso in b.members]


def global_sample(depth: str = "quick") -> list[str]:
    """Countries for a whole-world run: every region represented, then the largest by adults
    until most of the world's adults are covered. quick = 16 countries, deep = 32."""
    cs = sorted((c for c in countries().values() if c.simulatable and c.adults_m), key=lambda c: -c.adults_m)
    limit = 32 if depth == "deep" else 20
    per_region = 3 if depth == "deep" else 1
    eu_west = set(blocs()["EU"].members) | {"GBR", "CHE", "NOR"} if "EU" in blocs() else {"GBR"}

    def area(c: Country) -> str:
        # The World Bank puts Western Europe and Central Asia in one region; treat them apart.
        if c.region.startswith("Europe"):
            return "Western Europe" if c.iso3 in eu_west else "Eastern Europe and Central Asia"
        return c.region

    big = [c for c in cs if c.adults_m >= 3]  # regional representatives must be sizeable
    picked: list[str] = []
    for region in sorted({area(c) for c in big}):
        picked += [c.iso3 for c in big if area(c) == region][:per_region]
    for c in cs:
        if len(picked) >= limit:
            break
        if c.iso3 not in picked:
            picked.append(c.iso3)
    return picked[:limit] if len(picked) > limit else picked


def world_coverage(isos: list[str]) -> float:
    """Share of the world's adults living in these countries."""
    cs = countries()
    total = sum(c.adults_m or 0 for c in cs.values()) or 1
    return sum(cs[i].adults_m or 0 for i in isos if i in cs) / total
