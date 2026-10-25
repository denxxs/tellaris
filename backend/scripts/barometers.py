"""Regional surveys (Afrobarometer, Latinobarometro, Arab Barometer, Asian Barometer, South Asia
Barometer) recoded to the World Values Survey wave 7 columns, so their respondents can join the
pool for countries WVS and EVS don't cover.

Only questions that ask the same thing on a compatible scale are mapped. Each mapping is then
tested in countries both a barometer and WVS7 surveyed: if the barometer's answers don't come out
close to WVS's there (see `validate`), the question is dropped for that barometer. Nothing is
guessed: questions a barometer doesn't ask stay empty for its respondents.

All files are the user's own downloads in backend/var/datasets/ (see build_views.py); research use,
no redistribution.
"""

from __future__ import annotations

import re
import tempfile
import zipfile
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "var" / "datasets"

NEWS5 = {4: 1, 3: 2, 2: 3, 1: 4, 0: 5}  # every day .. never (0-4) -> WVS daily .. never (1-5)
SAME4 = {1: 1, 2: 2, 3: 3, 4: 4}
SAME2 = {1: 1, 2: 2}


@dataclass
class Source:
    name: str
    label: str  # short name shown with the respondent's answers
    citation: str
    files: list[str]  # globs under DATA; one frame per file
    pick: str = ""  # which file inside a zip
    country: str = "COUNTRY"  # column with the country (codes with value labels, or ISO numeric)
    country_is_isonum: bool = False
    weight: str | None = None
    sex: str = ""
    age: str = ""
    work: Callable[[pd.DataFrame], pd.Series] | None = None
    items: dict[str, tuple[str, dict | Callable]] = field(default_factory=dict)  # WVS column -> (source column, recode)
    year: Callable[[pd.DataFrame, str], int] | None = None


def _extract(path: Path, pick: str) -> Path:
    if path.suffix.lower() != ".zip":
        return path
    z = zipfile.ZipFile(path)
    inner = next(n for n in z.namelist() if n.lower().endswith((".sav", ".dta")) and not n.split("/")[-1].startswith("._")
                 and pick in n)
    return Path(z.extract(inner, tempfile.mkdtemp()))


def _read(path: Path) -> tuple[pd.DataFrame, dict[str, dict], dict[str, str]]:
    """Numeric codes, value labels and variable labels, column names upper-cased (files from the
    same survey differ in case)."""
    df, vl, labels = _read_raw(path)
    df.columns = [str(c).upper() for c in df.columns]
    return df, {str(k).upper(): v for k, v in vl.items()}, {str(k).upper(): v for k, v in labels.items()}


def _read_raw(path: Path) -> tuple[pd.DataFrame, dict[str, dict], dict[str, str]]:
    import pyreadstat

    if path.suffix.lower() == ".sav":
        df, m = pyreadstat.read_sav(str(path))
        return df, m.variable_value_labels, dict(zip(m.column_names, m.column_labels))
    try:
        df, m = pyreadstat.read_dta(str(path))
        return df, m.variable_value_labels, dict(zip(m.column_names, m.column_labels))
    except Exception:  # newer Stata formats pyreadstat can't read
        with pd.io.stata.StataReader(str(path)) as r:
            labels = r.variable_labels()
            vl = r.value_labels()
            lbl = dict(zip(r._varlist, r._lbllist))
        df = pd.read_stata(str(path), convert_categoricals=False)
        return df, {c: vl.get(lbl.get(c), {}) for c in df.columns}, labels


def _code(v) -> float:
    return pd.to_numeric(v, errors="coerce")


# ---------------------------------------------------------------- employment -> WVS Q279
# WVS Q279: 1 full time, 2 part time, 3 self employed, 4 retired, 5 homemaker, 6 student, 7 unemployed, 8 other.


