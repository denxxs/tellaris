"""Build oracle/data/ties.json: each country's measured ties to the rest of the world.

Sources (all free to reuse, downloaded into backend/var/datasets/ by hand or with curl):
- Trade in goods, 2024: CEPII BACI HS22 V202601 (Gaulier & Zignago 2010, CEPII WP 2010-23).
  baci/BACI_HS22_V202601.zip from https://www.cepii.fr/CEPII/en/bdd_modele/bdd_modele_item.asp?id=37
  Licence: Etalab Open Licence 2.0. "Manufactured" follows UNCTAD: SITC sections 5-8 less 667 and 68,
  via the World Bank WITS HS 2022 -> SITC Rev.4 concordance (baci/Concordance_H6_to_S4.zip from
  https://wits.worldbank.org/data/public/concordance/).
- Shared borders, official languages and colonial ties: CEPII Gravity V202211 (Conte, Cotterlaz and
  Mayer 2022, CEPII WP 2022-05), gravity/Gravity_csv_V202211.zip from
  https://www.cepii.fr/DATA_DOWNLOAD/gravity/data/ (Etalab 2.0).
- Trade in services: OECD-WTO Balanced Trade in Services (BaTIS), BPM6. Licence: ODbL.
  batis/OECD-WTO_BATIS_data_BPM6-1.zip from https://www.wto.org/english/res_e/statis_e/trade_datasets_e.htm
- Friendships: Meta Social Connectedness Index, country to country. Licence: CC0.
  sci/country.csv from https://data.humdata.org/dataset/social-connectedness-index
  Users per country: Meta's monthly Facebook users (facebook_users.json, from scripts/fetch_facebook_users.py).
  Countries without an index (China, Iran, Cuba...) are estimated from UN migrant links (see friendships.json "check").
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
TRADE_YEAR = 2024
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


def _manufactured_hs() -> set[str]:
    """HS 2022 codes that are manufactured goods by UNCTAD's definition (SITC 5-8 less 667 and 68)."""
    import pandas as pd

    z = zipfile.ZipFile(DATA / "baci" / "Concordance_H6_to_S4.zip")
    name = next(n for n in z.namelist() if n.upper().endswith(".CSV"))
    c = pd.read_csv(z.open(name), dtype=str, encoding="latin-1")
    hs, sitc = c.iloc[:, 0].str.zfill(6), c.iloc[:, 2].str.zfill(4)
    manuf = sitc.str[0].isin(list("5678")) & ~sitc.str.startswith("667") & ~sitc.str.startswith("68")
    return set(hs[manuf])


