"""Current affairs: the real news around a question, and who in the crowd would know it.

Every run starts from the world as it is today. Tellaris searches recent news for the question,
keeps items that are relevant and recent enough to matter, and gives each simulated person only
the items they would plausibly have come across: mass news reaches most people in a country,
niche news only reaches the people it concerns (an RBI circular reaches an Indian finance worker,
not an Indian student).

Nothing here is invented: an item exists only if a search result with a publish date backs it,
and its date, outlet and link come from that result, never from the model.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import math
import os
import re
from datetime import date, datetime
from functools import lru_cache
from typing import Any, Literal
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, Field, field_validator

from ..config import load_json
from ..llm import llm
from ..population import views
from ..population.models import Persona
from ..scenario.models import ScenarioSpec

log = logging.getLogger("oracle.news")

Reach = Literal["mass", "broad", "niche"]
Medium = Literal["tv", "newspaper", "radio", "internet", "social", "friends"]
MEDIA = ["tv", "newspaper", "radio", "internet", "social", "friends"]

REACH_LABEL = {"mass": "Everyone's talking about it", "broad": "Widely covered", "niche": "Specialist news"}
# Chance a person in the country hears an item of this reach, before anything about them.
REACH_BASE = {"mass": 0.85, "broad": 0.45, "niche": 0.07}
MAX_ITEMS = 14  # items kept per run: a prompt budget, see docs/no-assumptions.md


@lru_cache(maxsize=1)
def _decay() -> dict:
    try:
        return load_json("news_decay.json")
    except FileNotFoundError:
        return {}


def remembered(age_days: float) -> float:
    """Share of people who knew a story that still remember it after this many days: the memory
    chain model fitted to ~14,000 people's recall of news events (Meeter, Murre & Janssen 2005),
    averaged over their three samples. 1.0 without the data file."""
    params = (_decay().get("memory") or {}).get("params")
    if not params or age_days <= 0:
        return 1.0

    def p(t: float, m1: float, a1: float, m2: float, a2: float) -> float:
        r = m1 * (math.exp(-a1 * t) + m2 / (a2 - a1) * (math.exp(-a1 * t) - math.exp(-a2 * t)))
        return 1 - math.exp(-r)

    return sum(p(age_days, *k) / p(0, *k) for k in params.values()) / len(params)


def attention(age_days: float) -> float:
    """Share of a story's peak attention left after this many days (Wikipedia pageviews of news
    stories, scripts/fit_news_decay.py). 1.0 without the data file."""
    f = _decay().get("fit")
    if not f or age_days <= 0:
        return 1.0
    return min(1.0, f["fast_share"] * 0.5 ** (age_days / f["fast_half_life_days"])
               + f["slow_share"] * 0.5 ** (age_days / f["slow_half_life_days"]) + f["floor"])


class NewsHit(BaseModel):
    title: str
    url: str
    snippet: str
    published: date
    source: str
    query: str


class NewsQueries(BaseModel):
    queries: list[str] = Field(default_factory=list, description="6-8 short news search queries")


class NewsDraft(BaseModel):
    hit: int = Field(description="Number of the search result this item comes from")
    headline: str = Field(description="Short headline in plain words, at most 90 characters")
    summary: str = Field(description="One or two sentences: what happened and why it matters for the question")
    countries: list[str] = Field(default_factory=list, description="ISO3 codes where this is news; empty if global")
    reach: Reach = Field(description="mass: most people in those countries hear of it; broad: widely covered; niche: only people it concerns follow it")
    audiences: list[str] = Field(default_factory=list, description="Kinds of people who follow it closely even if niche: sectors, jobs or interests, e.g. finance, retail, students, gamers")
    media: list[Medium] = Field(default_factory=list, description="Where people come across this story: tv, newspaper, radio, internet, social (social media), friends (word of mouth). Empty if everywhere.")
    stance: Literal["helps", "hurts", "neutral"] = "neutral"
    relevance: float = Field(ge=0, le=1, description="How much it bears on the question, 0-1")
    lasting: bool = Field(default=False, description="True if it is still in effect and shaping things (a law, a price change, a market shift), not a one-day story")
    upcoming: str | None = Field(default=None, description="If it announces a scheduled future event, its date as YYYY-MM-DD; else null")

    @field_validator("headline", "summary")
    @classmethod
    def _trim(cls, v: str) -> str:
        return v.strip()[:400]


class NewsDrafts(BaseModel):
    items: list[NewsDraft] = Field(default_factory=list)


class NewsItem(BaseModel):
    id: str
    headline: str
    summary: str
    published: str
    source: str
    url: str
    countries: list[str] = Field(default_factory=list)
    reach: Reach = "broad"
    audiences: list[str] = Field(default_factory=list)
    media: list[Medium] = Field(default_factory=list)
    stance: Literal["helps", "hurts", "neutral"] = "neutral"
    relevance: float = 0.5
    lasting: bool = False
    upcoming: str | None = None
    score: float = 0.0
    age_days: int = 0  # days between publication and the run date
    known_share: float | None = None
    known_by_country: dict[str, float] = Field(default_factory=dict)


QUERIES_SYSTEM = """You plan news searches for a simulation of how real people will respond to a question.
Write 6-8 short news search queries (3-7 words each) that find CURRENT AFFAIRS shaping how people in the target
countries see this question right now: the product category and competitors, prices and the economy people feel
(inflation, jobs, rates), regulation and its dates, scandals or trends, and scheduled events coming up.
Search the category and the world around it, not just the product name (a new product has no news yet).
Use the countries' names. No quotes or operators."""