def _work_afro(df: pd.DataFrame, vl: dict) -> pd.Series:
    status = _code(df["Q94A"])
    occ = _code(df["Q94B"])
    occ_lbl = {k: str(v).lower() for k, v in vl.get("Q94B", {}).items()}
    retired = {k for k, v in occ_lbl.items() if "retired" in v}
    out = pd.Series(8.0, index=df.index)
    out[status == 3] = 1
    out[status == 2] = 2
    out[status == 1] = 7
    out[(status == 0) & (occ == 1)] = 6
    out[(status == 0) & (occ == 2)] = 5
    out[(status <= 1) & occ.isin(retired)] = 4
    return out


def _work_latino(df: pd.DataFrame, vl: dict) -> pd.Series:
    return _code(df["S18.A"]).map({1: 3, 2: 1, 3: 1, 4: 7, 5: 4, 6: 5, 7: 6}).fillna(8)


def _work_arab(df: pd.DataFrame, vl: dict) -> pd.Series:
    """Waves V, VII, VIII: Q1005 1 employed (Q1006 full/part time), 2 self-employed, 3 retired,
    4 housewife, 5 student, 6 unemployed."""
    s = _code(df["Q1005"])
    ft = _code(df["Q1006"]) if "Q1006" in df else pd.Series(np.nan, index=df.index)
    out = s.map({2: 3, 3: 4, 4: 5, 5: 6, 6: 7}).fillna(8)
    out[s == 1] = np.where(ft[s == 1] == 2, 2, 1)
    return out


def _work_arab4(df: pd.DataFrame, vl: dict) -> pd.Series:
    """Wave IV asks the non-working status (q1005) and full/part time (q1006) separately."""
    nw = _code(df["Q1005"])
    ft = _code(df["Q1006"])
    out = nw.map({1: 4, 2: 5, 3: 6, 5: 7, 4: 8})
    out[out.isna() & (ft == 1)] = 1
    out[out.isna() & (ft == 2)] = 2
    return out.fillna(8)


def _work_asia6(df: pd.DataFrame, vl: dict) -> pd.Series:
    emp, self_ = _code(df["SE9"]), _code(df["SE9A"])
    status, seek = _code(df["SE9E"]), _code(df["SE9D"])
    out = pd.Series(8.0, index=df.index)
    out[emp == 1] = np.where(self_[emp == 1] == 1, 3, 1)
    nw = emp == 2
    out[nw] = status[nw].map({1: 5, 2: 6, 3: 4, 5: 7}).fillna(8)
    out[nw & (seek == 1)] = 7
    return out


def _left_right(v: float) -> float | None:
    """Latinobarometro's 0-10 left-right scale onto WVS's 1-10 (same ends, linear)."""
    return float(round(1 + v * 0.9)) if 0 <= v <= 10 else None


