"""Asking a group: pick people from a group, ask them in character, sum the answers up."""

import time

import pytest
from fastapi.testclient import TestClient

from oracle.api.app import app
from tests.test_lenses import run

PROMPT = "Would people in India and Brazil pay $4 a month for an app that tracks their spending automatically?"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        c.put("/api/settings", json={"search_provider": "none"})
        yield c


@pytest.fixture(scope="module")
def done_run(client):
    return run(client, {"prompt": PROMPT, "targets": ["IND", "BRA"], "config": {"agents": 120}})


def ask(client, rid, body, timeout=60):
    rec = client.post(f"/api/runs/{rid}/interviews", json=body)
    assert rec.status_code == 200, rec.text
    iid = rec.json()["id"]
    start = time.time()
    while time.time() - start < timeout:
        r = client.get(f"/api/interviews/{iid}").json()
        if r["status"] != "running":
            return r
        time.sleep(0.1)
    raise TimeoutError(iid)


def test_choice_question_for_a_group(client, done_run):
    rid, _ = done_run
    r = ask(client, rid, {"question": "Which name do you prefer?", "kind": "choice", "options": ["Penny", "Ledgr", "Kosh"], "group": {"country": "IND"}, "limit": 25})
    assert r["status"] == "done" and r["group_label"] == "India"
    assert 0 < r["asked"] <= 25 and r["done"] == len(r["answers"]) == r["asked"]
    assert all(a["country"] == "IND" and a["choice"] in ("Penny", "Ledgr", "Kosh") for a in r["answers"])
    shares = r["results"]["all"]["options"]
    assert abs(sum(o["share"] for o in shares) - 1) < 1e-3
    assert r["digest"]["summary"] and r["digest"]["themes"]
    assert client.get(f"/api/runs/{rid}/interviews").json()[0]["id"] == r["id"]


def test_number_and_scale(client, done_run):
    rid, _ = done_run
    n = ask(client, rid, {"question": "What is the most you'd pay a month?", "kind": "number", "unit": "USD", "limit": 30})
    s = n["results"]["all"]
    assert s["p10"] <= s["median"] <= s["p90"] and n["group_label"] == "Everyone"
    sc = ask(client, rid, {"question": "How much do you worry about money?", "kind": "scale", "group": {"age": "18-29"}, "limit": 20})
    assert sum(sc["results"]["all"]["counts"]) == sc["results"]["all"]["n"]
    assert sc["group_label"] == "Under 30s"


def test_same_question_picks_the_same_people(client, done_run):
    rid, _ = done_run
    body = {"question": "What would make you try it?", "group": {"country": "BRA"}, "limit": 10}
    a, b = ask(client, rid, body), ask(client, rid, body)
    assert [x["persona_id"] for x in a["answers"]] == [x["persona_id"] for x in b["answers"]]


def test_bad_requests(client, done_run):
    rid, _ = done_run
    assert client.post(f"/api/runs/{rid}/interviews", json={"question": "Pick one", "kind": "choice", "options": ["A"]}).status_code == 422
    assert client.post(f"/api/runs/{rid}/interviews", json={"question": "Anyone there?", "group": {"country": "FRA"}}).status_code == 400
    assert client.post("/api/runs/nope/interviews", json={"question": "Hello there"}).status_code == 404
