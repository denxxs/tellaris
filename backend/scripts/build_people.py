"""Build oracle/data/people.json: the real-data facts used to build simulated people.

Everything here comes from published statistics, per country, with the year it refers to:

- World Bank (CC BY 4.0): population by 5-year age band and sex; Gini index; tertiary
  enrolment.
- ILOSTAT (CC BY 4.0):
  - employment by 2-digit occupation (ISCO-08) and by sex;
  - employment by age and occupation group;
  - mean monthly earnings by occupation group (US dollars);
  - employment by status (employees, employers, own-account workers);
  - labour-force participation by age.

Run:  cd backend && python scripts/build_people.py
Raw downloads are cached in backend/var/datasets/cache (not committed); delete the cache to refresh.
"""

from __future__ import annotations

import csv
import io
import json
import time
from datetime import date
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "var" / "datasets" / "cache"
OUT = ROOT / "oracle" / "data" / "people.json"
WB = "https://api.worldbank.org/v2"
ILO = "https://sdmx.ilo.org/rest/data/ILO,{flow},1.0/{key}"
SINCE = 2015
UA = {"User-Agent": "Mozilla/5.0 (compatible; oracle-data-build)"}

# Findex facts (World Bank source 28) and the population groups each is published for.
FINDEX = {
    "internet_daily": ["con26d"],
    "smartphone": ["con9a"],
    "account": ["account.t.d"],
    "credit_card": ["fin10"],
    "emergency_hard": ["fin24aN", "fin24aVD"],  # not possible, or possible but very difficult
    "news_online": ["con30d"],
}
FINDEX_GROUPS = {"": "all", ".1": "female", ".2": "male", ".3": "young", ".4": "older", ".7": "poorest40", ".8": "richest60", ".11": "out_lf", ".12": "in_lf"}

AGE5 = ["0004", "0509", "1014", "1519", "2024", "2529", "3034", "3539", "4044", "4549", "5054", "5559", "6064", "6569", "7074", "7579", "80UP"]
AGE5_LABEL = ["0-4", "5-9", "10-14", "15-19", "20-24", "25-29", "30-34", "35-39", "40-44", "45-49", "50-54", "55-59", "60-64", "65-69", "70-74", "75-79", "80+"]
AGEJOB = ["Y15-24", "Y25-54", "Y55-64", "YGE65"]
AGEJOB_LABEL = ["15-24", "25-54", "55-64", "65+"]


def cached(name: str, fetch) -> str:
    CACHE.mkdir(parents=True, exist_ok=True)
    p = CACHE / name
    if p.exists():
        return p.read_text(encoding="utf-8")
    text = fetch()
    p.write_text(text, encoding="utf-8")
    return text


def get(url: str, **kw) -> httpx.Response:
    for attempt in range(4):
        try:
            r = httpx.get(url, timeout=900, follow_redirects=True, headers={**UA, **kw.pop("headers", {})}, **kw)
            r.raise_for_status()
            return r
        except httpx.HTTPError:
            if attempt == 3:
                raise
            time.sleep(5 * (attempt + 1))
    raise RuntimeError("unreachable")


# ---------------------------------------------------------------- World Bank


def wb(code: str, source: int | None = None, zero_is_missing: bool = False) -> dict[str, tuple[float, int]]:
    """Latest non-empty value per country since SINCE. Findex marks questions it didn't ask with 0."""
    def fetch() -> str:
        params = {"format": "json", "per_page": 20000, "date": f"{SINCE}:{date.today().year}"}
        if source:
            params["source"] = source
        r = get(f"{WB}/country/all/indicator/{code}", params=params)
        return r.text

    rows = json.loads(cached(f"wb_{code}{f'_s{source}' if source else ''}.json", fetch))
    out: dict[str, tuple[float, int]] = {}
    for row in (rows[1] if len(rows) > 1 else None) or []:
        iso, v = row.get("countryiso3code") or row["country"]["id"], row.get("value")
        if not iso or len(iso) != 3 or v is None or (zero_is_missing and v == 0):
            continue
        y = int(row["date"])
        if iso not in out or y > out[iso][1]:
            out[iso] = (float(v), y)
    return out