SOURCES = [
    Source(
        name="Afrobarometer Round 10 (2024-25)", label="Afrobarometer",
        citation="Afrobarometer Data, Round 10 merged dataset (38 countries), 2026. www.afrobarometer.org",
        files=["afrobarometer/AB_R10.Merge-Dataset*.release.sav.zip"], pick=".sav",
        weight="withinwt_hh", sex="Q101", age="Q1", work=_work_afro,
        items={"Q203": ("Q65A", NEWS5), "Q202": ("Q65B", NEWS5), "Q201": ("Q65C", NEWS5),
               "Q207": ("Q65D", NEWS5), "Q206": ("Q65E", NEWS5)},
    ),
    Source(
        name="Latinobarometro 2024", label="Latinobarómetro",
        citation="Latinobarometer Study 2024. Latinobarometer Corporation, v2024.1 (v20250817).",
        files=["latinobarometro/*Latinobarometro_2024_Stata*.zip"], pick="esp_v",
        country="IDENPA", country_is_isonum=True, weight="WT", sex="SEXO", age="EDAD", work=_work_latino,
        items={"Q57": ("P10STGBS", SAME2), "Q71": ("P14ST.E", SAME4), "Q67": ("P14ST.K", SAME4),
               "Q66": ("P14ST.M", SAME4), "Q240": ("P16ST", _left_right)},
    ),
    Source(
        name="Arab Barometer Wave VIII (2023-24)", label="Arab Barometer",
        citation="Arab Barometer Wave VIII (2023-2024), English release v3. www.arabbarometer.org",
        files=["arabbarometer/ArabBarometer_WaveVIII_English*.zip"], pick=".dta",
        weight="WT", sex="Q1002", age="Q1001", work=_work_arab,
        items={"Q57": ("Q103", SAME2), "Q71": ("Q201A_1", SAME4)},
    ),
    Source(
        name="Arab Barometer Wave VII (2021-22)", label="Arab Barometer",
        citation="Arab Barometer Wave VII (2021-2022), English release v6. www.arabbarometer.org",
        files=["arabbarometer/AB7_English*.zip"], pick=".dta",
        weight="WT", sex="Q1002", age="Q1001", work=_work_arab,
        items={"Q57": ("Q103", SAME2), "Q71": ("Q201A_1", SAME4)},
    ),
    Source(
        name="Arab Barometer Wave V (2018-19)", label="Arab Barometer",
        citation="Arab Barometer Wave V (2018-2019), English release v2. www.arabbarometer.org",
        files=["arabbarometer/ArabBarometer_WaveV_ENG*.zip"], pick=".dta", country="country",
        weight="wt", sex="Q1002", age="Q1001", work=_work_arab,
        items={"Q57": ("Q103", SAME2), "Q71": ("Q201A_1", SAME4)},
    ),
    Source(
        name="Arab Barometer Wave IV (2016-17)", label="Arab Barometer",
        citation="Arab Barometer Wave IV (2016-2017), English. www.arabbarometer.org",
        files=["arabbarometer/ABIV_English*.zip"], pick=".dta", country="country",
        weight="wt", sex="q1002", age="q1001", work=_work_arab4,
        items={"Q57": ("q103", SAME2), "Q71": ("q2011", SAME4),
               "Q202": ("q4061", {1: 1, 2: 2, 3: 3, 4: 4, 5: 5}), "Q201": ("q4062", {1: 1, 2: 2, 3: 3, 4: 4, 5: 5})},
    ),
    Source(
        name="Asian Barometer Wave 6 (2020-25)", label="Asian Barometer",
        citation="Asian Barometer Survey Wave 6, country releases 2023-2026. www.asianbarometer.org",
        files=["asianbarometer/W6_*.zip"], pick=".dta", country="country",
        weight="w", sex="SE2", age="SE3_1", work=_work_asia6,
        items={"Q57": ("q22", SAME2), "Q71": ("q9", SAME4)},
    ),
]


def _iso_of_label(label: str) -> str | None:
    from oracle.world.countries import resolve

    name = re.sub(r"^\s*\d+\s*:\s*", "", str(label)).strip()
    fixes = {"hongkong": "Hong Kong", "cote d'ivoire": "Ivory Coast", "eswatini": "Eswatini", "cabo verde": "Cabo Verde"}
    return resolve(fixes.get(name.lower(), name))


