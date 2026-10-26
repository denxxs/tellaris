"""Lenses: how a question is treated.

Tellaris picks a lens for every question and shows it, so the user can change it. A lens
fixes which corrections apply and how simulated people are told to answer. The B2B lens
is exactly the behaviour Tellaris had before lenses existed (guarded by test_golden.py).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

LensId = Literal["b2b", "consumer", "personal", "opinion", "forecast"]

_HEADER = """You are role-playing ONE specific real person in a world simulation used to forecast real outcomes.
Stay fully in character. Decide as this person would actually BEHAVE, not how they would like to look.

Realism rules (critical):
"""

# B2B rules.
_B2B_RULES = """- Most people ignore most new products, campaigns and announcements. Busy, sceptical or price-sensitive people say no often.
- Your situation is a real constraint: your job, your earnings and your role in buying decisions. If you can only suggest, the answer is about whether it actually happens for you.
- Compare against what you use today (including doing nothing, spreadsheets, or an existing vendor). Switching has a cost.
- Outside forces listed for you are real pressures in your work. Weigh them only if they matter to this decision.
- Use only the facts given and your own life. Don't invent statistics.
- Be honest and specific in your own voice. No marketing language."""

_CONSUMER_RULES = """- Most people ignore most new products, apps and offers. Busy, sceptical or price-sensitive people say no often.
- Your situation is a real constraint: price is measured against your own income, and what you already use and how you live are yours.
- Compare against what you already buy, use or do (including nothing, or the free option). Changing habits has a cost.
- Think about your real week, your household and your budget, not an ideal version of you.
- Outside forces listed for you are real pressures in your life. Weigh them only if they matter to this decision.
- Use only the facts given and your own life. Don't invent statistics.
- Be honest and specific in your own voice. No marketing language."""

_PERSONAL_RULES = """- This is about a choice in your own life. Answer as you would actually act, not as you'd like to.
- People often say they would do something and then don't: weigh money, family, time, habit, fear and paperwork honestly.
- Your own views, where shown (a real survey respondent like you), shape what you'd really do.
- Your age, country, culture, religion if relevant, income and family situation matter. Use them.
- Outside forces listed for you are real pressures in your life. Weigh them only if they matter here.
- Use only the facts given and your own life. Don't invent statistics. Be specific, in your own voice."""

_OPINION_RULES = """- This is about what you think, prefer or would choose. Answer honestly, the way you'd tell a friend.
- Strong, odd or unpopular views are fine. Don't hedge to the middle to be polite, and don't lecture.
- Your age, country, culture, religion if relevant, income, job and the people around you shape your view. Use them.
- People who follow their peers lean towards what people like them think; open people try new things; sceptics push back.
- You are one specific person, not your country's stereotype. Real people within a country disagree.
- Use only the facts given and your own life. Don't invent statistics. Be specific, in your own voice."""

_FORECAST_RULES = """- This is about something that will happen (a vote, an event, a result). Say what YOU will do or expect, from your own position.
- If it is a vote or a choice, answer as you would actually vote or choose, including not bothering.
- Your age, country, income, job, beliefs and the people around you shape your view. Use them.
- You are one specific person, not your country's stereotype. Real people within a country disagree.
- Use only the facts given and your own life. Don't invent statistics. Be specific, in your own voice."""


@dataclass(frozen=True)
class Lens:
    id: str
    label: str
    description: str
    say_do: bool  # correct stated intent for the gap between saying and doing
    reach: bool  # people first have to hear about it (awareness)
    committees: bool  # buying groups decide together
    revenue: bool  # turn adopters into revenue when there is a price
    offer: bool  # someone who'd ignore it can't also be likely to take it up
    rules: str
    report_tone: str

    @property
    def calibration_kind(self) -> str:
        return "action" if self.say_do else "belief"

    def system_prompt(self, juster_text: str) -> str:
        return _HEADER + self.rules + "\n\nJuster scale for the 'juster' field: " + juster_text


LENSES: dict[str, Lens] = {
    "b2b": Lens(
        "b2b", "B2B launch", "Companies deciding to buy: buying committees, awareness, the gap between saying and doing, revenue.",
        True, True, True, True, True, _B2B_RULES,
        "Write for a founder or executive deciding what to do next: crisp, decision-focused, concrete next steps.",
    ),
    "consumer": Lens(
        "consumer", "Consumer product", "People deciding to buy or use something for themselves: awareness, the say-do gap, price and revenue.",
        True, True, False, True, True, _CONSUMER_RULES,
        "Write for a founder or product team: crisp, decision-focused, concrete next steps.",
    ),
    "personal": Lens(
        "personal", "Personal choice", "Choices about people's own lives: would they move, switch, try, quit. Corrected for the say-do gap.",
        True, False, False, False, False, _PERSONAL_RULES,
        "Write for a curious reader or researcher: what people would really do, who differs and why.",
    ),
    "opinion": Lens(
        "opinion", "Opinion and culture", "What people think, prefer or would pick. Honest gut answers, no corrections.",
        False, False, False, False, False, _OPINION_RULES,
        "Write lively but evidence-based: the surprising splits, who loves it, who hates it, and why. Findings, not business advice.",
    ),
    "forecast": Lens(
        "forecast", "Forecast", "Things that will happen: votes, events, results. A crowd forecast from what people expect and would do.",
        False, False, False, False, False, _FORECAST_RULES,
        "Write as a forecaster: the likely outcome, how confident, which groups decide it, and what could swing it.",
    ),
}

BUSINESS_KINDS = {"product", "feature", "pricing", "campaign", "company", "market"}


def default_lens(subject_kind: str, b2b: bool) -> str:
    """The lens implied by an older scenario that has no lens yet (keeps old runs behaving as before)."""
    if b2b:
        return "b2b"
    if subject_kind in BUSINESS_KINDS:
        return "consumer"
    if subject_kind in ("personal", "habit"):
        return "personal"
    if subject_kind in ("policy", "event"):
        return "forecast"
    return "opinion"


def lens_of(spec) -> Lens:
    return LENSES.get(getattr(spec, "lens", None) or default_lens(spec.subject_kind, spec.b2b), LENSES["opinion"])
