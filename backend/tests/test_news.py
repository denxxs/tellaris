"""Current affairs and the timeline: real dated news, who knows what, and events landing over time."""

import time
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from oracle.api.app import app
from oracle.population.models import Persona, Traits
from oracle.research import news as news_mod
from oracle.research.news import NewsHit, NewsItem, assign, know_chance, score
from oracle.scenario.models import ScenarioSpec, TimelineEvent
from oracle.simulate import timeline as tl

TODAY = date.today()


def person(pid, country="IND", sector="finance", occupation="Financial Analyst", age=35, openness=0.5):
    return Persona(
        id=pid, country=country, country_name=country, segment="adults", segment_index=0, occupation_id="x", occupation=occupation,
        isco=2411, sector=sector, company_type="enterprise", company_size=[250, 499], seniority="mid", buyer_role="user", age=age, gender="female",
        income_usd=20000, income_band="middle",
        traits=Traits(tech_affinity=0.5, skepticism=0.5, risk_appetite=0.5, price_sensitivity=0.5, conformity=0.5, openness=openness, budget_authority=0.2),
    )


def test_recent_news_outranks_old_unless_still_in_effect():
    fresh = score(0.8, TODAY - timedelta(days=5), False, TODAY)
    old = score(0.8, TODAY - timedelta(days=240), False, TODAY)
    old_law = score(0.8, TODAY - timedelta(days=240), True, TODAY)
    assert old_law >= fresh > old
    # Memory for news (Meeter, Murre & Janssen 2005): most of a story is still remembered a month on,
    # about half a year on; attention (pageviews) is mostly gone within days.
    from oracle.research.news import attention, remembered

    assert 0.75 < remembered(30) < 0.9 and 0.45 < remembered(365) < 0.65
    assert attention(7) < 0.1 < attention(1)


def test_niche_news_reaches_the_people_it_concerns():
    analyst = person("a")
    student = person("s", sector="education", occupation="University Student", age=20)
    brazilian = person("b", country="BRA")
    rbi = (["IND"], "niche", ["finance", "banking"])
    assert know_chance(analyst, *rbi) >= 0.7
    assert know_chance(student, *rbi) < 0.12
    assert know_chance(brazilian, *rbi) < 0.4
    fuel = (["IND"], "mass", [])
    assert know_chance(student, *fuel) > 0.6 and know_chance(brazilian, *fuel) < 0.25


def test_assign_is_reproducible_and_counts_who_knows():
    people = [person(f"p{i}", sector="finance" if i % 2 else "retail", occupation="Analyst" if i % 2 else "Shop assistant") for i in range(40)]
    item = NewsItem(id="n01", headline="RBI tightens rules", summary="", published=TODAY.isoformat(), source="x", url="u", countries=["IND"], reach="niche", audiences=["finance"])
    a = assign(people, [item], seed=3)
    b = assign(people, [item.model_copy()], seed=3)
    assert {k: [i.id for i in v] for k, v in a.items()} == {k: [i.id for i in v] for k, v in b.items()}
    knew = {pid for pid, v in a.items() if v}
    assert len([p for p in people if p.id in knew and p.sector == "finance"]) > len([p for p in people if p.id in knew and p.sector == "retail"])
    assert 0 < item.known_share < 1 and item.known_by_country["IND"] == item.known_share


def test_time_labels_follow_the_horizon():
    assert tl.unit_for(6) == "month" and tl.unit_for(36) == "quarter" and tl.unit_for(60) == "year"
    as_of = date(2026, 10, 20)
    ps = tl.periods(as_of, 12, 3)
    assert [p["end_month"] for p in ps] == [4, 8, 12]
    assert ps[0]["label"] == "Oct 2026 to Feb 2027"
    assert tl.round_of(3, 12, 3) == 1 and tl.round_of(4.5, 12, 3) == 2 and tl.round_of(13, 12, 3) is None
    assert tl.when(30, "year") == "Year 3" and tl.when(3, "month") == "Month 3"


def test_events_mix_real_scheduled_news_and_your_what_ifs():
    spec = ScenarioSpec(
        title="t", subject="s", question="q", persona_question="pq", horizon_months=12, targets=["IND"],
        events=[TimelineEvent(name="Rival cuts price", at_month=3, direction="hurts"), TimelineEvent(name="Too late", at_month=20)],
    )
    soon = (TODAY + timedelta(days=150)).isoformat()
    news = [NewsItem(id="n01", headline="New UPI fee starts", summary="", published=TODAY.isoformat(), source="Reuters", url="https://r", upcoming=soon)]
    ev = tl.events_for(spec, news, TODAY)
    assert [e["kind"] for e in ev] == ["assumed", "scheduled"]
    assert ev[1]["url"] == "https://r" and ev[1]["source"] == "Reuters"
    assert all(e["name"] != "Too late" for e in ev)


