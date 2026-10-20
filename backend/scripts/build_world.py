"""Build oracle/data/countries.json for every country from official open data.

Sources (fetched at build time, no keys):
- World Bank Open Data API: population, employment, GDP per person, internet use,
  sector employment shares, age structure, region, income level, capital coordinates.
- ILOSTAT SDMX API: employment by occupation (ISCO-08, or ISCO-88 where that is all
  a country reports), latest year since 2012.

Where a country has no ILO occupation survey, its occupation mix is predicted from a
least-squares model fitted on the countries that have one (sector shares and income).
Judgement indices (digital maturity, regulation, SaaS spend...) are derived from the
data with simple formulas; hand-tuned values in the curated file override them.

Run:  python scripts/build_world.py
"""

from __future__ import annotations

import csv
import io
import json
import math
import sys
import time
from datetime import date
from pathlib import Path

import httpx
import numpy as np
import pycountry

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "oracle" / "data"
CURATED = DATA / "countries_curated.json"
OUT = DATA / "countries.json"

WB = "https://api.worldbank.org/v2"
INDICATORS = {
    "population": "SP.POP.TOTL",
    "labor_force": "SL.TLF.TOTL.IN",
    "unemployment": "SL.UEM.TOTL.ZS",
    "gdp_pc": "NY.GDP.PCAP.CD",
    "internet": "IT.NET.USER.ZS",
    "agri": "SL.AGR.EMPL.ZS",
    "industry": "SL.IND.EMPL.ZS",
    "services": "SL.SRV.EMPL.ZS",
    "pop65": "SP.POP.65UP.TO.ZS",
    "pop014": "SP.POP.0014.TO.ZS",
    "urban": "SP.URB.TOTL.IN.ZS",
}

EU27 = ["AUT", "BEL", "BGR", "HRV", "CYP", "CZE", "DNK", "EST", "FIN", "FRA", "DEU", "GRC", "HUN", "IRL", "ITA", "LVA", "LTU",
        "LUX", "MLT", "NLD", "POL", "PRT", "ROU", "SVK", "SVN", "ESP", "SWE"]
BLOCS = {
    "EU": ("European Union", EU27, "Single market with shared regulation (GDPR, AI Act, DMA, DSA, NIS2, CSRD) whose rules reach well beyond its borders."),
    "ASEAN": ("ASEAN", ["BRN", "KHM", "IDN", "LAO", "MYS", "MMR", "PHL", "SGP", "THA", "VNM"], "Southeast Asian bloc with growing digital trade agreements."),
    "GCC": ("Gulf Cooperation Council", ["BHR", "KWT", "OMN", "QAT", "SAU", "ARE"], "Gulf economies with large sovereign funds and fast public-sector digitisation."),
    "MERCOSUR": ("Mercosur", ["ARG", "BRA", "PRY", "URY", "BOL"], "South American customs union."),
    "EAEU": ("Eurasian Economic Union", ["RUS", "BLR", "KAZ", "KGZ", "ARM"], "Russia-led customs union."),
    "AU": ("African Union", [], "All African states; the AfCFTA free trade area."),
    "ECOWAS": ("ECOWAS", ["BEN", "CPV", "CIV", "GMB", "GHA", "GIN", "GNB", "LBR", "NGA", "SEN", "SLE", "TGO"], "West African economic community."),
    "SADC": ("SADC", ["AGO", "BWA", "COM", "COD", "SWZ", "LSO", "MDG", "MWI", "MUS", "MOZ", "NAM", "SYC", "ZAF", "TZA", "ZMB", "ZWE"], "Southern African development community."),
    "EAC": ("East African Community", ["BDI", "COD", "KEN", "RWA", "SSD", "TZA", "UGA", "SOM"], "East African customs union."),
    "USMCA": ("USMCA", ["USA", "CAN", "MEX"], "North American trade agreement."),
    "SAARC": ("South Asia (SAARC)", ["AFG", "BGD", "BTN", "IND", "MDV", "NPL", "PAK", "LKA"], "South Asian association."),
    "BRICS": ("BRICS", ["BRA", "RUS", "IND", "CHN", "ZAF", "EGY", "ETH", "IRN", "ARE", "IDN"], "Emerging-economy bloc pushing alternatives in payments and trade."),
}
OECD = ["AUS", "AUT", "BEL", "CAN", "CHL", "COL", "CRI", "CZE", "DNK", "EST", "FIN", "FRA", "DEU", "GRC", "HUN", "ISL", "IRL", "ISR",
        "ITA", "JPN", "KOR", "LVA", "LTU", "LUX", "MEX", "NLD", "NZL", "NOR", "POL", "PRT", "SVK", "SVN", "ESP", "SWE", "CHE", "TUR",
        "GBR", "USA"]
