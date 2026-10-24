"""Build oracle/data/ties.json: each country's measured ties to the rest of the world.

Sources (all free to reuse, downloaded into backend/var/datasets/ by hand or with curl):
- Trade in goods, 2019 (last full year before COVID): CEPII Gravity V202211, BACI flows.
  Conte, M., P. Cotterlaz and T. Mayer (2022), "The CEPII Gravity database", CEPII WP 2022-05.
  gravity/Gravity_csv_V202211.zip from https://www.cepii.fr/DATA_DOWNLOAD/gravity/data/
  Licence: Etalab Open Licence 2.0. Also gives shared borders, official languages and colonial ties.
- Trade in services: OECD-WTO Balanced Trade in Services (BaTIS), BPM6. Licence: ODbL.
  batis/OECD-WTO_BATIS_data_BPM6-1.zip from https://www.wto.org/english/res_e/statis_e/trade_datasets_e.htm
- Friendships: Meta Social Connectedness Index, country to country. Licence: CC0.
  sci/country.csv from https://data.humdata.org/dataset/social-connectedness-index
- People living abroad: UN DESA International Migrant Stock 2024. Licence: CC BY 3.0 IGO.
  undesa/undesa_pd_2024_ims_stock_by_sex_destination_and_origin.xlsx from
  https://www.un.org/development/desa/pd/content/international-migrant-stock

EU members are counted together as "EU" (one market with common trade rules).

Run: python scripts/build_ties.py
"""

from __future__ import annotations

import json
import sys
import zipfile
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from oracle.world.countries import blocs, countries  # noqa: E402

DATA = ROOT / "var" / "datasets"
OUT = ROOT / "oracle" / "data" / "ties.json"
FRIENDS_OUT = ROOT / "oracle" / "data" / "friendships.json"
TRADE_YEAR = 2019
TOP = 8  # partners kept per list (the full distribution sums to 1; we keep the largest)

# BaTIS EBOPS 2010 items -> the services Oracle's jobs work in.
SERVICE_ITEMS = {
    "ict": ["SI"],  # telecommunications, computer and information services
    "finance": ["SF", "SG"],  # insurance and pension, financial services
    "business": ["SJ"],  # other business services (consulting, R&D, technical, trade-related)
    "travel": ["SD"],  # what visitors spend in the country
    "transport": ["SC"],
}


def _shares(values: dict[str, float]) -> tuple[dict[str, float], float]:
    total = sum(v for v in values.values() if v > 0)
    if total <= 0:
        return {}, 0.0
    top = sorted(((k, v / total) for k, v in values.items() if v > 0), key=lambda kv: -kv[1])[:TOP]
    return {k: round(s, 4) for k, s in top}, total


def _eu(code: str, eu: set[str], me: str) -> str | None:
    """Fold EU members into 'EU'; a country isn't its own partner."""
    if code == me:
        return None
    return "EU" if code in eu else code


def trade(cs: dict, eu: set[str]) -> dict[str, dict]:
    import pandas as pd

    z = zipfile.ZipFile(DATA / "gravity" / "Gravity_csv_V202211.zip")
    cols = ["year", "iso3_o", "iso3_d", "tradeflow_baci", "manuf_tradeflow_baci", "contig", "comlang_off", "col_dep_ever"]
    rows = []
    for ch in pd.read_csv(z.open("Gravity_V202211.csv"), usecols=cols, chunksize=1_000_000, low_memory=False):
        rows.append(ch[ch["year"] == TRADE_YEAR])
    g = pd.concat(rows)
    out: dict[str, dict] = defaultdict(dict)
    pairs: dict[str, dict[str, dict]] = defaultdict(dict)
    for r in g.itertuples(index=False):
        if r.iso3_o in cs and r.iso3_d in cs and r.iso3_o != r.iso3_d:
            pairs[r.iso3_o][r.iso3_d] = {"border": r.contig == 1, "language": r.comlang_off == 1, "colonial": r.col_dep_ever == 1}
    flows = g[g["tradeflow_baci"].notna() & (g["iso3_o"] != g["iso3_d"])]
    for iso in cs:
        ex, mex, oex, im = defaultdict(float), defaultdict(float), defaultdict(float), defaultdict(float)
        for r in flows[flows["iso3_o"] == iso].itertuples(index=False):
            k = _eu(r.iso3_d, eu, iso)
            if k:
                ex[k] += r.tradeflow_baci
                m = r.manuf_tradeflow_baci if r.manuf_tradeflow_baci == r.manuf_tradeflow_baci else 0.0
                mex[k] += m
                oex[k] += max(r.tradeflow_baci - m, 0.0)
        for r in flows[flows["iso3_d"] == iso].itertuples(index=False):
            k = _eu(r.iso3_o, eu, iso)
            if k:
                im[k] += r.tradeflow_baci
        for name, d in (("goods_exports", ex), ("manufactured_exports", mex), ("other_goods_exports", oex), ("goods_imports", im)):
            sh, total = _shares(d)
            if sh:
                out[iso][name] = {"shares": sh, "total_usd": round(total * 1000)}
    return out, pairs


