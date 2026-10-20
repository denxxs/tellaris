"""Country, bloc and occupation reference data."""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache
from typing import Any

from pydantic import BaseModel

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
    name: str
    aliases: list[str]
    region: str
    blocs: list[str]
    currency: str
    languages: list[str]
    population_m: float
    workforce_m: float
    gdp_pc_usd: float
    internet_pct: float
    english: float
    median_age: float
    isco: list[float]
    digital: float
    regulation: float
    saas: float
    startups: float
    price_sensitivity: float
    tech_trust: float
    names: dict[str, list[str]]

    def isco_shares(self) -> dict[int, float]:
        total = sum(self.isco) or 1.0
        return {i + 1: v / total for i, v in enumerate(self.isco)}

    def summary(self) -> dict[str, Any]:
        return self.model_dump(exclude={"names", "aliases", "isco"})


class Bloc(BaseModel):
    id: str
    name: str
    members: list[str]
    description: str


class Occupation(BaseModel):
    id: str
    title: str
    isco: int
    weight: float
    sectors: list[str]
    company_types: list[str]
    income_mult: float
    tech: float
    buyer_role: str


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9 ]+", " ", text.lower()).strip()


@lru_cache
def countries() -> dict[str, Country]:
    data = load_json("countries.json")
    return {c["iso3"]: Country.model_validate(c) for c in data["countries"]}


@lru_cache
def blocs() -> dict[str, Bloc]:
    data = load_json("countries.json")
    return {b["id"]: Bloc.model_validate(b) for b in data["blocs"]}


@lru_cache
def occupations() -> dict[str, Occupation]:
    data = load_json("occupations.json")
    return {o["id"]: Occupation.model_validate(o) for o in data["occupations"]}


@lru_cache
def company_types() -> dict[str, dict[str, Any]]:
    return load_json("occupations.json")["company_types"]


@lru_cache
def _alias_index() -> dict[str, str]:
    index: dict[str, str] = {}
    for iso, c in countries().items():
        index[_norm(iso)] = iso
        index[_norm(c.name)] = iso
        for a in c.aliases:
            index[_norm(a)] = iso
    for bid, b in blocs().items():
        index[_norm(bid)] = bid
        index[_norm(b.name)] = bid
    index["europe"] = "EU"
    index["european union"] = "EU"
    return index


def resolve(name: str) -> str | None:
    """Map a country/bloc name, alias or code to its ISO3 / bloc id."""
    if not name:
        return None
    key = _norm(name)
    idx = _alias_index()
    if key in idx:
        return idx[key]
    if len(key) == 2:
        two = {
            "us": "USA", "uk": "GBR", "gb": "GBR", "in": "IND", "de": "DEU", "fr": "FRA", "cn": "CHN",
            "jp": "JPN", "br": "BRA", "ca": "CAN", "au": "AUS", "sg": "SGP", "ae": "ARE", "mx": "MEX",
            "es": "ESP", "it": "ITA", "nl": "NLD", "se": "SWE", "pl": "POL", "ch": "CHE", "kr": "KOR",
            "id": "IDN", "vn": "VNM", "ph": "PHL", "za": "ZAF", "ng": "NGA", "ke": "KEN", "eg": "EGY",
            "sa": "SAU", "il": "ISR", "tr": "TUR", "ru": "RUS", "ie": "IRL", "no": "NOR", "ar": "ARG",
            "cl": "CHL", "co": "COL", "my": "MYS", "pk": "PAK", "bd": "BGD", "eu": "EU",
        }
        return two.get(key)
    return None


def find_mentions(text: str) -> list[str]:
    """Countries and blocs mentioned in free text, in order of appearance."""
    norm = f" {_norm(text)} "
    hits: list[tuple[int, str]] = []
    for alias, code in _alias_index().items():
        if len(alias) < 3 and alias not in {"us", "uk", "eu"}:
            continue
        pos = norm.find(f" {alias} ")
        if pos >= 0:
            hits.append((pos, code))
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
