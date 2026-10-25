"""Build oracle/data/contacts.json: how many people of each age someone talks to on a typical day.

Source: Prem K, van Zandvoort K, Klepac P, et al. (2021) "Projecting contact matrices in 177
geographical regions: an update and comparison with empirical data for the COVID-19 era."
PLOS Computational Biology 17(7): e1009098. doi:10.1371/journal.pcbi.1009098 (article CC BY 4.0;
matrices from the GPL-3.0 repository below, corrected version of Oct 2022).
The matrices extend the POLYMOD and other diary surveys (a contact = a conversation of at least a
few words, or touch) to 177 countries using each country's household, school and work data.

Download synthetic_contacts_2021.csv from
https://github.com/kieshaprem/synthetic-contact-matrices (generate_synthetic_matrices/output/
syntheticmatrices/) into backend/var/datasets/prem/ and run:

    python scripts/build_contacts.py

Only people aged 15+ are simulated, so only contacts between those ages are kept. Countries the
study doesn't cover use the adult-population-weighted average of covered countries at the same
World Bank income level, and say so.

How unequal contacts are between people (some meet 3 people a day, some 40) comes from diary
surveys on socialcontactdata.org (CC BY 4.0, normal times, adults 15+): the negative binomial
dispersion k of contacts per person per day (variance = mean + mean^2 / k). Download each
record's participant_common, contact_common and sday CSVs from Zenodo into
backend/var/datasets/contacts_surveys/<record id>/. Countries without a survey use the median k.
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
SURVEYS_DIR = ROOT / "var" / "datasets" / "contacts_surveys"
# Zenodo record -> countries it covers, and the citation. Pre- and post-pandemic diaries only.
SURVEYS = {
    "3874674": (["RUS"], "Litvinova et al. 2019, Russia 2016 (doi:10.5281/zenodo.3874674)"),
    "3874675": (["ZMB", "ZAF"], "Dodd et al. 2016, Zambia and South Africa 2011 (doi:10.5281/zenodo.3874675)"),
    "3878754": (["CHN"], "Zhang et al. 2019, China 2017-18 (doi:10.5281/zenodo.3878754)"),
    "4302055": (["BEL"], "Willem et al. 2012, Belgium 2010-11 (doi:10.5281/zenodo.4302055)"),
    "4739777": (["THA"], "Meeyai et al. 2015, Thailand (doi:10.5281/zenodo.4739777)"),
    "4086739": (["THA"], "Wirya et al. 2020, Thailand 2015 (doi:10.5281/zenodo.4086739)"),
    "5062244": (["NLD"], "van de Kassteele et al. 2017, Netherlands 2006-07 (doi:10.5281/zenodo.5062244)"),
    "6385759": (["TWN"], "Fu et al. 2012, Taiwan 2010 (doi:10.5281/zenodo.6385759)"),
    "13101862": (["GMB"], "Gambia BHDSS/FWHDSS 2022 (doi:10.5281/zenodo.13101862)"),
    "17579537": (["ITA"], "MixIT, Italy 2022-23 (doi:10.5281/zenodo.17579537)"),
}


def _nb_k(x) -> float:
    """Maximum-likelihood negative binomial dispersion k, mean fixed at the sample mean."""
    import numpy as np
    from scipy import optimize, special

    mu = float(x.mean())

    def nll(logk: float) -> float:
        k = np.exp(logk)
        return -float(np.sum(special.gammaln(x + k) - special.gammaln(k) - special.gammaln(x + 1)
                             + k * np.log(k / (k + mu)) + x * np.log(mu / (k + mu))))

    return float(np.exp(optimize.minimize_scalar(nll, bounds=(-5, 6), method="bounded").x))


def dispersion() -> dict:
    """Contacts-per-person dispersion by country from the diary surveys that are present."""
    import glob

    import numpy as np
    import pandas as pd

    counts: dict[str, list] = defaultdict(list)
    cites: dict[str, list[str]] = defaultdict(list)
    for rid, (isos, cite) in SURVEYS.items():
        d = SURVEYS_DIR / rid
        pf, cf = glob.glob(str(d / "*participant_common.csv")), glob.glob(str(d / "*contact_common.csv"))
        if not pf or not cf:
            continue
        p = pd.read_csv(pf[0], low_memory=False)
        c = pd.read_csv(cf[0], low_memory=False)
        age = p["part_age"] if "part_age" in p else p.get("part_age_exact")
        if age is None or pd.to_numeric(age, errors="coerce").isna().all():
            age = (p["part_age_est_min"] + p["part_age_est_max"]) / 2
        p["age"] = pd.to_numeric(age, errors="coerce")
        p["contacts"] = p["part_id"].map(c.groupby("part_id").size()).fillna(0)
        x = p.loc[p["age"] >= 15, "contacts"].to_numpy(float)
        for iso in isos:
            counts[iso].append(x)
            cites[iso].append(cite)
    out = {}
    for iso, xs in counts.items():
        x = np.concatenate(xs)
        out[iso] = {"k": round(_nb_k(x), 3), "people": int(len(x)), "mean": round(float(x.mean()), 2), "source": "; ".join(cites[iso])}
    ks = sorted(v["k"] for v in out.values())
    median = ks[len(ks) // 2] if len(ks) % 2 else (ks[len(ks) // 2 - 1] + ks[len(ks) // 2]) / 2 if ks else None
    return {"countries": out, "median_k": round(median, 3) if median else None,
            "note": "Negative binomial dispersion k of contacts per adult per day (variance = mean + mean^2/k), "
                    "from CC BY 4.0 diary surveys on socialcontactdata.org. Countries without a survey use median_k."}


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
    disp = dispersion()
    print(f"dispersion: {len(disp['countries'])} countries with a diary survey, median k {disp['median_k']}")
    OUT.write_text(json.dumps({
        "_meta": {
            "built": date.today().isoformat(),
            "source": "Prem et al. (2021) PLOS Comput Biol 17(7): e1009098, doi:10.1371/journal.pcbi.1009098; matrices from github.com/kieshaprem/synthetic-contact-matrices (GPL-3.0, corrected 2022 version)",
            "note": "Mean daily contacts a person in the row age band has with people in the column age band, by setting. Ages 15+ only.",
            "bands": BANDS,
            "settings": SETTINGS,
        },
        "countries": out,
        "dispersion": disp,
    }, separators=(",", ":")), encoding="utf-8")
    own = sum(1 for v in out.values() if v["source"] == "Prem et al. 2021")
    print(f"wrote {OUT}: {len(out)} countries, {own} with their own matrices")


if __name__ == "__main__":
    main()