# ---------------------------------------------------------------- ILOSTAT


def ilo(flow: str, key: str, name: str) -> list[dict[str, str]]:
    def fetch() -> str:
        r = get(
            ILO.format(flow=flow, key=key),
            params={"startPeriod": str(SINCE), "dimensionAtObservation": "AllDimensions"},
            headers={"Accept": "application/vnd.sdmx.data+csv;version=1.0.0"},
        )
        return r.text

    return list(csv.DictReader(io.StringIO(cached(f"ilo_{name}.csv", fetch))))


def latest_complete(rows: list[dict[str, str]], dim: str, need: set[str] | None = None, extra: str | None = None) -> dict[str, tuple[int, dict]]:
    """Per country, the latest year that has every value in `need` (or any values). Values keyed by `dim`
    (and by `extra` when given, as (dim, extra))."""
    by: dict[tuple[str, int], dict] = {}
    for r in rows:
        try:
            v = float(r["OBS_VALUE"])
        except (TypeError, ValueError):
            continue
        k = (r[dim], r[extra]) if extra else r[dim]
        by.setdefault((r["REF_AREA"], int(r["TIME_PERIOD"])), {})[k] = v
    out: dict[str, tuple[int, dict]] = {}
    for (iso, y), vals in by.items():
        keys = {k[0] if isinstance(k, tuple) else k for k in vals}
        if need and not need <= keys:
            continue
        if iso not in out or y > out[iso][0]:
            out[iso] = (y, vals)
    return out


