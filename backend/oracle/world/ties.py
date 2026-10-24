"""Each country's measured ties to the rest of the world (built by scripts/build_ties.py).

Trade in goods (CEPII Gravity / BACI, 2019), trade in services (OECD-WTO BaTIS), friendships
(Meta Social Connectedness Index) and people living abroad (UN DESA migrant stock 2024).
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from ..config import load_json

# Which list feeds which channel, who in the target it concerns, and how to say it.
# sectors: the jobs whose work the tie is part of ("all" = everyone).
CHANNELS: dict[str, dict[str, Any]] = {
    "exports": {"list": "manufactured_exports", "sectors": ["manufacturing", "logistics"],
                "text": "{pct} of {tgt}'s manufactured exports go to {src}", "about": "Who buys the country's manufactured goods"},
    "commodities": {"list": "other_goods_exports", "sectors": ["agriculture"],
                    "text": "{pct} of {tgt}'s farm, mining and energy exports go to {src}", "about": "Who buys the country's farm, mining and energy goods"},
    "imports": {"list": "goods_imports", "sectors": ["retail", "manufacturing", "logistics"],
                "text": "{pct} of {tgt}'s imported goods come from {src}", "about": "Where the country's imported goods come from"},
    "tech_exports": {"list": "ict_services_exports", "sectors": ["software", "it_services", "telecom"],
                     "text": "{pct} of the IT and telecom services {tgt} sells abroad go to {src}", "about": "Who buys the country's IT and telecom services"},
    "finance_exports": {"list": "finance_services_exports", "sectors": ["finance"],
                        "text": "{pct} of the financial and insurance services {tgt} sells abroad go to {src}", "about": "Who buys the country's financial services"},
    "business_exports": {"list": "business_services_exports", "sectors": ["services"],
                         "text": "{pct} of the business services {tgt} sells abroad (consulting, R&D, back office) go to {src}", "about": "Who buys the country's business services"},
    "tourism": {"list": "travel_services_exports", "sectors": ["hospitality", "retail"],
                "text": "Visitors from {src} account for {pct} of what foreign visitors spend in {tgt}", "about": "Where the country's visitors come from"},
    "friends": {"list": "friendships", "sectors": ["all"],
                "text": "{pct} of {tgt}'s friendships abroad are with people in {src}", "about": "Where people's friends abroad live"},
    "diaspora": {"list": "emigrants", "sectors": ["all"],
                 "text": "{n} people from {tgt} live in {src} ({pct} of those living abroad)", "about": "Where people from the country who moved abroad live"},
    "regulation": {"list": None, "sectors": ["all"],
                   "text": "{tgt} is an EU member, so EU law applies directly.", "about": "Rules that apply across borders"},
}
SOURCES = {
    "exports": "CEPII Gravity (BACI), 2019", "commodities": "CEPII Gravity (BACI), 2019", "imports": "CEPII Gravity (BACI), 2019",
    "tech_exports": "OECD-WTO BaTIS", "finance_exports": "OECD-WTO BaTIS", "business_exports": "OECD-WTO BaTIS", "tourism": "OECD-WTO BaTIS",
    "friends": "Meta Social Connectedness Index", "diaspora": "UN migrant stock 2024", "regulation": "EU membership",
}


@lru_cache
def ties() -> dict[str, dict]:
    try:
        return load_json("ties.json")["countries"]
    except FileNotFoundError:
        return {}


@lru_cache
def friend_shares() -> dict[str, dict[str, float]]:
    try:
        return load_json("friendships.json")["share"]
    except FileNotFoundError:
        return {}


def of(iso: str) -> dict:
    return ties().get(iso, {})


def partners(iso: str, channel: str) -> list[tuple[str, float, dict]]:
    """(partner, share, extra) for a channel, largest first. Shares are of the list's total."""
    t = of(iso)
    name = CHANNELS[channel]["list"]
    if channel == "friends":
        f = t.get("friendships") or {}
        abroad = f.get("abroad_share") or 0
        return [(k, v / abroad, {}) for k, v in (f.get("abroad") or {}).items()] if abroad else []
    if channel == "diaspora":
        e = t.get("emigrants") or {}
        total = e.get("total") or 0
        return [(k, n / total, {"n": n}) for k, n in (e.get("by_country") or {}).items()] if total else []
    d = t.get(name) or {}
    return [(k, v, {"year": d.get("year")}) for k, v in (d.get("shares") or {}).items()]


def pair_note(iso: str, partner: str) -> str:
    f = (of(iso).get("pairs") or {}).get(partner) or {}
    bits = [w for k, w in (("border", "shares a border"), ("language", "shares an official language"), ("colonial", "colonial-era tie")) if f.get(k)]
    return f" ({', '.join(bits)})" if bits else ""


def friend_share(a: str, b: str) -> float | None:
    """Share of a's friendships that are with people in b (a itself included). None = no data."""
    s = friend_shares().get(a)
    if s is None:
        return None
    return s.get(b, 0.0)