def trade(cs: dict, eu: set[str]) -> dict[str, dict]:
    import pandas as pd

    z = zipfile.ZipFile(DATA / "baci" / "BACI_HS22_V202601.zip")
    codes = pd.read_csv(z.open("country_codes_V202601.csv"))
    to3 = dict(zip(codes["country_code"], codes["country_iso3"]))
    manuf = _manufactured_hs()
    parts = []
    for ch in pd.read_csv(z.open(f"BACI_HS22_Y{TRADE_YEAR}_V202601.csv"), usecols=["i", "j", "k", "v"], chunksize=2_000_000):
        ch["m"] = ch["k"].astype(str).str.zfill(6).isin(manuf)
        ch["mv"] = ch["v"].where(ch["m"], 0.0)
        parts.append(ch.groupby(["i", "j"])[["v", "mv"]].sum())
    flows = pd.concat(parts).groupby(level=[0, 1]).sum().reset_index()
    flows["o"] = flows["i"].map(to3)
    flows["d"] = flows["j"].map(to3)
    flows = flows[flows["o"].isin(cs) & flows["d"].isin(cs) & (flows["o"] != flows["d"])]
    print(f"BACI {TRADE_YEAR}: {len(flows):,} country pairs, {flows['mv'].sum() / flows['v'].sum():.0%} manufactured")

    g = pd.read_csv(zipfile.ZipFile(DATA / "gravity" / "Gravity_csv_V202211.zip").open("Gravity_V202211.csv"),
                    usecols=["year", "iso3_o", "iso3_d", "contig", "comlang_off", "col_dep_ever", "dist"], low_memory=False)
    g = g[g["year"] == g["year"].max()]
    pairs: dict[str, dict[str, dict]] = defaultdict(dict)
    for r in g.itertuples(index=False):
        if r.iso3_o in cs and r.iso3_d in cs and r.iso3_o != r.iso3_d:
            pairs[r.iso3_o][r.iso3_d] = {"border": r.contig == 1, "language": r.comlang_off == 1, "colonial": r.col_dep_ever == 1}

    pair_trade: dict[tuple[str, str], float] = defaultdict(float)
    for r in flows.itertuples(index=False):
        pair_trade[tuple(sorted((r.o, r.d)))] += r.v
    dist = {(r.iso3_o, r.iso3_d): r.dist for r in g.itertuples(index=False) if r.dist == r.dist}
    out: dict[str, dict] = defaultdict(dict)
    ex: dict[str, dict] = defaultdict(lambda: defaultdict(float))
    mex: dict[str, dict] = defaultdict(lambda: defaultdict(float))
    oex: dict[str, dict] = defaultdict(lambda: defaultdict(float))
    im: dict[str, dict] = defaultdict(lambda: defaultdict(float))
    for r in flows.itertuples(index=False):
        k = _eu(r.d, eu, r.o)
        if k:
            ex[r.o][k] += r.v
            mex[r.o][k] += r.mv
            oex[r.o][k] += max(r.v - r.mv, 0.0)
        k = _eu(r.o, eu, r.d)
        if k:
            im[r.d][k] += r.v
    for iso in cs:
        for name, d in (("goods_exports", ex[iso]), ("manufactured_exports", mex[iso]), ("other_goods_exports", oex[iso]), ("goods_imports", im[iso])):
            sh, total = _shares(d)
            if sh:
                out[iso][name] = {"shares": sh, "total_usd": round(total * 1000), "year": TRADE_YEAR}
    return out, pairs, {"trade": pair_trade, "dist": dist}


# National surveys that give destinations directly, used ahead of anything else.
# India: RBI Survey on Computer Software and ITES Exports 2024-25 (press release 2025-2026/1446),
# Table 5, share of software services exports (computer services and ITES/BPO). "Europe" less the UK
# is counted as EU (the RBI region also holds Switzerland, Norway and others).
NATIONAL_SURVEYS = {
    ("IND", "ict"): {"shares": {"USA": 0.529, "EU": 0.173, "GBR": 0.155, "CAN": 0.013}, "year": 2025, "total_usd": 204.7e9,
                     "source": "RBI Survey on Computer Software and ITES Exports 2024-25"},
}


