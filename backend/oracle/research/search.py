"""Live research: web search, then distil results into dated, sourced facts.

Providers: DuckDuckGo (free, no key), Tavily (key), or none. Agents only see
facts that came from these sources, so a stale model cannot invent "news".
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import date
from typing import Any

import httpx
from pydantic import BaseModel, Field

from ..llm import llm

log = logging.getLogger("oracle.research")


class SearchHit(BaseModel):
    title: str
    url: str
    snippet: str
    query: str


class Fact(BaseModel):
    statement: str = Field(description="One concrete, checkable fact in plain language")
    relevance: str = Field(description="Why it matters for the scenario")
    countries: list[str] = Field(default_factory=list, description="ISO3 codes it applies to; empty = all")
    stance: str = Field(default="neutral", description="helps | hurts | neutral for the subject")
    source_urls: list[str] = Field(default_factory=list)
    public: bool = Field(default=True, description="False for internal facts a customer or voter could not know")


class FactSheet(BaseModel):
    facts: list[Fact] = Field(default_factory=list)
    competitors: list[str] = Field(default_factory=list)
    price_points: list[str] = Field(default_factory=list, description="Observed competitor or market prices")


async def _ddg(query: str, n: int) -> list[SearchHit]:
    def run() -> list[dict[str, Any]]:
        try:
            try:
                from ddgs import DDGS
            except ImportError:  # older package name
                from duckduckgo_search import DDGS

            return list(DDGS().text(query, max_results=n))
        except Exception as exc:  # noqa: BLE001
            log.warning("duckduckgo search failed for %r: %s", query, exc)
            return []

    rows = await asyncio.to_thread(run)
    return [
        SearchHit(title=r.get("title", ""), url=r.get("href", ""), snippet=r.get("body", ""), query=query)
        for r in rows
        if r.get("href")
    ]


async def _tavily(query: str, n: int) -> list[SearchHit]:
    key = os.environ.get("TAVILY_API_KEY")
    if not key:
        return await _ddg(query, n)
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                "https://api.tavily.com/search",
                json={"api_key": key, "query": query, "max_results": n, "search_depth": "advanced"},
            )
            r.raise_for_status()
            rows = r.json().get("results", [])
    except Exception as exc:  # noqa: BLE001
        log.warning("tavily search failed for %r: %s", query, exc)
        return []
    return [
        SearchHit(title=x.get("title", ""), url=x.get("url", ""), snippet=x.get("content", "")[:700], query=query)
        for x in rows
        if x.get("url")
    ]


async def search(queries: list[str], provider: str, per_query: int = 5) -> list[SearchHit]:
    if provider == "none" or not queries:
        return []
    fn = _tavily if provider == "tavily" else _ddg
    results = await asyncio.gather(*(fn(q, per_query) for q in queries[:8]))
    seen: set[str] = set()
    hits: list[SearchHit] = []
    for batch in results:
        for h in batch:
            if h.url not in seen:
                seen.add(h.url)
                hits.append(h)
    return hits


DISTIL_SYSTEM = """You are a research analyst preparing a fact sheet for a simulation.
Use ONLY the search results provided. Every fact must cite at least one URL from them.
Prefer recent, specific, numeric facts: competitor names and prices, regulations and their dates,
market sizes, adoption rates, notable news. Skip vague marketing claims. 6-15 facts."""


async def research(
    subject: str, question: str, queries: list[str], targets: list[str], provider: str, model: str
) -> tuple[FactSheet, list[SearchHit]]:
    hits = await search(queries, provider)
    if model.startswith("mock/") and not hits:
        sheet = await llm.json(
            task="research_facts",
            model=model,
            system=DISTIL_SYSTEM,
            user="",
            schema=FactSheet,
            mock_ctx={"subject": subject, "targets": targets},
        )
        return sheet, hits
    if not hits:
        return FactSheet(), hits
    listing = "\n\n".join(f"[{i + 1}] {h.title}\nURL: {h.url}\n{h.snippet}" for i, h in enumerate(hits[:40]))
    user = (
        f"Today is {date.today().isoformat()}.\nSubject: {subject}\nQuestion: {question}\n"
        f"Target countries: {', '.join(targets)}\n\nSEARCH RESULTS:\n{listing}"
    )
    sheet = await llm.json(
        task="research_facts",
        model=model,
        system=DISTIL_SYSTEM,
        user=user,
        schema=FactSheet,
        temperature=0.2,
        mock_ctx={"subject": subject, "targets": targets, "hits": [h.model_dump() for h in hits[:10]]},
    )
    valid_urls = {h.url for h in hits}
    for f in sheet.facts:
        f.source_urls = [u for u in f.source_urls if u in valid_urls] or f.source_urls[:1]
    return sheet, hits


FILES_SYSTEM = """You turn a user's own documents (pitch decks, product docs, pricing pages, research) into facts for a simulation.
Extract 4-12 concrete facts: what the product does, its price and plans, who it is for, claims it makes, competitors named, market numbers.
Mark public=false for anything a customer or member of the public could not know (internal targets, costs, roadmaps, confidential figures).
Use source_urls = ["file:<file name>"] for each fact. Do not invent anything that is not in the documents."""


async def facts_from_files(context: str, subject: str, targets: list[str], model: str) -> FactSheet:
    """Facts from the user's own documents. Internal facts are kept for the analyst only."""
    if not context:
        return FactSheet()
    user = f"Subject: {subject}\nTarget countries: {', '.join(targets)}\n\nDOCUMENTS:\n{context}"
    sheet = await llm.json(
        task="file_facts", model=model, system=FILES_SYSTEM, user=user, schema=FactSheet, temperature=0.2,
        mock_ctx={"context": context[:4000]},
    )
    for f in sheet.facts:
        f.source_urls = [u if u.startswith("file:") else f"file:{u}" for u in f.source_urls] or ["file:your documents"]
    return sheet