G7 = ["CAN", "FRA", "DEU", "ITA", "JPN", "GBR", "USA"]

# Rough share of adults who can work in English (judgement; default 0.12).
ENGLISH = {
    "USA": .95, "GBR": .98, "IRL": .99, "AUS": .97, "NZL": .98, "CAN": .86, "SGP": .85, "PHL": .6, "IND": .12, "PAK": .1, "NGA": .55,
    "KEN": .5, "GHA": .5, "UGA": .35, "ZAF": .6, "ZWE": .45, "ZMB": .4, "BWA": .5, "NAM": .45, "MYS": .6, "NLD": .9, "SWE": .89,
    "NOR": .9, "DNK": .86, "FIN": .75, "ISR": .85, "ARE": .8, "MLT": .88, "CYP": .75, "JAM": .95, "TTO": .95, "BHS": .97, "BRB": .97,
    "LKA": .25, "BGD": .08, "RWA": .3, "TZA": .2, "DEU": .56, "AUT": .73, "BEL": .6, "CHE": .65, "LUX": .7, "PRT": .45, "POL": .37,
}

# Which curated country's name pool suits a country without its own (mock mode only;
# real models invent culturally fitting names themselves).
NAME_DONOR_BY_REGION = {
    "North America": "USA", "Latin America & Caribbean": "MEX", "Europe & Central Asia": "DEU",
    "Middle East & North Africa": "EGY", "Middle East, North Africa, Afghanistan & Pakistan": "EGY",
    "South Asia": "IND", "East Asia & Pacific": "CHN", "Sub-Saharan Africa": "NGA",
}
NAME_DONOR = {
    "BRA": "BRA", "PRT": "BRA", "AGO": "BRA", "MOZ": "BRA", "AUT": "DEU", "LUX": "FRA", "BEL": "NLD", "FRA": "FRA", "MCO": "FRA",
    "CIV": "FRA", "SEN": "FRA", "CMR": "FRA", "MLI": "FRA", "BFA": "FRA", "NER": "FRA", "TCD": "FRA", "GAB": "FRA", "COG": "FRA",
    "COD": "FRA", "GIN": "FRA", "BEN": "FRA", "TGO": "FRA", "MDG": "FRA", "HTI": "FRA", "RUS": "RUS", "BLR": "RUS", "UKR": "RUS",
    "KAZ": "RUS", "KGZ": "RUS", "UZB": "TUR", "TKM": "TUR", "AZE": "TUR", "TUR": "TUR", "TJK": "RUS", "MDA": "RUS", "ARM": "RUS",
    "GEO": "RUS", "POL": "POL", "CZE": "POL", "SVK": "POL", "HRV": "POL", "SRB": "POL", "SVN": "POL", "BIH": "POL", "MNE": "POL",
    "MKD": "POL", "BGR": "RUS", "ROU": "ITA", "HUN": "POL", "LTU": "POL", "LVA": "POL", "EST": "SWE", "FIN": "SWE", "SWE": "SWE",
    "NOR": "NOR", "DNK": "NOR", "ISL": "NOR", "ITA": "ITA", "MLT": "ITA", "GRC": "ITA", "CYP": "ITA", "ALB": "ITA", "ESP": "ESP",
    "IRL": "IRL", "GBR": "GBR", "AUS": "AUS", "NZL": "AUS", "JPN": "JPN", "KOR": "KOR", "PRK": "KOR", "VNM": "VNM", "THA": "VNM",
    "KHM": "VNM", "LAO": "VNM", "MMR": "VNM", "IDN": "IDN", "MYS": "MYS", "BRN": "MYS", "PHL": "PHL", "SGP": "SGP", "PAK": "PAK",
    "AFG": "PAK", "BGD": "BGD", "NPL": "IND", "LKA": "IND", "IRN": "TUR", "ISR": "ISR", "KEN": "KEN", "TZA": "KEN", "UGA": "KEN",
    "RWA": "KEN", "ETH": "KEN", "ZAF": "ZAF", "ZWE": "ZAF", "BWA": "ZAF", "NAM": "ZAF", "ZMB": "ZAF", "MWI": "ZAF", "SAU": "SAU",
    "ARE": "ARE", "QAT": "SAU", "KWT": "SAU", "BHR": "SAU", "OMN": "SAU", "CAN": "CAN", "ARG": "ARG", "URY": "ARG", "CHL": "CHL",
    "COL": "COL", "VEN": "COL", "ECU": "COL", "PER": "COL", "BOL": "COL", "PRY": "ARG", "CHN": "CHN", "HKG": "CHN", "MAC": "CHN",
    "TWN": "CHN", "MNG": "CHN",
}