def main() -> None:
    countries: dict[str, dict] = {}

    def c(iso: str) -> dict:
        return countries.setdefault(iso, {})

    # Population by age band and sex.
    print("World Bank: population by age and sex")
    tot = {"female": wb("SP.POP.TOTL.FE.IN"), "male": wb("SP.POP.TOTL.MA.IN")}
    bands = {(sex, b): wb(f"SP.POP.{b}.{'FE' if sex == 'female' else 'MA'}.5Y") for sex in ("female", "male") for b in AGE5}
    for iso in set(tot["female"]) & set(tot["male"]):
        rec = {"year": tot["female"][iso][1], "bands": AGE5_LABEL}
        ok = True
        for sex in ("female", "male"):
            shares = [bands[(sex, b)].get(iso) for b in AGE5]
            if any(s is None for s in shares):
                ok = False
                break
            rec[sex] = [round(tot[sex][iso][0] * s[0] / 100) for s in shares]
        if ok:
            c(iso)["age_sex"] = rec

    print("World Bank: labour force and unemployment")
    lf, un = wb("SL.TLF.TOTL.IN"), wb("SL.UEM.TOTL.ZS")
    for iso in set(lf) & set(un):
        c(iso)["labour"] = {"force": round(lf[iso][0]), "unemployment_pct": round(un[iso][0], 2), "year": min(lf[iso][1], un[iso][1])}

    print("World Bank: Gini and tertiary enrolment")
    for iso, (v, y) in wb("SI.POV.GINI").items():
        c(iso)["gini"] = {"value": v, "year": y}
    for iso, (v, y) in wb("SE.TER.ENRR").items():
        c(iso)["tertiary_enrolment"] = {"value": round(v, 2), "year": y}

    # Findex: digital and money facts by group.
    print("World Bank: Global Findex facts by group")
    for fact, codes in FINDEX.items():
        for suffix, group in FINDEX_GROUPS.items():
            parts = [wb(f"{code}{suffix}", source=28, zero_is_missing=True) for code in codes]
            for iso in set.intersection(*(set(p) for p in parts)):
                v = sum(p[iso][0] for p in parts) / 100
                y = min(p[iso][1] for p in parts)
                rec = c(iso).setdefault("findex", {}).setdefault(fact, {})
                rec[group] = round(min(max(v, 0.0), 1.0), 4)
                rec["year"] = max(rec.get("year", 0), y)

    # Employment by 2-digit occupation, by sex.
    print("ILOSTAT: employment by 2-digit occupation and sex (a few minutes the first time)")
    rows = ilo("DF_EMP_TEMP_SEX_OC2_NB", ".A..SEX_T+SEX_F+SEX_M.", "oc2_sex")
    rows = [r for r in rows if r["OC2"].startswith("OC2_ISCO08_") and r["OC2"][-2:].isdigit()]
    for iso, (y, vals) in latest_complete(rows, "OC2", extra="SEX").items():
        total = {k[0][-2:]: round(v * 1000) for k, v in vals.items() if k[1] == "SEX_T" and v > 0}
        fem = {k[0][-2:]: v for k, v in vals.items() if k[1] == "SEX_F"}
        mal = {k[0][-2:]: v for k, v in vals.items() if k[1] == "SEX_M"}
        if len(total) < 20:
            continue
        share_f = {g: round(fem[g] / (fem[g] + mal[g]), 3) for g in total if g in fem and g in mal and fem[g] + mal[g] > 0}
        c(iso)["oc2"] = {"year": y, "employed": total, "female_share": share_f}

    # Age by occupation group.
    print("ILOSTAT: employment by age and occupation group")
    rows = ilo("DF_EMP_TEMP_SEX_AGE_OCU_NB", ".A..SEX_T..", "age_ocu")
    rows = [r for r in rows if r["AGE"].startswith("AGE_AGGREGATE_Y") and r["AGE"] != "AGE_AGGREGATE_YGE15" and r["OCU"].startswith("OCU_ISCO08_") and r["OCU"][-1].isdigit()]
    for iso, (y, vals) in latest_complete(rows, "OCU", extra="AGE").items():
        groups: dict[str, list[int]] = {}
        for g in range(0, 10):
            counts = [vals.get((f"OCU_ISCO08_{g}", f"AGE_AGGREGATE_{a}")) for a in AGEJOB]
            if all(v is not None for v in counts) and sum(counts) > 0:
                groups[str(g)] = [round(v * 1000) for v in counts]
        if len(groups) >= 7:
            c(iso)["age_by_group"] = {"year": y, "bands": AGEJOB_LABEL, "groups": groups}

    # Mean monthly earnings by occupation group, US dollars.
    print("ILOSTAT: earnings by occupation group")
    key = ".A..SEX_T." + "+".join(f"OCU_ISCO08_{g}" for g in range(0, 10)) + "+OCU_ISCO08_TOTAL.CUR_TYPE_USD"
    rows = ilo("DF_EAR_EMTA_SEX_OCU_CUR_NB", key, "earnings")
    for iso, (y, vals) in latest_complete(rows, "OCU", need={"OCU_ISCO08_TOTAL"}).items():
        g = {k.rsplit("_", 1)[1]: round(v, 2) for k, v in vals.items()}
        if len(g) >= 8:
            c(iso)["earnings_usd_month"] = {"year": y, "groups": g}

    # Employees, employers, own-account workers.
    print("ILOSTAT: employment by status")
    rows = ilo("DF_EMP_TEMP_SEX_STE_NB", ".A..SEX_T.STE_ICSE93_1+STE_ICSE93_2+STE_ICSE93_3+STE_ICSE93_TOTAL", "status")
    for iso, (y, vals) in latest_complete(rows, "STE", need={"STE_ICSE93_1", "STE_ICSE93_2", "STE_ICSE93_3", "STE_ICSE93_TOTAL"}).items():
        c(iso)["status"] = {
            "year": y, "employees": round(vals["STE_ICSE93_1"] * 1000), "employers": round(vals["STE_ICSE93_2"] * 1000),
            "own_account": round(vals["STE_ICSE93_3"] * 1000), "employed": round(vals["STE_ICSE93_TOTAL"] * 1000),
        }

    # Where ILO has no status table, the World Bank's shares of employment (ILO modelled estimates).
    emp_pct, self_pct, fam_pct = wb("SL.EMP.MPYR.ZS"), wb("SL.EMP.SELF.ZS"), wb("SL.FAM.WORK.ZS")
    own_pct = {iso: (max(0.0, self_pct[iso][0] - emp_pct[iso][0] - fam_pct[iso][0]), self_pct[iso][1]) for iso in self_pct if iso in emp_pct and iso in fam_pct}
    for iso, rec in countries.items():
        if "status" in rec or iso not in emp_pct or iso not in own_pct:
            continue
        oc2 = rec.get("oc2")
        employed = sum(oc2["employed"].values()) if oc2 else None
        if employed:
            rec["status"] = {
                "year": min(emp_pct[iso][1], own_pct[iso][1]), "employers": round(employed * emp_pct[iso][0] / 100),
                "own_account": round(employed * own_pct[iso][0] / 100), "employed": employed, "source": "World Bank SL.EMP.MPYR.ZS; own-account = SL.EMP.SELF.ZS - employers - SL.FAM.WORK.ZS",
            }

    # Labour-force participation by age.
    print("ILOSTAT: labour-force participation by age")
    rows = ilo("DF_EAP_2WAP_SEX_AGE_RT", ".A..SEX_T.AGE_YTHADULT_Y15-24+AGE_AGGREGATE_YGE65+AGE_YTHADULT_YGE15", "lfpr")
    rows = [r for r in rows if int(r["TIME_PERIOD"]) < date.today().year]  # ILO also publishes projections
    need = {"AGE_YTHADULT_Y15-24", "AGE_AGGREGATE_YGE65", "AGE_YTHADULT_YGE15"}
    for iso, (y, vals) in latest_complete(rows, "AGE", need=need).items():
        c(iso)["participation"] = {"year": y, "15-24": round(vals["AGE_YTHADULT_Y15-24"] / 100, 4), "65+": round(vals["AGE_AGGREGATE_YGE65"] / 100, 4), "15+": round(vals["AGE_YTHADULT_YGE15"] / 100, 4)}

    countries = {k: v for k, v in countries.items() if len(k) == 3 and k.isalpha() and k.isupper()}
    out = {
        "_meta": {
            "built": date.today().isoformat(),
            "sources": {
                "age_sex": "World Bank, SP.POP.<band>.<sex>.5Y and SP.POP.TOTL.<sex>.IN (UN World Population Prospects)",
                "gini": "World Bank, SI.POV.GINI",
                "findex": "World Bank Global Findex (source 28): con26d daily internet use, con9a smartphone, account.t.d account, fin10 credit card, fin24aN+fin24aVD emergency funds not possible or very difficult, con30d read news online; by sex, age, income and labour-force status",
                "labour": "World Bank, SL.TLF.TOTL.IN and SL.UEM.TOTL.ZS (ILO modelled estimates)",
                "tertiary_enrolment": "World Bank, SE.TER.ENRR (gross, %)",
                "oc2": "ILOSTAT, DF_EMP_TEMP_SEX_OC2_NB: employment by sex and 2-digit ISCO-08 occupation",
                "age_by_group": "ILOSTAT, DF_EMP_TEMP_SEX_AGE_OCU_NB: employment by age and ISCO-08 major group",
                "earnings_usd_month": "ILOSTAT, DF_EAR_EMTA_SEX_OCU_CUR_NB: mean nominal monthly earnings of employees by ISCO-08 major group, US dollars",
                "status": "ILOSTAT, DF_EMP_TEMP_SEX_STE_NB: employment by status in employment (ICSE-93)",
                "participation": "ILOSTAT, DF_EAP_2WAP_SEX_AGE_RT: labour-force participation rate by age",
            },
            "licence": "World Bank and ILOSTAT data are CC BY 4.0.",
            "note": "Each block carries the year it refers to: the latest year the source has since 2015. Counts are people.",
            "count": len(countries),
        },
        "countries": dict(sorted(countries.items())),
    }
    OUT.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    have = {k: sum(1 for v in countries.values() if k in v) for k in ("findex", "labour", "age_sex", "oc2", "age_by_group", "earnings_usd_month", "status", "participation", "gini", "tertiary_enrolment")}
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KB) for {len(countries)} countries: {have}")



