"""Fetch each country's monthly Facebook users (adults 18+) from Meta's ad reach estimates.

Meta doesn't publish user counts, but its Marketing API estimates how many monthly active users
an ad aimed at a country could reach. Researchers use these to scale the Social Connectedness
Index (e.g. Fatehkia et al.; Bailey et al.). Nothing is bought: the estimate is free.

You need (see the steps the assistant gave you):
- an access token with the ads_read permission, saved as the only line of backend/var/meta_token.txt
  (backend/var is gitignored, so it never reaches git);
- your ad account id (act_1234567890, shown in the Ads Manager address bar).

Run:  cd backend && python scripts/fetch_facebook_users.py act_1234567890

Writes backend/var/datasets/facebook_users.json (kept local). build_ties.py uses it when present.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import date
from pathlib import Path

import httpx
import pycountry

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from oracle.world.countries import countries  # noqa: E402

TOKEN_FILE = ROOT / "var" / "meta_token.txt"
OUT = ROOT / "var" / "datasets" / "facebook_users.json"
API = "https://graph.facebook.com/v22.0"


def main() -> None:
    if len(sys.argv) < 2 or not sys.argv[1].startswith("act_"):
        sys.exit("usage: python scripts/fetch_facebook_users.py act_<your ad account id>")
    account = sys.argv[1]
    if not TOKEN_FILE.exists():
        sys.exit(f"save your access token as the only line of {TOKEN_FILE} first")
    token = TOKEN_FILE.read_text(encoding="utf-8").strip()
    out: dict[str, dict] = {}
    failed: dict[str, str] = {}
    for iso3 in sorted(countries()):
        c = pycountry.countries.get(alpha_3=iso3)
        iso2 = "XK" if iso3 == "XKX" else c.alpha_2 if c else None
        if not iso2:
            continue
        spec = {"geo_locations": {"countries": [iso2]}, "age_min": 18, "age_max": 65, "publisher_platforms": ["facebook"]}
        for attempt in range(3):
            r = httpx.get(f"{API}/{account}/delivery_estimate", timeout=60, params={
                "access_token": token, "optimization_goal": "REACH", "targeting_spec": json.dumps(spec)})
            if r.status_code == 200:
                d = (r.json().get("data") or [{}])[0]
                lo, hi = d.get("estimate_mau_lower_bound"), d.get("estimate_mau_upper_bound")
                if lo is not None and hi is not None:
                    out[iso3] = {"lower": lo, "upper": hi, "mid": (lo + hi) / 2}
                else:
                    failed[iso3] = "no estimate"
                break
            err = r.json().get("error", {}) if r.headers.get("content-type", "").startswith("application/json") else {}
            if err.get("code") in (4, 17, 80004, 613):  # rate limited: wait and retry
                time.sleep(60 * (attempt + 1))
                continue
            failed[iso3] = err.get("message", f"HTTP {r.status_code}")[:120]
            if err.get("code") in (190, 200, 10):  # bad token or missing permission: stop now
                sys.exit(f"Meta refused the request: {failed[iso3]}")
            break
        time.sleep(1.5)
        print(f"{iso3}: {out.get(iso3, {}).get('mid', failed.get(iso3))}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "_meta": {"fetched": date.today().isoformat(), "source": "Meta Marketing API delivery_estimate, monthly active Facebook users aged 18+",
                  "not_available": failed},
        "countries": out,
    }, indent=1), encoding="utf-8")
    print(f"wrote {OUT}: {len(out)} countries, {len(failed)} without an estimate")


if __name__ == "__main__":
    main()
