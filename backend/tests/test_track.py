"""Track record: freeze a prediction, resolve it later, score it and fit the correction."""

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from oracle.api.app import app
from tests.test_lenses import run


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        c.put("/api/settings", json={"search_provider": "none"})
        yield c


def future(days=30):
    return (date.today() + timedelta(days=days)).isoformat()


def test_track_resolve_and_fit(client):
    rid, r = run(client, {"prompt": "Will voters in Germany support a ban on new petrol cars from 2035? Outcomes: Support, Oppose", "targets": ["DEU"]})
    head = r["results"]["headline"]

    # Dates in the past are refused: the prediction must come before the outcome.
    bad = client.post(f"/api/runs/{rid}/track", json={"resolves_on": (date.today() - timedelta(days=2)).isoformat()})
    assert bad.status_code == 400

    p = client.post(f"/api/runs/{rid}/track", json={"resolves_on": future(), "note": "Bundestag vote"}).json()
    assert p["status"] == "open" and p["predicted"] == head["value"] and p["kind"] == "belief"
    assert client.get(f"/api/runs/{rid}/track").json()[0]["id"] == p["id"]

    done = client.post(f"/api/track/{p['id']}/resolve", json={"actual": 0.41, "source": "https://example.org/result"}).json()
    assert done["status"] == "resolved" and done["blind"] is True
    assert done["error"] == pytest.approx(head["value"] - 0.41, abs=1e-4)
    assert client.post(f"/api/track/{p['id']}/resolve", json={"actual": 0.5}).status_code == 400

    # Fitting needs at least three resolved predictions of a kind.
    assert client.post("/api/track/fit/belief").status_code == 400
    for actual in (0.35, 0.6):
        q = client.post(f"/api/runs/{rid}/track", json={"resolves_on": future(60)}).json()
        client.post(f"/api/track/{q['id']}/resolve", json={"actual": actual})
    t = client.get("/api/track").json()
    s = t["summary"]
    assert s["resolved"] == 3 and s["open"] == 0 and s["by_kind"]["belief"]["can_fit"]
    assert 0 <= s["mae"] <= 1 and len(s["points"]) == 3

    fit = client.post("/api/track/fit/belief").json()
    assert fit["n"] == 3 and fit["calibration"]["source"] == "track record"
    assert client.get("/api/calibration").json()["belief"]["source"] == "track record"
    client.delete("/api/calibration/belief")

    client.delete(f"/api/track/{p['id']}")
    assert client.get("/api/track").json()["summary"]["total"] == 2


def test_unfinished_runs_cannot_be_tracked(client):
    assert client.post("/api/runs/nope/track", json={"resolves_on": future()}).status_code == 404
