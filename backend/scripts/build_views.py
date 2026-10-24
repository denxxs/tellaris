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
        g = g[(g["Q260"].isin([1, 2])) & (g["Q262"] >= 15)]
        # Where each respondent places their household on the country's 1-10 income scale, turned
        # into the share of the (weighted) sample below and at their step, so it can be compared
        # with a simulated person's earnings percentile.
        inc = g[g["Q288"].between(1, 10)]
        steps = inc.groupby("Q288")["W_WEIGHT"].sum().sort_index()
        cum = (steps.cumsum() / steps.sum()).to_dict()
        lo_of, prev = {}, 0.0
        for s, c in cum.items():
            lo_of[int(s)] = (round(prev, 4), round(c, 4))
            prev = c
        rows = []
        for r in g.itertuples(index=False):
            d = r._asdict()
            lo, hi = lo_of.get(int(d["Q288"]), (None, None))
            answers = [int(d[c]) if int(d[c]) > 0 else None for c in answer_cols]
            rows.append([
                int(d["Q260"]), int(d["Q262"]), int(d["Q279"]), int(d["Q281"]),
                lo, hi, round(float(d["W_WEIGHT"]), 4), *answers,
            ])
        out[iso] = {"year": int(g["A_YEAR"].max()), "rows": rows}
    POOL_PATH.parent.mkdir(parents=True, exist_ok=True)
    POOL_PATH.write_text(json.dumps({
        "_meta": {
            "built": date.today().isoformat(),
            "source": f"World Values Survey wave 7, {zips[-1].name}",
            "citation": "Haerpfer et al. (eds.) 2022. World Values Survey: Round Seven - Country-Pooled Datafile Version 6.0. doi:10.14281/18241.24",
            "licence": "Non-commercial use; redistribution prohibited. Not committed.",
            "row": ["sex", "age", "work", "occupation", "income_lo", "income_hi", "weight", *[q.key for q in QUESTIONS]],
        },
        "countries": out,
    }, separators=(",", ":")), encoding="utf-8")
    n = sum(len(v["rows"]) for v in out.values())
    print(f"wrote {POOL_PATH}: {n:,} respondents in {len(out)} countries")


if __name__ == "__main__":
    main()
