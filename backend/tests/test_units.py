import numpy as np
import pytest

from oracle.llm.client import extract_json
from oracle.population.sampler import PopulationBuilder, _allocate
from oracle.scenario.compiler import normalize
from oracle.scenario.levers import apply_lever
from oracle.scenario.models import Force, ScenarioSpec, Segment
from oracle.simulate.calibrate import apply, default_calibration, fit_platt
from oracle.world.countries import expand_codes, find_mentions, resolve
from oracle.world.influence import expand


def make_spec(**kw) -> ScenarioSpec:
    base = dict(
        title="Test", question="q", subject="An AI tool for finance teams", persona_question="Would you buy it?",
        targets=["IND", "USA"], b2b=True, sectors=["software", "it_services", "finance"],
        segments=[
            Segment(name="Founders", occupations=["founder_b2b_saas"], weight=1),
            Segment(name="IT analysts", occupations=["it_services_analyst"], weight=1),
            Segment(name="CFOs", occupations=["cfo"], weight=0.5),
        ],
    )
    base.update(kw)
    return normalize(ScenarioSpec(**base), "test")


def test_extract_json_variants():
    assert extract_json('{"a": 1}') == {"a": 1}
    assert extract_json('Sure!\n```json\n{"a": 2}\n```') == {"a": 2}
    assert extract_json('Here: {"a": {"b": "}"}} trailing') == {"a": {"b": "}"}}
    assert extract_json('{"a": [1, 2,],}') == {"a": [1, 2]}
    with pytest.raises(ValueError):
        extract_json("no json here")


def test_country_resolution():
    assert resolve("India") == "IND"
    assert resolve("the US") == "USA"
    assert resolve("uk") == "GBR"
    assert resolve("European Union") == "EU"
    assert find_mentions("Launching in the USA and India, maybe Germany later")[:3] == ["USA", "IND", "DEU"]
    assert "DEU" in expand_codes(["EU"])


def test_ties_are_measured_and_sourced():
    # Indian IT services: the biggest buyers abroad, from OECD-WTO services trade data.
    infl = expand(["IND"], sectors=["it_services"])
    tech = {i.code: e for i in infl for e in i.edges if e.channel == "tech_exports"}
    assert "USA" in tech and "EU" in tech
    # India doesn't report its partners; its central bank's survey of software exporters does.
    assert tech["USA"].strength > 0.5 and "RBI" in tech["USA"].note
    assert all(0 < e.strength <= 1 and "Source:" in e.note for i in infl for e in i.edges)
    # EU law applies to members as a fact; non-members get no invented "regulation" strength.
    assert any(e.channel == "regulation" and e.strength == 1.0 for i in expand(["DEU"]) for e in i.edges)
    assert not any(e.channel == "regulation" for i in expand(["IND"]) for e in i.edges)


def test_contacts_abroad_follow_friendship_data():
    from oracle.simulate.diffusion import country_mix

    ind = country_mix("IND", ["IND", "USA"])
    mex = country_mix("MEX", ["MEX", "USA"])
    assert ind["IND"] > 0.95 and mex["USA"] > ind["USA"] * 5  # Mexico is far more tied to the US
    # Meta has no index for China: its ties are estimated by the model fitted on measured pairs,
    # and say so.
    from oracle.world import ties as ties_mod
    chn = country_mix("CHN", ["CHN", "USA"])
    assert chn["CHN"] > 0.9 and 0 < chn["USA"] < 0.1
    assert ties_mod.of("CHN")["friendships"]["estimated"] is True


def test_allocate_exact_and_covering():
    a = _allocate(10, {"a": 0.7, "b": 0.2, "c": 0.1})
    assert sum(a.values()) == 10 and all(v >= 1 for v in a.values())


def test_population_structure_and_exposure():
    spec = make_spec()
    infl = expand(spec.targets, sectors=spec.sectors)
    people = PopulationBuilder(spec, infl, seed=1).build(300, influencer_voices=10)
    core = [p for p in people if p.influencer_voice is None]
    voices = [p for p in people if p.influencer_voice]
    assert len(core) == 300 and len(voices) == 10
    buyers = [p for p in core if p.is_buyer]
    assert abs(sum(p.weight for p in buyers) - 1.0) < 1e-6
    assert all(p.weight == 0 for p in voices)
    analysts = [p for p in core if p.country == "IND" and p.occupation_id == "it_services_analyst"]
    # Every Indian IT-services analyst works in an industry that sells to the EU: no odds involved.
    assert analysts and all(any(e.source == "EU" and e.channel == "tech_exports" for e in p.exposures) for p in analysts)
    # Outside voices come from where the targets' friends abroad live.
    from oracle.world.ties import partners
    abroad = {c for t in spec.targets for c, _, _ in partners(t, "friends")}
    assert {p.country for p in voices} <= abroad
    founders = [p for p in core if p.occupation_id == "founder_b2b_saas"]
    assert all(p.seniority == "executive" for p in founders)


