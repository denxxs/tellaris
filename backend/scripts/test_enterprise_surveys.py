"""Test whether World Bank Enterprise Surveys improve company sizes where ILOSTAT has no workplace survey.

The Enterprise Surveys (Standardized Raw Database 2006-2025, the user's own download under the World
Bank Data Access Protocol; never committed) cover formal private firms with 5+ employees in ~170
countries. For countries that also have ILOSTAT workplace-size data or OECD enterprise data, this
compares four estimates against the truth: the Enterprise Survey shape directly, the income-group
average used now, and the income-group average adjusted by how the country's Enterprise Survey shape
differs from its peers' (adjustment fitted leaving the tested country out). Result (Oct 2026): the
Enterprise Surveys did not beat the income-group average in either test, so firms.json does not use
them. Writes docs/enterprise_surveys_test.json.

    python scripts/test_enterprise_surveys.py   (needs the Standardized Raw Database .dta in var/datasets/enterprise-surveys/)
"""
import re
import sys
from collections import defaultdict

import numpy as np
import pandas as pd
import pycountry

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))
import build_firms as bf  # noqa: E402
from oracle.world.countries import countries  # noqa: E402

ALIAS = {"DRC": "COD", "Congo": "COG", "Kosovo": "XKX", "Turkiye": "TUR", "Türkiye": "TUR", "Russia": "RUS", "Moldova": "MDA",
         "Bolivia": "BOL", "Venezuela": "VEN", "Tanzania": "TZA", "Laos": "LAO", "Lao PDR": "LAO", "Vietnam": "VNM",
         "Iran": "IRN", "Syria": "SYR", "Cote dIvoire": "CIV", "CotedIvoire": "CIV", "WestBankAndGaza": "PSE",
         "West Bank and Gaza": "PSE", "Micronesia": "FSM", "Taiwan": "TWN", "Korea": "KOR", "SouthSudan": "SSD",
         "Gambia": "GMB", "Bahamas": "BHS", "Kyrgyz Republic": "KGZ", "KyrgyzRepublic": "KGZ", "Slovak Republic": "SVK",
         "SlovakRepublic": "SVK", "Egypt": "EGY", "Yemen": "YEM", "NorthMacedonia": "MKD", "Macedonia": "MKD",
         "FYROM": "MKD", "CzechRepublic": "CZE", "Czechia": "CZE", "Eswatini": "SWZ", "Swaziland": "SWZ", "Timor-Leste": "TLS",
         "TimorLeste": "TLS", "CaboVerde": "CPV", "Cabo Verde": "CPV", "CapeVerde": "CPV", "St Lucia": "LCA", "StLucia": "LCA",
         "St Vincent and Grenadines": "VCT", "StVincentandGrenadines": "VCT", "St Kitts and Nevis": "KNA", "StKittsandNevis": "KNA",
         "BosniaandHerzegovina": "BIH", "Bosnia and Herzegovina": "BIH", "Antigua and Barbuda": "ATG", "AntiguaandBarbuda": "ATG"}


def iso_of(name):
    if name in ALIAS:
        return ALIAS[name]
    for cand in (name, re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name)):
        if cand in ALIAS:
            return ALIAS[cand]
        try:
            return pycountry.countries.lookup(cand).alpha_3
        except LookupError:
            try:
                return pycountry.countries.search_fuzzy(cand)[0].alpha_3
            except LookupError:
                pass
    return None


CORE = ROOT / "var/datasets/enterprise-surveys/es_core.parquet"
if not CORE.exists():  # first run: read the needed columns from the user's Stata file
    import glob

    import pyreadstat

    dta = sorted(glob.glob(str(ROOT / "var/datasets/enterprise-surveys/*.dta")))[-1]
    pyreadstat.read_dta(dta, usecols=["country", "idstd", "wt", "size_num"], apply_value_formats=False)[0].to_parquet(CORE)
