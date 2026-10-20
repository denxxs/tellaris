"""Offline mock model ("mock/oracle").

Produces schema-valid, plausible output from the structured context each call
passes in, so the full pipeline, UI and tests run with no API keys and no cost.
Answers follow the persona's traits and exposures, so results have realistic
structure, but they are NOT predictions. The UI labels mock runs clearly.
"""

from __future__ import annotations

import hashlib
import math
import random
import re
from typing import Any

MOCK_LATENCY = (0.004, 0.03)


def latency() -> float:
    return random.uniform(*MOCK_LATENCY)


def _rng(*parts: Any) -> random.Random:
    h = hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()
    return random.Random(int(h[:16], 16))


def _clip(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def respond(task: str, ctx: dict[str, Any], system: str = "", user: str = "") -> dict[str, Any]:
    fn = HANDLERS.get(task)
    if fn is None:
        raise ValueError(f"mock has no handler for task '{task}'")
    return fn(ctx)


# ---------------------------------------------------------------- scenario

KEYWORD_OCCUPATIONS = [
    (r"\bfounders?\b|\bstartups?\b", ["founder_b2b_saas"], "Startup founders"),
    (r"infosys|cognizant|\btcs\b|wipro|accenture|it services|outsourc", ["it_services_analyst", "it_services_engineer"], "IT services staff"),
    (r"financial analyst|analysts?\b", ["financial_analyst", "it_services_analyst"], "Financial analysts"),
    (r"\bcfo|finance (team|leader|director)", ["cfo", "accountant"], "Finance leaders"),
    (r"\bcto\b|engineering lead|vp engineering", ["cto"], "Engineering leaders"),
    (r"developers?|engineers?\b", ["software_engineer"], "Software engineers"),
    (r"marketing|marketers?", ["head_marketing", "marketing_specialist"], "Marketing teams"),
    (r"\bsales\b", ["vp_sales", "sales_rep"], "Sales teams"),
    (r"\bhr\b|human resources|recruit", ["head_hr"], "HR leaders"),
    (r"doctors?|clinic|hospital|health", ["doctor", "nurse"], "Healthcare workers"),
    (r"teachers?|schools?", ["teacher"], "Teachers"),
    (r"students?|college|universit", ["student"], "Students"),
    (r"small business|shop|merchant|restaurant", ["smb_owner"], "Small business owners"),
    (r"farmers?|agri", ["farmer"], "Farmers"),
    (r"product managers?", ["product_manager"], "Product managers"),
    (r"security|compliance|ciso", ["ciso"], "Security leaders"),
]


_COMMON = {"We", "We're", "Our", "Will", "The", "If", "Target", "AI", "B2B", "SaaS", "Is", "Should", "How", "What", "Would", "In", "My", "It", "This", "Outcomes", "Yes", "No", "CFOs", "EU"}


def _title(prompt: str) -> str:
    """A short title: the product's name if one is given, else the opening words."""
    from ..world.countries import resolve

    body = re.split(r"outcomes?:", prompt, flags=re.IGNORECASE)[0]
    for m in re.finditer(r"\b[A-Z][a-zA-Z]{2,}\b", body):
        word = m.group(0)
        if word in _COMMON or resolve(word) or re.search(r"(^|[.?!:]\s*)$", body[: m.start()]):
            continue  # common words, places, and words that just start a sentence
        if re.search(rf"\b(in|from|across|to|at)\s+{word}\b", prompt):
            continue  # a place or an employer, not the product
        return f"{word}: will people adopt it?"
    first = re.split(r"[.\n!?]", prompt.strip())[0]
    words = first.split()
    return (" ".join(words[:6]).strip(" ,:;") + "…") if len(words) > 6 else (first or "Untitled scenario")


def compile_scenario(ctx: dict[str, Any]) -> dict[str, Any]:
    from ..world.countries import find_mentions

    prompt: str = ctx["prompt"]
    low = prompt.lower()
    targets = ctx.get("targets") or [c for c in find_mentions(prompt)] or ["USA"]

    belief = bool(re.search(r"\bvote|referendum|election|plebiscite|survey|approve of|support the\b|policy|\blaw\b|ban\b", low))
    b2b = (not belief) and bool(re.search(r"b2b|saas|enterprise|for (teams|companies|businesses)|founders?|crm|api\b|workflow|platform", low))
    kind = "event" if belief else ("pricing" if re.search(r"\bpric(e|ing)\b", low) and "launch" not in low else "product")

    m = re.search(r"outcomes?:\s*([^.?\n]+)", prompt, re.IGNORECASE)
    outcomes = [o.strip() for o in m.group(1).split(",")][:6] if m else (["Adopt", "Don't adopt"] if not belief else ["Yes", "No"])
    if len(outcomes) < 2:
        outcomes = ["Yes", "No"]

    price = None
    pm = re.search(r"[$€£₹]\s?(\d+(?:[.,]\d+)?)\s*(?:/|per\s+)?(seat|user|month|mo|year|yr)?", prompt, re.IGNORECASE)
    if pm:
        period = (pm.group(2) or "month").lower()
        period = {"mo": "month", "yr": "year", "seat": "per-seat-month", "user": "per-seat-month"}.get(period, period)
        price = {"amount": float(pm.group(1).replace(",", "")), "currency": "USD", "period": period}

    hm = re.search(r"(\d+)\s*(months?|years?)", low)
    horizon = 12
    if hm:
        horizon = int(hm.group(1)) * (12 if hm.group(2).startswith("year") else 1)
        horizon = max(1, min(horizon, 120))

    # Segments, tied to the countries named in the same clause ("CFOs in the USA, plus analysts in India").
    clauses = [c for c in re.split(r"[.;]|,\s*plus\b|\bplus\b|,\s*and\b|\bwhile\b", prompt) if c.strip()]
    segments: list[dict[str, Any]] = []
    for pattern, occ, name in KEYWORD_OCCUPATIONS:
        found = [c for c in clauses if re.search(pattern, c.lower())]
        if not found:
            continue
        seg_countries: list[str] = []
        for c in found:
            seg_countries += [x for x in find_mentions(c) if x not in seg_countries]
        segments.append({
            "name": name, "description": f"{name} relevant to the scenario", "occupations": occ, "weight": 1.0,
            "is_buyer": True, "countries": seg_countries,
        })
    if not segments:
        if b2b:
            segments = [
                {"name": "B2B SaaS founders", "occupations": ["founder_b2b_saas"], "weight": 1.2, "is_buyer": True, "company_types": ["startup", "scaleup"]},
                {"name": "Engineering leaders", "occupations": ["cto"], "weight": 0.8, "is_buyer": True},
                {"name": "Finance leaders", "occupations": ["cfo"], "weight": 0.6, "is_buyer": True},
                {"name": "Product managers", "occupations": ["product_manager"], "weight": 0.7, "is_buyer": True},
            ]
        else:
            segments = [{"name": "Adults", "description": "Representative adults", "occupations": [], "weight": 1.0, "is_buyer": True}]

    forces = []
    if "EU" not in targets and any(t in targets for t in ["IND", "USA", "GBR", "AUS", "SGP", "ISR", "CAN"]) and (b2b or "ai" in low.split()):
        forces.append({
            "name": "EU AI Act and GDPR obligations", "origin": "EU", "affects": [], "sectors": ["software", "it_services", "finance"],
            "channel": "regulation", "direction": "hurts", "strength": 0.55,
            "description": "Vendors and IT-services firms serving EU clients must show data protection, transparency and risk controls, which slows procurement of new AI tools.",
        })
    if b2b:
        forces.append({
            "name": "Tighter software budgets", "origin": "USA", "affects": [], "sectors": ["software", "it_services"], "channel": "monetary",
            "direction": "hurts", "strength": 0.4, "description": "Higher interest rates keep CFOs consolidating tools and cutting seats.",
        })
    modes = ["reaction"]
    if b2b:
        modes.append("committee")
    if not belief or re.search(r"viral|social|word of mouth|community|trend", low):
        modes.append("diffusion")

    subject = prompt.strip().replace("\n", " ")
    if len(subject) > 700:
        subject = subject[:700] + "..."
    first = outcomes[0]
    pq = (
        f"Within the next {horizon} months, would you {first.lower()} this?" if not belief
        else f"How will you personally decide? Options: {', '.join(outcomes)}."
    )
    return {
        "title": _title(prompt),
        "question": f"Share of the target population who choose '{first}' within {horizon} months",
        "subject_kind": kind,
        "subject": subject,
        "outcome_type": "binary" if len(outcomes) == 2 else "categorical",
        "outcomes": outcomes,
        "persona_question": pq,
        "horizon_months": horizon,
        "targets": targets,
        "segments": segments,
        "general_population_share": 0.0 if b2b else 0.1,
        "sectors": ["software", "it_services"] if b2b else [],
        "b2b": b2b,
        "modes": modes,
        "forces": forces,
        "price": price,
        "competitors": [],
        "assumed_reach": 0.9 if belief else (0.35 if b2b else 0.45),
        "research_queries": [f"{_title(prompt)} competitors", f"{_title(prompt)} market size"],
        "key_uncertainties": ["How many buyers hear about it", "Price versus existing tools"],
        "assumptions": ["Offline mock scenario - connect a real model for real analysis"],
    }


# ---------------------------------------------------------------- research

def research_facts(ctx: dict[str, Any]) -> dict[str, Any]:
    hits = ctx.get("hits") or []
    if hits:
        facts = [
            {"statement": (h.get("snippet") or h.get("title", ""))[:220], "relevance": "Search result about the subject", "countries": [], "stance": "neutral", "source_urls": [h.get("url")]}
            for h in hits[:8]
        ]
        return {"facts": facts, "competitors": [], "price_points": []}
    return {
        "facts": [
            {"statement": "[Offline demo] Several established tools already cover part of this need.", "relevance": "Buyers compare against what they use today", "countries": [], "stance": "hurts", "source_urls": []},
            {"statement": "[Offline demo] Budgets for new software are under review at many companies.", "relevance": "Slower purchasing", "countries": [], "stance": "hurts", "source_urls": []},
            {"statement": "[Offline demo] Interest in AI-assisted workflows keeps growing.", "relevance": "Tailwind for new tools", "countries": [], "stance": "helps", "source_urls": []},
        ],
        "competitors": [],
        "price_points": [],
    }


# ---------------------------------------------------------------- personas

PRIORITIES = {
    1: ["Hit this quarter's numbers", "Hire and keep good people", "Cut costs without slowing growth", "Prepare the board update", "Close the next funding round"],
    2: ["Ship the current project on time", "Learn new AI tools", "Get promoted this cycle", "Reduce manual reporting work", "Keep clients happy"],
    3: ["Meet monthly targets", "Clear the ticket backlog", "Get certified", "Handle more accounts", "Avoid weekend work"],
    4: ["Keep processing times down", "Avoid errors in data", "Get a stable shift", "Learn new software", "Save for a home"],
    0: ["Pay the bills", "Family time", "Find better work", "Stay healthy", "Save money"],
}
FRUSTRATIONS = [
    "Too many tools that don't talk to each other", "Approvals take forever", "Constant price increases from vendors",
    "Meetings eat the day", "Unclear priorities from leadership", "Security reviews block everything", "Rising cost of living",
    "Data spread across spreadsheets", "Vendors overpromise", "Slow internal IT",
]
SOURCES = {
    "software": ["Hacker News", "LinkedIn", "Lenny's Newsletter", "founder WhatsApp groups", "X / Twitter", "Product Hunt", "YouTube"],
    "it_services": ["LinkedIn", "Economic Times", "internal Yammer", "Moneycontrol", "WhatsApp groups", "Naukri", "YouTube"],
    "finance": ["Bloomberg", "Financial Times", "LinkedIn", "Mint", "Reuters", "CFO peer groups"],
    "default": ["WhatsApp", "YouTube", "Facebook", "local news", "Instagram", "friends and family", "TikTok"],
}
VOICES = ["blunt and numbers-first", "warm but cautious", "dry and sceptical", "energetic, talks fast", "careful, asks lots of questions", "pragmatic, no-nonsense", "polite, avoids conflict"]


def enrich_personas(ctx: dict[str, Any]) -> dict[str, Any]:
    from ..world.countries import countries

    out = []
    for p in ctx["people"]:
        r = _rng("enrich", p["id"], p["country"])
        c = countries().get(p["country"])
        pool = c.names["given"] if c else ["Alex", "Sam"]
        # The curated pools alternate men's and women's names, so pick from the matching half.
        if p["gender"] == "man":
            pool = pool[0::2] or pool
        elif p["gender"] == "woman":
            pool = pool[1::2] or pool
        given = r.choice(pool)
        family = r.choice(c.names["family"]) if c else "Lee"
        pri = PRIORITIES.get(p["isco"], PRIORITIES[2] if p["isco"] in (2, 3) else PRIORITIES[0])
        src = SOURCES.get(p["sector"], SOURCES["default"])
        years = max(1, p["age"] - 23)
        job = p["occupation"].split(" (")[0].strip()
        sceptic = p["traits"]["skepticism"] > 0.6
        out.append({
            "id": p["id"],
            "name": f"{given} {family}",
            "tagline": r.choice([f"{job} in {p['country_name']}", f"{job}. {p['age']}. {p['country_name']}.", f"{job}, {p['company_type'].replace('_', ' ')}"]),
            "bio": (
                f"{given} has spent about {min(years, 35)} years working, now as a {job.lower()} "
                f"at a {p['company_type'].replace('_', ' ')} in {p['country_name']}. "
                + ("Known for questioning every new tool before trying it." if sceptic else "Usually open to trying new things if they save time.")
            ),
            "values": r.sample(VALUES, 3),
            "priorities": r.sample(pri, 3),
            "frustrations": r.sample(FRUSTRATIONS, 2),
            "typical_day": r.choice(DAYS).format(job=job.lower()),
            "tools_today": r.sample(TOOLS.get(p["sector"], TOOLS["default"]), 3),
            "household": r.choice(HOUSEHOLDS if p["age"] > 26 else ["Lives with flatmates", "Lives with parents", "Lives alone"]),
            "info_sources": r.sample(src, 3),
            "voice": r.choice(VOICES),
        })
    return {"people": out}


VALUES = ["Getting things done", "Family first", "Fairness", "Independence", "Security", "Learning", "Status", "Saving money", "Doing things properly", "Community", "Speed", "Trust"]
DAYS = [
    "Starts early with email, then back-to-back meetings; the real {job} work happens after six.",
    "Commutes an hour each way, spends most of the day in spreadsheets and calls.",
    "Mornings on the most urgent problem, afternoons firefighting whatever broke.",
    "Works from home three days a week; blocks time for deep work but rarely keeps it.",
    "A long day on their feet, catching up on messages in the evening.",
]
TOOLS = {
    "software": ["Slack", "Notion", "Jira", "Google Workspace", "HubSpot", "ChatGPT", "GitHub"],
    "it_services": ["Microsoft Teams", "Excel", "SAP", "ServiceNow", "Outlook", "Jira", "ChatGPT"],
    "finance": ["Excel", "QuickBooks", "Bloomberg", "NetSuite", "Tally", "Power BI", "Outlook"],
    "retail": ["WhatsApp Business", "a POS system", "Instagram", "Excel", "Shopify"],
    "default": ["WhatsApp", "Excel", "Gmail", "Google Sheets", "a phone banking app", "YouTube"],
}
HOUSEHOLDS = ["Married, two children", "Lives with partner", "Single parent of one", "Lives with partner and parents", "Lives alone", "Married, no children"]


# ---------------------------------------------------------------- reactions

REASONS_POS = ["It would save my team real hours every week", "Fits how we already work", "Cheaper than what we pay now", "Peers I trust are using something like it", "Solves a problem I have right now", "Looks easy to try without a big commitment"]
REASONS_NEG = ["We already have a tool that does most of this", "Not a priority this year", "I'd need sign-off I won't get", "I don't see enough proof it works", "Switching would cost more than it saves", "Not relevant to my job"]
OBJECTIONS = ["Price is too high for our size", "Security and data-protection review would take months", "Integration with our current stack is unclear", "Unknown vendor - what if they shut down?", "No local support or invoicing", "Compliance with EU clients' requirements", "My team won't change habits", "Budget is frozen"]
CHANGE = ["A free pilot with our own data", "A case study from a company like mine", "A lower entry price", "SOC 2 / ISO 27001 and an EU data option", "A recommendation from someone I trust", "Integration with tools we already use"]


def _base_probability(p: dict[str, Any], spec: dict[str, Any]) -> float:
    t = p["traits"]
    belief = spec["subject_kind"] in ("event", "policy", "other")
    if belief:
        r = _rng("belief-lean", spec["title"], p["country"], p["segment"])
        x = 0.0 + 0.9 * (t["openness"] - 0.5) - 0.5 * (t["conformity"] - 0.5) + r.uniform(-0.3, 0.3)
        if p["age"] > 55:
            x -= 0.25
        if p["income_band"] in ("high", "very high"):
            x += 0.1
        return _clip(1 / (1 + math.exp(-x * 2.2)))
    x = -1.1
    x += 2.0 * (t["tech_affinity"] - 0.5)
    x -= 1.8 * (t["skepticism"] - 0.5)
    x += 0.9 * (t["risk_appetite"] - 0.5)
    x += 0.6 * (t["openness"] - 0.5)
    if spec.get("price"):
        amount = spec["price"]["amount"]
        monthly = amount / 12 if spec["price"]["period"] == "year" else amount
        burden = monthly * 12 / max(p["income_usd"], 1000)
        x -= 2.4 * t["price_sensitivity"] * min(burden * 20, 2.5)
    if spec.get("b2b"):
        x += 1.0 * (t["budget_authority"] - 0.4)
        if p["buyer_role"] == "none":
            x -= 1.5
    if not p["is_buyer"] and not p.get("influencer_voice"):
        x -= 0.4
    for e in p["exposures"]:
        if e["direction"] == "helps":
            x += 0.5 * e["strength"]
        elif e["direction"] == "hurts":
            x -= 0.7 * e["strength"]
        elif e["channel"] == "regulation":
            x -= 0.25 * e["strength"]
        elif e["channel"] in ("capital", "technology", "outsourcing"):
            x += 0.15 * e["strength"]
    return _clip(1 / (1 + math.exp(-x)))


def react(ctx: dict[str, Any]) -> dict[str, Any]:
    p, spec, run = ctx["persona"], ctx["spec"], ctx.get("run", 0)
    r = _rng("react", p["id"], run, spec["title"])
    base = _base_probability(p, spec)
    prob = _clip(base + r.gauss(0, 0.08), 0.01, 0.98)
    juster = int(round(prob * 10))
    t = p["traits"]
    belief = spec["subject_kind"] in ("event", "policy", "other")
    if belief:
        attention = r.choice(["consider", "evaluate", "consider"])
    elif prob < 0.12:
        attention = "ignore" if t["tech_affinity"] < 0.5 or r.random() < 0.5 else "skim"
    elif prob < 0.3:
        attention = "skim"
    elif prob < 0.6:
        attention = "consider"
    else:
        attention = "evaluate"
    outcomes = spec["outcomes"]
    choice = outcomes[0] if prob >= 0.5 else outcomes[-1]
    option_probs = None
    if spec["outcome_type"] == "categorical":
        rest = (1 - prob) / max(len(outcomes) - 1, 1)
        option_probs = {o: (prob if i == 0 else rest) for i, o in enumerate(outcomes)}
    wtp = None
    if spec.get("price"):
        amount = spec["price"]["amount"]
        wtp = round(max(0.0, amount * (0.25 + 1.6 * prob) * (1.3 - t["price_sensitivity"]) * r.lognormvariate(0, 0.3)), 2)
    estimate = None
    if spec["outcome_type"] == "numeric":
        lo, hi = (spec.get("numeric_range") or [0, 100])[:2]
        estimate = round(lo + (hi - lo) * prob, 3)
    pos = prob >= 0.5
    reasons = r.sample(REASONS_POS if pos else REASONS_NEG, 2)
    objections = r.sample(OBJECTIONS, 2 if pos else 3)
    exposures = [e for e in p["exposures"] if e["strength"] >= 0.35]
    if any(e["channel"] == "regulation" for e in exposures):
        objections[0] = "Compliance with EU clients' requirements"
    influences = [e["source"] for e in exposures[:2] if r.random() < 0.7]
    occ = p["occupation"].split("(")[0].strip().lower()
    if belief:
        quote = r.choice([f"I've thought about it and I'm going with {choice}.", f"Honestly, {choice} - my whole circle is talking about it.", f"It's close for me, but {choice}."])
    elif pos:
        quote = r.choice([
            f"As a {occ}, this would actually save me time. I'd try it if the setup is quick.",
            f"If it does what it says, I'd push for it - but I want a pilot first.",
            "Looks useful. I'd put it in front of my team next month.",
        ])
    else:
        quote = r.choice([
            f"We already have something for this. Not switching unless it's clearly better.",
            f"Not a priority for me right now, honestly.",
            f"Sounds nice, but {objections[0].lower()}.",
            "I'd need to see proof from a company like mine before I even look.",
        ])
    return {
        "attention": attention, "juster": juster, "likelihood": round(prob, 3), "choice": choice, "option_probs": option_probs,
        "estimate": estimate, "willingness_to_pay": wtp, "reasons": reasons, "objections": objections,
        "change_mind": r.sample(CHANGE, 2), "influences": influences, "quote": quote, "confidence": round(r.uniform(0.4, 0.85), 2),
    }


# ---------------------------------------------------------------- committees

def committee_turn(ctx: dict[str, Any]) -> dict[str, Any]:
    p, role, rnd, spec = ctx["persona"], ctx["role"], ctx["round"], ctx["spec"]
    r = _rng("turn", p["id"], role, rnd, spec["title"])
    base = _base_probability(p, spec) * 2 - 1
    shift = {"security_legal": -0.35, "economic_buyer": -0.15, "procurement": -0.2, "champion": 0.3, "technical": -0.05}.get(role, 0)
    stance = max(-1.0, min(1.0, base + shift + r.gauss(0, 0.15) + (0.05 * rnd if role == "champion" else -0.03 * rnd)))
    lines = {
        "champion": ["This solves a real problem for my team. I'd like a 30-day pilot.", "We waste hours on this every week. The pilot cost is small."],
        "economic_buyer": ["What's the payback period? I need numbers before I sign anything.", "Budget is tight; show me what we cut to pay for this."],
        "technical": ["Integration looks doable, but I need API docs and an uptime SLA.", "My worry is another tool to maintain. Who owns it?"],
        "security_legal": ["Where is the data stored? Our EU clients will ask for DPAs and audit rights.", "No SOC 2 report, no deal. That's policy."],
        "procurement": ["We need at least two competing quotes.", "Can we get annual pricing with an exit clause?"],
    }
    return {
        "stance": round(stance, 2),
        "statement": r.choice(lines.get(role, ["I need to understand the impact on my team first."])),
        "conditions": r.sample(CHANGE, 1),
        "concerns": r.sample(OBJECTIONS, 1),
    }


def committee_decision(ctx: dict[str, Any]) -> dict[str, Any]:
    transcript, spec = ctx["transcript"], ctx["spec"]
    r = _rng("decision", spec["title"], len(transcript), sum(t["stance"] for t in transcript))
    last_round = max((t["round"] for t in transcript), default=0)
    final = [t["stance"] for t in transcript if t["round"] == last_round] or [0]
    avg, low = sum(final) / len(final), min(final)
    score = avg + 0.4 * low
    prob = _clip(1 / (1 + math.exp(-(score * 2.5 - 0.8))))
    decision = "buy" if prob > 0.6 else "pilot" if prob > 0.35 else "defer" if prob > 0.15 else "reject"
    blockers = list({c for t in transcript for c in t["concerns"]})[:3]
    return {
        "decision": decision,
        "probability_of_purchase": round(prob, 3),
        "deal_cycle_months": round(r.uniform(1.5, 4) if decision in ("buy", "pilot") else r.uniform(4, 9), 1),
        "decisive_factor": blockers[0] if decision in ("defer", "reject") and blockers else "Champion's case on time saved",
        "blockers": blockers,
        "conditions": list({c for t in transcript for c in t["conditions"]})[:2],
        "summary": f"The committee leaned {'towards' if prob > 0.35 else 'against'} it; the strongest objection came from the {'security' if low < -0.3 else 'budget'} side.",
    }


# ---------------------------------------------------------------- diffusion

def diffuse_update(ctx: dict[str, Any]) -> dict[str, Any]:
    p, cur, nb, news = ctx["persona"], ctx["p"], ctx["neighbors"], ctx.get("news")
    r = _rng("diffuse", p["id"], cur, len(nb), news)
    target = sum(nb) / len(nb) if nb else cur
    pull = p["traits"]["conformity"] * 0.6 * (target - cur)
    news_effect = -0.06 if news and any(w in news.lower() for w in ("regulat", "act", "budget", "ban")) else (0.04 if news else 0)
    new = _clip(cur + pull + news_effect + r.gauss(0, 0.04), 0.01, 0.99)
    changed = abs(new - cur) > 0.05
    return {
        "juster": int(round(new * 10)),
        "changed": changed,
        "why": ("People I trust are more positive than I was." if new > cur else "What I'm hearing makes me more cautious.") if changed else "Nothing I heard changes my view.",
        "quote": "I'm warming up to it." if new > cur + 0.05 else ("I'm cooling on it." if new < cur - 0.05 else "Still where I was."),
        "share": new > 0.55 or r.random() < 0.15,
    }


# ---------------------------------------------------------------- analysis

def themes(ctx: dict[str, Any]) -> dict[str, Any]:
    from collections import Counter

    out = {}
    for key, items in ctx["raw"].items():
        c = Counter(i.strip() for i in items if i.strip())
        total = sum(c.values()) or 1
        out[key] = [{"theme": t[:48], "share": round(n / total, 3), "example": t} for t, n in c.most_common(5)]
    return out


def _p(v: float) -> str:
    return f"{v * 100:.1f}%" if v < 0.1 else f"{v:.0%}"


def report(ctx: dict[str, Any]) -> dict[str, Any]:
    spec, res = ctx["spec"], ctx["results"]
    h = res["headline"]
    v = h["value"]
    verdict = "strong" if v > 0.35 else "promising" if v > 0.18 else "uncertain" if v > 0.08 else "weak" if v > 0.03 else "unlikely"
    countries = sorted(res["by_country"], key=lambda c: -c["value"])
    segs = sorted(res["by_segment"], key=lambda s: -s["value"])
    infl = res.get("influence_effects") or []
    drivers = [
        {"factor": d["trait"].replace("_", " "), "effect": "positive" if d["correlation"] > 0 else "negative", "evidence": f"Correlation {d['correlation']:+.2f} with willingness"}
        for d in (res.get("drivers") or [])[:4]
    ]
    country_ins = [{"title": f"{c['label']}: {c['value']:.0%}", "detail": f"{c['n']} agents. Top objection: {(c.get('top_objection') or ['none'])[0]}."} for c in countries[:4]]
    seg_ins = [{"title": f"{s['label']}: {s['value']:.0%}", "detail": f"{s['n']} agents; {s['calibrated']:.0%} if they hear about it."} for s in segs[:4]]
    inf_ins = [
        {"title": f"{i['source_name']} ({i['channel']})", "detail": f"Exposed people: {i['exposed_value']:.0%} vs others {(i['others_value'] or 0):.0%} ({(i['delta'] or 0):+.0%}). {i['note']}"}
        for i in infl[:3]
    ]
    levers = []
    if spec.get("price"):
        amt = spec["price"]["amount"]
        levers.append({"label": f"Cut price to {amt * 0.6:g}", "description": "Test a 40% lower entry price", "changes": {"price_amount": round(amt * 0.6, 2)}})
    levers.append({"label": "Add EU data residency + SOC 2", "description": "Remove the compliance objection", "changes": {"subject_append": "It is SOC 2 Type II certified and offers EU data residency with a standard DPA."}})
    levers.append({"label": "Double awareness", "description": "Stronger distribution", "changes": {"assumed_reach": min(1.0, spec.get("assumed_reach", 0.4) * 2)}})
    return {
        "headline": f"{h['label']}: about {_p(v)} (likely {_p(h['ci'][0])} to {_p(h['ci'][1])}).",
        "verdict": verdict,
        "summary": (
            f"This is an offline demo run using the mock model, so treat the numbers as illustrative only. "
            f"Strongest market: {countries[0]['label'] if countries else 'n/a'}. Strongest segment: {segs[0]['label'] if segs else 'n/a'}. "
            "Connect a real model in Settings for real analysis."
        ),
        "drivers": drivers,
        "country_insights": country_ins,
        "segment_insights": seg_ins,
        "influence_insights": inf_ins,
        "risks": ["Mock model output - not a real prediction", "Low awareness limits adoption regardless of fit"],
        "recommendations": [
            {"action": f"Focus first on {segs[0]['label'] if segs else 'the strongest segment'}", "why": "Highest simulated willingness", "expected_impact": "Faster early traction", "priority": "high"},
            {"action": "Run the top lever as a what-if", "why": "See how much the main objection costs you", "expected_impact": "Quantified upside", "priority": "medium"},
        ],
        "levers": levers,
        "confidence_note": f"{h['n']} agents, {h['samples']} samples, mock model. Not a forecast.",
    }


def text(task: str, messages: list[dict[str, str]], ctx: dict[str, Any]) -> str:
    p = ctx.get("persona") or ctx
    last = messages[-1]["content"] if messages else ""
    r = _rng("chat", p.get("id"), last)
    name = (p.get("name") or "I").split(" ")[0]
    opener = r.choice(["Honestly,", "Look,", "Fair question.", "Hmm."])
    stance = ctx.get("stance")
    view = ""
    if stance is not None:
        view = " I'm leaning towards it." if stance >= 0.5 else " I'm not convinced yet."
    return (
        f"{opener} as {p.get('occupation', 'someone in my job').split('(')[0].strip().lower()} in {p.get('country_name', 'my country')}, "
        f"my day is mostly about {', '.join((p.get('priorities') or ['getting work done'])[:2]).lower()}.{view} "
        f"(Offline demo reply from {name} - connect a real model in Settings for real conversations.)"
    )


HANDLERS = {
    "compile_scenario": compile_scenario,
    "research_facts": research_facts,
    "enrich_personas": enrich_personas,
    "react": react,
    "committee_turn": committee_turn,
    "committee_decision": committee_decision,
    "diffuse_update": diffuse_update,
    "themes": themes,
    "report": report,
}


# ---------------------------------------------------------------- society

AGREE = [
    "Same here, {name}. {reason}.",
    "This. {reason}.",
    "Agree with {name} - {reason_lc}.",
    "{name} is right, {reason_lc}.",
]
DISAGREE = [
    "Not so sure, {name}. {objection}.",
    "Respectfully, no. {objection}.",
    "{name}, have you tried rolling this out for real? {objection}.",
    "I'd push back on that. {objection}.",
]
POST_YES = [
    "Been looking at this. {reason}. Might actually try it.",
    "Unpopular opinion maybe, but this one makes sense for teams like mine. {reason}.",
    "Tried something similar last year. {reason}. Curious if this is better.",
]
POST_NO = [
    "Every month there's a new tool like this. {objection}.",
    "Pass for now. {objection}.",
    "Who is actually buying these? {objection}.",
]


def society_turn(ctx: dict[str, Any]) -> dict[str, Any]:
    p, cur, visible, news, rnd = ctx["persona"], ctx["p"], ctx.get("visible") or [], ctx.get("news"), ctx.get("round", 1)
    r = _rng("society", p["id"], rnd, len(visible))
    t = p["traits"]
    peers = [v["p"] for v in visible if v.get("p") is not None]
    target = sum(peers) / len(peers) if peers else cur
    pull = t["conformity"] * 0.6 * (target - cur)
    news_effect = (-0.06 if any(w in news.lower() for w in ("regulat", "act", "budget", "ban", "rate")) else 0.04) if news else 0
    new = _clip(cur + pull + news_effect + r.gauss(0, 0.04), 0.01, 0.99)
    changed = abs(new - cur) > 0.05
    activity = 0.12 + 0.3 * t["openness"] + (0.15 if abs(cur - 0.5) > 0.3 else 0) + (0.1 if news else 0)
    action, reply_to, text = "quiet", None, ""
    if r.random() < activity:
        reason = r.choice(REASONS_POS)
        objection = r.choice(OBJECTIONS)
        if visible and r.random() < 0.6:
            # Prefer answering someone you disagree with.
            others = sorted(visible, key=lambda v: -abs((v.get("p") or 0.5) - new))
            target_item = others[0] if r.random() < 0.6 else r.choice(visible)
            first = (target_item.get("author_name") or "").split(" ")[0] or "there"
            agree = (target_item.get("p") or 0.5) >= 0.5 and new >= 0.5 or (target_item.get("p") or 0.5) < 0.5 and new < 0.5
            tpl = r.choice(AGREE if agree else DISAGREE)
            text = tpl.format(name=first, reason=reason, reason_lc=reason[0].lower() + reason[1:], objection=objection)
            action, reply_to = "reply", target_item["id"]
        else:
            text = r.choice(POST_YES if new >= 0.5 else POST_NO).format(reason=reason, objection=objection)
            action = "post"
    return {
        "action": action,
        "reply_to": reply_to,
        "text": text,
        "juster": int(round(new * 10)),
        "changed": changed,
        "why": ("People I trust are more positive than I was." if new > cur else "What I'm reading makes me more cautious.") if changed else "Nothing new for me here.",
    }


def file_facts(ctx: dict[str, Any]) -> dict[str, Any]:
    text = ctx.get("context") or ""
    names = re.findall(r"=== FILE: (.+?) \(", text) or ["your documents"]
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text) if 30 < len(s.strip()) < 220 and not s.startswith("===")]
    keyed = [s for s in sentences if re.search(r"[$€£₹]|\d|price|customer|market|compet|plan", s, re.I)] or sentences
    facts = []
    for s in keyed[:8]:
        internal = bool(re.search(r"internal|confidential|target|roadmap|burn|runway|forecast", s, re.I))
        facts.append({"statement": s, "relevance": "From your documents", "countries": [], "stance": "neutral", "source_urls": [f"file:{names[0]}"], "public": not internal})
    return {"facts": facts, "competitors": [], "price_points": []}


HANDLERS["society_turn"] = society_turn
HANDLERS["file_facts"] = file_facts
