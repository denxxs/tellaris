"""Build oracle/data/firms.json: how big the places people work at are, and who works for the state.

Sources (all fetched at build time, no keys):

- ILOSTAT (CC BY 4.0), DF_EMP_TEMP_SEX_OCU_EST_NB: employment by occupation group (ISCO-08
  major group) and size of the workplace (1, 2-4, 5-9, 10-19, 20-49, 50+ people; some
  countries publish only 1-4, 5-49, 50+). Household surveys, so informal work is included.
- ILOSTAT, DF_EMP_PUBL_SEX_OC2_NB with DF_EMP_TEMP_SEX_OC2_NB: share of each 2-digit
  occupation employed in the public sector.
- OECD Structural Business Statistics (CC BY 4.0), DF_SDBS_ISIC4: persons employed in
  enterprises of 50-249 and 250+ people, business economy except finance (BTNXK).
- US Census Bureau, Statistics of US Businesses 2022 (public domain): employment by enterprise
  size in fine classes up to 20,000+ (us_state_naics_detailedsizes_2022.txt and
  us_naicssector_large_emplsize_2022.xlsx, downloaded into backend/var/datasets/).

How they fit together, finest first:
1. Below 50 people: the country's own ILO workplace-size shares for the person's job group.
2. 50+ split into 50-249 and 250+: the country's OECD enterprise shares (the US from SUSB);
   elsewhere the employment-weighted average of covered countries at the same World Bank
   income level (all covered countries when none share it).
3. Finer classes inside 50-249 and 250+: the US shape (SUSB), the only source with them.
Countries without an ILO workplace survey use the employment-weighted average of surveyed
countries at the same income level. Every country records which of these it used.

Run:  cd backend && python scripts/build_firms.py
"""

from __future__ import annotations

import csv
import io
import json
import math
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from build_people import cached, get, ilo, latest_complete  # noqa: E402

from oracle.world.countries import countries  # noqa: E402

OUT = ROOT / "oracle" / "data" / "firms.json"
DATASETS = ROOT / "var" / "datasets"
SUSB_DETAILED = DATASETS / "us_state_naics_detailedsizes_2022.txt"
SUSB_LARGE = DATASETS / "us_naicssector_large_emplsize_2022.xlsx"
OECD = "https://sdmx.oecd.org/public/rest/data/OECD.SDD.TPS,DSD_SDBSBSC_ISIC4@DF_SDBS_ISIC4,1.0/A..EMPN.BTNXK.S50T249+S_GE250."

# Size classes, as [lo, hi] people (hi None = no upper end).
SMALL_DETAIL = {"EST_DETAILS_S1": [1, 1], "EST_DETAILS_S2-4": [2, 4], "EST_DETAILS_S5-9": [5, 9],
                "EST_DETAILS_S10-19": [10, 19], "EST_DETAILS_S20-49": [20, 49], "EST_DETAILS_SGE50": [50, None]}
SMALL_AGG = {"EST_AGGREGATE_S1-4": [1, 4], "EST_AGGREGATE_S5-49": [5, 49], "EST_AGGREGATE_SGE50": [50, None]}
MID = [[50, 99], [100, 249]]
LARGE = [[250, 499], [500, 999], [1000, 1999], [2000, 4999], [5000, 19999], [20000, None]]


def _split(lo: float, hi: float, at: float) -> float:
    """Share of a size class below `at`, spreading the class evenly on a log scale."""
    return math.log(at / lo) / math.log((hi + 1) / lo)


def us_shape() -> dict:
    """US employment by enterprise size: 50-249 vs 250+, and the finer classes inside each."""
    import pandas as pd

    d = pd.read_csv(SUSB_DETAILED, dtype=str, encoding="latin-1")
    d = d[(d.STATE == "00") & (d.NAICS == "--")]
    emp = {r.ENTRSIZEDSCR.split(":", 1)[1].strip().replace(",", ""): float(r.EMPL) for r in d.itertuples()}
    big = pd.read_excel(SUSB_LARGE, header=2)
    big = big[big["NAICS"] == "--"]
    for r in big.itertuples():
        emp[str(r[3]).split(":", 1)[1].replace("employees", "").strip().replace(",", "")] = float(r.Employment)
    below250 = emp["200-299"] * _split(200, 299, 250)
    c50_99 = emp["50-74"] + emp["75-99"]
    c100_249 = emp["100-149"] + emp["150-199"] + below250
    c250_499 = emp["200-299"] - below250 + emp["300-399"] + emp["400-499"]
    large = [c250_499, emp["500-749"] + emp["750-999"], emp["1000-1499"] + emp["1500-1999"],
             emp["2000-2499"] + emp["2500-4999"], emp["5000-9999"] + emp["10000-19999"], emp["20000+"]]
    mid = [c50_99, c100_249]
    return {
        "mid_share_of_50plus": round(sum(mid) / (sum(mid) + sum(large)), 4),
        "mid": [round(x / sum(mid), 4) for x in mid],
        "large": [round(x / sum(large), 4) for x in large],
        "year": 2022,
    }