ALIASES_EXTRA = {
    "USA": ["us", "usa", "america", "the us", "the states", "united states of america"], "GBR": ["uk", "britain", "great britain", "england", "gb", "united kingdom"],
    "KOR": ["south korea", "korea", "republic of korea"], "PRK": ["north korea"], "RUS": ["russia"], "IRN": ["iran"], "VNM": ["vietnam"],
    "LAO": ["laos"], "SYR": ["syria"], "VEN": ["venezuela"], "EGY": ["egypt"], "COD": ["drc", "dr congo", "congo kinshasa", "democratic republic of the congo"],
    "COG": ["congo", "republic of the congo", "congo brazzaville"], "CIV": ["ivory coast", "cote d'ivoire"], "TUR": ["turkey", "turkiye"],
    "CZE": ["czech republic", "czechia"], "SVK": ["slovakia"], "KGZ": ["kyrgyzstan"], "TZA": ["tanzania"], "YEM": ["yemen"],
    "ARE": ["uae", "emirates", "dubai", "abu dhabi"], "SAU": ["saudi", "ksa"], "HKG": ["hong kong"], "MAC": ["macau", "macao"],
    "TWN": ["taiwan"], "BHS": ["bahamas"], "GMB": ["gambia"], "MKD": ["north macedonia", "macedonia"], "MDA": ["moldova"],
    "BOL": ["bolivia"], "CHN": ["china", "prc", "mainland china"], "NLD": ["netherlands", "holland"], "PHL": ["philippines"],
    "STP": ["sao tome"], "FSM": ["micronesia"], "BRN": ["brunei"], "SWZ": ["eswatini", "swaziland"], "CPV": ["cape verde"],
    "TLS": ["east timor", "timor leste"], "PSE": ["palestine", "west bank and gaza"], "KNA": ["st kitts"], "LCA": ["st lucia"],
    "VCT": ["st vincent"], "BRA": ["brasil"], "MEX": ["mexico"], "DEU": ["deutschland"], "ESP": ["espana"], "IND": ["bharat"],
}


