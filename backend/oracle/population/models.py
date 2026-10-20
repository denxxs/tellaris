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
    tech_affinity: float
    skepticism: float
    risk_appetite: float
    price_sensitivity: float
    conformity: float
    openness: float
    budget_authority: float


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
    income_usd: int
    income_band: str
    traits: Traits
    exposures: list[Exposure] = Field(default_factory=list)
    is_buyer: bool = True
    weight: float = 1.0
    represents: float = 0.0  # real people this agent stands for (estimate)
    influencer_voice: str | None = None  # bloc/country code if sampled as an outside voice

    # Filled in by enrichment
    name: str = ""
    bio: str = ""
    priorities: list[str] = Field(default_factory=list)
    frustrations: list[str] = Field(default_factory=list)
    info_sources: list[str] = Field(default_factory=list)
    voice: str = ""

    def card(self) -> str:
        """Compact description for prompts."""
        t = self.traits
        lines = [
            f"Name: {self.name or 'unnamed'} | {self.age}-year-old {self.gender} in {self.country_name}",
            f"Job: {self.occupation} ({self.seniority}) at a {self.company_type.replace('_', ' ')}"
            + (f" with ~{self.company_size:,} people" if self.company_size > 1 else "")
            + f", sector: {self.sector.replace('_', ' ')}",
            f"Income: ~${self.income_usd:,}/year ({self.income_band} for {self.country_name})",
            f"Buying role: {self.buyer_role.replace('_', ' ')}; budget authority {t.budget_authority:.0%}",
            "Traits (0-1): "
            f"tech affinity {t.tech_affinity:.2f}, skepticism {t.skepticism:.2f}, risk appetite {t.risk_appetite:.2f}, "
            f"price sensitivity {t.price_sensitivity:.2f}, follows peers {t.conformity:.2f}, openness {t.openness:.2f}",
        ]
        if self.bio:
            lines.append(f"Background: {self.bio}")
        if self.priorities:
            lines.append(f"Current priorities: {'; '.join(self.priorities)}")
        if self.frustrations:
            lines.append(f"Frustrations: {'; '.join(self.frustrations)}")
        if self.info_sources:
            lines.append(f"Gets information from: {', '.join(self.info_sources)}")
        return "\n".join(lines)
