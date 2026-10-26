"""Sensitivity test for the numbers that are settings, not facts about the world.

A few values have no published data behind them because they are about the simulation itself:
how many posts on the topic a person sees per day (feed_size), how many current-affairs items a
run keeps (news_items), how many days the society runs (diffusion_rounds) and how many people are
simulated (agents). For each, this script reruns the same questions with the real configured
models, changing one setting at a time around its default, and checks whether the answer moves
by more than its own 95% interval at the default. A setting passes when it doesn't.

Runs use a copy of var/settings.json in a temporary folder, so the user's settings and database
are never touched. Writes docs/sensitivity.json.

    python scripts/sensitivity.py
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TMP = Path(tempfile.mkdtemp(prefix="tellaris-sensitivity-"))
shutil.copy(ROOT / "var" / "settings.json", TMP / "settings.json")
os.environ["ORACLE_VAR_DIR"] = str(TMP)
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from oracle.api.app import app  # noqa: E402

OUT = ROOT.parent / "docs" / "sensitivity.json"
QUESTIONS = [
    {"prompt": "Would people in India and Brazil pay $3 a month for an app that tracks their spending automatically?", "targets": ["IND", "BRA"]},
    {"prompt": "Should cities ban cars from their centres? What do people in Germany and the United States think? Outcomes: Yes, No",
     "targets": ["DEU", "USA"]},
]
BASE = {"agents": 120, "runs_per_agent": 1, "committees": 0, "diffusion_rounds": 3, "diffusion_agent_cap": 60, "seed": 7,
        "feed_style": "ranked", "feed_size": 5, "news_items": 14, "influencer_voices": 0}
VARY = {"feed_size": [3, 8], "news_items": [7, 21], "diffusion_rounds": [5, 7], "agents": [240]}


def run(client: TestClient, q: dict, cfg: dict, tries: int = 3) -> dict:
    """One run; a run that fails (rate limits, an expired key) is retried, then reported as an error."""
    for attempt in range(tries):
        r = _once(client, q, cfg)
        if "error" not in r:
            return r
        print("  retrying after error:", r["error"][:160], flush=True)
        time.sleep(60 * (attempt + 1))
    return r


def _once(client: TestClient, q: dict, cfg: dict) -> dict:
    rid = client.post("/api/runs", json={**q, "config": cfg}).json()["id"]
    while True:
        r = client.get(f"/api/runs/{rid}").json()
        if r["status"] in ("done", "failed"):
            break
        time.sleep(2)
    if r["status"] != "done":
        return {"error": r.get("error")}
    h = r["results"]["headline"]
    if "leading" in h:
        return {"value": h["leading"]["share"], "ci": h["leading"]["ci"], "what": f"share choosing {h['leading']['option']}"}
    return {"value": h.get("value"), "ci": h.get("ci"), "what": "headline value"}


def main() -> None:
    out = {"_meta": {"built": date.today().isoformat(), "base": BASE, "rule": "a setting passes when every variant's answer lies inside the base run's 95% interval"},
           "questions": []}
    with TestClient(app) as client:
        for q in QUESTIONS:
            base = run(client, q, BASE)
            if "error" in base:
                print("base run failed; question skipped:", base["error"][:200], flush=True)
                out["questions"].append({**q, "base": base, "variants": []})
                continue
            rows = []
            for key, values in VARY.items():
                for v in values:
                    r = run(client, q, {**BASE, key: v})
                    inside = r.get("value") is not None and base.get("ci") and base["ci"][0] <= r["value"] <= base["ci"][1]
                    rows.append({"setting": key, "setting_value": v, **r, "inside_base_ci": bool(inside) if "error" not in r else None})
                    print(q["targets"], key, v, r, "error" if "error" in r else ("inside" if inside else "OUTSIDE"), flush=True)
            out["questions"].append({**q, "base": base, "variants": rows})
            OUT.write_text(json.dumps(out, indent=1), encoding="utf-8")
    verdict = {}
    for q in out["questions"]:
        for r in q["variants"]:
            if r["inside_base_ci"] is not None:  # failed runs say nothing either way
                verdict.setdefault(r["setting"], []).append(r["inside_base_ci"])
    out["verdict"] = {k: "passes" if all(v) else "moves the answer" for k, v in verdict.items()}
    out["verdict"].update({k: "not tested (runs failed)" for k in VARY if k not in verdict})
    OUT.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out["verdict"]))
    shutil.rmtree(TMP, ignore_errors=True)


if __name__ == "__main__":
    main()
