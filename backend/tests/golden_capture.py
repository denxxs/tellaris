"""Records what the B2B path produces today, so later changes can be checked against it."""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ["ORACLE_VAR_DIR"] = tempfile.mkdtemp(prefix="oracle-golden-")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from fastapi.testclient import TestClient  # noqa: E402

from oracle.api.app import app  # noqa: E402

PROMPT = (
    "We're launching Ledgerly, a B2B SaaS that uses AI to automate month-end close for finance teams, "
    "at $49 per seat per month. Target B2B SaaS founders and CFOs in the USA, plus financial analysts at "
    "Infosys, Cognizant and TCS in India. Will they adopt it within 12 months?"
)
CFG = {"agents": 120, "runs_per_agent": 2, "committees": 6, "diffusion_rounds": 2, "diffusion_agent_cap": 60, "influencer_voices": 8, "seed": 11}


def run() -> dict:
    with TestClient(app) as c:
        c.put("/api/settings", json={"search_provider": "none"})
        rid = c.post("/api/runs", json={"prompt": PROMPT, "config": CFG}).json()["id"]
        while c.get(f"/api/runs/{rid}").json()["status"] not in ("done", "failed"):
            time.sleep(0.2)
        r = c.get(f"/api/runs/{rid}").json()
    res = r["results"]
    h = res["headline"]
    return {
        "headline": {k: h[k] for k in ("stated", "calibrated", "value", "ci", "reach", "n", "people", "adopters")},
        "by_country": {c["key"]: c["value"] for c in res["by_country"]},
        "by_segment": {c["key"]: c["value"] for c in res["by_segment"]},
        "committees": res["committees"]["purchase_probability"],
        "society_final": res["diffusion"]["rounds"][-1]["calibrated"],
        "spec": {k: r["spec"][k] for k in ("b2b", "modes", "assumed_reach", "price", "targets")},
    }


if __name__ == "__main__":
    out = run()
    Path(__file__).with_name("golden_b2b.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out["headline"]))
