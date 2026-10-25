import json

import numpy as np

from oracle.population import views


def _pool(tmp_path, monkeypatch):
    keys = [q.key for q in views.QUESTIONS]
    rows = []
    # 30 women aged 30 working as professionals (all trust people), 30 men aged 70 retired (none do).
    for _ in range(30):
        a = [None] * len(keys)
        a[keys.index("trust_people")] = 1
        a[keys.index("news_social")] = 1
        rows.append([2, 30, 1, 1, 0.0, 0.5, 1.0, *a])
    for _ in range(30):
        a = [None] * len(keys)
        a[keys.index("trust_people")] = 2
        rows.append([1, 70, 4, 6, 0.5, 1.0, 1.0, *a])
    path = tmp_path / "wvs_pool.json"
    path.write_text(json.dumps({"_meta": {"row": ["sex", "age", "work", "occupation", "income_lo", "income_hi", "weight", *keys]},
                                "countries": {"KEN": {"year": 2021, "rows": rows}}}))
    monkeypatch.setattr(views, "POOL_PATH", path)
    views.pool.cache_clear()


def test_match_uses_people_like_them(tmp_path, monkeypatch):
    _pool(tmp_path, monkeypatch)
    rng = np.random.default_rng(0)
    m = views.match("KEN", rng, sex="woman", age=31, population=None, isco_major=2, self_employed=False, income_pct=0.2)
    assert m.answers["trust_people"] == 1 and m.year == 2021
    assert m.matched_on == ["sex", "age", "work", "occupation", "income"]
    r = views.match("KEN", rng, sex="man", age=72, population="retirees", isco_major=None, self_employed=False, income_pct=None)
    assert r.answers["trust_people"] == 2 and "occupation" not in r.matched_on
    # Nobody like a 50-year-old man in work: the match loosens rather than failing.
    x = views.match("KEN", rng, sex="man", age=50, population=None, isco_major=7, self_employed=False, income_pct=None)
    assert x is not None and x.matched_on == ["sex"]
    assert m.source == "World Values Survey"
    # A country the survey didn't cover gets no views, not borrowed ones.
    assert views.match("FRA", rng, sex="man", age=50, population=None, isco_major=7, self_employed=False, income_pct=None) is None
    views.pool.cache_clear()


def test_views_reach_the_prompt_and_drivers(tmp_path, monkeypatch):
    _pool(tmp_path, monkeypatch)
    from oracle.population.models import Persona

    p = Persona(id="p1", country="KEN", country_name="Kenya", segment="s", segment_index=0, occupation_id="teacher",
                occupation="Teacher", isco=2, sector="education", company_type="public", seniority="staff",
                buyer_role="none", age=31, gender="woman", views={"trust_people": 1, "news_social": 1}, views_from={"year": 2021})
    card = p.card()
    assert "Thinks most people can be trusted" in card and "World Values Survey 2021" in card and "Social media: daily" in card
    assert p.model_dump()["views_text"]["news"] == ["Social media: daily"]
    assert views.scores(p.views) == {"trust_people": 1.0, "news_social": 4.0}
    views.pool.cache_clear()


def test_news_reach_follows_their_own_news_habits(tmp_path, monkeypatch):
    _pool(tmp_path, monkeypatch)
    views._country_days.cache_clear()
    from oracle.research.news import know_chance

    from oracle.population.models import Persona

    def kenyan(pid, answers):
        return Persona(id=pid, country="KEN", country_name="Kenya", segment="s", segment_index=0, occupation_id="x",
                       occupation="Teacher", isco=2, sector="education", company_type="smb", seniority="staff",
                       buyer_role="none", age=40, gender="woman", views=answers)

    daily = kenyan("a", {"news_social": 1})
    never = kenyan("b", {"news_social": 5})
    unknown = kenyan("c", {})
    # Everyone in the pool who answered gets news from social media daily, so daily is the average.
    assert views.news_attention("KEN", daily.views, ["social"]) == 1.0
    assert views.news_attention("KEN", never.views, ["social"]) == 0.0
    assert views.news_attention("FRA", daily.views, ["social"]) == 1.0  # country not surveyed: no adjustment
    k = lambda p: know_chance(p, ["KEN"], "broad", [], ["social"])  # noqa: E731
    assert k(daily) == k(unknown) > k(never) == 0
    views.pool.cache_clear()
    views._country_days.cache_clear()


def test_survey_without_occupation_still_matches_and_names_its_source(tmp_path, monkeypatch):
    """Barometer respondents carry no occupation: matching skips it (and says so) but still uses
    sex, age and work, and the respondent's own survey is named."""
    keys = [q.key for q in views.QUESTIONS]
    a = [None] * len(keys)
    a[keys.index("news_radio")] = 1
    rows = [[2, 30, 1, -1, None, None, 1.0, *a] for _ in range(20)] + [[1, 60, 4, -1, None, None, 1.0, *[None] * len(keys)] for _ in range(20)]
    path = tmp_path / "wvs_pool.json"
    path.write_text(json.dumps({"_meta": {"row": ["sex", "age", "work", "occupation", "income_lo", "income_hi", "weight", *keys]},
                                "countries": {"GHA": {"year": 2024, "rows": rows, "sources": [{"name": "Afrobarometer", "year": 2024}],
                                                      "row_src": [0] * len(rows)}}}))
    monkeypatch.setattr(views, "POOL_PATH", path)
    views.pool.cache_clear()
    m = views.match("GHA", np.random.default_rng(0), sex="woman", age=31, population=None, isco_major=2, self_employed=False, income_pct=0.3)
    assert m.answers == {"news_radio": 1} and m.source == "Afrobarometer" and m.year == 2024
    assert "occupation" not in m.matched_on and m.matched_on[:2] == ["sex", "age"]
    views.pool.cache_clear()


def test_borrowed_views_say_where_they_come_from(tmp_path, monkeypatch):
    """A country no survey covers borrows a real respondent from a similar country, and says so."""
    keys = [q.key for q in views.QUESTIONS]
    a = [None] * len(keys)
    a[keys.index("trust_people")] = 1
    rows = [[2, 30, 1, 1, 0.0, 1.0, 1.0, *a] for _ in range(20)]
    path = tmp_path / "wvs_pool.json"
    path.write_text(json.dumps({"_meta": {"row": ["sex", "age", "work", "occupation", "income_lo", "income_hi", "weight", *keys]},
                                "countries": {"BEL": {"year": 2018, "rows": rows, "borrowed_from": ["DEU"],
                                                      "sources": [{"name": "World Values Survey", "year": 2018, "borrowed_from": "DEU"}],
                                                      "row_src": [0] * len(rows)}}}))
    monkeypatch.setattr(views, "POOL_PATH", path)
    views.pool.cache_clear()
    m = views.match("BEL", np.random.default_rng(0), sex="woman", age=31, population=None, isco_major=2, self_employed=False, income_pct=0.5)
    assert m.borrowed_from == "DEU" and m.answers == {"trust_people": 1}
    from oracle.population.models import Persona

    p = Persona(id="p1", country="BEL", country_name="Belgium", segment="s", segment_index=0, occupation_id="teacher",
                occupation="Teacher", isco=2, sector="education", company_type="public", seniority="staff", buyer_role="none",
                age=31, gender="woman", views=m.answers, views_from={"year": 2018, "source": m.source, "borrowed_from": "DEU"})
    assert "no survey covers Belgium" in p.card() and "Germany" in p.card()
    views.pool.cache_clear()