def services(cs: dict, eu: set[str]) -> dict[str, dict]:
    import pandas as pd

    path = DATA / "batis" / "OECD-WTO_BATIS_data_BPM6-1.zip"
    if not path.exists():
        print("no BaTIS file; services ties skipped")
        return {}
    try:
        z = zipfile.ZipFile(path)
    except zipfile.BadZipFile:
        print("BaTIS file incomplete; services ties skipped")
        return {}
    name = next(n for n in z.namelist() if n.lower().endswith(".csv"))
    to3 = _iso2_to_3(cs)
    wanted = {i for items in SERVICE_ITEMS.values() for i in items}
    keep = []
    cols = ["Reporter", "Partner", "Flow", "Item_code", "Year", "Balanced_value"]
    for ch in pd.read_csv(z.open(name), usecols=cols, chunksize=3_000_000, low_memory=False, keep_default_na=False, na_values=[""]):
        ch = ch[(ch["Flow"] == "X") & ch["Item_code"].isin(wanted) & (ch["Year"] >= 2018)]
        keep.append(ch)
    d = pd.concat(keep)
    d["rep3"] = d["Reporter"].astype(str).str.strip().map(to3)
    d["par3"] = d["Partner"].astype(str).str.strip().map(to3)
    d = d.dropna(subset=["rep3", "par3", "Balanced_value"])
    # Latest year that covers most countries (the newest one is often still partial).
    cover = d.groupby("Year")["rep3"].nunique()
    latest = int(max(y for y, n in cover.items() if n >= 0.9 * cover.max()))
    d = d[d["Year"] == latest]
    print("BaTIS year", latest, "reporters", d["rep3"].nunique())
    out: dict[str, dict] = defaultdict(dict)
    for iso, g in d.groupby("rep3"):
        for kind, items in SERVICE_ITEMS.items():
            by = defaultdict(float)
            for r in g[g["Item_code"].isin(items)].itertuples(index=False):
                k = _eu(r.par3, eu, iso)
                if k:
                    by[k] += float(r.Balanced_value)
            sh, total = _shares(by)
            if sh:
                out[iso][f"{kind}_services_exports"] = {"shares": sh, "total_usd": round(total * 1e6), "year": latest}
    return out


def _iso2_to_3(cs: dict) -> dict[str, str]:
    import pandas as pd

    z = zipfile.ZipFile(DATA / "gravity" / "Gravity_csv_V202211.zip")
    iso2 = pd.read_csv(z.open("Countries_V202211.csv"), keep_default_na=False)  # keep Namibia's "NA"
    to3 = {str(r.iso2).strip(): r.iso3 for r in iso2.itertuples() if r.iso3 in cs and str(r.iso2).strip()}
    to3.setdefault("XK", "XKX")
    return to3