def test_segments_tied_to_countries():
    spec = make_spec(segments=[
        Segment(name="Founders", occupations=["founder_b2b_saas"], countries=["USA"]),
        Segment(name="IT analysts", occupations=["it_services_analyst"], countries=["India"]),
    ])
    assert spec.segments[1].countries == ["IND"]
    people = PopulationBuilder(spec, [], seed=4).build(200)
    assert all(p.country == "USA" for p in people if p.segment == "Founders")
    assert all(p.country == "IND" for p in people if p.segment == "IT analysts")
    buyers = [p for p in people if p.is_buyer]
    assert abs(sum(p.weight for p in buyers) - 1) < 1e-6
    # No published count of SaaS founders: groups are weighted equally and their size is left unknown.
    b = PopulationBuilder(spec, [], seed=4)
    people = b.build(200)
    assert "Founders" in b.unknown_sizes
    assert all(p.represents == 0 for p in people if p.segment == "Founders")
    assert all(p.represents > 0 for p in people if p.segment == "IT analysts")


def test_population_weighting_uses_real_sizes():
    spec = make_spec(segments=[
        Segment(name="US engineers", occupations=["software_engineer"], countries=["USA"]),
        Segment(name="Indian farmers", occupations=["farmer"], countries=["India"]),
    ], general_population_share=0)
    people = PopulationBuilder(spec, [], seed=4).build(200)
    assert abs(sum(p.weight for p in people) - 1) < 1e-6
    engineers = sum(p.weight for p in people if p.segment == "US engineers")
    farmers = sum(p.weight for p in people if p.segment == "Indian farmers")
    assert farmers > engineers * 5


def test_company_sizes_come_from_data():
    from oracle.population import firms
    # Shares across all size classes add up for every job group.
    for iso in ("USA", "IND", "NGA", "BRA"):
        assert abs(sum(p for *_, p in firms.ladder(iso, 2)) - 1) < 0.01, iso
    # Indian elementary workers mostly work in tiny workplaces; Brazilian professionals far less so.
    small = lambda iso, g: sum(p for lo, hi, p in firms.ladder(iso, g) if hi is not None and hi <= 9)  # noqa: E731
    assert small("NGA", 9) > 0.8 and small("BRA", 2) < 0.5
    spec = make_spec(segments=[Segment(name="Engineers", occupations=["software_engineer"], countries=["USA"])], general_population_share=0)
    people = PopulationBuilder(spec, [], seed=3).build(150)
    assert all(p.company_size and p.company_size_text for p in people)
    assert not any(p.company_type in ("startup", "scaleup") for p in people)  # age of firm isn't size: never assumed
    assert len({tuple(p.company_size) for p in people}) >= 5


def test_public_sector_share_comes_from_data():
    spec = make_spec(segments=[Segment(name="Teachers", occupations=["teacher"], countries=["FRA"])], targets=["FRA"], general_population_share=0)
    people = PopulationBuilder(spec, [], seed=3).build(200)
    gov = sum(p.company_type == "government" for p in people) / len(people)
    from oracle.population import firms
    from oracle.world.countries import occupations
    expected = firms.public_share("FRA", occupations()["teacher"].isco08)
    assert 0.4 < expected < 0.95 and abs(gov - expected) < 0.1


def test_equal_weighting_counts_every_group_the_same():
    spec = make_spec(segments=[
        Segment(name="Founders", occupations=["founder_b2b_saas"], countries=["USA"]),
        Segment(name="IT analysts", occupations=["it_services_analyst"], countries=["India"]),
    ], general_population_share=0)
    people = PopulationBuilder(spec, [], seed=4, weighting="equal").build(200)
    founders = sum(p.weight for p in people if p.segment == "Founders")
    assert abs(founders - 0.5) < 1e-6


def test_every_country_is_covered():
    from oracle.world.countries import countries
    from oracle.world.influence import expand
    cs = countries()
    assert len(cs) >= 200
    for iso in ["PER", "KAZ", "KEN", "TWN", "ETH", "URY", "FJI", "MNG"]:
        assert iso in cs, iso
        assert expand([iso]), f"no influencers for {iso}"
    sim = [c for c in cs.values() if c.simulatable]
    assert len(sim) >= 185
    assert all(abs(sum(c.isco) - 1) < 0.02 for c in sim)
    # No guessed figures: territories without labour-force data are left empty, not filled in.
    assert cs["AND"].workforce_m is None and not cs["AND"].simulatable


