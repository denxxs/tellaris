"""Measure how fast public attention to a news story fades, from Wikipedia pageviews.

Articles linked from Wikipedia's daily "Current events" pages (2023-2024) whose views spike at
least SPIKE times above their usual level are followed for a year after the peak. Each story's
extra attention (views above its level before the story, or none for articles created with it) is
divided by its peak; the median over stories gives the decay curve, and a two-stage decay is
fitted to it: a fast stage (the story is news) and a slow one (it is remembered and looked up).

Attention is not memory: people stop looking a story up within days but remember it for months.
How long people remember news comes from Meeter, Murre & Janssen (2005), who tested about 14,000
people on news events 1 day to 2 years old and fitted the two-store memory chain model; their
parameters (Table 3, open recall questions) are stored alongside.

Writes oracle/data/news_decay.json, read by oracle/research/news.py. Wikimedia pageviews are
public (CC0); requests carry a project user agent and are rate-limited.

    python scripts/fit_news_decay.py
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import random
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import httpx
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "oracle" / "data" / "news_decay.json"
CACHE = ROOT / "var" / "datasets" / "cache" / "pageviews"
UA = {"User-Agent": "Tellaris-research/0.1 (https://github.com/denxxs/tellaris)"}
MONTHS = [date(y, m, 1) for y in (2023, 2024) for m in range(1, 13)]
PER_MONTH = 160  # articles sampled per month's current-events page
SPIKE = 10.0  # peak must be this many times the article's usual daily views
MIN_PEAK = 2000  # and at least this many views
DAYS = 365
# Meeter, Murre & Janssen (2005) "Remembering the news: Modeling retention data from a study with
# 14,000 participants", Memory & Cognition 33(5):793-810, doi:10.3758/BF03193075, Table 3:
# memory chain model (mu1, a1, mu2, a2; time in days) for open (recall) questions.
MEMORY = {"Experiment 1 (Dutch)": [0.92, 0.032, 0.018, 0.0010], "Experiment 2 (US)": [0.49, 0.018, 0.011, 0.0],
          "Experiment 3 (Dutch)": [0.76, 0.020, 0.010, 0.00045]}


async def links(client: httpx.AsyncClient, month: date) -> list[str]:
    page = f"Portal:Current_events/{month.strftime('%B_%Y')}"
    r = await client.get("https://en.wikipedia.org/w/api.php", params={
        "action": "parse", "page": page, "prop": "links", "format": "json", "formatversion": 2})
    r.raise_for_status()
    return [x["title"] for x in r.json()["parse"]["links"] if x.get("ns") == 0 and x.get("exists")]


async def views(client: httpx.AsyncClient, sem: asyncio.Semaphore, title: str, start: date, end: date) -> dict[date, int]:
    key = CACHE / (hashlib.sha1(f"{title}|{start}|{end}".encode()).hexdigest() + ".json")
    if key.exists():
        raw = json.loads(key.read_text(encoding="utf-8"))
    else:
        url = ("https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/"
               f"{title.replace(' ', '_').replace('/', '%2F')}/daily/{start:%Y%m%d}/{end:%Y%m%d}")
        async with sem:
            r = await client.get(url)
            await asyncio.sleep(0.05)
        raw = r.json().get("items", []) if r.status_code == 200 else []
        key.write_text(json.dumps(raw), encoding="utf-8")
    return {datetime.strptime(x["timestamp"][:8], "%Y%m%d").date(): int(x["views"]) for x in raw}


def curve(v: dict[date, int], month: date) -> list[float] | None:
    """Extra attention after the peak, as a share of the peak's extra attention (None = no spike)."""
    window = [d for d in v if month <= d < month + timedelta(days=31)]
    if not window:
        return None
    peak_day = max(window, key=lambda d: v[d])
    peak = v[peak_day]
    before = [v[d] for d in v if peak_day - timedelta(days=60) <= d < peak_day - timedelta(days=7)]
    base = float(np.median(before)) if len(before) >= 20 else 0.0  # new article: no level before the story
    if peak < MIN_PEAK or peak < SPIKE * max(base, 1.0):
        return None
    # Ignore spikes that are just the tail of an earlier one (peak must be near the top of the page's history).
    if any(v[d] > peak for d in v if d < peak_day):
        return None
    out = []
    for t in range(DAYS + 1):
        d = peak_day + timedelta(days=t)
        if d not in v:
            return None
        out.append((v[d] - base) / (peak - base))
    return out


