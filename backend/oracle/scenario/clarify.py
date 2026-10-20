"""Before a run: read the question, pick a lens and scope, and ask only what really matters."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from ..llm import llm
from .lenses import LENSES


class Question(BaseModel):
    id: str = Field(description="Short id, e.g. 'price'")
    question: str = Field(description="The question, in plain words, under 120 characters")
    why: str = Field(default="", description="One short line on why it changes the result")
    kind: Literal["single", "multi", "boolean", "number", "short", "long"] = Field(
        description="single = pick one, multi = pick several, boolean = yes/no, number, short or long text"
    )
    options: list[str] = Field(default_factory=list, description="For single and multi: 2-6 options in the user's terms")
    default: str = Field(default="", description="Your best guess, used if the user skips")
    unit: str | None = Field(default=None, description="For number: the unit, e.g. USD per month")

    @field_validator("options")
    @classmethod
    def _cap(cls, v: list[str]) -> list[str]:
        return [o.strip()[:80] for o in v if o.strip()][:6]


class Clarification(BaseModel):
    reading: str = Field(description="One sentence: how you understand the question")
    lens: Literal["b2b", "consumer", "personal", "opinion", "forecast"]
    lens_reason: str = Field(default="", description="A few words on why this lens")
    scope: Literal["countries", "global"] = "countries"
    questions: list[Question] = Field(default_factory=list, description="0-4 questions; empty when the description is clear")

    @field_validator("questions")
    @classmethod
    def _limit(cls, v: list[Question]) -> list[Question]:
        return v[:4]


def _lens_lines() -> str:
    return "\n".join(f"- {l.id}: {l.label}. {l.description}" for l in LENSES.values())


SYSTEM = f"""You prepare a question for a simulation of real people. Read the user's description (and any files) and decide:

1. The lens:
{_lens_lines()}
2. scope: "global" if the user wants the whole world or "everywhere", else "countries".
3. Up to 4 clarifying questions, ONLY when the answer would materially change who is simulated or what they judge:
   an unknown or ambiguous price or plan, unclear target people or countries, an unclear time frame, what counts as success,
   or which options people choose between. Do not ask about things you can reasonably assume. A clear description gets 0 questions.
   Prefer "single" (multiple choice) with your best guess as the default and as one of the options. Keep questions short and friendly.
   Never ask for internal or sensitive data."""


async def clarify(prompt: str, targets: list[str], context: str, model: str) -> Clarification:
    user = (
        f"Today is {date.today().isoformat()}.\n"
        f"Countries the user picked: {', '.join(targets) if targets else 'none'}\n\n"
        + (f"FILES:\n{context[:12000]}\n\n" if context else "")
        + f"DESCRIPTION:\n\"\"\"\n{prompt}\n\"\"\""
    )
    return await llm.json(
        task="clarify", model=model, system=SYSTEM, user=user, schema=Clarification, temperature=0.2,
        mock_ctx={"prompt": prompt + ("\n" + context[:2000] if context else ""), "targets": targets},
    )


def apply_answers(prompt: str, answers: list[dict[str, str]]) -> str:
    """Fold the user's answers into the description the planner reads."""
    lines = [f"- {a.get('question', '').strip()} {a.get('answer', '').strip()}".rstrip() for a in answers if a.get("answer")]
    if not lines:
        return prompt
    return prompt.rstrip() + "\n\nClarifications from the user:\n" + "\n".join(lines)