d = pd.read_parquet(CORE)
d["name"] = d.country.str.replace(r"\d{4}$", "", regex=True).str.strip()
d["year"] = d.country.str[-4:].astype(int)
d["iso"] = d.name.map({n: iso_of(n) for n in d.name.unique()})
print("unmapped", sorted(d[d.iso.isna()].name.unique()))
d = d[d.iso.notna() & (d.size_num >= 5)]
latest = d.groupby("iso").year.transform("max")
d = d[d.year == latest]
d["w"] = d.wt * d.size_num
EDGES = [5, 10, 20, 50, 250, np.inf]
d["cls"] = pd.cut(d.size_num, EDGES, right=False, labels=False)
es = {}
for iso, g in d.groupby("iso"):
    t = g.groupby("cls").w.sum().reindex(range(5), fill_value=0.0)
    if t.sum() > 0 and len(g) >= 100:
        es[iso] = {"year": int(g.year.iloc[0]), "n": len(g), "shares": (t / t.sum()).tolist()}
print(len(es), "countries with an ES shape")

cs = countries()
work = bf.workplaces()
mid = bf.oecd_mid_share()
by_income = defaultdict(list)
for i, c in cs.items():
    by_income[c.income].append(i)


def within5(sh):  # ILO detail: [1, 2-4, 5-9, 10-19, 20-49, 50+] -> shares within 5+ of 5-9, 10-19, 20-49, 50+
    s = sh[2:]
    return np.array(s) / sum(s)


def es4(s):
    return np.array(s[:3] + [s[3] + s[4]])


errs_es, errs_pool = [], []
for iso, rec in work.items():
    if rec["kind"] != "detail" or iso not in es or iso not in cs:
        continue
    truth = within5(rec["groups"]["all"])
    others = [i for i in by_income[cs[iso].income] if i != iso]
    p = bf.pooled(work, others)
    if not p:
        continue
    errs_es.append(np.abs(es4(es[iso]["shares"]) - truth).sum() / 2)
    errs_pool.append(np.abs(within5(p["all"]) - truth).sum() / 2)
print(f"within-5+ shape, {len(errs_es)} countries with both: ES error {np.median(errs_es):.3f} vs income-group average {np.median(errs_pool):.3f} (median share misplaced)")

e1, e2 = [], []
for iso, (share, y) in mid.items():
    if iso not in es or iso not in cs:
        continue
    s = es[iso]["shares"]
    es_mid = s[3] / (s[3] + s[4]) if s[3] + s[4] > 0 else None
    others = [i for i in by_income[cs[iso].income] if i in mid and i != iso]
    pool = np.mean([mid[i][0] for i in others]) if others else None
    if es_mid is not None and pool is not None:
        e1.append(abs(es_mid - share))
        e2.append(abs(pool - share))
print(f"50-249 share of 50+, {len(e1)} countries with both: ES error {np.median(e1):.3f} vs income-group average {np.median(e2):.3f}")
fallback = [i for i, c in cs.items() if c.simulatable and i not in work and i != "IND"]
print("fallback countries", len(fallback), "covered by ES", sum(i in es for i in fallback))
nomid = [i for i, c in cs.items() if c.simulatable and i not in mid]
print("no OECD mid", len(nomid), "covered by ES", sum(i in es for i in nomid))

# Does a country's ES deviation from its income group's ES average predict its true deviation?
def es_pool(isos):
    v = [es4(es[i]["shares"]) for i in isos if i in es]
    return np.mean(v, axis=0) if v else None

rows = []
for iso, rec in work.items():
    if rec["kind"] != "detail" or iso not in es or iso not in cs:
        continue
    others = [i for i in by_income[cs[iso].income] if i != iso]
    p = bf.pooled(work, others); ep = es_pool([o for o in others if o in work])
    if not p or ep is None:
        continue
    rows.append((iso, within5(rec["groups"]["all"]), within5(p["all"]), es4(es[iso]["shares"]) - ep))
