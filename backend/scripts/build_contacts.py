"""Build oracle/data/contacts.json: how many people of each age someone talks to on a typical day.

Source: Prem K, van Zandvoort K, Klepac P, et al. (2021) "Projecting contact matrices in 177
geographical regions: an update and comparison with empirical data for the COVID-19 era."
PLOS Computational Biology 17(7): e1009098. doi:10.1371/journal.pcbi.1009098 (CC BY 4.0).
The matrices extend the POLYMOD and other diary surveys (a contact = a conversation of at least a
few words, or touch) to 177 countries using each country's household, school and work data.

Download synthetic_contacts_2021.csv from
https://github.com/kieshaprem/synthetic-contact-matrices (generate_synthetic_matrices/output/
syntheticmatrices/) into backend/var/datasets/prem/ and run:

    python scripts/build_contacts.py

Only people aged 15+ are simulated, so only contacts between those ages are kept. Countries the
study doesn't cover use the adult-population-weighted average of covered countries at the same
World Bank income level, and say so.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from oracle.world.countries import countries  # noqa: E402

SRC = ROOT / "var" / "datasets" / "prem" / "synthetic_contacts_2021.csv"
OUT = ROOT / "oracle" / "data" / "contacts.json"
BANDS = ["15 to 19", "20 to 24", "25 to 29", "30 to 34", "35 to 39", "40 to 44", "45 to 49", "50 to 54",
         "55 to 59", "60 to 64", "65 to 69", "70 to 74", "75+"]
SETTINGS = ["home", "work", "school", "others"]


def main() -> None:
    import pandas as pd

    d = pd.read_csv(SRC)
    d = d[(d.setting == "overall") & d.location_contact.isin(SETTINGS) & d.age_contactor.isin(BANDS) & d.age_cotactee.isin(BANDS)]
    idx = {b: i for i, b in enumerate(BANDS)}
    raw: dict[str, dict[str, list[list[float]]]] = {}
    for (iso, loc), g in d.groupby(["iso3c", "location_contact"]):
        m = [[0.0] * len(BANDS) for _ in BANDS]
        for r in g.itertuples(index=False):
            m[idx[r.age_contactor]][idx[r.age_cotactee]] = float(r.mean_number_of_contacts)
        raw.setdefault(iso, {})[loc] = m

    cs = countries()
    by_income: dict[str, list[str]] = defaultdict(list)
    for iso, c in cs.items():
        if iso in raw:
            by_income[c.income].append(iso)

    def average(isos: list[str]) -> dict[str, list[list[float]]]:
        w = [cs[i].adults_m or 0.0 for i in isos]
        return {s: [[sum(raw[i][s][r][c] * wi for i, wi in zip(isos, w)) / (sum(w) or 1) for c in range(len(BANDS))]
                    for r in range(len(BANDS))] for s in SETTINGS}

    out: dict[str, dict] = {}
    for iso, c in cs.items():
        if not c.simulatable:
            continue
        if iso in raw:
            m, src = raw[iso], "Prem et al. 2021"
        else:
            peers = by_income.get(c.income) or [i for v in by_income.values() for i in v]
            m, src = average(peers), f"Prem et al. 2021, average of {len(peers)} countries at the same income level"
        out[iso] = {"source": src, **{s: [[round(x, 3) for x in row] for row in m[s]] for s in SETTINGS}}
    OUT.write_text(json.dumps({
        "_meta": {
            "built": date.today().isoformat(),
            "source": "Prem et al. (2021) PLOS Comput Biol 17(7): e1009098, doi:10.1371/journal.pcbi.1009098, CC BY 4.0",
            "note": "Mean daily contacts a person in the row age band has with people in the column age band, by setting. Ages 15+ only.",
            "bands": BANDS,
            "settings": SETTINGS,
        },
        "countries": out,
    }, separators=(",", ":")), encoding="utf-8")
    own = sum(1 for v in out.values() if v["source"] == "Prem et al. 2021")
    print(f"wrote {OUT}: {len(out)} countries, {own} with their own matrices")


if __name__ == "__main__":
    main()