def fit(med: np.ndarray) -> dict:
    """Two-stage decay with a floor: a*0.5^(t/h1) + b*0.5^(t/h2) + c."""
    from scipy.optimize import curve_fit

    t = np.arange(len(med), dtype=float)

    def f(t, a, h1, b, h2, c):
        return a * 0.5 ** (t / h1) + b * 0.5 ** (t / h2) + c

    w = 1 / np.sqrt(1 + t)  # every day counts, early days a bit more where the curve is steep
    p, _ = curve_fit(f, t, med, p0=[0.8, 1.5, 0.15, 30.0, 0.02], sigma=1 / w,
                     bounds=([0, 0.05, 0, 2, 0], [1.2, 20, 1, 2000, 0.5]), maxfev=20000)
    a, h1, b, h2, c = (float(x) for x in p)
    resid = med - f(t, *p)
    return {"fast_share": round(a, 4), "fast_half_life_days": round(h1, 2), "slow_share": round(b, 4),
            "slow_half_life_days": round(h2, 1), "floor": round(c, 4),
            "r2": round(float(1 - (resid ** 2).sum() / ((med - med.mean()) ** 2).sum()), 4)}


async def main() -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    rng = random.Random(0)
    sem = asyncio.Semaphore(6)
    async with httpx.AsyncClient(headers=UA, timeout=60, follow_redirects=True) as client:
        jobs = []
        for m in MONTHS:
            titles = await links(client, m)
            for t in rng.sample(titles, min(PER_MONTH, len(titles))):
                jobs.append((t, m))
        print(f"{len(jobs)} articles from {len(MONTHS)} months of current-events pages")
        res = await asyncio.gather(*(views(client, sem, t, m - timedelta(days=60), m + timedelta(days=31 + DAYS + 5)) for t, m in jobs))
    curves = [c for (t, m), v in zip(jobs, res) if (c := curve(v, m)) is not None]
    print(f"{len(curves)} stories spiked at least {SPIKE:g}x")
    arr = np.array(curves)
    med = np.median(arr, axis=0)
    p = fit(med)
    sample_days = [0, 1, 2, 3, 7, 14, 30, 60, 90, 180, 365]
    OUT.write_text(json.dumps({
        "_meta": {
            "built": date.today().isoformat(),
            "source": "Wikimedia pageviews (CC0) for articles linked from English Wikipedia's Portal:Current_events, 2023-2024",
            "method": f"{len(jobs)} articles sampled ({PER_MONTH} per month); kept {len(curves)} whose daily views peaked at least "
                      f"{SPIKE:g}x their usual level and {MIN_PEAK}+ views; attention above the usual level divided by the peak's; "
                      "median over stories per day; fitted a*0.5^(t/h1) + b*0.5^(t/h2) + c.",
            "limits": "English Wikipedia readers (worldwide but English-speaking); pageviews measure looking a story up, not knowing it.",
        },
        "memory": {
            "source": "Meeter, Murre & Janssen (2005), Memory & Cognition 33(5):793-810, doi:10.3758/BF03193075, Table 3",
            "model": "p(t) = 1 - exp(-r(t)), r(t) = mu1*(exp(-a1 t) + mu2/(a2-a1)*(exp(-a1 t) - exp(-a2 t))), t in days; "
                     "share still remembered = p(t)/p(0), averaged over the three experiments (open recall questions)",
            "params": MEMORY,
        },
        "stories": len(curves),
        "fit": p,
        "median_curve": {str(d): round(float(med[d]), 4) for d in sample_days},
        "p25_curve": {str(d): round(float(np.percentile(arr[:, d], 25)), 4) for d in sample_days},
        "p75_curve": {str(d): round(float(np.percentile(arr[:, d], 75)), 4) for d in sample_days},
    }, indent=1), encoding="utf-8")
    print(json.dumps(p))
    print({d: round(float(med[d]), 3) for d in sample_days})


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
