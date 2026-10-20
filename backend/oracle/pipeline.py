"""Runs a full simulation: scenario -> research -> world -> population ->
reactions -> committees -> diffusion -> report, streaming progress as it goes."""

from __future__ import annotations

import asyncio
from datetime import date
import logging
import secrets
import traceback
import uuid
from typing import Any

from .config import settings_store
from .events import RunChannel, hub
from .llm import Usage, current_usage
from .population.enrich import enrich
from .population.models import Persona
from .population.sampler import PopulationBuilder
from .report.writer import extract_themes, write_report
from .files import bundle
from .research.graph import build_graph, mentions
from .research.graph import context_for as graph_context_for
from .research.search import FactSheet, facts_from_files, research
from .scenario.clarify import apply_answers
from .scenario.compiler import compile_scenario, normalize
from .scenario.models import RunRequest, ScenarioSpec
from .simulate import committee as committee_mod
from .simulate.aggregate import Aggregator
from .scenario.lenses import lens_of
from .simulate.calibrate import DEFAULT_PARAMS, Calibration
from .simulate import timeline as tl
from .simulate.society import meeting_items, run_society
from .research.news import NewsItem, assign, gather_news, known_record, news_lines
from .simulate.reaction import Reaction, react_all
from .store import store
from .world.influence import InfluenceEdge, expand, graph_payload

log = logging.getLogger("oracle.pipeline")

STAGES = [
    ("scenario", "Understanding the question", 0.0, 0.07),
    ("research", "Researching the real world", 0.07, 0.11),
    ("news", "Reading the news", 0.11, 0.14),
    ("graph", "Mapping the topic", 0.14, 0.16),
    ("world", "Mapping influence between countries", 0.16, 0.18),
    ("population", "Building the population", 0.18, 0.32),
    ("reactions", "Simulating individual reactions", 0.32, 0.72),
    ("committees", "Running buying committees", 0.72, 0.82),
    ("diffusion", "People talk it over", 0.82, 0.91),
    ("report", "Writing the analysis", 0.91, 1.0),
]
STAGE = {s[0]: s for s in STAGES}

tasks: dict[str, asyncio.Task] = {}


def lite(p: Persona) -> dict[str, Any]:
    return {
        "id": p.id, "name": p.name, "country": p.country, "segment": p.segment, "occupation": p.occupation,
        "seniority": p.seniority, "voice": p.influencer_voice, "exposures": [e.source for e in p.exposures],
    }


async def load_calibration(spec: ScenarioSpec) -> Calibration:
    kind = lens_of(spec).calibration_kind
    saved = await store.calibration(kind)
    if saved:
        try:
            return Calibration.model_validate(saved)
        except Exception:  # noqa: BLE001
            pass
    a, b = DEFAULT_PARAMS[kind]
    return Calibration(kind=kind, a=a, b=b, source="default")


def _society_point(d: dict[str, Any] | None) -> dict[str, Any] | None:
    """Where a run's conversation ended, for comparing two runs."""
    if not d or not d.get("rounds"):
        return None
    f = d.get("feed") or {}
    curve = (d.get("bass") or {}).get("curve") or []
    return {
        "feed": f.get("style", "word_of_mouth"),
        "after_talk": d["rounds"][-1]["calibrated"],
        "outside_share": f.get("outside_share"),
        "adoption_end": curve[-1]["adoption"] if curve else None,
    }


