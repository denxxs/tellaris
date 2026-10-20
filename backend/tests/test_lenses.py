"""Any question: lenses, groups by age or trait, global runs, clarifying questions."""

import time

import pytest
from fastapi.testclient import TestClient

from oracle.api.app import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        c.put("/api/settings", json={"search_provider": "none"})
        yield c


def run(client, body, timeout=180):
    body.setdefault("config", {})
    body["config"] = {"agents": 80, "runs_per_agent": 1, "committees": 3, "diffusion_rounds": 1, "diffusion_agent_cap": 40, "seed": 5, **body["config"]}
    rid = client.post("/api/runs", json=body).json()["id"]
    start = time.time()
    while time.time() - start < timeout:
        r = client.get(f"/api/runs/{rid}").json()
        if r["status"] in ("done", "failed"):
            assert r["status"] == "done", r.get("error")
            return rid, r
        time.sleep(0.2)
    raise TimeoutError(rid)


def test_opinion_question_uses_opinion_lens(client):
    _, r = run(client, {"prompt": "Pineapple on pizza: what do people in Italy and the USA think of it? Outcomes: Love it, It's fine, Never"})
    spec, h = r["spec"], r["results"]["headline"]
    assert spec["lens"] == "opinion" and spec["b2b"] is False and "committee" not in spec["modes"]
    assert spec["outcome_type"] == "categorical"
    assert h["kind"] == "belief" and h["lens"] == "opinion" and h["reach"] == 1.0
    assert h["leading"]["option"] in spec["outcomes"] and 0 <= h["leading"]["ci"][0] <= h["leading"]["share"] <= h["leading"]["ci"][1] <= 1
    assert h["label"].startswith("Share choosing") and h["leading"]["option"]
    assert not r["results"].get("committees")
    assert h.get("revenue") is None


def test_gen_z_group_has_the_right_ages(client):
    rid, r = run(client, {"prompt": "Would Gen Z women in Brazil eat lab-grown meat if it cost the same as normal meat?"})
    seg = r["spec"]["segments"][0]
    assert seg["age_min"] == 18 and seg["age_max"] == 28 and seg["gender"] == "woman"
    people = client.get(f"/api/runs/{rid}/personas").json()
    buyers = [p for p in people if p["segment"] == seg["name"]]
    assert buyers and all(18 <= p["age"] <= 28 for p in buyers)


def test_trait_groups_are_estimates(client):
    spec = client.post("/api/scenario/preview", json={"prompt": "Would dog owners in the UK pay $15 a month for a dog-walking app?"}).json()["spec"]
    seg = next(s for s in spec["segments"] if s.get("trait"))
    heads = client.post("/api/scenario/headcount", json={"spec": spec}).json()
    row = next(x for x in heads["segments"] if x["name"] == seg["name"])
    assert row["estimated"] is True and row["total"] > 0


def test_global_run_finds_where_it_works(client):
    rid, r = run(client, {"prompt": "Would people around the world try a four-day work week if pay dropped by 10%?", "scope": "global", "config": {"agents": 400, "diffusion_rounds": 1}})
    spec = r["spec"]
    assert spec["scope"] == "global" and len(spec["targets"]) == 20
    sp = r["results"]["splits"]
    assert "country" in sp["dimensions"] and "age" in sp["dimensions"] and "region" in sp["dimensions"]
    for c in sp["hot"]:
        assert c["ci"][0] > r["results"]["headline"]["ci"][1]
    for c in sp["cold"]:
        assert c["ci"][1] < r["results"]["headline"]["ci"][0]


def test_lens_override_turns_off_committees(client):
    prompt = "We're launching Ledgerly, a B2B SaaS for finance teams at $49 per seat per month in the USA. Will CFOs adopt it within 12 months?"
    _, r = run(client, {"prompt": prompt, "lens": "consumer"})
    assert r["spec"]["lens"] == "consumer" and not r["results"].get("committees")


def test_clarifying_questions(client):
    vague = client.post("/api/scenario/clarify", json={"prompt": "An app that reminds people to drink water"}).json()
    assert vague["lens"] == "consumer" and len(vague["questions"]) >= 2
    ids = {q["id"] for q in vague["questions"]}
    assert {"price", "where"} <= ids
    for q in vague["questions"]:
        assert q["kind"] == "single" and q["default"] in q["options"]
    clear = client.post("/api/scenario/clarify", json={"prompt": "Will voters in Germany support a ban on new petrol cars from 2035? Outcomes: Support, Oppose"}).json()
    assert clear["lens"] == "forecast" and clear["questions"] == []
    # Answers are folded into what the planner reads.
    _, r = run(client, {"prompt": "An app that reminds people to drink water", "targets": ["USA"], "clarifications": [{"question": "What will it cost a typical customer?", "answer": "$3 a month"}]})
    assert "$3 a month" in r["prompt"] or "$3 a month" in r["spec"]["subject"] or r["spec"]["price"]["amount"] == 3


def test_global_clarify_never_asks_where(client):
    c = client.post("/api/scenario/clarify", json={"prompt": "An app that reminds people to drink water", "scope": "global"}).json()
    assert c["scope"] == "global"
    assert "where" not in {q["id"] for q in c["questions"]}


def test_spots_are_not_repeated_under_two_names(client):
    _, r = run(client, {"prompt": "Pineapple on pizza: love it or hate it? Outcomes: Love it, It's fine, Never.", "targets": ["ITA", "USA", "BRA", "JPN"]})
    sp = r["results"]["splits"]
    keys = [(c["n"], c["value"], tuple(c["ci"])) for c in sp["hot"] + sp["cold"]]
    assert len(keys) == len(set(keys))
    assert r["results"]["headline"]["label"].startswith("Share choosing")
