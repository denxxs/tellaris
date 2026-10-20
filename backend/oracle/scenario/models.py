"""Scenario: the structured version of whatever the user asked."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

SubjectKind = Literal[
    "product", "feature", "pricing", "campaign", "company", "market",  # people deciding to buy or do something
    "personal", "habit",  # people deciding something about their own life
    "policy", "event", "opinion", "preference", "hypothetical", "culture", "other",  # what people think or would choose
]
OutcomeType = Literal["binary", "categorical", "numeric"]
Mode = Literal["reaction", "committee", "diffusion"]


class Segment(BaseModel):
    """A group of people to simulate."""

    name: str = Field(description="Short label, e.g. 'B2B SaaS founders'")
    description: str = Field(default="", description="Who they are and why they matter for this question")
    occupations: list[str] = Field(
        default_factory=list,
        description="Occupation ids from the catalogue. Leave empty for a general-population segment.",
    )
    custom_occupation: str | None = Field(
        default=None, description="Free-text occupation if nothing in the catalogue fits"
    )
    company_types: list[str] = Field(default_factory=list, description="Company types from the catalogue")
    countries: list[str] = Field(
        default_factory=list,
        description="ISO3 codes where this segment exists (e.g. IT-services analysts only in IND). Empty = all targets.",
    )
    age_min: int | None = Field(default=None, ge=15, le=95, description="Youngest age in the group, e.g. 18 for Gen Z adults")
    age_max: int | None = Field(default=None, ge=15, le=100, description="Oldest age in the group, e.g. 28 for Gen Z")
    gender: Literal["any", "woman", "man"] = Field(default="any", description="Only when the question is about one gender")
    trait: str | None = Field(default=None, description="Any other defining trait, e.g. 'own a dog', 'Taylor Swift fans'")
    trait_share: float | None = Field(default=None, ge=0, le=1, description="Estimated share of the base population with the trait")
    weight: float = Field(default=1.0, ge=0, description="Relative share of agents for this segment")
    is_buyer: bool = Field(default=True, description="True if this segment's behaviour is the outcome being predicted")


class Force(BaseModel):
    """An outside force acting on the scenario (regulation, competitor move, macro shock...)."""

    name: str
    origin: str = Field(description="Country ISO3, bloc id (e.g. EU) or 'global'")
    affects: list[str] = Field(default_factory=list, description="ISO3 codes affected; empty = all targets")
    sectors: list[str] = Field(default_factory=lambda: ["all"])
    channel: str = Field(default="regulation")
    direction: Literal["helps", "hurts", "mixed"] = "mixed"
    strength: float = Field(default=0.5, ge=0, le=1)
    description: str = ""


class Price(BaseModel):
    amount: float
    currency: str = "USD"
    period: str = Field(default="month", description="month | year | one-time | per-seat-month | usage")


class ScenarioSpec(BaseModel):
    lens: Literal["b2b", "consumer", "personal", "opinion", "forecast"] | None = Field(
        default=None,
        description="How to treat the question: b2b (companies buying), consumer (people buying or using something), "
        "personal (choices about one's own life), opinion (what people think or prefer), forecast (votes, events, results)",
    )
    scope: Literal["countries", "global"] = Field(default="countries", description="global when the question is about the whole world")
    title: str = Field(description="Short title, max ~8 words")
    question: str = Field(description="The precise question being predicted")
    subject_kind: SubjectKind = "product"
    subject: str = Field(description="What is being evaluated, described clearly and neutrally")
    outcome_type: OutcomeType = "binary"
    outcomes: list[str] = Field(
        default_factory=lambda: ["Yes", "No"],
        description="Possible outcomes. Binary: [positive, negative]. Categorical: 2-6 options.",
    )
    numeric_unit: str | None = None
    numeric_range: list[float] | None = None
    persona_question: str = Field(
        description="The question each simulated person answers about THEIR OWN behaviour or belief"
    )
    horizon_months: int = Field(default=12, ge=1, le=120)
    targets: list[str] = Field(description="Target countries as ISO3 codes")
    target_weights: dict[str, float] = Field(default_factory=dict)
    segments: list[Segment] = Field(default_factory=list)
    general_population_share: float = Field(default=0.15, ge=0, le=1)
    sectors: list[str] = Field(default_factory=list, description="Sectors most relevant to the scenario")
    b2b: bool = False
    committee_roles: list[str] = Field(
        default_factory=lambda: ["champion", "economic_buyer", "technical", "security_legal"]
    )
    modes: list[Mode] = Field(default_factory=lambda: ["reaction"])
    forces: list[Force] = Field(default_factory=list)
    price: Price | None = None
    competitors: list[str] = Field(default_factory=list)
    assumed_reach: float = Field(
        default=0.6,
        ge=0,
        le=1,
        description="Share of the target audience who would realistically hear about it within the horizon",
    )
    research_queries: list[str] = Field(default_factory=list)
    key_uncertainties: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)

    @field_validator("targets")
    @classmethod
    def _upper(cls, v: list[str]) -> list[str]:
        return [x.strip().upper() for x in v if x and x.strip()]

    @model_validator(mode="after")
    def _consistency(self) -> "ScenarioSpec":
        if self.outcome_type == "binary" and len(self.outcomes) != 2:
            self.outcomes = (self.outcomes + ["Yes", "No"])[:2] if self.outcomes else ["Yes", "No"]
        if self.outcome_type == "categorical" and len(self.outcomes) < 2:
            self.outcome_type = "binary"
            self.outcomes = ["Yes", "No"]
        if self.outcome_type == "numeric" and not self.outcomes:
            self.outcomes = ["value"]
        if "reaction" not in self.modes:
            self.modes = ["reaction", *self.modes]
        if self.b2b and "committee" not in self.modes:
            self.modes.append("committee")
        return self


class RunConfig(BaseModel):
    """User-controlled knobs for a simulation run."""

    agents: int = Field(default=200, ge=10, le=5000)
    runs_per_agent: int = Field(default=2, ge=1, le=8, description="Independent samples per agent (ensemble)")
    committees: int = Field(default=12, ge=0, le=200)
    committee_rounds: int = Field(default=2, ge=1, le=5)
    diffusion_rounds: int = Field(default=3, ge=0, le=10)
    diffusion_agent_cap: int = Field(default=150, ge=0, le=5000)
    influencer_voices: int = Field(default=12, ge=0, le=200, description="Extra agents from influencer countries")
    research: bool = True
    influence_threshold: float = Field(default=0.25, ge=0, le=1)
    seed: int | None = None
    temperature: float = Field(default=0.9, ge=0, le=1.5)
    weighting: Literal["population", "equal"] = Field(
        default="population",
        description="population: each person counts for the real headcount they stand for; equal: every group counts the same",
    )


class RunRequest(BaseModel):
    prompt: str = Field(min_length=10, max_length=20000)
    targets: list[str] = Field(default_factory=list, description="Optional country overrides")
    config: RunConfig = Field(default_factory=RunConfig)
    spec: ScenarioSpec | None = Field(default=None, description="Pre-edited scenario (skips the builder)")
    parent_id: str | None = None
    file_ids: list[str] = Field(default_factory=list, description="Uploaded context files")
    lens: Literal["b2b", "consumer", "personal", "opinion", "forecast"] | None = Field(default=None, description="Override the detected lens")
    scope: Literal["countries", "global"] | None = Field(default=None, description="Override: simulate the whole world")
    global_depth: Literal["quick", "deep"] = "quick"
    clarifications: list[dict[str, str]] = Field(default_factory=list, description="Answers to Oracle's clarifying questions")