for beta in (0.0, 0.1, 0.2, 0.3, 0.5):
    e = [np.abs(np.clip(pool + beta * dev, 0, None) / np.clip(pool + beta * dev, 0, None).sum() - t).sum() / 2 for _, t, pool, dev in rows]
    print(f"shape: beta {beta}: median error {np.median(e):.3f}")
# leave-one-out beta by least squares
errs = []
for k in range(len(rows)):
    tr = [r for j, r in enumerate(rows) if j != k]
    X = np.concatenate([r[3] for r in tr]); Y = np.concatenate([r[1] - r[2] for r in tr])
    b = float(X @ Y / (X @ X))
    _, t, pool, dev = rows[k]
    est = np.clip(pool + b * dev, 0, None); est /= est.sum()
    errs.append(np.abs(est - t).sum() / 2)
X = np.concatenate([r[3] for r in rows]); Y = np.concatenate([r[1] - r[2] for r in rows])
print(f"LOO-fitted beta {X @ Y / (X @ X):.3f}: median error {np.median(errs):.3f}; corr {np.corrcoef(X, Y)[0,1]:.3f}")

m = []
for iso, (share, y) in mid.items():
    if iso not in es or iso not in cs: continue
    s = es[iso]["shares"]
    others = [i for i in by_income[cs[iso].income] if i in mid and i != iso and i in es]
    if not others or s[3] + s[4] == 0: continue
    pool = np.mean([mid[i][0] for i in others])
    esp = np.mean([es[i]["shares"][3] / (es[i]["shares"][3] + es[i]["shares"][4]) for i in others])
    m.append((share - pool, s[3] / (s[3] + s[4]) - esp))
m = np.array(m)
print(f"mid share: corr of ES deviation with true deviation {np.corrcoef(m[:,0], m[:,1])[0,1]:.3f} (n={len(m)})")
e_pool, e_adj = [], []
for k in range(len(m)):
    tr = np.delete(m, k, axis=0)
    b = float(tr[:,1] @ tr[:,0] / (tr[:,1] @ tr[:,1]))
    e_pool.append(abs(m[k,0])); e_adj.append(abs(m[k,0] - b * m[k,1]))
print(f"mid share LOO: pool error {np.median(e_pool):.3f} mean {np.mean(e_pool):.3f}; adjusted {np.median(e_adj):.3f} mean {np.mean(e_adj):.3f}; beta {m[:,1] @ m[:,0] / (m[:,1] @ m[:,1]):.3f}")

import json  # noqa: E402

(ROOT.parent / "docs" / "enterprise_surveys_test.json").write_text(json.dumps({
    "source": "World Bank Enterprise Surveys, Standardized Raw Database 2006-2025 (latest survey per country, firms with 5+ employees, workers = weight x full-time employees)",
    "countries_with_es": len(es),
    "within_5plus_shape": {"countries": len(errs_es), "median_share_misplaced_es_direct": round(float(np.median(errs_es)), 3),
                            "median_share_misplaced_income_group_average": round(float(np.median(errs_pool)), 3),
                            "median_share_misplaced_adjusted_loo": round(float(np.median(errs)), 3),
                            "correlation_es_deviation_vs_true_deviation": round(float(np.corrcoef(X, Y)[0, 1]), 3)},
    "mid_share_of_50plus": {"countries": int(len(m)), "median_abs_error_es_direct": round(float(np.median(e1)), 3),
                            "median_abs_error_income_group_average": round(float(np.median(e_pool)), 3),
                            "median_abs_error_adjusted_loo": round(float(np.median(e_adj)), 3),
                            "correlation_es_deviation_vs_true_deviation": round(float(np.corrcoef(m[:, 0], m[:, 1])[0, 1]), 3)},
    "decision": "Not used: no estimate built from the Enterprise Surveys beat the income-group average on countries where the truth is known.",
}, indent=1), encoding="utf-8")
