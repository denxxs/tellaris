"""Knowledge graph: cleaned, private facts kept private, people grounded, mentions counted."""

import pytest
from fastapi.testclient import TestClient

from oracle.api.app import app
from oracle.research.graph import GEntity, GRelation, KnowledgeGraph, clean, context_for
from oracle.research.search import Fact
from oracle.scenario.models import ScenarioSpec
from tests.test_lenses import run


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        c.put("/api/settings", json={"search_provider": "none"})
        yield c


def spec(**kw):
    base = {
        "title": "Penny", "question": "Will people use Penny?", "subject": "Penny tracks your spending.", "persona_question": "Would you use it?",
        "targets": ["IND"], "outcomes": ["Yes", "No"], "subject_kind": "product", "segments": [{"name": "Adults"}],
    }
    return ScenarioSpec.model_validate({**base, **kw})


def test_clean_dedupes_links_and_keeps_private_facts_private():
    facts = [Fact(statement="Walnut has 2M users in India", relevance="", public=True), Fact(statement="We burn $90k a month", relevance="", public=False)]
    kg = KnowledgeGraph(
        entities=[
            GEntity(id="penny", name="Penny", type="product", facts=[2]),
            GEntity(id="walnut", name="Walnut", type="competitor", countries=["IND"], facts=[1]),
            GEntity(id="walnut-dup", name="walnut", type="competitor"),
            GEntity(id="lonely", name="Nobody links here", type="concept"),
            GEntity(id="second", name="Another product", type="product"),
        ],
        relations=[
            GRelation(source="penny", target="walnut-dup", label="competes with", detail="Walnut is the obvious comparison.", facts=[1]),
            GRelation(source="penny", target="ghost", label="uses"),
            GRelation(source="second", target="penny", label="partners with", facts=[2]),
        ],
    )
    g = clean(kg, spec(), facts)
    names = {e["name"] for e in g["entities"]}
    assert "Nobody links here" not in names and len([e for e in g["entities"] if e["type"] == "product"]) == 1
    rel = {(r["source"], r["target"]): r for r in g["relations"]}
    assert ("penny", "walnut") in rel and rel[("penny", "walnut")]["public"] is True
    assert rel[("penny", "walnut")]["sources"][0]["statement"].startswith("Walnut")
    assert rel[("second", "penny")]["public"] is False  # cites an internal fact
    product = next(e for e in g["entities"] if e["type"] == "product")
    assert product["public"] and product["sources"][0]["public"] is False  # listed for the user, marked private
    assert len(g["relations"]) == 2


def test_people_only_get_public_links_that_touch_them():
    from oracle.population.models import Persona

    g = {
        "product": "p",
        "entities": [
            {"id": "p", "name": "Penny", "type": "product", "summary": "", "countries": [], "public": True},
            {"id": "w", "name": "Walnut", "type": "competitor", "summary": "", "countries": ["IND"], "public": True},
            {"id": "m", "name": "Mint", "type": "competitor", "summary": "", "countries": ["USA"], "public": True},
            {"id": "s", "name": "Secret partner", "type": "company", "summary": "", "countries": [], "public": False},
        ],
        "relations": [
            {"source": "p", "target": "w", "label": "competes with", "detail": "Walnut is popular in India.", "public": True},
            {"source": "p", "target": "m", "label": "competes with", "detail": "Mint is popular in the US.", "public": True},
            {"source": "s", "target": "p", "label": "funds", "detail": "A secret partner funds it.", "public": False},
        ],
    }
    from oracle.population.sampler import PopulationBuilder

    people = PopulationBuilder(spec(targets=["IND", "USA"]), [], seed=2).build(40)
    ind = next(x for x in people if x.country == "IND")
    usa = next(x for x in people if x.country == "USA")
    assert isinstance(ind, Persona)
    know = context_for(g, {"IND": "India", "USA": "United States"})
    a, b = know(ind), know(usa)
    assert "Walnut is popular in India." in a and "Mint is popular in the US." not in a
    assert "Mint is popular in the US." in b and "Walnut is popular in India." not in b
    assert not any("secret" in x.lower() for x in a + b)


def test_run_has_a_graph_with_mentions(client):
    rid, r = run(client, {"prompt": "Would people in India pay $4 a month for an app that tracks spending? Competitors: Walnut, Money Manager.", "targets": ["IND"]})
    g = r["results"]["graph"]
    types = {e["type"] for e in g["entities"]}
    assert g["product"] in {e["id"] for e in g["entities"]} and "product" in types and "place" in types
    ids = {e["id"] for e in g["entities"]}
    assert all(x["source"] in ids and x["target"] in ids for x in g["relations"])
    talked = [e for e in g["entities"] if e["mentions"]["people"] > 0]
    assert talked, "the canned answers mention price, trust and switching"
    s = talked[0]["mentions"]["samples"][0]
    assert s["persona_id"] and s["text"]
    assert rid


def test_graph_can_be_switched_off(client):
    _, r = run(client, {"prompt": "Would people in India pay $4 a month for an app that tracks spending?", "targets": ["IND"], "config": {"knowledge_graph": False}})
    assert "graph" not in r["results"]
