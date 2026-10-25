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
        out[iso] = {"year": int(g["A_YEAR"].max()), "source": "WVS7", "rows": _rows(g.rename(columns={"W_WEIGHT": "W"}), answer_cols)}
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
            out[iso] = {"year": int(g["year"].max()), "source": "EVS 2017 (joint EVS/WVS)", "rows": _rows(g, answer_cols)}
            added.append(iso)
        sources.append(f"Joint EVS/WVS 2017-2022 v5.0 (EVS countries not in WVS7: {len(added)})")
        print(f"EVS: added {len(added)} countries: {', '.join(sorted(added))}")

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
