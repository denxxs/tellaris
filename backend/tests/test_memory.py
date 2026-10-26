"""Memory and reflection: people remember what they saw, reflect once, and their profile and chat use it."""

import pytest
from fastapi.testclient import TestClient

from oracle.api.app import app
from oracle.simulate.memory import Mind
from tests.test_lenses import run

PROMPT = "Pineapple on pizza: love it or hate it? Outcomes: Love it, It's fine, Never."


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        c.put("/api/settings", json={"search_provider": "none"})
        yield c


def test_recall_keeps_what_the_recall_curve_keeps():
    m = Mind()
    m.add(0, "said", "I like it")
    for i in range(1, 9):
        m.add(i, "saw", f"post {i}", who="A", item=f"f{i}")
    m.add(3, "reply", "you're wrong", who="B", item="r1")
    m.add(3, "reply", "duplicate", who="B", item="r1")  # same item is remembered once
    texts = [x.text for x in m.recall(now=9, key="p1")]
    assert "you're wrong" in texts and "duplicate" not in texts
    assert len(texts) >= 7  # after nine days about 94% of memories are still there
    assert [x.n for x in m.recall(now=9, key="p1")] == sorted(x.n for x in m.recall(now=9, key="p1"))
    # a year on, about four in ten are gone
    assert 0.3 < len(m.recall(now=400, key="p1")) / 10 < 0.9


def test_people_remember_and_reflect(client):
    rid, r = run(client, {"prompt": PROMPT, "targets": ["ITA", "USA"], "config": {"diffusion_rounds": 2, "diffusion_agent_cap": 40}})
    ref = r["results"]["diffusion"]["reflection"]
    assert ref["people"] > 0 and 0 <= ref["after"] <= 1 and 0 <= ref["before"] <= 1
    assert abs(sum(x["share"] for x in ref["moved_by"]) - 1) < 0.01 or not ref["moved_by"]
    assert ref["examples"] and ref["examples"][0]["belief"]

    pid = ref["examples"][0]["persona_id"]
    prof = client.get(f"/api/runs/{rid}/personas/{pid}").json()
    mind = prof["persona"]["mind"]
    assert mind["memories"][0]["kind"] == "said"
    assert len(mind["trajectory"]) == 3  # start + 2 rounds
    assert mind["reflection"]["belief"]
    valid = {m["n"] for m in mind["memories"]}
    assert set(mind["reflection"]["influences"]) <= valid


def test_memory_can_be_switched_off(client):
    _, r = run(client, {"prompt": PROMPT, "targets": ["ITA"], "config": {"diffusion_rounds": 1, "diffusion_agent_cap": 30, "memory": False}})
    assert r["results"]["diffusion"]["reflection"] == {"people": 0}
