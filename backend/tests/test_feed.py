"""Feed styles: word of mouth (contacts only), a ranked feed with likes and reshares, and viral amplification."""

import time

import networkx as nx
import pytest
from fastapi.testclient import TestClient

from oracle.api.app import app
from oracle.simulate.feed import FeedState, apply_engagement, pick, record_seen
from tests.test_lenses import run

PROMPT = "Would people in India and Brazil pay $3 a month for Penny, an app that tracks spending automatically?"
CFG = {"agents": 160, "runs_per_agent": 1, "diffusion_rounds": 3, "diffusion_agent_cap": 60, "seed": 21}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        c.put("/api/settings", json={"search_provider": "none"})
        yield c


def _item(iid, author, rnd, **kw):
    return {"id": iid, "author": author, "author_name": author.upper(), "round": rnd, "kind": "post", "text": iid, "agrees": 0, "disagrees": 0, **kw}


def _graph():
    # me - a - b - c, and a stranger s nobody knows.
    g = nx.Graph()
    g.add_edges_from([("me", "a"), ("a", "b"), ("b", "c")])
    g.add_node("s")
    return g


def test_word_of_mouth_shows_only_contacts():
    g = _graph()
    talk = [_item("f1", "a", 0), _item("f2", "b", 0), _item("f3", "s", 0, likes=50)]
    got = pick("word_of_mouth", "me", 1, talk, g, FeedState(), {})
    assert [x["id"] for x in got] == ["f1"]


def test_ranked_feed_reaches_beyond_contacts_and_says_why():
    g = _graph()
    names = {"a": "Ana"}
    talk = [_item("f1", "a", 0), _item("f2", "b", 0), _item("f3", "s", 0, likes=40, reshares=5), _item("f4", "c", 0)]
    fs = FeedState()
    fs.resharers["f4"] = {"a"}
    got = {x["id"]: x for x in pick("ranked", "me", 1, talk, g, fs, names)}
    assert got["f1"]["via"] is None  # a contact's own post
    assert got["f2"]["via"] == "a friend of a friend"
    assert got["f3"]["via"] == "popular outside your circle"
    assert got["f4"]["via"] == "reshared by Ana"


def test_viral_lifts_popular_strangers_more_than_ranked():
    g = _graph()
    talk = [_item("f1", "a", 0), _item("f3", "s", 0, likes=12, reshares=2)]
    ranked = [x["id"] for x in pick("ranked", "me", 1, talk, g, FeedState(), {})]
    viral = [x["id"] for x in pick("viral", "me", 1, talk, g, FeedState(), {})]
    assert ranked[0] == "f1" and viral[0] == "f3"


def test_engagement_only_counts_items_you_saw():
    g = _graph()
    items = {"f1": _item("f1", "a", 0), "f2": _item("f2", "b", 0)}
    fs = FeedState()
    record_seen(fs, "me", [items["f1"], items["f2"]], items, g)
    assert items["f1"]["seen"] == 1 and "seen_outside" not in items["f1"]
    assert items["f2"]["seen_outside"] == 1
    assert apply_engagement(fs, "me", "Me", ["f1", "f1", "zz"], "f2", {"f1", "f2"}, items) == (1, 1)
    assert apply_engagement(fs, "me", "Me", ["f1"], "f2", {"f1", "f2"}, items) == (0, 0)  # one like and one reshare per person
    assert items["f2"]["reshared_by"] == [{"id": "me", "name": "Me"}]


def test_feed_styles_change_how_far_posts_travel(client):
    out = {}
    for style in ("word_of_mouth", "ranked", "viral"):
        _, r = run(client, {"prompt": PROMPT, "targets": ["IND", "BRA"], "config": {**CFG, "feed_style": style}})
        out[style] = r["results"]["diffusion"]["feed"]
    wom, ranked, viral = out["word_of_mouth"], out["ranked"], out["viral"]
    assert wom["style"] == "word_of_mouth" and wom["likes"] == 0 and wom["outside_share"] == 0
    assert ranked["likes"] > 0 and ranked["outside_share"] > 0
    assert viral["outside_share"] > ranked["outside_share"]
    assert viral["top_reach"] >= ranked["top_reach"]
    assert viral["travelled"][0]["seen"] >= viral["travelled"][-1]["seen"]
    assert all(t["likes"] <= t["seen"] for t in viral["travelled"])


def test_feed_what_if_keeps_the_same_people(client):
    cfg = {**CFG, "seed": None}  # no seed given: Oracle picks one and the what-if reuses it
    rid, r = run(client, {"prompt": PROMPT, "targets": ["IND", "BRA"], "config": cfg})
    seed = r["results"]["seed"]
    assert isinstance(seed, int)
    new = client.post(f"/api/runs/{rid}/whatif", json={"label": "Viral", "config_patch": {"feed_style": "viral"}}).json()["id"]
    while client.get(f"/api/runs/{new}").json()["status"] not in ("done", "failed"):
        time.sleep(0.2)
    r2 = client.get(f"/api/runs/{new}").json()
    assert r2["results"]["seed"] == seed
    assert r2["request"]["config"]["feed_style"] == "viral"
    a = sorted((p["name"], p["country"], p["occupation"]) for p in client.get(f"/api/runs/{rid}/personas").json())
    b = sorted((p["name"], p["country"], p["occupation"]) for p in client.get(f"/api/runs/{new}/personas").json())
    assert a == b
