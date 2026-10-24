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
    # A country the survey didn't cover gets no views, not borrowed ones.
    assert views.match("FRA", rng, sex="man", age=50, population=None, isco_major=7, self_employed=False, income_pct=None) is None
    views.pool.cache_clear()


def test_views_reach_the_prompt_and_drivers(tmp_path, monkeypatch):
    _pool(tmp_path, monkeypatch)
    from oracle.population.models import Persona

    p = Persona(id="p1", country="KEN", country_name="Kenya", segment="s", segment_index=0, occupation_id="teacher",
                occupation="Teacher", isco=2, sector="education", company_type="public", company_size=1, seniority="staff",
                buyer_role="none", age=31, gender="woman", views={"trust_people": 1, "news_social": 1}, views_from={"year": 2021})
    card = p.card()
    assert "Thinks most people can be trusted" in card and "WVS 2021" in card and "Social media: daily" in card
    assert p.model_dump()["views_text"]["news"] == ["Social media: daily"]
    assert views.scores(p.views) == {"trust_people": 1.0, "news_social": 4.0}
    views.pool.cache_clear()