HITS = [
    NewsHit(title="India's UPI fee for big merchants starts", url="https://example.org/upi-fee", snippet=f"Fee takes effect {(TODAY + timedelta(days=120)).isoformat()} for payment apps in India.", published=TODAY - timedelta(days=10), source="Reuters", query="q"),
    NewsHit(title="Fuel prices rise across India", url="https://example.org/fuel", snippet="Petrol up again in India.", published=TODAY - timedelta(days=3), source="The Hindu", query="q"),
    NewsHit(title="Budgeting apps boom among Gen Z", url="https://example.org/genz", snippet="Young people in India and Brazil try money apps.", published=TODAY - timedelta(days=40), source="Mint", query="q"),
]


@pytest.fixture(scope="module")
def client():
    mp = pytest.MonkeyPatch()

    async def fake_search(queries, provider, as_of, per_query=6):
        return [h for h in HITS if h.published <= as_of]

    mp.setattr(news_mod, "search_news", fake_search)
    with TestClient(app) as c:
        c.put("/api/settings", json={"search_provider": "duckduckgo"})
        yield c
        c.put("/api/settings", json={"search_provider": "none"})
    mp.undo()


def _run(client, body):
    rid = client.post("/api/runs", json=body).json()["id"]
    for _ in range(900):
        r = client.get(f"/api/runs/{rid}").json()
        if r["status"] in ("done", "failed"):
            assert r["status"] == "done", r.get("error")
            return rid, r
        time.sleep(0.2)
    raise TimeoutError(rid)


PROMPT = "Would people in India and Brazil pay $3 a month for Penny, an app that tracks spending automatically?"
CFG = {"agents": 120, "runs_per_agent": 1, "committees": 0, "diffusion_rounds": 3, "diffusion_agent_cap": 50, "research": False, "seed": 4}


def test_a_run_uses_real_news_and_a_timeline(client):
    rid, r = _run(client, {"prompt": PROMPT, "targets": ["IND", "BRA"], "config": CFG})
    res = r["results"]
    assert res["as_of"] == TODAY.isoformat()
    urls = {h.url for h in HITS}
    assert res["news"] and all(n["url"] in urls and n["published"] for n in res["news"])
    assert all(0 <= n["known_share"] <= 1 for n in res["news"])
    t = res["timeline"]
    assert [p["round"] for p in t["periods"]] == [1, 2, 3] and t["unit"] == "month"
    sched = [e for e in t["events"] if e["kind"] == "scheduled"]
    assert sched and sched[0]["url"] == "https://example.org/upi-fee" and sched[0]["round"] == 1
    assert t["base"] is None  # no what-ifs, no base case
    people = client.get(f"/api/runs/{rid}/personas").json()
    profiles = [client.get(f"/api/runs/{rid}/personas/{p['id']}").json()["persona"] for p in people[:30]]
    known = [n for pr in profiles for n in pr.get("news", [])]
    assert known and all(n["url"] in urls for n in known)


def test_what_if_events_get_a_base_case(client):
    _, plain = _run(client, {"prompt": PROMPT, "targets": ["IND", "BRA"], "config": CFG})
    spec = plain["spec"]
    spec["events"] = [{"name": "Rival app goes free", "description": "The biggest rival drops its fee to zero.", "at_month": 2, "countries": ["IND"], "reach": "mass", "direction": "hurts"}]
    _, r = _run(client, {"prompt": PROMPT, "targets": ["IND", "BRA"], "config": CFG, "spec": spec})
    t = r["results"]["timeline"]
    assumed = [e for e in t["events"] if e["kind"] == "assumed"]
    assert assumed and assumed[0]["round"] == 1 and assumed[0]["heard_share"] > 0.3
    assert t["base"] and len(t["base"]["opinion"]) == len(t["opinion"])
    assert t["opinion"][-1]["value"] < t["base"]["opinion"][-1]["value"]  # a rival going free hurts


def test_news_can_be_switched_off(client):
    _, r = _run(client, {"prompt": PROMPT, "targets": ["IND"], "config": {**CFG, "news": False}})
    assert "news" not in r["results"]