# Economies the World Bank does not cover. Figures from national statistics, rounded.
SUPPLEMENT = {
    "TWN": {
        "name": "Taiwan", "region": "East Asia & Pacific", "income": "High income", "capital": "Taipei", "lon": 121.56, "lat": 25.04,
        "population": 23.4e6, "labor_force": 11.9e6, "unemployment": 3.4, "gdp_pc": 33000, "internet": 90.0,
        "agri": 4.6, "industry": 35.0, "services": 60.4, "pop65": 18.4, "pop014": 11.6,
        "source": "DGBAS Taiwan national statistics (approximate, 2024)",
    },
}


def get(url: str, **params) -> httpx.Response:
    for attempt in range(4):
        try:
            r = httpx.get(url, params=params, timeout=120, follow_redirects=True)
            r.raise_for_status()
            return r
        except Exception as exc:  # noqa: BLE001
            print(f"  retry {attempt + 1}: {exc}", file=sys.stderr)
            time.sleep(2 + attempt * 3)
    raise RuntimeError(f"failed: {url}")


def wb_countries() -> dict[str, dict]:
    rows = get(f"{WB}/country", format="json", per_page=400).json()[1]
    out = {}
    for c in rows:
        if c["region"]["id"] == "NA":  # aggregates
            continue
        out[c["id"]] = {
            "iso3": c["id"],
            "name": c["name"],
            "region": c["region"]["value"].strip(),
            "income": c["incomeLevel"]["value"],
            "capital": c["capitalCity"],
            "lon": float(c["longitude"]) if c["longitude"] else None,
            "lat": float(c["latitude"]) if c["latitude"] else None,
        }
    return out


def wb_indicator(code: str) -> dict[str, tuple[float, int]]:
    rows = get(f"{WB}/country/all/indicator/{code}", format="json", mrnev=1, per_page=500).json()
    out = {}
    for r in rows[1] or []:
        if r["value"] is not None and r["countryiso3code"]:
            out[r["countryiso3code"]] = (float(r["value"]), int(r["date"]))
    return out


def ilo_occupations() -> dict[str, dict]:
    """Latest ISCO major-group employment shares per country."""
    groups = [f"OCU_ISCO08_{i}" for i in range(1, 10)] + [f"OCU_ISCO88_{i}" for i in range(1, 10)]
    url = (
        "https://sdmx.ilo.org/rest/data/ILO,DF_EMP_TEMP_SEX_OCU_NB,1.0/"
        f".A..SEX_T.{'+'.join(groups)}"
    )
    r = httpx.get(
        url, params={"startPeriod": "2012", "dimensionAtObservation": "AllDimensions"},
        headers={"Accept": "application/vnd.sdmx.data+csv;version=1.0.0"}, timeout=600,
    )
    r.raise_for_status()
    data: dict[tuple[str, str, int], dict[int, float]] = {}
    for row in csv.DictReader(io.StringIO(r.text)):
        try:
            v = float(row["OBS_VALUE"])
        except (TypeError, ValueError):
            continue
        ocu = row["OCU"]
        scheme = "08" if "ISCO08" in ocu else "88"
        g = int(ocu.rsplit("_", 1)[1])
        data.setdefault((row["REF_AREA"], scheme, int(row["TIME_PERIOD"])), {})[g] = v
    best: dict[str, dict] = {}
    for (iso, scheme, year), vals in data.items():
        if len(vals) < 9:
            continue
        cur = best.get(iso)
        # Prefer ISCO-08, then the latest year.
        key = (scheme == "08", year)
        if cur is None or key > (cur["scheme"] == "08", cur["year"]):
            total = sum(vals.values())
            best[iso] = {"scheme": scheme, "year": year, "shares": [vals[g] / total for g in range(1, 10)]}
    return best