def services(cs: dict, eu: set[str]) -> dict[str, dict]:
    """Who buys each country's services, best source first:
    1. a national survey of destinations (NATIONAL_SURVEYS);
    2. the country's own reported figures by partner (BaTIS Reported_value, against its reported world total);
    3. BaTIS balanced estimates (modelled where countries don't report partners)."""
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
    cols = ["Reporter", "Partner", "Flow", "Item_code", "Year", "Reported_value", "Balanced_value"]
    for ch in pd.read_csv(z.open(name), usecols=cols, chunksize=3_000_000, low_memory=False, keep_default_na=False, na_values=[""]):
        ch = ch[(ch["Flow"] == "X") & ch["Item_code"].isin(wanted) & (ch["Year"] >= 2018)]
        keep.append(ch)
    d = pd.concat(keep)
    d["Reporter"] = d["Reporter"].astype(str).str.strip()
    d["Partner"] = d["Partner"].astype(str).str.strip()
    d["rep3"] = d["Reporter"].map(to3)
    world = d[d["Partner"] == "WL"]
    d["par3"] = d["Partner"].map(to3)
    d = d.dropna(subset=["rep3", "par3", "Balanced_value"])
    # Latest year that covers most countries (the newest one is often still partial).
    cover = d.groupby("Year")["rep3"].nunique()
    latest = int(max(y for y, n in cover.items() if n >= 0.9 * cover.max()))
    d = d[d["Year"] == latest]
    world = world[world["Year"] == latest].dropna(subset=["rep3"])
    print("BaTIS year", latest, "reporters", d["rep3"].nunique())
    out: dict[str, dict] = defaultdict(dict)
    counts = defaultdict(int)
    for iso, g in d.groupby("rep3"):
        for kind, items in SERVICE_ITEMS.items():
            key = f"{kind}_services_exports"
            if (iso, kind) in NATIONAL_SURVEYS:
                out[iso][key] = dict(NATIONAL_SURVEYS[(iso, kind)])
                counts["survey"] += 1
                continue
            gi = g[g["Item_code"].isin(items)]
            wl = world[(world["rep3"] == iso) & world["Item_code"].isin(items)]["Reported_value"].sum()
            reported = gi.dropna(subset=["Reported_value"])
            if wl > 0 and len(reported):
                by = defaultdict(float)
                for r in reported.itertuples(index=False):
                    k = _eu(r.par3, eu, iso)
                    if k:
                        by[k] += float(r.Reported_value)
                top = sorted(((k, v / wl) for k, v in by.items() if v > 0), key=lambda kv: -kv[1])[:TOP]
                if top:
                    out[iso][key] = {"shares": {k: round(v, 4) for k, v in top}, "total_usd": round(wl * 1e6), "year": latest,
                                     "source": f"{cs[iso].name}'s own reported figures (OECD-WTO BaTIS)"}
                    counts["reported"] += 1
                    continue
            by = defaultdict(float)
            for r in gi.itertuples(index=False):
                k = _eu(r.par3, eu, iso)
                if k:
                    by[k] += float(r.Balanced_value)
            sh, total = _shares(by)
            if sh:
                out[iso][key] = {"shares": sh, "total_usd": round(total * 1e6), "year": latest,
                                 "source": "OECD-WTO BaTIS estimate"}
                counts["estimate"] += 1
    print(f"  services lists: {counts['survey']} from national surveys, {counts['reported']} from countries' own figures, {counts['estimate']} BaTIS estimates")
    return out


def _iso2_to_3(cs: dict) -> dict[str, str]:
    import pandas as pd

    z = zipfile.ZipFile(DATA / "gravity" / "Gravity_csv_V202211.zip")
    iso2 = pd.read_csv(z.open("Countries_V202211.csv"), keep_default_na=False)  # keep Namibia's "NA"
    to3 = {str(r.iso2).strip(): r.iso3 for r in iso2.itertuples() if r.iso3 in cs and str(r.iso2).strip()}
    to3.setdefault("XK", "XKX")
    return to3


FB_USERS = DATA / "facebook_users.json"
# Where Meta's tool refuses (sanctions), the last published figure from the same tool, or the
# nearest published count.
FB_USERS_PUBLISHED = {
    "RUS": (8.6e6, "Meta ad reach, early 2022, via DataReportal Digital 2022 (before the ban)"),
    "SDN": (2.91e6, "social media users, DataReportal Digital 2024 (no Meta figure published)"),
}


def _users(cs: dict) -> tuple[dict[str, float], dict[str, str]]:
    """Social-network users per country: Meta's monthly Facebook users (adults, ad reach estimate)
    where it gives one; elsewhere (Facebook blocked or not sold to advertisers) internet users."""
    fb = json.loads(FB_USERS.read_text(encoding="utf-8"))["countries"] if FB_USERS.exists() else {}
    users, how = {}, {}
    for iso, c in cs.items():
        if iso in fb:
            users[iso], how[iso] = float(fb[iso]["mid"]), "facebook"
        elif iso in FB_USERS_PUBLISHED:
            users[iso], how[iso] = FB_USERS_PUBLISHED[iso][0], FB_USERS_PUBLISHED[iso][1]
        elif c.internet_pct:
            users[iso], how[iso] = c.population_m * 1e6 * c.internet_pct, "internet"
    return users, how