def test_territories_without_labour_data_are_not_simulated():
    spec = make_spec(targets=["AND", "FRA"])
    assert spec.targets == ["FRA"]
    assert spec.target_weights == {"FRA": 1.0}


def test_headcounts_are_plausible():
    from oracle.population.headcount import occupation_headcount as h
    # ILOSTAT's US count for ISCO 25 split by BLS OEWS: software, web and systems-analyst jobs.
    assert 2e6 < h("USA", "software_engineer") < 6e6
    assert h("USA", "founder_b2b_saas") is None  # no published count
    assert h("IND", "software_engineer") > 1e6
    assert h("IND", "farmer") > 5e7


def test_mentions_avoid_false_friends():
    assert find_mentions("Can you help us decide on pricing?") == []
    assert find_mentions("Launch in the US and South Africa") == ["USA", "ZAF"]
    assert "PER" in find_mentions("Selling to farmers in Peru and Bolivia")


def test_population_is_seeded():
    spec = make_spec()
    infl = expand(spec.targets)
    a = PopulationBuilder(spec, infl, seed=7).build(50)
    b = PopulationBuilder(spec, infl, seed=7).build(50)
    assert [p.model_dump() for p in a] == [p.model_dump() for p in b]


def test_contacts_follow_contact_surveys():
    from oracle.simulate.diffusion import build_network, daily_contacts
    spec = make_spec(segments=[Segment(name="Everyone", occupations=[])], targets=["IND"], general_population_share=0)
    people = PopulationBuilder(spec, [], seed=2).build(400)
    g = build_network(people, seed=2)
    mean_deg = sum(d for _, d in g.degree()) / len(people)
    expected = sum(sum(sum(row) for row in daily_contacts("IND", p.age).values()) for p in people) / len(people)
    assert abs(mean_deg - expected) / expected < 0.15  # a few draws land on someone already known
    young = [g.degree(p.id) for p in people if p.age < 25]
    old = [g.degree(p.id) for p in people if p.age >= 65]
    assert sum(young) / len(young) > sum(old) / len(old)  # the surveys: the young talk to more people


def test_general_population_uses_country_mix():
    spec = make_spec(targets=["IND"], b2b=False, segments=[Segment(name="Adults", weight=1)], general_population_share=0)
    people = PopulationBuilder(spec, [], seed=3).build(600)
    farmers = sum(p.occupation_id in ("farmer", "agri_worker") for p in people) / len(people)
    assert farmers > 0.12  # agriculture is a big share of Indian employment


def test_calibration_shrinks_action_intent():
    cal = default_calibration("product")
    assert apply(0.6, cal) < 0.6
    belief = default_calibration("event")
    assert abs(apply(0.5, belief) - 0.5) < 1e-6


def test_fit_platt_recovers_bias():
    rng = np.random.default_rng(0)
    raw = list(rng.uniform(0.2, 0.9, 40))
    actual = [max(0.0, min(1.0, r - 0.15)) for r in raw]
    cal = fit_platt(raw, actual, "action")
    preds = [apply(r, cal) for r in raw]
    err_before = np.mean(np.abs(np.array(raw) - actual))
    err_after = np.mean(np.abs(np.array(preds) - actual))
    assert err_after < err_before


def test_lever_application():
    spec = make_spec(price={"amount": 49, "currency": "USD", "period": "month"})
    s2 = apply_lever(spec, {"price_amount": 29, "subject_append": "Now SOC 2 certified.", "add_force": {"name": "X", "origin": "EU", "strength": 0.3}})
    assert s2.price.amount == 29
    assert s2.subject.endswith("Now SOC 2 certified.")
    assert any(f.name == "X" for f in s2.forces)
    assert spec.price.amount == 49  # original untouched


def test_normalize_overrides_and_forces():
    spec = ScenarioSpec(
        title="t", question="q", subject="s", persona_question="p", targets=["Germany"],
        forces=[Force(name="AI Act", origin="European Union", affects=["india"])],
        segments=[Segment(name="x", occupations=["not_a_real_job"])],
    )
    out = normalize(spec, "prompt", ["India", "USA"])
    assert out.targets == ["IND", "USA"]
    assert abs(sum(out.target_weights.values()) - 1) < 1e-3
    assert out.forces[0].origin == "EU" and out.forces[0].affects == ["IND"]
    assert out.segments[0].custom_occupation == "not a real job"