def clip(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def main() -> None:
    print("World Bank: countries")
    meta = wb_countries()
    ind: dict[str, dict] = {}
    for key, code in INDICATORS.items():
        print(f"World Bank: {code}")
        ind[key] = wb_indicator(code)
    for iso, sup in SUPPLEMENT.items():
        meta[iso] = {k: sup[k] for k in ("name", "region", "income", "capital", "lon", "lat")} | {"iso3": iso}
        for key in INDICATORS:
            if key in sup:
                ind[key][iso] = (sup[key], 2024)
    print("ILOSTAT: occupations (this can take a minute)")
    occ = ilo_occupations()
    print(f"  {len(occ)} countries with occupation surveys")
    curated = {c["iso3"]: c for c in json.loads(CURATED.read_text(encoding="utf-8"))["countries"]}

    def val(key, iso, default=None):
        v = ind[key].get(iso)
        return v[0] if v else default

    # Fit occupation shares from sector shares and income where ILO data exists.
    feats, targets = [], []
    for iso, o in occ.items():
        a, i_, s, g = val("agri", iso), val("industry", iso), val("services", iso), val("gdp_pc", iso)
        if None in (a, i_, s, g):
            continue
        feats.append([1, a / 100, i_ / 100, math.log(g)])
        targets.append(o["shares"])
    X, Y = np.array(feats), np.array(targets)
    coef, *_ = np.linalg.lstsq(X, Y, rcond=None)
    print(f"  occupation model fitted on {len(X)} countries")

    # Median age from the age structure, fitted on the curated countries.
    ma_x, ma_y = [], []
    for iso, c in curated.items():
        p65, p014 = val("pop65", iso), val("pop014", iso)
        if p65 is not None and p014 is not None:
            ma_x.append([1, p65, p014])
            ma_y.append(c["median_age"])
    age_coef, *_ = np.linalg.lstsq(np.array(ma_x), np.array(ma_y), rcond=None)

    bloc_members = {k: set(v[1]) for k, v in BLOCS.items()}
    africa = {iso for iso, m in meta.items() if m["region"] == "Sub-Saharan Africa"} | {"EGY", "LBY", "TUN", "DZA", "MAR"}
    bloc_members["AU"] = africa

    countries = []
    years = {}
    for iso, m in sorted(meta.items(), key=lambda kv: kv[1]["name"]):
        pop = val("population", iso)
        gdp = val("gdp_pc", iso)
        if pop is None or gdp is None or pop < 50_000:
            continue
        lf = val("labor_force", iso)
        unemp = val("unemployment", iso, 6.0)
        workforce = (lf * (1 - unemp / 100)) if lf else pop * 0.42
        internet = val("internet", iso, 50.0) / 100
        agri, indus, serv = val("agri", iso), val("industry", iso), val("services", iso)
        if iso in occ:
            isco = occ[iso]["shares"]
            isco_source = f"ILOSTAT ISCO-{occ[iso]['scheme']} {occ[iso]['year']}"
        elif None not in (agri, indus, serv):
            pred = np.array([1, agri / 100, indus / 100, math.log(gdp)]) @ coef
            pred = np.clip(pred, 0.005, None)
            isco = list(pred / pred.sum())
            isco_source = "modelled from sector employment and income"
        else:
            isco = [0.05, 0.12, 0.1, 0.07, 0.2, 0.1, 0.13, 0.09, 0.14]
            isco_source = "regional default"
        p65, p014 = val("pop65", iso), val("pop014", iso)
        median_age = float(np.array([1, p65, p014]) @ age_coef) if p65 is not None and p014 is not None else 30.0

        f = clip((math.log(max(gdp, 300)) - math.log(800)) / (math.log(80000) - math.log(800)))
        is_eu = iso in bloc_members["EU"]
        derived = {
            "digital": round(clip(0.1 + 0.6 * internet + 0.3 * f), 2),
            "regulation": round(0.88 if is_eu else clip(0.3 + 0.35 * f + (0.15 if iso in OECD else 0)), 2),
            "saas": round(clip(f ** 1.25), 2),
            "startups": round(clip(0.25 + 0.45 * f + 0.15 * internet), 2),
            "price_sensitivity": round(clip(0.95 - 0.65 * f), 2),
            "tech_trust": round(clip(0.8 - 0.25 * f + 0.05 * internet), 2),
        }
        blocs = [b for b, mem in bloc_members.items() if iso in mem]
        if iso in OECD:
            blocs.append("OECD")
        if iso in G7:
            blocs.append("G7")
        cur = curated.get(iso, {})
        names = cur.get("names") or curated[NAME_DONOR.get(iso) or NAME_DONOR_BY_REGION.get(m["region"], "USA")]["names"]
        num = pycountry.countries.get(alpha_3=iso)
        aliases = {m["name"].lower()}
        if num:
            aliases |= {num.name.lower(), getattr(num, "common_name", num.name).lower(), getattr(num, "official_name", num.name).lower()}
        aliases |= set(ALIASES_EXTRA.get(iso, []))
        aliases |= set(cur.get("aliases", []))
        country = {
            "iso3": iso,
            "iso_num": num.numeric if num else None,
            "name": cur.get("name") or m["name"],
            "aliases": sorted(a for a in aliases if a),
            "region": m["region"],
            "income": m["income"],
            "capital": m["capital"],
            "anchor": [m["lon"], m["lat"]] if m["lon"] is not None else None,
            "blocs": sorted(set(blocs)),
            "currency": cur.get("currency", ""),
            "languages": cur.get("languages", []),
            "population_m": round(pop / 1e6, 3),
            "workforce_m": round(workforce / 1e6, 3),
            "gdp_pc_usd": round(gdp),
            "internet_pct": round(internet, 3),
            "english": cur.get("english", ENGLISH.get(iso, 0.12)),
            "median_age": round(cur.get("median_age", median_age), 1),
            "pop65": round(p65 / 100, 3) if p65 is not None else None,
            "pop014": round(p014 / 100, 3) if p014 is not None else None,
            "sector_shares": [round(x / 100, 3) if x is not None else None for x in (agri, indus, serv)],
            "isco": [round(x, 4) for x in isco],
            "isco_source": isco_source,
            "names": names,
            "curated": bool(cur),
        }
        for k, v in derived.items():
            country[k] = cur.get(k, v)
        countries.append(country)
        years[iso] = {k: ind[k][iso][1] for k in INDICATORS if iso in ind[k]}

    out = {
        "_meta": {
            "built": date.today().isoformat(),
            "sources": [
                "World Bank Open Data (api.worldbank.org): SP.POP.TOTL, SL.TLF.TOTL.IN, SL.UEM.TOTL.ZS, NY.GDP.PCAP.CD, IT.NET.USER.ZS, SL.AGR/IND/SRV.EMPL.ZS, SP.POP.65UP.TO.ZS, SP.POP.0014.TO.ZS",
                "ILOSTAT (sdmx.ilo.org): DF_EMP_TEMP_SEX_OCU_NB, employment by occupation, both sexes, latest year since 2012",
            ],
            "note": "Each figure is the most recent value the source has. Occupation shares come from ILO surveys where they exist and from a model fitted on those surveys elsewhere (see isco_source). Indices (digital, regulation, saas, startups, price_sensitivity, tech_trust) are judgements derived from the data, with hand-tuned values for 39 major markets.",
            "isco_order": ["managers", "professionals", "technicians", "clerical", "service_sales", "skilled_agri", "craft", "operators", "elementary"],
            "count": len(countries),
        },
        "countries": countries,
        "blocs": [{"id": k, "name": v[0], "members": sorted(m for m in bloc_members[k] if any(c["iso3"] == m for c in countries)), "description": v[2]} for k, v in BLOCS.items()],
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Wrote {len(countries)} countries to {OUT}")
    print(f"  occupations from surveys: {sum(1 for c in countries if c['isco_source'].startswith('ILOSTAT'))}")


if __name__ == "__main__":
    main()
