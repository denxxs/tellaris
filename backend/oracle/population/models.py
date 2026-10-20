from __future__ import annotations

from pydantic import BaseModel, Field


class Exposure(BaseModel):
    """An outside force this person actually feels in their work or life."""

    source: str  # country / bloc code, or "global"
    source_name: str
    channel: str
    strength: float
    note: str
    direction: str = "mixed"  # helps | hurts | mixed
    origin: str = "map"  # map | scenario


class Traits(BaseModel):
    """Personality measures, only where survey data supplies them (None = no data, left out)."""

    tech_affinity: float | None = None
    skepticism: float | None = None
    risk_appetite: float | None = None
    price_sensitivity: float | None = None
    conformity: float | None = None
    openness: float | None = None
    budget_authority: float | None = None


FACT_TEXT = {
    "internet_daily": ("Uses the internet every day", "Doesn't use the internet every day"),
    "smartphone": ("Main phone is a smartphone", "Main phone isn't a smartphone"),
    "account": ("Has a bank or mobile-money account", "Has no bank or mobile-money account"),
    "credit_card": ("Has a credit card", "Has no credit card"),
    "emergency_hard": ("Would struggle to find emergency money within a month", "Could find emergency money within a month"),
    "news_online": ("Read news online in the past three months", "Hasn't read news online lately"),
}
SENIORITY_TEXT = {"executive": "executive", "senior": "manager", "staff": "", "none": ""}


class Persona(BaseModel):
    id: str
    country: str
    country_name: str
    segment: str
    segment_index: int
    occupation_id: str
    occupation: str
    isco: int
    sector: str
    company_type: str
    company_size: int
    seniority: str
    buyer_role: str
    age: int
    gender: str
    income_usd: int | None = None
    income_band: str = ""
    traits: Traits = Field(default_factory=Traits)
    facts: dict[str, bool] = Field(default_factory=dict)  # digital and money facts, drawn from Global Findex
    exposures: list[Exposure] = Field(default_factory=list)
    is_buyer: bool = True
    weight: float = 1.0
    represents: float = 0.0  # real people this agent stands for (estimate)
    influencer_voice: str | None = None  # bloc/country code if sampled as an outside voice
    group_trait: str | None = None  # a defining trait from their group, e.g. "owns a dog"
    news: list[dict] = Field(default_factory=list)  # current affairs this person has come across

    # Filled in by enrichment
    name: str = ""
    bio: str = ""
    priorities: list[str] = Field(default_factory=list)
    frustrations: list[str] = Field(default_factory=list)
    info_sources: list[str] = Field(default_factory=list)
    voice: str = ""
    tagline: str = ""
    values: list[str] = Field(default_factory=list)
    typical_day: str = ""
    tools_today: list[str] = Field(default_factory=list)
    household: str = ""

    def card(self) -> str:
        """Compact description for prompts."""
        t = self.traits
        level = SENIORITY_TEXT.get(self.seniority, self.seniority)
        working = self.seniority != "none"
        lines = [f"Name: {self.name or 'unnamed'} | {self.age}-year-old {self.gender} in {self.country_name}"]
        if working:
            lines.append(
                f"Job: {self.occupation}{f' ({level})' if level else ''}"
                + (f" at a {self.company_type.replace('_', ' ')}" if self.company_type not in ("none", "") else "")
                + (f" with ~{self.company_size:,} people" if self.company_size > 1 else "")
                + (f", sector: {self.sector.replace('_', ' ')}" if self.sector not in ("none", "") else "")
            )
        else:
            lines.append(f"Situation: {self.occupation}")
        if self.income_usd is not None:
            lines.append(f"Earnings: ~${self.income_usd:,}/year ({self.income_band} in {self.country_name})")
        elif not working:
            lines.append("No earnings of their own")
        if self.buyer_role not in ("none", ""):
            lines.append(f"Role in buying decisions: {self.buyer_role.replace('_', ' ')}")
        known = [FACT_TEXT[k][0 if v else 1] for k, v in self.facts.items() if k in FACT_TEXT]
        if known:
            lines.append("Facts: " + "; ".join(known))
        measured = {
            "tech affinity": t.tech_affinity, "scepticism": t.skepticism, "risk appetite": t.risk_appetite,
            "price sensitivity": t.price_sensitivity, "follows peers": t.conformity, "openness": t.openness,
        }
        shown = [f"{k} {v:.2f}" for k, v in measured.items() if v is not None]
        if shown:
            lines.append("Traits (0-1, from survey data): " + ", ".join(shown))
        # Only facts from data or from the user reach the prompt; the model-written face (name aside) does not.
        if self.group_trait:
            lines.append(f"Also true about you: {self.group_trait}")
        return "\n".join(lines)