# ---------------------------------------------------------------- detailed job split (US data)

OES_GLOB = "oesm*nat*.zip"
CROSSWALK = "ISCO_SOC_Crosswalk.xls"
WITHIN_OUT = ROOT / "oracle" / "data" / "isco_within.json"


def build_within() -> None:
    """Share of each ISCO-08 unit group within its 2-digit group, from BLS Occupational Employment
    and Wage Statistics (national, detailed occupations) mapped through the BLS ISCO-08/SOC crosswalk.
    A SOC occupation mapped to several ISCO groups is split evenly between them (the crosswalk
    gives no weights). Needs the two BLS files in backend/var/datasets/ (download them in a browser)."""
    import re
    import zipfile

    import pandas as pd
    import xlrd

    folder = ROOT / "var" / "datasets"
    oes = sorted(folder.glob(OES_GLOB))
    cw = folder / CROSSWALK
    if not oes or not cw.exists():
        print(f"skipping the detailed split: put {OES_GLOB} and {CROSSWALK} in {folder}")
        return
    z = zipfile.ZipFile(oes[-1])
    sheet = next(n for n in z.namelist() if n.lower().endswith(".xlsx"))
    df = pd.read_excel(z.open(sheet))
    df.columns = [str(c).upper() for c in df.columns]
    df = df[df["O_GROUP"].astype(str).str.lower() == "detailed"]
    emp = {str(r.OCC_CODE): float(r.TOT_EMP) for r in df.itertuples() if str(r.TOT_EMP).replace(".", "").isdigit()}

    book = xlrd.open_workbook(str(cw))
    links: dict[str, set[str]] = {}
    for sh in book.sheets():
        for i in range(sh.nrows):
            row = [str(x).strip() for x in sh.row_values(i)]
            isco = next((x for x in row if re.fullmatch(r"\d{4}(\.0)?", x)), None)
            soc = next((x for x in row if re.fullmatch(r"\d{2}-\d{4}", x)), None)
            if isco and soc:
                links.setdefault(soc, set()).add(isco[:4])
    by4: dict[str, float] = {}
    matched = 0.0
    for soc, n in emp.items():
        targets = links.get(soc)
        if not targets:
            continue
        matched += n
        for code in targets:
            by4[code] = by4.get(code, 0.0) + n / len(targets)
    by2: dict[str, float] = {}
    for code, n in by4.items():
        by2[code[:2]] = by2.get(code[:2], 0.0) + n
    share = {code: round(n / by2[code[:2]], 6) for code, n in sorted(by4.items()) if by2[code[:2]] > 0}
    WITHIN_OUT.write_text(json.dumps({
        "_meta": {
            "built": date.today().isoformat(),
            "source": f"BLS OEWS {oes[-1].name} (detailed occupations, national) mapped to ISCO-08 with the BLS ISCO-08/SOC crosswalk",
            "coverage": round(matched / sum(emp.values()), 3),
            "note": "US within-group mix, applied to every country's real 2-digit counts. US wage-and-salary jobs only.",
        },
        "share": share,
    }, indent=0), encoding="utf-8")
    print(f"wrote {WITHIN_OUT}: {len(share)} unit groups, {matched / sum(emp.values()):.0%} of US jobs matched")


if __name__ == "__main__":
    import sys

    if sys.argv[1:] == ["within"]:
        build_within()
    else:
        main()
        build_within()
