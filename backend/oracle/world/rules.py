"""Influence edges for every country, generated from rules.

Hand-written edges in influence.json are specific and win when they cover the same
(source, target, channel). These rules make sure every country, including the ones
nobody wrote edges for, has the outside forces that plainly shape it: US platforms
and capital, Chinese trade and lending, EU rules on anyone selling into Europe, and
regional hubs (Russia in Central Asia, the Gulf through remittances, France in the
CFA franc zone, India in South Asia, South Africa in SADC...).
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from .countries import blocs, countries

CFA = ["BEN", "BFA", "CIV", "GNB", "MLI", "NER", "SEN", "TGO", "CMR", "CAF", "TCD", "COG", "GNQ", "GAB"]
CENTRAL_ASIA = ["KAZ", "KGZ", "TJK", "TKM", "UZB"]
CAUCASUS_EAST = ["ARM", "AZE", "GEO", "BLR", "MDA"]
EU_NEIGHBOURS = ["NOR", "ISL", "CHE", "GBR", "UKR", "MDA", "GEO", "SRB", "BIH", "MNE", "MKD", "ALB", "XKX", "TUR", "MAR", "TUN", "DZA", "EGY", "ISR", "LBN", "JOR"]
CENTRAL_AMERICA_CARIB = ["GTM", "HND", "SLV", "NIC", "CRI", "PAN", "DOM", "HTI", "JAM", "CUB", "TTO", "BHS", "BRB", "BLZ"]
GULF_REMITTANCE = {"PAK": .45, "IND": .3, "BGD": .4, "NPL": .5, "LKA": .4, "PHL": .35, "EGY": .45, "JOR": .4, "LBN": .35, "YEM": .45, "SDN": .35, "KEN": .2, "UGA": .2, "ETH": .2}
PACIFIC = ["FJI", "PNG", "SLB", "VUT", "WSM", "TON", "KIR", "FSM", "MHL", "PLW", "NRU", "TUV"]
COMMONWEALTH_AFRICA = ["NGA", "GHA", "KEN", "UGA", "TZA", "ZAF", "ZMB", "ZWE", "MWI", "BWA", "NAM", "SLE", "GMB", "RWA", "MUS"]
GERMAN_SUPPLY = ["POL", "CZE", "HUN", "SVK", "AUT", "SVN", "ROU", "NLD", "BEL"]
SOUTH_ASIA_SMALL = ["NPL", "BTN", "LKA", "MDV", "BGD"]


def _edge(source: str, target: str, channel: str, strength: float, sectors: list[str], note: str) -> dict[str, Any]:
    return {"source": source, "target": target, "channel": channel, "strength": round(min(0.95, max(0.05, strength)), 2), "sectors": sectors, "note": note, "origin": "rule"}


@lru_cache
def generated_edges() -> list[dict[str, Any]]:
    cs = countries()
    eu = set(blocs()["EU"].members) if "EU" in blocs() else set()
    out: list[dict[str, Any]] = []
    for iso, c in cs.items():
        rich = c.gdp_pc_usd >= 20000
        region = c.region

        # EU law applies directly to members; reaches neighbours and anyone selling into Europe.
        if iso in eu:
            out.append(_edge("EU", iso, "regulation", 0.9, ["all"], "EU law applies directly (GDPR, AI Act, DSA, DMA, NIS2)."))
        elif iso in EU_NEIGHBOURS:
            out.append(_edge("EU", iso, "regulation", 0.55, ["software", "finance", "it_services", "manufacturing", "agriculture"], "Close trade ties mean EU standards and data rules shape what local firms must comply with."))
            out.append(_edge("EU", iso, "trade", 0.55, ["all"], "The EU is the main export market."))
        elif iso != "USA" and iso not in ("CHN", "RUS"):
            out.append(_edge("EU", iso, "regulation", 0.25 + 0.15 * c.digital, ["software", "it_services", "finance"], "Firms with European clients must meet GDPR, the EU AI Act and EU procurement rules."))

        # US technology platforms, capital and interest rates.
        if iso != "USA":
            if iso not in ("CHN", "RUS", "IRN", "PRK", "CUB"):
                out.append(_edge("USA", iso, "technology", 0.3 + 0.35 * c.internet_pct, ["software", "media", "all"], "US cloud, AI and software platforms set the defaults businesses build on."))
            if c.startups >= 0.35 and iso not in ("CHN", "RUS", "IRN", "PRK", "CUB"):
                out.append(_edge("USA", iso, "capital", 0.15 + 0.35 * c.startups, ["software", "finance"], "US venture capital and acquirers shape startup funding and go-to-market."))
            if not rich:
                out.append(_edge("USA", iso, "monetary", 0.35, ["finance", "all"], "US interest rates move the currency, import prices and the cost of capital."))
            if iso in CENTRAL_AMERICA_CARIB:
                out.append(_edge("USA", iso, "diaspora", 0.55, ["all"], "Remittances from the US and US demand dominate the economy."))

        # China: trade, lending and infrastructure.
        if iso != "CHN":
            share = {"Sub-Saharan Africa": 0.45, "East Asia & Pacific": 0.45, "Latin America & Caribbean": 0.35, "South Asia": 0.3}.get(region, 0.25)
            if iso in CENTRAL_ASIA:
                share = 0.5
            if rich:
                share -= 0.1
            out.append(_edge("CHN", iso, "trade", share, ["manufacturing", "retail", "energy", "telecom"], "China is a leading supplier of goods, components and infrastructure finance."))

        # Regional hubs.
        if iso in CENTRAL_ASIA or iso in CAUCASUS_EAST:
            out.append(_edge("RUS", iso, "geopolitics", 0.45, ["all"], "Russian trade, remittances and security ties weigh on policy and the economy."))
        if iso in GULF_REMITTANCE:
            out.append(_edge("GCC", iso, "diaspora", GULF_REMITTANCE[iso], ["all"], "Workers in the Gulf send home remittances that support households and spending."))
        if iso in CFA:
            out.append(_edge("FRA", iso, "monetary", 0.4, ["finance", "all"], "The CFA franc's euro peg links money and credit to France and the euro area."))
        if iso in COMMONWEALTH_AFRICA:
            out.append(_edge("GBR", iso, "diaspora", 0.25, ["finance", "education", "all"], "Legal, education and diaspora ties to the UK."))
        if iso in SOUTH_ASIA_SMALL:
            out.append(_edge("IND", iso, "trade", 0.5, ["all"], "India is the dominant trade partner and transit route."))
        if iso in blocs().get("SADC", type("x", (), {"members": []})).members and iso != "ZAF":
            out.append(_edge("ZAF", iso, "trade", 0.4, ["retail", "finance", "manufacturing"], "South African retailers, banks and supply chains operate across the region."))
        if iso in blocs().get("ECOWAS", type("x", (), {"members": []})).members and iso != "NGA":
            out.append(_edge("NGA", iso, "trade", 0.3, ["retail", "finance"], "Nigeria is the region's largest market and its fintechs expand across it."))
        if iso in blocs().get("MERCOSUR", type("x", (), {"members": []})).members and iso != "BRA":
            out.append(_edge("BRA", iso, "trade", 0.45, ["manufacturing", "agriculture", "retail"], "Brazil is the bloc's largest economy and trade partner."))
        if iso in PACIFIC:
            out.append(_edge("AUS", iso, "capital", 0.5, ["all"], "Australian aid, banks and trade anchor the economy."))
        if iso in GERMAN_SUPPLY:
            out.append(_edge("DEU", iso, "supply_chain", 0.5, ["manufacturing"], "A core supplier to German industry."))
        if region == "East Asia & Pacific" and iso not in ("JPN", "CHN") and not rich:
            out.append(_edge("JPN", iso, "capital", 0.3, ["manufacturing", "finance"], "Japanese investment and manufacturing networks."))
        if iso in ("ARG", "CHL", "COL", "PER", "ECU", "BOL", "URY", "PRY", "VEN") or iso in CENTRAL_AMERICA_CARIB:
            out.append(_edge("ESP", iso, "capital", 0.2, ["finance", "telecom"], "Spanish banks and telecoms are major investors."))
        if iso in ("EGY", "JOR", "PAK", "BHR", "OMN", "LBN", "SDN"):
            out.append(_edge("SAU", iso, "capital", 0.4, ["finance", "energy", "all"], "Saudi deposits, investment and oil credit support the economy."))
    return out