def friendships(cs: dict, pairs: dict, extra: dict, mig: dict, into: dict) -> dict[str, dict]:
    """Share of a country's friendships that are with each country (itself included).

    Measured: connections_ij = SCI_ij x users_i x users_j (Meta Social Connectedness Index), users
    from Meta's ad reach estimates. For countries Meta has no index for (China, Iran, Cuba...):
    - a measured country's share of friendships with them = its measured share of friendships
      abroad x their share of the migrants linking it to the world (UN DESA, both directions);
    - their own friendships abroad split like their migrant links, and the share kept at home
      comes from a fit on measured countries (population, income, migration).
    Several ways were tested on measured countries treated as hidden; this one came closest
    (see the "check" block in friendships.json for its error)."""
    import math

    import numpy as np
    import pandas as pd

    to3 = _iso2_to_3(cs)
    users, how = _users(cs)
    s = pd.read_csv(DATA / "sci" / "country.csv", keep_default_na=False)
    sci: dict[str, dict[str, float]] = defaultdict(dict)
    for r in s.itertuples(index=False):
        a, b = to3.get(r.user_country), to3.get(r.friend_country)
        if a and b and r.scaled_sci > 0:
            sci[a][b] = float(r.scaled_sci)
    measured = {a for a in sci if a in users}
    estimated = sorted(i for i, c in cs.items() if i not in measured and c.gdp_pc_usd)

    def links(a: str) -> dict[str, float]:
        return {b: v * users[a] * users[b] for b, v in sci[a].items() if b in users}

    def migrant_shares(a: str) -> dict[str, float]:
        m = {b: mig.get(a, {}).get(b, 0.0) + mig.get(b, {}).get(a, 0.0) for b in cs if b != a}
        t = sum(m.values())
        return {b: v / t for b, v in m.items() if v > 0} if t else {}

    share: dict[str, dict[str, float]] = {}
    for a in measured:
        d = links(a)
        total = sum(d.values())
        if not total:
            continue
        sh = {b: v / total for b, v in d.items()}
        abroad = 1 - sh.get(a, 0.0)
        ms = migrant_shares(a)
        add = {b: abroad * ms[b] for b in estimated if ms.get(b)}
        keep = 1 - sum(add.values())
        share[a] = {**{b: v * keep for b, v in sh.items()}, **add}

    # Share kept at home for unmeasured countries, fitted on measured ones (logit).
    def home_x(a: str) -> list[float]:
        c = cs[a]
        pop = c.population_m * 1e6
        return [1.0, math.log(pop), math.log(c.gdp_pc_usd), math.log1p(sum(mig.get(a, {}).values()) / pop * 1000),
                math.log1p(sum(into.get(a, {}).values()) / pop * 1000)]

    HX, hy = [], []
    for a in measured:
        h = share.get(a, {}).get(a, 0.0)
        if 0 < h < 1 and cs[a].gdp_pc_usd:
            HX.append(home_x(a))
            hy.append(math.log(h / (1 - h)))
    HX, hy = np.array(HX), np.array(hy)
    hcoef, *_ = np.linalg.lstsq(HX, hy, rcond=None)
    h_r2 = 1 - ((hy - HX @ hcoef) ** 2).sum() / ((hy - hy.mean()) ** 2).sum()
    for a in estimated:
        ms = migrant_shares(a)
        if not ms:
            continue
        h = 1 / (1 + math.exp(-float(np.array(home_x(a)) @ hcoef)))
        share[a] = {a: h, **{b: (1 - h) * v for b, v in ms.items()}}

    # How well this works, on measured countries: (1) another country's share of friendships with a
    # hidden one, (2) a hidden country's own split abroad.
    ratios, wrong, top_right = [], [], []
    for a in measured:
        d = links(a)
        total = sum(d.values()) or 1.0
        abroad = 1 - d.get(a, 0.0) / total
        ms = migrant_shares(a)
        for h, v in d.items():
            if h != a and v / total > 0.005 and ms.get(h):
                ratios.append(abroad * ms[h] / (v / total))
        bs = [b for b in d if b != a and b in ms]
        if len(bs) >= 5:
            truth = np.array([d[b] for b in bs])
            truth /= truth.sum()
            guess = np.array([ms[b] for b in bs])
            guess /= guess.sum()
            wrong.append(np.abs(guess - truth).sum() / 2)
            top_right.append(bs[int(guess.argmax())] == bs[int(truth.argmax())])
    r = np.array(ratios)
    check = {"others_ties_to_hidden_country": {"predicted_over_true_median": round(float(np.median(r)), 2),
                                               "within_2x": round(float(np.mean((r > 0.5) & (r < 2))), 2),
                                               "p10_p90": [round(float(np.percentile(r, 10)), 2), round(float(np.percentile(r, 90)), 2)], "pairs": len(r)},
             "hidden_country_own_split": {"misallocated_median": round(float(np.median(wrong)), 2), "top_partner_right": round(float(np.mean(top_right)), 2)},
             "home_share_model_r2": round(float(h_r2), 2),
             "alternatives_tried": "regressions on distance, border, language, colonial tie, migrants, trade, income and size (one- and two-way country effects), and each country's own migrant-distance relation: all further off for ties to hidden countries"}

    out, full = {}, {}
    for a, sh in share.items():
        full[a] = {k: round(v, 6) for k, v in sorted(sh.items(), key=lambda kv: -kv[1]) if v >= 1e-6}
        abroad = {k: v for k, v in sh.items() if k != a}
        top = sorted(abroad.items(), key=lambda kv: -kv[1])[:TOP]
        out[a] = {"home_share": round(sh.get(a, 0.0), 4), "abroad": {k: round(v, 5) for k, v in top},
                  "abroad_share": round(sum(abroad.values()), 4), "estimated": a in estimated}
    approx = {i: h for i, h in how.items() if h != "facebook" and i in measured}
    FRIENDS_OUT.write_text(json.dumps({
        "_meta": {
            "built": date.today().isoformat(),
            "source": "Meta Social Connectedness Index, country to country (CC0); users from Meta Marketing API ad reach estimates; UN DESA migrant stock 2024 for countries without an index",
            "note": "Share of country A's friendships that are with people in country B (A itself included).",
            "estimated": estimated,
            "users_not_from_meta_tool": approx,
            "check": check,
        },
        "share": full,
    }, separators=(",", ":")), encoding="utf-8")
    print(f"friendships: {len(measured)} measured, {len(estimated)} estimated ({', '.join(estimated)})")
    print(f"  check: {check['others_ties_to_hidden_country']}; own split {check['hidden_country_own_split']}; home R2 {h_r2:.2f}")
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
    return res, out_of, into


def main() -> None:
    cs = countries()
    eu = set(blocs()["EU"].members)
    goods, pairs, extra = trade(cs, eu)
    print("trade:", len(goods), "countries")
    serv = services(cs, eu)
    print("services:", len(serv), "countries")
    mig, out_of, into = migrants(cs)
    print("migrants:", len(mig), "countries")
    friends = friendships(cs, pairs, extra, out_of, into)
    print("friendships:", len(friends), "countries")
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
                "goods": f"CEPII BACI HS22 V202601, {TRADE_YEAR}, Etalab Open Licence 2.0",
                "services": "OECD-WTO Balanced Trade in Services (BaTIS) BPM6, ODbL",
                "friendships": "Meta Social Connectedness Index (country to country), CC0; users from Meta ad reach estimates; countries without an index estimated from UN migrant links (see friendships.json)",
                "migrants": "UN DESA International Migrant Stock 2024, CC BY 3.0 IGO",
            },
            "note": "Shares are of each list's total; only the largest partners are kept. EU members are counted together as EU.",
        },
        "countries": ties,
    }, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