def friendships(cs: dict) -> dict[str, dict]:
    """Share of a country's Facebook friendships that are with each country (itself included).
    Connections_ij is proportional to SCI_ij x users_i x users_j; users are approximated by
    internet users (World Bank), since Facebook's user counts aren't published."""
    import pandas as pd

    to3 = _iso2_to_3(cs)
    s = pd.read_csv(DATA / "sci" / "country.csv", keep_default_na=False)
    users = {iso: c.population_m * 1e6 * (c.internet_pct or 0) for iso, c in cs.items()}
    raw: dict[str, dict[str, float]] = defaultdict(dict)
    for r in s.itertuples(index=False):
        a, b = to3.get(r.user_country), to3.get(r.friend_country)
        if a and b and users.get(b):
            raw[a][b] = float(r.scaled_sci) * users[b]
    out = {}
    full = {}
    for a, d in raw.items():
        total = sum(d.values())
        full[a] = {k: round(v / total, 6) for k, v in sorted(d.items(), key=lambda kv: -kv[1]) if v / total >= 1e-6}
        home = d.get(a, 0.0) / total
        abroad = {k: v for k, v in d.items() if k != a}
        ab_total = sum(abroad.values())
        top = sorted(abroad.items(), key=lambda kv: -kv[1])[:TOP]
        out[a] = {"home_share": round(home, 4), "abroad": {k: round(v / total, 5) for k, v in top}, "abroad_share": round(ab_total / total, 4)}
    FRIENDS_OUT.write_text(json.dumps({
        "_meta": {
            "built": date.today().isoformat(),
            "source": "Meta Social Connectedness Index, country to country (CC0)",
            "note": "Share of country A's Facebook friendships that are with people in country B (A itself included). Connections are SCI x users x users, with users approximated by World Bank internet users.",
        },
        "share": full,
    }, separators=(",", ":")), encoding="utf-8")
    return out


def migrants(cs: dict) -> dict[str, dict]:
    import pandas as pd

    df = pd.read_excel(DATA / "undesa" / "undesa_pd_2024_ims_stock_by_sex_destination_and_origin.xlsx", sheet_name="Table 1", header=None, skiprows=11)
    by_num = {int(c.iso_num): iso for iso, c in cs.items() if c.iso_num}
    out_of: dict[str, dict[str, float]] = defaultdict(dict)
    into: dict[str, dict[str, float]] = defaultdict(dict)
    for r in df.itertuples(index=False):
        dest, origin, n = by_num.get(int(r[4]) if r[4] == r[4] else -1), by_num.get(int(r[6]) if r[6] == r[6] else -1), r[14]
        if dest and origin and dest != origin and n == n and float(n) > 0:
            out_of[origin][dest] = float(n)
            into[dest][origin] = float(n)
    res: dict[str, dict] = defaultdict(dict)
    for iso, d in out_of.items():
        top = sorted(d.items(), key=lambda kv: -kv[1])[:TOP]
        res[iso]["emigrants"] = {"by_country": {k: int(v) for k, v in top}, "total": int(sum(d.values()))}
    for iso, d in into.items():
        top = sorted(d.items(), key=lambda kv: -kv[1])[:TOP]
        res[iso]["immigrants"] = {"by_country": {k: int(v) for k, v in top}, "total": int(sum(d.values()))}
    return res


def main() -> None:
    cs = countries()
    eu = set(blocs()["EU"].members)
    goods, pairs = trade(cs, eu)
    print("trade:", len(goods), "countries")
    serv = services(cs, eu)
    print("services:", len(serv), "countries")
    friends = friendships(cs)
    print("friendships:", len(friends), "countries")
    mig = migrants(cs)
    print("migrants:", len(mig), "countries")
    ties = {}
    for iso in cs:
        t = {**goods.get(iso, {}), **serv.get(iso, {}), **mig.get(iso, {})}
        if iso in friends:
            t["friendships"] = friends[iso]
        partners = set()
        for v in t.values():
            if isinstance(v, dict):
                partners |= set((v.get("shares") or v.get("by_country") or v.get("abroad") or {}).keys())
        t["pairs"] = {p: f for p, f in pairs.get(iso, {}).items() if p in partners and any(f.values())}
        if t:
            ties[iso] = t
    OUT.write_text(json.dumps({
        "_meta": {
            "built": date.today().isoformat(),
            "trade_year": TRADE_YEAR,
            "sources": {
                "goods": "CEPII Gravity V202211 (BACI flows), Etalab Open Licence 2.0",
                "services": "OECD-WTO Balanced Trade in Services (BaTIS) BPM6, ODbL",
                "friendships": "Meta Social Connectedness Index (country to country), CC0; users approximated by World Bank internet users",
                "migrants": "UN DESA International Migrant Stock 2024, CC BY 3.0 IGO",
            },
            "note": "Shares are of each list's total; only the largest partners are kept. EU members are counted together as EU.",
        },
        "countries": ties,
    }, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