def test_scenario_force_is_felt_once():
    from oracle.world.influence import InfluenceEdge
    spec = make_spec(forces=[Force(name="AI Act", origin="EU", affects=[], sectors=["all"], strength=0.9, direction="hurts", description="x")])
    extra = [InfluenceEdge(source="EU", target=t, channel="regulation", strength=0.9, sectors=["all"], note="AI Act: x", origin="scenario") for t in spec.targets]
    infl = expand(spec.targets, extra, sectors=spec.sectors)
    people = PopulationBuilder(spec, infl, seed=5).build(200)
    for p in people:
        notes = [e.note for e in p.exposures]
        assert len(notes) == len(set(notes)), notes


async def test_names_are_unique_within_a_run():
    from oracle.population.enrich import enrich
    spec = make_spec()
    people = PopulationBuilder(spec, [], seed=9).build(300)
    await enrich(people, "mock/oracle", "test")
    names = [p.name for p in people]
    assert len(names) == len(set(names))


def test_bedrock_credentials_are_explicit(tmp_path):
    import os

    from oracle.config import SettingsStore, UserSettings, bedrock_kwargs

    # No keys and no permission: refuse, never fall back to the machine's AWS account.
    with pytest.raises(PermissionError):
        bedrock_kwargs(UserSettings())

    store = SettingsStore(tmp_path / "s.json")
    store.update({"secrets": {"AWS_ACCESS_KEY_ID": "AKIATESTTESTTEST1234", "AWS_SECRET_ACCESS_KEY": "secretsecretsecret9876", "NOT_ALLOWED": "x"}, "extra": {"AWS_REGION_NAME": "eu-west-1"}})
    s = store.get()
    assert "NOT_ALLOWED" not in s.secrets
    kw = bedrock_kwargs(s)
    assert kw == {"aws_access_key_id": "AKIATESTTESTTEST1234", "aws_secret_access_key": "secretsecretsecret9876", "aws_region_name": "eu-west-1"}
    # Secrets never reach the process environment or the browser.
    assert os.environ.get("AWS_SECRET_ACCESS_KEY") != "secretsecretsecret9876"
    pub = store.public()
    assert pub["secrets"]["AWS_SECRET_ACCESS_KEY"] == {"set": True, "masked": "••••9876"}
    assert "secretsecretsecret9876" not in str(pub)
    # A masked value sent back unchanged keeps the saved secret.
    store.update({"secrets": {"AWS_SECRET_ACCESS_KEY": "••••9876"}})
    assert store.get().secrets["AWS_SECRET_ACCESS_KEY"] == "secretsecretsecret9876"
    # Clearing removes it; then machine credentials only with explicit permission.
    store.update({"secrets": {"AWS_ACCESS_KEY_ID": "", "AWS_SECRET_ACCESS_KEY": ""}, "bedrock_machine_credentials": True, "extra": {"AWS_PROFILE": "personal"}})
    assert bedrock_kwargs(store.get()) == {"aws_region_name": "eu-west-1", "aws_profile_name": "personal"}

    # A Bedrock API key wins over everything and is sent as the bearer token.
    store.update({"secrets": {"AWS_BEARER_TOKEN_BEDROCK": "bedrock-api-key-abcdef123456"}, "bedrock_machine_credentials": False})
    assert bedrock_kwargs(store.get()) == {"api_key": "bedrock-api-key-abcdef123456", "aws_region_name": "eu-west-1"}
    assert store.public()["secrets"]["AWS_BEARER_TOKEN_BEDROCK"]["masked"] == "••••3456"


def test_machine_bedrock_key_ignored_unless_allowed(tmp_path, monkeypatch):
    import os

    from oracle.config import SettingsStore

    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "someone-elses-key")
    SettingsStore(tmp_path / "s.json")
    assert "AWS_BEARER_TOKEN_BEDROCK" not in os.environ
    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "my-own-key")
    store = SettingsStore(tmp_path / "s2.json")
    store.update({"bedrock_machine_credentials": True})
    assert os.environ.get("AWS_BEARER_TOKEN_BEDROCK") == "my-own-key"


async def test_bedrock_call_without_credentials_fails_cleanly():
    from oracle.llm import LLMError, llm

    with pytest.raises(LLMError, match="Bedrock has no keys"):
        await llm.text(task="t", model="bedrock/amazon.nova-lite-v1:0", messages=[{"role": "user", "content": "hi"}])
