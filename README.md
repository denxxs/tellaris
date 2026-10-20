# Product Oracle

Simulate a world of people to see how a product, price, policy or any idea will land.

Describe what you want to know in plain words. Oracle builds a population across the countries you pick (founders, CFOs, analysts at Indian IT firms, teachers, farmers, any job), works out which outside countries and blocs shape those markets (for example, EU rules reaching Indian IT firms with EU clients), lets every person decide for themselves, and tells you what is likely to happen, why, and what would change it.

## Run it

Needs Python 3.11+ and Node 20+.

```powershell
# one-time setup
pip install -e backend[dev]
cd frontend; npm install; cd ..

# start both servers
./dev.ps1
```

Then open http://localhost:3000. Without any keys it runs in demo mode on an offline stand-in model. Add real models on the **Models** page.

Or start them separately:

```bash
cd backend && python -m oracle          # API on :8000
cd frontend && npm run dev              # app on :3000
```

## How a run works

1. **Scenario**: a planner model turns your paragraph into a precise question, the groups of people to simulate (tied to specific countries if you say so), outside factors, price and time frame. You can review and edit all of it before running.
2. **Research**: web search (DuckDuckGo free, or Tavily) for current facts, competitors and prices. People only see facts with sources.
3. **Influence map**: a graph of countries and blocs linked by regulation, outsourcing, capital, trade, technology and more. Targets pull in their direct and indirect influencers.
4. **Population**: people are sampled from real labour-market structure (ISCO job mix, income levels, digital maturity) and weighted to represent their country and group. Each one feels the outside forces that touch their sector. A model then gives them a name, backstory and point of view.
5. **Reactions**: every person answers in character, several times across different models, on the Juster probability scale.
6. **Buying committees** (B2B): champion, budget owner, technical and security reviewers argue it out over rounds, then a deal decision is made.
7. **Word of mouth**: people talk over a small-world network, news arrives mid-way, views shift. The result drives a Bass adoption projection over your time frame.
8. **Analysis**: stated intent is corrected for the say/do gap, multiplied by awareness, bootstrapped for a likely range, broken down by country, group, job, seniority and company type, with measured effects of each outside force, pricing curves, objection themes and a written report with testable what-ifs.

## Any model, any provider

All model calls go through [LiteLLM](https://docs.litellm.ai/docs/providers): OpenAI, Anthropic, Gemini, Azure, Mistral, Groq, DeepSeek, OpenRouter, Together, xAI, Ollama and any OpenAI-compatible server. Set three roles on the Models page:

- **Planner**: sets up the scenario (use a strong model)
- **Crowd**: answers as people, thousands of calls (use fast, cheap models; mix providers to cancel out bias)
- **Analyst**: research, themes and the report

Keys are saved in `backend/var/settings.json` on your machine and never committed.

## Accuracy

The **Accuracy** page runs Oracle on questions with known outcomes, scores the error, and fits the say/do correction from the results. Built-in cases are famous votes and adoption numbers that models may already know, so their scores are optimistic. Add cases from after your models' training cutoff for an honest test.

Simulations are not ground truth. Treat results as a well-structured, explainable estimate, and check them against real-world tests.

## Project layout

```
backend/oracle/
  scenario/     paragraph -> scenario, what-if levers
  research/     web search -> sourced facts
  world/        countries, blocs, occupations, influence graph
  population/   sampling and persona enrichment
  simulate/     reactions, committees, diffusion, calibration, aggregation
  report/       themes and written analysis
  backtest/     known-outcome cases and scoring
  llm/          provider-agnostic client + offline mock
  api/          FastAPI app (REST + live event stream)
frontend/       Next.js app
```

Tests: `cd backend && python -m pytest`.
