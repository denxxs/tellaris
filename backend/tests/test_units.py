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


def test_eu_influences_india_for_it_services():
    infl = expand(["IND"], sectors=["it_services"])
    codes = [i.code for i in infl]
    assert "EU" in codes and "USA" in codes
    eu = next(i for i in infl if i.code == "EU")
    assert any(e.channel == "regulation" for e in eu.edges)


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
    exposed = [p for p in analysts if any(e.source == "EU" for e in p.exposures)]
    # A good share of Indian IT-services analysts should feel EU regulation/outsourcing.
    assert len(exposed) / max(len(analysts), 1) > 0.3
    founders = [p for p in core if p.occupation_id == "founder_b2b_saas"]
    assert all(p.traits.budget_authority > 0.8 for p in founders)


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
    # Population weighting: India's IT analysts far outnumber US SaaS founders.
    founders = sum(p.weight for p in buyers if p.segment == "Founders")
    analysts = sum(p.weight for p in buyers if p.segment == "IT analysts")
    assert analysts > founders * 5
    assert all(p.represents > 0 for p in people)


def test_equal_weighting_respects_group_weights():
    spec = make_spec(segments=[
        Segment(name="Founders", occupations=["founder_b2b_saas"], countries=["USA"]),
        Segment(name="IT analysts", occupations=["it_services_analyst"], countries=["India"]),
    ], target_weights={"USA": 0.5, "IND": 0.5}, general_population_share=0)
    people = PopulationBuilder(spec, [], seed=4, weighting="equal").build(200)
    founders = sum(p.weight for p in people if p.segment == "Founders")
    assert 0.3 < founders < 0.7


def test_every_country_is_covered():
    from oracle.world.countries import countries
    from oracle.world.influence import expand
    cs = countries()
    assert len(cs) >= 200
    for iso in ["PER", "KAZ", "KEN", "TWN", "ETH", "URY", "FJI", "MNG"]:
        assert iso in cs, iso
        assert expand([iso]), f"no influencers for {iso}"
    assert all(abs(sum(c.isco) - 1) < 0.02 for c in cs.values())


def test_headcounts_are_plausible():
    from oracle.population.headcount import occupation_headcount as h
    assert 1e6 < h("USA", "software_engineer") < 4e6
    assert 1e4 < h("USA", "founder_b2b_saas") < 2e5
    assert h("IND", "it_services_analyst") > h("USA", "it_services_analyst")
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