def oecd_mid_share() -> dict[str, tuple[float, int]]:
    """Share of 50+ enterprise employment in 50-249, latest year per country."""
    text = cached("oecd_sdbs_btnxk.csv", lambda: get(
        OECD, params={"startPeriod": "2015", "dimensionAtObservation": "AllDimensions"},
        headers={"Accept": "application/vnd.sdmx.data+csv;version=1.0.0"}).text)
    by: dict[tuple[str, int], dict[str, float]] = defaultdict(dict)
    for r in csv.DictReader(io.StringIO(text)):
        try:
            by[(r["REF_AREA"], int(r["TIME_PERIOD"]))][r["SIZE_CLASS"]] = float(r["OBS_VALUE"])
        except (TypeError, ValueError):
            continue
    out: dict[str, tuple[float, int]] = {}
    for (iso, y), v in by.items():
        if "S50T249" in v and "S_GE250" in v and v["S50T249"] + v["S_GE250"] > 0:
            if iso not in out or y > out[iso][1]:
                out[iso] = (v["S50T249"] / (v["S50T249"] + v["S_GE250"]), y)
    return out


# ILO skill level of each ISCO-08 major group (armed forces have none).
SKILL_OF = {"1": "L3-4", "2": "L3-4", "3": "L3-4", "4": "L2", "5": "L2", "6": "L2", "7": "L2", "8": "L2", "9": "L1", "TOTAL": "TOTAL", "0": "TOTAL"}
# Which detailed classes make up each coarse class.
COARSE = [[0, 1], [2, 3, 4], [5]]  # 1-4 = 1 + 2-4; 5-49 = 5-9 + 10-19 + 20-49; 50+


def workplaces() -> dict[str, dict]:
    """Per country: shares of employment by workplace size class for each job group.

    ILO publishes coarse classes (1-4, 5-49, 50+) by ISCO major group, and fine classes
    (1, 2-4, 5-9, 10-19, 20-49, 50+) only by skill level. Each job group's coarse shares are
    split with the same country's fine shares for its skill level, from the same survey year."""
    rows = ilo("DF_EMP_TEMP_SEX_OCU_EST_NB", ".A..SEX_T..", "ocu_est")
    coarse: dict[tuple[str, int], dict[str, list]] = defaultdict(dict)
    fine: dict[tuple[str, int], dict[str, list]] = defaultdict(dict)
    vals: dict[tuple[str, int], dict[tuple[str, str], float]] = defaultdict(dict)
    for r in rows:
        try:
            v = float(r["OBS_VALUE"])
        except (TypeError, ValueError):
            continue
        vals[(r["REF_AREA"], int(r["TIME_PERIOD"]))][(r["OCU"], r["EST"])] = v
    for key, v in vals.items():
        for scheme in ("ISCO08", "ISCO88"):
            for g in ["TOTAL", *map(str, range(10))]:
                counts = [v.get((f"OCU_{scheme}_{g}", code)) for code in SMALL_AGG]
                if None not in counts and sum(counts) > 0:
                    coarse[key].setdefault("all" if g == "TOTAL" else g, [c / sum(counts) for c in counts] + [sum(counts)])
        for lvl in ("TOTAL", "L3-4", "L2", "L1"):
            counts = [v.get((f"OCU_SKILL_{lvl}", code)) for code in SMALL_DETAIL]
            if None not in counts and sum(counts) > 0:
                fine[key][lvl] = [c / sum(counts) for c in counts]
    out: dict[str, dict] = {}
    for (iso, y), groups in coarse.items():
        if "all" not in groups:
            continue
        f = fine.get((iso, y), {})
        if "TOTAL" in f:
            classes, kind = list(SMALL_DETAIL.values()), "detail"
            res = {}
            for g, row in groups.items():
                d = f.get(SKILL_OF["TOTAL" if g == "all" else g]) or f["TOTAL"]
                shares = []
                for ci, parts in enumerate(COARSE):
                    dd = d if sum(d[i] for i in parts) > 0 else f["TOTAL"]  # skill level empty here: whole-country shape
                    within = sum(dd[i] for i in parts)
                    shares += [row[ci] * dd[i] / within if within > 0 else 0.0 for i in parts]
                res[g] = [round(x, 4) for x in shares] + [row[-1]]
        else:
            classes, kind = list(SMALL_AGG.values()), "aggregate"
            res = {g: [round(x, 4) for x in row[:-1]] + [row[-1]] for g, row in groups.items()}
        cur = out.get(iso)
        if cur is None or (kind == "detail", y) > (cur["kind"] == "detail", cur["year"]):
            out[iso] = {"year": y, "kind": kind, "classes": classes,
                        "groups": {g: r[:-1] for g, r in res.items()}, "n": {g: r[-1] for g, r in res.items()}}
    return out


