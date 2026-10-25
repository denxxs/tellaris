"""Build the pool of real survey respondents that simulated people are matched to.

Source: World Values Survey wave 7 (2017-2022), country-pooled file v6.0.
Haerpfer, C., Inglehart, R., Moreno, A., Welzel, C., Kizilova, K., Diez-Medrano J., M. Lagos,
P. Norris, E. Ponarin & B. Puranen (eds.). 2022. World Values Survey: Round Seven - Country-Pooled
Datafile Version 6.0. Madrid, Spain & Vienna, Austria: JD Systems Institute & WVSA Secretariat.
doi:10.14281/18241.24

WVS data may be used for non-commercial research and must not be redistributed, so neither the
download nor this pool is committed. Download "WVS Cross-National Wave 7 csv v6 0.zip" from
https://www.worldvaluessurvey.org/WVSDocumentationWV7.jsp into backend/var/datasets/ and run:

    python scripts/build_views.py

It writes backend/var/datasets/wvs_pool.json. Without it, people simply carry no survey views.

Optional: the joint EVS/WVS 2017-2022 file (v5.0, CSV) from
https://www.worldvaluessurvey.org/WVSEVSjoint2017.jsp in backend/var/datasets/wvs_evs/ adds the
European Values Study countries that WVS7 doesn't cover (same licence terms). Only the questions
both surveys share are in it, so those respondents leave the others empty.

Optional: regional barometers (Afrobarometer, Latinobarometro, Arab Barometer, Asian Barometer) in
backend/var/datasets/<name>/, read by scripts/barometers.py, add countries neither WVS nor EVS
covers, with only the questions that pass a comparison with WVS (docs/views_harmonisation.json).
"""

from __future__ import annotations

import io
import json
import sys
import zipfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from oracle.population.views import MATCH_COLUMNS, POOL_PATH, QUESTIONS  # noqa: E402  (POOL_PATH follows ORACLE_VAR_DIR)
from oracle.world.countries import countries  # noqa: E402

FOLDER = ROOT / "var" / "datasets"
DONORS = 3  # most similar surveyed countries a country without a survey borrows from
LEAVE_REGION = 1.0  # log income gap beyond which the stand-ins come from any region
REPORT_PATH = ROOT.parent / "docs" / "views_harmonisation.json"  # aggregate test results only (no microdata)


# Joint EVS/WVS 2017-2022 (v5.0): adds the European Values Study countries WVS7 doesn't cover.
# Only the common core is in the joint file, so EVS respondents have no answer for the questions
# missing below (news habits, technology, banks, TV...), and no occupation; those stay empty.
JOINT_GLOB = "wvs_evs/*EVS_WVS_Joint_Csv*.zip"
JOINT_CITATION = ("EVS/WVS (2024). European Values Study and World Values Survey: Joint EVS/WVS 2017-2022 Dataset "
                  "(Joint EVS/WVS). JD Systems Institute & WVSA. Dataset Version 5.0.0, doi:10.14281/18241.26")
JOINT_OF_WVS = {  # WVS7 column -> joint column (from the official variable correspondence)
    "Q260": "X001", "Q262": "X003", "Q279": "X028",
    "Q57": "A165", "Q61": "G007_34_B", "Q63": "G007_36_B", "Q77": "E069_13", "Q71": "E069_11", "Q66": "E069_04",
    "Q109": "E039", "Q106": "E035", "Q107": "E036", "Q111": "B008", "Q240": "E033", "Q6": "A006", "Q48": "A173",
}


def _steps(inc, weight) -> dict[int, tuple[float, float]]:
    """Where each income step sits in the country's weighted sample: (share below, share at or below),
    so it can be compared with a simulated person's earnings percentile."""
    import pandas as pd

    ok = inc.between(1, 10)
    steps = pd.Series(weight[ok].values, index=inc[ok].astype(int).values).groupby(level=0).sum().sort_index()
    cum = (steps.cumsum() / steps.sum()).to_dict()
    lo_of, prev = {}, 0.0
    for st, c in cum.items():
        lo_of[int(st)] = (round(prev, 4), round(c, 4))
        prev = c
    return lo_of