DISTIL_SYSTEM = """You select the current affairs that real people in the target countries would carry into this question.
Use ONLY the numbered search results. Each item must come from one result (give its number). Skip results that are
irrelevant, duplicates of another item, adverts or evergreen explainers. Judge reach honestly: most news is niche or
broad; only stories that dominate a country's conversation are mass. Prefer what is recent, unless an older story
is still in effect. 4-14 items."""


def _domain(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def _date(v: Any) -> date | None:
    if not v:
        return None
    s = str(v).strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%a, %d %b %Y %H:%M:%S %Z", "%a, %d %b %Y %H:%M:%S %z"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        try:
            return date(int(m[1]), int(m[2]), int(m[3]))
        except ValueError:
            return None
    return None


async def _ddg_news(query: str, n: int) -> list[NewsHit]:
    def run() -> list[dict[str, Any]]:
        try:
            try:
                from ddgs import DDGS
            except ImportError:  # older package name
                from duckduckgo_search import DDGS

            return list(DDGS().news(query, max_results=n))
        except Exception as exc:  # noqa: BLE001
            log.warning("duckduckgo news failed for %r: %s", query, exc)
            return []

    out = []
    for r in await asyncio.to_thread(run):
        d = _date(r.get("date"))
        if r.get("url") and d:
            out.append(NewsHit(title=r.get("title", ""), url=r["url"], snippet=(r.get("body") or "")[:500], published=d, source=r.get("source") or _domain(r["url"]), query=query))
    return out


async def _tavily_news(query: str, n: int) -> list[NewsHit]:
    key = os.environ.get("TAVILY_API_KEY")
    if not key:
        return await _ddg_news(query, n)
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post("https://api.tavily.com/search", json={"api_key": key, "query": query, "max_results": n, "topic": "news", "days": 365})
            r.raise_for_status()
            rows = r.json().get("results", [])
    except Exception as exc:  # noqa: BLE001
        log.warning("tavily news failed for %r: %s", query, exc)
        return []
    out = []
    for x in rows:
        d = _date(x.get("published_date"))
        if x.get("url") and d:
            out.append(NewsHit(title=x.get("title", ""), url=x["url"], snippet=(x.get("content") or "")[:500], published=d, source=_domain(x["url"]), query=query))
    return out


async def search_news(queries: list[str], provider: str, as_of: date, per_query: int = 6) -> list[NewsHit]:
    """Dated news results, newest first. Results dated after `as_of` are dropped."""
    if provider == "none" or not queries:
        return []
    fn = _tavily_news if provider == "tavily" else _ddg_news
    batches = await asyncio.gather(*(fn(q, per_query) for q in queries[:8]))
    seen: set[str] = set()
    hits = []
    for batch in batches:
        for h in batch:
            if h.url not in seen and h.published <= as_of:
                seen.add(h.url)
                hits.append(h)
    hits.sort(key=lambda h: h.published, reverse=True)
    return hits


def score(relevance: float, published: date, lasting: bool, as_of: date) -> float:
    """Relevance times the share of people who still remember a story this old (news recall
    data). A story still in effect (a law, a price) is met again every day, so it doesn't fade."""
    age = max((as_of - published).days, 0)
    return round(relevance * (1.0 if lasting else remembered(age)), 4)


def _context(spec: ScenarioSpec, as_of: date) -> str:
    return (
        f"Today is {as_of.isoformat()}.\nSubject: {spec.subject}\nQuestion: {spec.question}\n"
        f"Target countries: {', '.join(spec.targets)}\n"
        + (f"Competitors and alternatives: {', '.join(spec.competitors[:8])}\n" if spec.competitors else "")
        + (f"Sectors: {', '.join(spec.sectors)}\n" if spec.sectors else "")
    )


async def gather_news(spec: ScenarioSpec, provider: str, model: str, as_of: date, max_items: int = MAX_ITEMS) -> tuple[list[NewsItem], int]:
    """The current affairs around this question, best first, and how many results were read."""
    if provider == "none":
        return [], 0
    ctx = _context(spec, as_of)
    try:
        planned = await llm.json(
            task="news_queries", model=model, system=QUERIES_SYSTEM, user=ctx, schema=NewsQueries, temperature=0.2,
            mock_ctx={"spec": spec.model_dump()},
        )
        queries = [q.strip() for q in planned.queries if q.strip()][:8]
    except Exception as exc:  # noqa: BLE001
        log.warning("news query planning failed: %s", exc)
        queries = []
    if not queries:
        queries = [f"{spec.subject[:60]} news", *(f"{c} news" for c in spec.competitors[:2])]
    hits = await search_news(queries, provider, as_of)
    if not hits:
        return [], 0
    hits = hits[:40]
    listing = "\n\n".join(f"[{i + 1}] {h.published.isoformat()}, {h.source}: {h.title}\n{h.snippet}" for i, h in enumerate(hits))
    drafts = await llm.json(
        task="news_items", model=model, system=DISTIL_SYSTEM, user=f"{ctx}\nSEARCH RESULTS:\n{listing}", schema=NewsDrafts, temperature=0.2,
        mock_ctx={"spec": spec.model_dump(), "hits": [h.model_dump(mode="json") for h in hits]},
    )
    items: list[NewsItem] = []
    used: set[int] = set()
    for d in drafts.items:
        if not 1 <= d.hit <= len(hits) or d.hit in used:
            continue
        used.add(d.hit)
        h = hits[d.hit - 1]
        up = _date(d.upcoming)
        items.append(
            NewsItem(
                id=f"n{len(items) + 1:02d}", headline=d.headline or h.title[:90], summary=d.summary, published=h.published.isoformat(),
                source=h.source, url=h.url, countries=[c.upper()[:3] for c in d.countries],
                reach=d.reach, audiences=[a.strip().lower() for a in d.audiences if a.strip()][:6], media=list(dict.fromkeys(d.media)), stance=d.stance,
                relevance=d.relevance, lasting=d.lasting, upcoming=up.isoformat() if up and up > as_of else None,
                score=score(d.relevance, h.published, d.lasting, as_of), age_days=max((as_of - h.published).days, 0),
            )
        )
    items.sort(key=lambda it: -it.score)
    items = items[:max_items]
    for i, it in enumerate(items):
        it.id = f"n{i + 1:02d}"
    return items, len(hits)


# ---------------------------------------------------------------- who knows what

_WORD = re.compile(r"[a-z]{4,}")


def _about(p: Persona) -> str:
    return " ".join([p.sector, p.occupation, p.segment, p.company_type, p.group_trait or ""]).lower().replace("_", " ")


def concerns(p: Persona, audiences: list[str]) -> bool:
    """Does an item's audience include this person's work or interests?"""
    about = _about(p)
    for a in audiences:
        for w in _WORD.findall(a.lower()):
            if w[:5] in about:
                return True
    return False


def know_chance(p: Persona, countries: list[str], reach: str, audiences: list[str], media: list[str] | None = None,
                age_days: int = 0, lasting: bool = False) -> float:
    """How likely this person is to have come across an item and still remember it."""
    base = REACH_BASE.get(reach, 0.3)
    if countries and p.country not in countries:
        base *= 0.2 if reach == "mass" else 0.06  # foreign news rarely travels unless it's huge
    elif not countries:
        base *= 0.8
    if concerns(p, audiences):
        base = max(base, 0.8 if (not countries or p.country in countries) else 0.35)
    # How often they get news where this story runs, against their country's average (their own
    # survey answers, World Values Survey). Without survey views nothing is adjusted.
    base *= views.news_attention(p.country, p.views, media or MEDIA)
    if not lasting:
        base *= remembered(age_days)  # people forget old news (recall data); what's still in effect they keep meeting
    return max(0.0, min(0.97, base))


def draw(seed: Any, pid: str, item_id: str) -> float:
    """A fixed uniform number for this person and item, so reruns agree."""
    h = hashlib.sha256(f"{seed}|{pid}|{item_id}".encode()).digest()
    return int.from_bytes(h[:8], "big") / 2**64


def assign(people: list[Persona], items: list[NewsItem], seed: Any) -> dict[str, list[NewsItem]]:
    """Each person's news: the items they came across, most important first."""
    out: dict[str, list[NewsItem]] = {}
    for p in people:
        known = [it for it in items
                 if draw(seed, p.id, it.id) < know_chance(p, it.countries, it.reach, it.audiences, it.media, it.age_days, it.lasting)]
        known.sort(key=lambda it: -it.score)
        out[p.id] = known
    weights = {p.id: max(p.weight, 1e-9) for p in people if p.influencer_voice is None}
    total = sum(weights.values()) or 1.0
    for it in items:
        it.known_share = round(sum(w for pid, w in weights.items() if it in out.get(pid, [])) / total, 4)
        by_c: dict[str, list[float]] = {}
        for p in people:
            if p.id in weights:
                by_c.setdefault(p.country, []).append(1.0 if it in out[p.id] else 0.0)
        it.known_by_country = {c: round(sum(v) / len(v), 3) for c, v in by_c.items()}
    return out


def month_name(d: date | str) -> str:
    d = date.fromisoformat(d) if isinstance(d, str) else d
    return d.strftime("%b %Y")


def news_lines(items: list[NewsItem]) -> list[str]:
    return [f"- {month_name(it.published)}, {it.source}: {it.headline}. {it.summary}" for it in items]


def known_record(items: list[NewsItem]) -> list[dict[str, Any]]:
    return [{"id": it.id, "headline": it.headline, "published": it.published, "source": it.source, "url": it.url, "reach": it.reach} for it in items]