def public_shares() -> dict[str, dict]:
    """Per country: share of each 2-digit occupation working in the public sector."""
    pub = ilo("DF_EMP_PUBL_SEX_OC2_NB", ".A..SEX_T.", "publ_oc2")
    tot = ilo("DF_EMP_TEMP_SEX_OC2_NB", ".A..SEX_T+SEX_F+SEX_M.", "oc2_sex")
    tot = [r for r in tot if r["SEX"] == "SEX_T"]
    keep = lambda rows, dim: [r for r in rows if r[dim].startswith("OC2_ISCO08_") and r[dim][-2:].isdigit()]  # noqa: E731
    pub_by: dict[tuple[str, int], dict[str, float]] = defaultdict(dict)
    for r in keep(pub, "OC2"):
        try:
            pub_by[(r["REF_AREA"], int(r["TIME_PERIOD"]))][r["OC2"][-2:]] = float(r["OBS_VALUE"])
        except (TypeError, ValueError):
            pass
    tot_by: dict[tuple[str, int], dict[str, float]] = defaultdict(dict)
    for r in keep(tot, "OC2"):
        try:
            tot_by[(r["REF_AREA"], int(r["TIME_PERIOD"]))][r["OC2"][-2:]] = float(r["OBS_VALUE"])
        except (TypeError, ValueError):
            pass
    out: dict[str, dict] = {}
    for (iso, y), p in pub_by.items():
        t = tot_by.get((iso, y))
        if not t:
            continue
        shares = {g: round(min(1.0, p.get(g, 0.0) / n), 4) for g, n in t.items() if n > 0}
        if len(shares) < 20 or (iso in out and out[iso]["year"] >= y):
            continue
        out[iso] = {"year": y, "by2": shares, "employed": {g: n for g, n in t.items()}}
    return out


def pooled(per: dict[str, dict], members: list[str]) -> dict | None:
    """Employment-weighted average workplace-size shares of countries publishing detail classes."""
    acc: dict[str, list[float]] = {}
    for iso in members:
        rec = per.get(iso)
        if not rec or rec["kind"] != "detail":
            continue
        for g, shares in rec["groups"].items():
            n = rec["n"].get(g, 0)
            cur = acc.setdefault(g, [0.0] * len(shares))
            for i, s in enumerate(shares):
                cur[i] += s * n
    if "all" not in acc:
        return None
    return {g: [round(x / sum(v), 4) for x in v] for g, v in acc.items() if sum(v) > 0}