def _rows(g, answer_cols: list[str]) -> list[list]:
    """Standard rows from a frame with WVS7 column names (missing answer columns = no data)."""
    import pandas as pd

    g = g[(g["Q260"].isin([1, 2])) & (g["Q262"] >= 15)]
    lo_of = _steps(g["Q288"], g["W"]) if "Q288" in g else {}
    rows = []
    for _, d in g.iterrows():
        inc = d.get("Q288")
        lo, hi = lo_of.get(int(inc), (None, None)) if pd.notna(inc) and 1 <= inc <= 10 else (None, None)
        occ = d.get("Q281")
        answers = [int(d[c]) if c in d and pd.notna(d[c]) and int(d[c]) > 0 else None for c in answer_cols]
        rows.append([int(d["Q260"]), int(d["Q262"]), int(d["Q279"]),
                     int(occ) if occ is not None and pd.notna(occ) else -1, lo, hi, round(float(d["W"]), 4), *answers])
    return rows


def main() -> None:
    import pandas as pd

    zips = sorted(FOLDER.glob("*WVS_Cross-National_Wave_7_csv*.zip"))
    if not zips:
        print(f"put the WVS wave 7 csv zip in {FOLDER} first")
        return
    z = zipfile.ZipFile(zips[-1])
    name = next(n for n in z.namelist() if n.lower().endswith(".csv"))
    answer_cols = [q.column for q in QUESTIONS]
    cols = ["B_COUNTRY_ALPHA", "A_YEAR", "W_WEIGHT", *MATCH_COLUMNS, *answer_cols]
    df = pd.read_csv(io.TextIOWrapper(z.open(name), encoding="utf-8"), usecols=cols, low_memory=False)
    known = countries()
    out: dict[str, dict] = {}
    for iso, g in df.groupby("B_COUNTRY_ALPHA"):
        if iso not in known:
            continue  # Northern Ireland: the UK has its own sample
        rows = _rows(g.rename(columns={"W_WEIGHT": "W"}), answer_cols)
        out[iso] = {"year": int(g["A_YEAR"].max()), "source": "World Values Survey", "rows": rows,
                    "sources": [{"name": "World Values Survey", "year": int(g["A_YEAR"].max())}], "row_src": [0] * len(rows)}
    sources = [f"World Values Survey wave 7, {zips[-1].name}"]

    joint = sorted(FOLDER.glob(JOINT_GLOB))
    if joint:
        jz = zipfile.ZipFile(joint[-1])
        jname = next(n for n in jz.namelist() if n.lower().endswith(".csv"))
        jcols = ["study", "cntry", "year", "gwght", "X047E_EVS5", *JOINT_OF_WVS.values()]
        j = pd.read_csv(io.TextIOWrapper(jz.open(jname), encoding="utf-8", errors="replace"), usecols=jcols, low_memory=False)
        j = j[j["study"] == 1]  # EVS part; WVS respondents are already in from the full WVS7 file
        by_num = {int(c.iso_num): i for i, c in known.items() if str(getattr(c, "iso_num", "") or "").isdigit()}
        j = j.rename(columns={v: k for k, v in JOINT_OF_WVS.items()} | {"gwght": "W", "X047E_EVS5": "Q288"})
        added = []
        for num, g in j.groupby("cntry"):
            iso = by_num.get(int(num))
            if not iso or iso in out:
                continue  # WVS7 has the fuller questionnaire for countries in both
            g = g.where(g >= 0)  # negative codes are missing answers
            g["Q279"] = g["Q279"].fillna(0)
            rows = _rows(g, answer_cols)
            out[iso] = {"year": int(g["year"].max()), "source": "European Values Study", "rows": rows,
                        "sources": [{"name": "European Values Study", "year": int(g["year"].max())}], "row_src": [0] * len(rows)}
            added.append(iso)
        sources.append(f"Joint EVS/WVS 2017-2022 v5.0 (EVS countries not in WVS7: {len(added)})")
        print(f"EVS: added {len(added)} countries: {', '.join(sorted(added))}")

    # Regional barometers, for countries WVS and EVS don't cover. Only questions that came out close
    # to WVS in countries both surveyed are kept (barometers.validate); the test is saved for the paper.
    report, report_doc = {}, {}
    try:
        import barometers
    except ImportError:
        barometers = None
    if barometers is not None:
        report = barometers.validate(df)
        base = set(out)
        added: dict[str, list[str]] = {}
        series_done: set[tuple[str, str]] = set()  # (survey series, country): newest wave only
        for src in barometers.SOURCES:  # listed newest first within each series
            d = barometers.load(src.name)
            if d.empty:
                continue
            series = src.name.split(" Wave")[0].split(" Round")[0].split(" 20")[0]
            kept = [c for c, r in report.get(src.name, {}).items() if r["kept"]]
            for iso, g in d.groupby("iso"):
                if iso in base or iso not in known or (series, iso) in series_done:
                    continue
                series_done.add((series, iso))
                rows = _rows(g[["W", "Q260", "Q262", "Q279", *kept]], answer_cols)
                rec = out.setdefault(iso, {"year": 0, "source": "", "rows": [], "sources": [], "row_src": []})
                rec["row_src"] += [len(rec["sources"])] * len(rows)
                rec["sources"].append({"name": src.label, "year": int(g["year"].max())})
                rec["rows"] += rows
                rec["year"] = max(rec["year"], int(g["year"].max()))
                rec["source"] = " + ".join(x for x in (rec["source"], src.label) if x)
                added.setdefault(src.name, []).append(iso)
        for name, isos in added.items():
            sources.append(f"{name} ({len(isos)} countries not in WVS/EVS)")
            print(f"{name}: added {', '.join(sorted(isos))}")
        report_doc = {
            "note": "Gap between a barometer's and WVS7's average answer (0-1 scale) in countries both surveyed. "
                    "A question is used for a barometer only when the median gap is at most 0.10 over 3+ countries.",
            "sources": {s.name: s.citation for s in barometers.SOURCES},
            "questions": {name: {q: {k: v for k, v in r.items()} for q, r in items.items()} for name, items in report.items()},
        }

    # Countries no survey covers borrow respondents from the 3 most similar fully surveyed (WVS7)
    # countries: same World Bank region and closest income per person, leaving the region when its
    # closest 3 differ by more than e^1 (2.7x) in income. Chosen by hiding each WVS country and
    # comparing rules (see donor_test below and docs/views_harmonisation.json). Every borrowed
    # answer says where it came from.
    import math

    import numpy as np

    full = {i for i, v in out.items() if v["source"] == "World Values Survey" and known[i].gdp_pc_usd}

    def donors(iso: str, cand: set[str]) -> list[str]:
        g = math.log(known[iso].gdp_pc_usd)
        near = lambda d: abs(math.log(known[d].gdp_pc_usd) - g)  # noqa: E731
        same = sorted((d for d in cand if known[d].region == known[iso].region), key=near)[:DONORS]
        if len(same) == DONORS and near(same[-1]) <= LEAVE_REGION:
            return same
        return sorted(cand, key=near)[:DONORS]

    def profile(rows: list[list]) -> dict[str, float]:
        res = {}
        for qi, q in enumerate(QUESTIONS):
            codes = [v for v in range(0, 12) if q.score(v) is not None and q.text(v) is not None]
            if not codes:
                continue  # unordered answers (how society should change): no average to compare
            lo, hi = min(q.score(v) for v in codes), max(q.score(v) for v in codes)
            pairs = [(q.score(r[7 + qi]), r[6]) for r in rows if r[7 + qi] is not None and q.score(r[7 + qi]) is not None]
            if len(pairs) >= 30:
                v, w = np.array(pairs).T
                res[q.key] = float(np.average((v - lo) / (hi - lo), weights=w))
        return res

    prof = {i: profile(out[i]["rows"]) for i in full}

    def gap(t: str, ds: list[str]) -> float:
        keys = set(prof[t]).intersection(*[set(prof[d]) for d in ds])
        return float(np.mean([abs(prof[t][k] - np.mean([prof[d][k] for d in ds])) for k in keys]))

    chosen = [gap(t, donors(t, full - {t})) for t in full]
    base = [float(np.mean([gap(t, [d]) for d in full - {t} if known[d].region == known[t].region] or [np.nan])) for t in full]
    base = [b for b in base if not np.isnan(b)]
    donor_test = {"rule": f"{DONORS} closest WVS7 countries by income per person in the same World Bank region (anywhere if those differ by more than e^{LEAVE_REGION} in income)",
                  "tested_on": len(full), "median_gap": round(float(np.median(chosen)), 3), "mean_gap": round(float(np.mean(chosen)), 3),
                  "p90_gap": round(float(np.percentile(chosen, 90)), 3),
                  "baseline_random_same_region_median_gap": round(float(np.median(base)), 3),
                  "note": "Gap = mean over questions of |average answer of the stand-ins - real average answer| on a 0-1 scale, "
                          "each WVS7 country hidden in turn. Also tried: 1, 2 or 5 stand-ins; closest income anywhere; strongest Meta friendship tie (all worse or no better). "
                          "Checked again on 72 barometer-only countries (their own questions): median gap 0.088 with this rule vs 0.091 staying in the region; "
                          "Qatar 0.18 vs 0.23, so rich Gulf states take high-income stand-ins rather than poorer Arab neighbours."}
    print(f"stand-in test: median gap {donor_test['median_gap']} vs {donor_test['baseline_random_same_region_median_gap']} for a random country in the region")
    borrowed = []
    for iso, c in known.items():
        if iso in out or not c.simulatable or not c.gdp_pc_usd:
            continue
        pick = donors(iso, full)
        rec = {"year": 0, "source": "", "rows": [], "sources": [], "row_src": [], "borrowed_from": pick}
        for d in pick:
            src = out[d]
            total = sum(r[6] for r in src["rows"]) or 1.0
            rows = [[*r[:6], round(r[6] / total, 8), *r[7:]] for r in src["rows"]]  # each donor counts equally
            rec["row_src"] += [len(rec["sources"])] * len(rows)
            rec["sources"].append({"name": src["sources"][0]["name"], "year": src["year"], "borrowed_from": d})
            rec["rows"] += rows
            rec["year"] = max(rec["year"], src["year"])
        rec["source"] = f"borrowed from {', '.join(pick)} (no survey covers this country)"
        out[iso] = rec
        borrowed.append(iso)
    if borrowed:
        sources.append(f"{len(borrowed)} countries without any survey borrow from the {DONORS} most similar WVS7 countries (same region, closest income)")
        print(f"borrowed for {len(borrowed)} countries: {', '.join(sorted(borrowed))}")

    REPORT_PATH.write_text(json.dumps({**report_doc, "countries_without_a_survey": donor_test}, indent=1), encoding="utf-8")

    POOL_PATH.parent.mkdir(parents=True, exist_ok=True)
    POOL_PATH.write_text(json.dumps({
        "_meta": {
            "built": date.today().isoformat(),
            "source": "; ".join(sources),
            "citation": "Haerpfer et al. (eds.) 2022. World Values Survey: Round Seven - Country-Pooled Datafile Version 6.0. doi:10.14281/18241.24"
                        + (f"; {JOINT_CITATION}" if joint else ""),
            "licence": "Non-commercial use; redistribution prohibited. Not committed.",
            "row": ["sex", "age", "work", "occupation", "income_lo", "income_hi", "weight", *[q.key for q in QUESTIONS]],
        },
        "countries": out,
    }, separators=(",", ":")), encoding="utf-8")
    n = sum(len(v["rows"]) for v in out.values())
    print(f"wrote {POOL_PATH}: {n:,} respondents in {len(out)} countries")


if __name__ == "__main__":
    main()