@lru_cache(maxsize=None)
def load(source_name: str) -> pd.DataFrame:
    """Respondents of one source with WVS7 column names: iso, year, W, Q260, Q262, Q279 and the
    mapped answer columns (NaN where not asked or not answered)."""
    from oracle.world.countries import countries

    src = next(s for s in SOURCES if s.name == source_name)
    by_num = {int(c.iso_num): i for i, c in countries().items() if str(c.iso_num or "").isdigit()}
    frames = []
    for pattern in src.files:
        for f in sorted(DATA.glob(pattern)):
            df, vl, _labels = _read(_extract(f, src.pick))
            cc = _code(df[src.country.upper()])
            if src.country_is_isonum:
                iso = cc.map(lambda v: by_num.get(int(v)) if pd.notna(v) else None)
            else:
                names = vl.get(src.country.upper(), {})
                iso = cc.map(lambda v: _iso_of_label(names.get(v, names.get(int(v), ""))) if pd.notna(v) else None)
            out = pd.DataFrame({"iso": iso})
            out["W"] = _code(df[src.weight.upper()]) if src.weight and src.weight.upper() in df else 1.0
            sex = _code(df[src.sex.upper()])
            out["Q260"] = sex.where(sex.isin([1, 2]))
            age = _code(df[src.age.upper()])
            out["Q262"] = age.where((age >= 15) & (age <= 110))
            out["Q279"] = src.work(df, vl) if src.work else 0
            for wvs_col, (col, recode) in src.items.items():
                v = _code(df[col.upper()]) if col.upper() in df else pd.Series(np.nan, index=df.index)
                out[wvs_col] = v.map(recode) if isinstance(recode, dict) else v.map(lambda x: recode(x) if pd.notna(x) else None)
            yr = None
            for ycol in ("year", "Year", "YEAR", "NUMINVES"):
                if ycol in df:
                    y = _code(df[ycol])
                    yr = y.where(y > 1900, y + 2000)
                    break
            out["year"] = yr if yr is not None else int(re.search(r"(20\d\d)", src.name).group(1))
            frames.append(out)
    if not frames:
        return pd.DataFrame()
    d = pd.concat(frames, ignore_index=True)
    return d[d["iso"].notna() & d["Q260"].notna() & d["Q262"].notna() & (d["W"] > 0)]


# ---------------------------------------------------------------- testing against WVS


def _score_range(column: str) -> tuple[Callable[[float], float | None], float, float] | None:
    from oracle.population.views import QUESTIONS

    q = next((q for q in QUESTIONS if q.column == column), None)
    if not q:
        return None
    vals = [s for v in range(0, 12) if (s := q.score(v)) is not None and q.text(v) is not None]
    return q.score, min(vals), max(vals)


def _wmean_score(values: pd.Series, weights: pd.Series, column: str) -> float | None:
    sr = _score_range(column)
    if not sr:
        return None
    score, lo, hi = sr
    s = values.map(lambda v: score(int(v)) if pd.notna(v) else None).astype(float)
    ok = s.notna()
    if ok.sum() < 50:
        return None
    return float(np.average((s[ok] - lo) / (hi - lo), weights=weights[ok]))


def validate(wvs: pd.DataFrame, max_gap: float = 0.10, min_countries: int = 3) -> dict[str, dict]:
    """For every source and mapped question: in countries both surveyed, the gap between the two
    surveys' average answer (0-1 scale). A question is kept for a source when the median gap over
    at least `min_countries` countries is at most `max_gap`. `wvs` is the WVS7 file with
    B_COUNTRY_ALPHA, W_WEIGHT and the answer columns."""
    report = {}
    for src in SOURCES:
        d = load(src.name)
        if d.empty:
            continue
        rows = {}
        for col in src.items:
            gaps = {}
            for iso, g in d.groupby("iso"):
                w = wvs[wvs["B_COUNTRY_ALPHA"] == iso]
                if w.empty:
                    continue
                a = _wmean_score(g[col], g["W"], col)
                b = _wmean_score(w[col].where(w[col] > 0), w["W_WEIGHT"], col)
                if a is not None and b is not None:
                    gaps[iso] = round(abs(a - b), 3)
            med = float(np.median(list(gaps.values()))) if gaps else None
            rows[col] = {"countries": len(gaps), "median_gap": round(med, 3) if med is not None else None,
                         "max_gap": max(gaps.values()) if gaps else None, "gaps": gaps,
                         "kept": bool(gaps) and len(gaps) >= min_countries and med <= max_gap}
        report[src.name] = rows
    return report