class Runner:
    def __init__(self, run_id: str, req: RunRequest, ch: RunChannel):
        self.id = run_id
        self.req = req
        self.ch = ch
        # Every run gets a seed, so a what-if can rebuild the same people and change one thing.
        self.cfg = req.config if req.config.seed is not None else req.config.model_copy(update={"seed": secrets.randbelow(2**31)})
        self.settings = settings_store.get()
        self.usage = Usage()

    async def stage(self, name: str, status: str, **extra: Any) -> None:
        key, label, lo, hi = STAGE[name]
        progress = lo if status == "start" else hi
        await self.ch.emit("stage", {"stage": key, "label": label, "status": status, "progress": progress, **extra})
        await store.update_run(self.id, stage=key, progress=progress)

    async def progress(self, name: str, frac: float) -> None:
        _, _, lo, hi = STAGE[name]
        await store.update_run(self.id, progress=lo + (hi - lo) * max(0.0, min(1.0, frac)))

    async def log(self, message: str, level: str = "info") -> None:
        await self.ch.emit("log", {"message": message, "level": level})

    async def run(self) -> None:
        token = current_usage.set(self.usage)
        try:
            await store.update_run(self.id, status="running")
            await self._run()
            await store.update_run(self.id, status="done", progress=1.0, usage=self.usage.to_dict())
            await self.ch.emit("done", {"usage": self.usage.to_dict()})
        except asyncio.CancelledError:
            await store.update_run(self.id, status="cancelled", error="Cancelled by user", usage=self.usage.to_dict())
            await self.ch.emit("error", {"message": "Cancelled"})
            raise
        except Exception as exc:  # noqa: BLE001
            log.exception("run %s failed", self.id)
            await store.update_run(self.id, status="failed", error=f"{type(exc).__name__}: {exc}", usage=self.usage.to_dict())
            await self.ch.emit("error", {"message": f"{type(exc).__name__}: {exc}", "trace": traceback.format_exc()[-2000:]})
        finally:
            current_usage.reset(token)
            await self.ch.close()
            hub.drop(self.id)
            tasks.pop(self.id, None)

    async def _run(self) -> None:
        roles = self.settings.roles
        crowd = roles.crowd or [roles.planner]
        req = self.req
        as_of = date.today()

        # 1. Scenario (with the user's files, if any)
        await self.stage("scenario", "start")
        context, file_metas = bundle(req.file_ids)
        if file_metas:
            await self.ch.emit("files", file_metas)
            await self.log(f"Read {len(file_metas)} {'file' if len(file_metas) == 1 else 'files'}: {', '.join(m['name'] for m in file_metas)}")
        prompt = apply_answers(req.prompt, req.clarifications)
        if req.spec is not None:
            spec = req.spec
            if req.lens:
                spec.lens = req.lens
            spec = normalize(spec, prompt, req.targets or None, req.global_depth)
        else:
            spec = await compile_scenario(
                prompt, roles.planner, req.targets or None, context,
                lens=req.lens, scope=req.scope, global_depth=req.global_depth,
            )
        await store.update_run(self.id, spec=spec.model_dump(), title=spec.title)
        await self.ch.emit("scenario", spec.model_dump())
        await self.stage("scenario", "done")

        # 2. Research: the user's files first, then the web.
        sheet = FactSheet()
        web = self.cfg.research and self.settings.search_provider != "none"
        if web or context:
            await self.stage("research", "start")
            if context:
                try:
                    from_files = await facts_from_files(context, spec.subject, spec.targets, roles.analyst)
                    sheet.facts.extend(from_files.facts)
                    sheet.competitors.extend(from_files.competitors)
                    sheet.price_points.extend(from_files.price_points)
                    await self.log(f"Took {len(from_files.facts)} facts from your files")
                except Exception as exc:  # noqa: BLE001
                    await self.log(f"Couldn't read facts from your files: {exc}", "warn")
            if web:
                queries = spec.research_queries or [f"{spec.subject[:120]} market", f"{spec.subject[:80]} competitors pricing"]
                try:
                    found, hits = await research(spec.subject, spec.question, queries, spec.targets, self.settings.search_provider, roles.analyst)
                    sheet.facts.extend(found.facts)
                    sheet.competitors.extend(found.competitors)
                    sheet.price_points.extend(found.price_points)
                    await self.log(f"Read {len(hits)} web sources, kept {len(found.facts)} facts")
                except Exception as exc:  # noqa: BLE001
                    await self.log(f"Web research failed, continuing without it: {exc}", "warn")
            if sheet.competitors:
                spec.competitors = list(dict.fromkeys([*spec.competitors, *sheet.competitors]))[:10]
            await store.update_run(self.id, research=sheet.model_dump(), spec=spec.model_dump())
            await self.ch.emit("research", sheet.model_dump())
            await self.stage("research", "done")
        else:
            await self.stage("research", "skipped")

        # 2a. Current affairs: the real news around the question, today.
        news: list[NewsItem] = []
        news_status = "off" if not self.cfg.news else "no_search" if self.settings.search_provider == "none" else "none_found"
        if self.cfg.news and self.settings.search_provider != "none":
            await self.stage("news", "start")
            try:
                news, read = await gather_news(spec, self.settings.search_provider, roles.analyst, as_of)
                await self.log(f"Read {read} news stories, kept {len(news)} that matter now" if read else "Found no recent news on this; people go on what they already know")
                await self.ch.emit("news", [n.model_dump() for n in news])
                await self.stage("news", "done", items=len(news))
            except Exception as exc:  # noqa: BLE001 - news helps but must never stop a run
                await self.log(f"Couldn't read the news, continuing without it: {exc}", "warn")
                await self.stage("news", "skipped")
        else:
            await self.stage("news", "skipped")

        # 2b. Knowledge graph of the topic.
        graph: dict[str, Any] | None = None
        if self.cfg.knowledge_graph:
            await self.stage("graph", "start")
            try:
                graph = await build_graph(spec, sheet.facts, roles.analyst)
                await self.ch.emit("graph", graph)
                await self.stage("graph", "done", entities=len(graph["entities"]), links=len(graph["relations"]))
            except Exception as exc:  # noqa: BLE001 - the graph helps but must never stop a run
                await self.log(f"Couldn't map the topic, continuing without it: {exc}", "warn")
                await self.stage("graph", "skipped")
        else:
            await self.stage("graph", "skipped")

        # 3. World
        await self.stage("world", "start")
        extra = [
            InfluenceEdge(
                source=f.origin, target=t, channel=f.channel, strength=f.strength, sectors=f.sectors or ["all"],
                note=f"{f.name}: {f.description}", origin="scenario",
            )
            for f in spec.forces
            if f.origin and f.origin not in ("global",)
            for t in (f.affects or spec.targets)
            if t != f.origin
        ]
        influencers = expand(spec.targets, extra, self.cfg.influence_threshold, spec.sectors or None)
        world = graph_payload(spec.targets, influencers)
        await store.update_run(self.id, world=world)
        await self.ch.emit("world", world)
        await self.stage("world", "done", influencers=len(influencers))

        # 4. Population
        await self.stage("population", "start")
        people = await self._population(spec, influencers)
        await self.stage("population", "done", agents=len(people))

        # 5. Reactions
        await self.stage("reactions", "start")
        total = len(people) * self.cfg.runs_per_agent
        done_count = 0

        async def on_reaction(r: Reaction, p: Persona) -> None:
            nonlocal done_count
            done_count += 1
            await self.ch.buffered("reactions", {"id": p.id, "p": r.p_stated, "choice": r.choice, "attention": r.attention, "quote": r.quote[:220], "model": r.model, "run": r.run})
            if done_count % 25 == 0:
                await self.progress("reactions", done_count / max(total, 1))

        # The business lens keeps its locked prompt; other lenses get each person's slice of the graph.
        known_for = None
        if graph and lens_of(spec).id != "b2b":
            known_for = graph_context_for(graph, {p.country: p.country_name for p in people})
        # Each person knows only the news they'd plausibly have come across.
        heard = assign(people, news, self.cfg.seed) if news else {}
        if heard:
            for p in people:
                p.news = known_record(heard.get(p.id, []))
            await store.save_personas(self.id, [p.model_dump() for p in people])
        reactions = await react_all(
            people, spec, sheet.facts, crowd, self.cfg.runs_per_agent, self.cfg.temperature, on_reaction, known_for=known_for,
            news_for=(lambda p: news_lines(heard.get(p.id, []))) if heard else None, today=as_of,
        )
        await self.ch.flush()
        await store.save_reactions(self.id, [r.model_dump() for r in reactions])
        if not reactions:
            raise RuntimeError("No agent produced a valid answer. Check the crowd models in Settings.")
        await self.stage("reactions", "done", samples=len(reactions))

        cal = await load_calibration(spec)
        agg = Aggregator(people, reactions, spec, cal, seed=self.cfg.seed)
        results = agg.results()
        await self.ch.emit("interim", {"headline": results["headline"], "by_country": results["by_country"]})

        # 6. Committees
        comms: list[committee_mod.Committee] = []
        if lens_of(spec).committees and "committee" in spec.modes and self.cfg.committees > 0:
            await self.stage("committees", "start")
            comms = committee_mod.form_committees(spec, people, self.cfg.committees, seed=self.cfg.seed)
            finished = 0

            async def on_committee(c: committee_mod.Committee) -> None:
                nonlocal finished
                finished += 1
                await self.ch.emit("committee", {"id": c.id, "country": c.country, "company_type": c.company_type, "decision": c.decision.model_dump() if c.decision else None, "members": c.members})
                await self.progress("committees", finished / max(len(comms), 1))

            comms = await committee_mod.run_committees(comms, people, spec, sheet.facts, crowd, roles.analyst, self.cfg.committee_rounds, self.cfg.temperature, on_committee)
            await store.save_committees(self.id, [c.model_dump() for c in comms])
            results["committees"] = committee_mod.summarize(comms, spec)
            await self.stage("committees", "done", committees=len(comms))
        else:
            await self.stage("committees", "skipped")

        # 7. Society: people post, reply and change their minds; meetings join the feed.
        # Rounds are periods of real time; real scheduled events and your what-ifs land in theirs.
        periods = tl.periods(as_of, spec.horizon_months, self.cfg.diffusion_rounds)
        events = tl.events_for(spec, news, as_of)
        for e in events:
            e["round"] = tl.round_of(e["at_month"], spec.horizon_months, self.cfg.diffusion_rounds)
        base: dict[str, Any] | None = None
        if "diffusion" in spec.modes and self.cfg.diffusion_rounds > 0:
            await self.stage("diffusion", "start")

            async def on_round(snap: dict[str, Any]) -> None:
                await self.ch.emit("diffusion_round", snap)
                await self.progress("diffusion", snap["round"] / max(self.cfg.diffusion_rounds, 1))

            async def on_items(items: list[dict[str, Any]]) -> None:
                for it in items:
                    await self.ch.buffered("feed", it, every=0.3)

            meetings = meeting_items(comms) if comms else []
            minds: dict[str, dict[str, Any]] = {}
            summary, feed = await run_society(
                people, reactions, spec, cal, crowd, self.cfg.diffusion_rounds, self.cfg.diffusion_agent_cap,
                self.cfg.temperature, seed=self.cfg.seed, initial_items=meetings, on_items=on_items, on_round=on_round,
                memory=self.cfg.memory, minds_out=minds, feed_style=self.cfg.feed_style, events=events, periods=periods,
            )
            if any(e["kind"] == "assumed" for e in events):
                # The same people again with only the real world, so you can see what your what-ifs add.
                await self.log("Running the base case: the same people with real news only")
                base_summary, _ = await run_society(
                    people, reactions, spec, cal, crowd, self.cfg.diffusion_rounds, self.cfg.diffusion_agent_cap,
                    self.cfg.temperature, seed=self.cfg.seed, initial_items=meetings, memory=self.cfg.memory,
                    feed_style=self.cfg.feed_style, events=[dict(e) for e in events if e["kind"] != "assumed"], periods=periods,
                )
                base = {
                    "opinion": [{"round": r["round"], "value": r["calibrated"]} for r in base_summary["rounds"]],
                    "adoption": base_summary["bass"]["curve"],
                }
            await self.ch.flush()
            await store.save_feed(self.id, feed)
            if minds:
                # Memories and reflections live on each person's record, read by their profile and chat.
                await store.save_personas(self.id, [{**p.model_dump(), "mind": minds[p.id]} for p in people if p.id in minds])
                ref = summary.get("reflection") or {}
                if ref.get("people"):
                    await self.log(f"{ref['people']} people reflected on what they saw; {ref['changed_mind']} changed their minds")
            results["diffusion"] = summary
            await self.stage("diffusion", "done", posts=summary.get("society", {}).get("posts", 0))
        else:
            await self.stage("diffusion", "skipped")

        if graph:
            talk = await store.feed(self.id) if "diffusion" in results else []
            found = mentions(graph, reactions, talk, {p.id: p for p in people})
            for e in graph["entities"]:
                e["mentions"] = found.get(e["id"], {"people": 0, "lean": None, "samples": []})
            results["graph"] = graph

        # 8. Themes + report
        await self.stage("report", "start")
        themes = await extract_themes(agg.raw_lists(), roles.analyst, seed=self.cfg.seed)
        results["themes"] = themes.model_dump()
        results["seed"] = self.cfg.seed
        results["as_of"] = as_of.isoformat()
        results["news_status"] = "ok" if news else news_status
        if news:
            results["news"] = [n.model_dump() for n in news]
        results["timeline"] = {
            "as_of": as_of.isoformat(),
            "horizon_months": spec.horizon_months,
            "unit": tl.unit_for(spec.horizon_months),
            "periods": periods if "diffusion" in results else [],
            "events": events,
            "opinion": [{"round": r["round"], "value": r["calibrated"]} for r in results["diffusion"]["rounds"]] if "diffusion" in results else [],
            "adoption": results["diffusion"]["bass"]["curve"] if "diffusion" in results else [],
            "base": base,
        }
        if req.parent_id:
            parent = await store.get_run(req.parent_id)
            if parent and parent.get("results"):
                ph = parent["results"]["headline"]
                results["comparison"] = {
                    "parent_id": req.parent_id,
                    "parent_title": parent.get("title"),
                    "parent_value": ph.get("value"),
                    "delta": round(results["headline"]["value"] - (ph.get("value") or 0), 4),
                }
                old = {n.get("url") for n in parent["results"].get("news") or []}
                if parent["results"].get("as_of"):
                    results["comparison"]["parent_as_of"] = parent["results"]["as_of"]
                    results["comparison"]["new_news"] = [n.id for n in news if n.url not in old]
                soc = _society_point(results.get("diffusion"))
                psoc = _society_point(parent["results"].get("diffusion"))
                if soc and psoc:
                    # The feed changes the conversation, not first reactions, so compare where the talk ended too.
                    results["comparison"]["society"] = {"parent": psoc, "this": soc, "delta": round(soc["after_talk"] - psoc["after_talk"], 4)}
        await store.update_run(self.id, results=results)
        await self.ch.emit("results", results)
        report = await write_report(spec, results, roles.analyst)
        await store.update_run(self.id, report=report.model_dump())
        await self.ch.emit("report", report.model_dump())
        await self.stage("report", "done")

    async def _population(self, spec: ScenarioSpec, influencers) -> list[Persona]:
        roles = self.settings.roles
        if self.req.parent_id:
            parent = await store.get_run(self.req.parent_id)
            pspec = (parent or {}).get("spec") or {}
            if pspec and sorted(pspec.get("targets", [])) == sorted(spec.targets) and [s.get("name") for s in pspec.get("segments", [])] == [s.name for s in spec.segments]:
                rows = await store.personas(self.req.parent_id)
                if rows:
                    people = [Persona.model_validate(r) for r in rows]
                    await store.save_personas(self.id, [p.model_dump() for p in people])
                    await self.ch.emit("personas", [lite(p) for p in people])
                    await self.log(f"Reusing the same {len(people)} people as the original run, so the comparison is fair")
                    return people

        builder = PopulationBuilder(spec, influencers, seed=self.cfg.seed, weighting=self.cfg.weighting)
        people = builder.build(self.cfg.agents, self.cfg.influencer_voices)
        await self.log(f"Sampled {len(people)} people across {len(spec.targets)} countries and {len(spec.segments)} segments")
        enriched = 0

        async def on_batch(batch: list[Persona]) -> None:
            nonlocal enriched
            enriched += len(batch)
            await self.ch.emit("personas", [lite(p) for p in batch])
            await self.progress("population", enriched / max(len(people), 1))

        context = f"{spec.title}. {spec.question}"
        await enrich(people, roles.crowd[0] if roles.crowd else roles.planner, context, on_batch)
        await store.save_personas(self.id, [p.model_dump() for p in people])
        return people


async def start_run(req: RunRequest) -> str:
    run_id = uuid.uuid4().hex[:12]
    await store.create_run(run_id, req.prompt, req.model_dump(), req.parent_id)
    ch = hub.open(run_id)
    runner = Runner(run_id, req, ch)
    tasks[run_id] = asyncio.create_task(runner.run())
    return run_id


async def cancel_run(run_id: str) -> bool:
    t = tasks.get(run_id)
    if not t:
        return False
    t.cancel()
    return True