def main() -> None:
    cs = countries()
    print("US Census SUSB: enterprise sizes")
    us = us_shape()
    print("OECD SDBS: enterprise sizes")
    mid = oecd_mid_share()
    mid["USA"] = (us["mid_share_of_50plus"], us["year"])
    print(f"  {len(mid)} countries")
    print("ILOSTAT: employment by job group and workplace size")
    work = workplaces()
    print(f"  {len(work)} countries ({sum(1 for w in work.values() if w['kind'] == 'detail')} with detailed classes)")
    print("ILOSTAT: public-sector employment by 2-digit occupation")
    pub = public_shares()
    print(f"  {len(pub)} countries")

    by_income: dict[str, list[str]] = defaultdict(list)
    for iso, c in cs.items():
        by_income[c.income].append(iso)
    pool_work = {inc: pooled(work, isos) for inc, isos in by_income.items()}
    pool_all = pooled(work, list(work))

    def pool_mid(inc: str) -> tuple[float, str]:
        isos = [i for i in by_income[inc] if i in mid]
        src = f"average of {len(isos)} countries at the same income level (OECD, US Census)"
        if not isos:
            isos, src = list(mid), f"average of all {len(mid)} countries with enterprise data (OECD, US Census)"
        weights = [sum(pub.get(i, {}).get("employed", {}).values()) or 1.0 for i in isos]
        return round(sum(mid[i][0] * w for i, w in zip(isos, weights)) / sum(weights), 4), src

    def pool_pub(inc: str) -> tuple[dict[str, float], str]:
        isos = [i for i in by_income[inc] if i in pub] or list(pub)
        acc_p: dict[str, float] = defaultdict(float)
        acc_t: dict[str, float] = defaultdict(float)
        for i in isos:
            for g, n in pub[i]["employed"].items():
                acc_t[g] += n
                acc_p[g] += n * pub[i]["by2"].get(g, 0.0)
        return {g: round(acc_p[g] / acc_t[g], 4) for g in acc_t if acc_t[g] > 0}, f"average of {len(isos)} countries at the same income level (ILOSTAT)"

    out: dict[str, dict] = {}
    for iso, c in cs.items():
        if not c.simulatable:
            continue
        rec: dict = {}
        w = work.get(iso)
        if w:
            rec["workplace"] = {"classes": w["classes"], "groups": w["groups"],
                                "source": f"ILOSTAT workplace size by occupation, {w['year']}"}
        else:
            p = pool_work.get(c.income) or pool_all
            label = f"average of surveyed countries at the same income level ({c.income}), ILOSTAT" if pool_work.get(c.income) else "average of all surveyed countries, ILOSTAT"
            rec["workplace"] = {"classes": list(SMALL_DETAIL.values()), "groups": p, "source": label}
        if iso in mid:
            share, y = mid[iso]
            rec["mid_share_of_50plus"] = round(share, 4)
            rec["enterprise_source"] = "US Census SUSB 2022" if iso == "USA" else f"OECD Structural Business Statistics {y}"
        else:
            rec["mid_share_of_50plus"], rec["enterprise_source"] = pool_mid(c.income)
        if iso in pub:
            rec["public"] = {"by2": pub[iso]["by2"], "source": f"ILOSTAT public-sector employment, {pub[iso]['year']}"}
        else:
            shares, src = pool_pub(c.income)
            rec["public"] = {"by2": shares, "source": src}
        out[iso] = rec

    OUT.write_text(json.dumps({
        "_meta": {
            "built": date.today().isoformat(),
            "sources": [
                "ILOSTAT DF_EMP_TEMP_SEX_OCU_EST_NB: employment by occupation and workplace size (CC BY 4.0)",
                "ILOSTAT DF_EMP_PUBL_SEX_OC2_NB and DF_EMP_TEMP_SEX_OC2_NB: public-sector employment by 2-digit occupation (CC BY 4.0)",
                "OECD Structural Business Statistics DF_SDBS_ISIC4, persons employed by enterprise size, BTNXK (CC BY 4.0)",
                "US Census Bureau, Statistics of US Businesses 2022 (public domain)",
            ],
            "note": "Workplace size below 50 people is the size of the workplace (household surveys), above 50 the size of the enterprise (business registers); people at small branches of large firms are counted as small. Classes inside 50-249 and 250+ use the US shape everywhere.",
            "mid_classes": MID,
            "large_classes": LARGE,
            "us_mid": us["mid"],
            "us_large": us["large"],
        },
        "countries": out,
    }, separators=(",", ":")), encoding="utf-8")
    own = sum(1 for r in out.values() if r["workplace"]["source"].startswith("ILOSTAT workplace"))
    print(f"wrote {OUT}: {len(out)} countries, {own} with their own workplace survey, {sum(1 for i in out if i in mid)} with enterprise data")


if __name__ == "__main__":
    main()
