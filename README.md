# Product Oracle

Simulate a world of people to see how a product, price, policy or any idea will land.

Describe what you want to know in plain words. Oracle builds a population across any of 202 countries you pick (founders, CFOs, analysts at Indian IT firms, teachers, farmers, any job), works out which outside countries and blocs shape those markets (for example, EU rules reaching Indian IT firms with EU clients), lets every person decide for themselves, and tells you what is likely to happen, why, and what would change it.

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

You write a paragraph (and optionally attach a pitch deck, product doc, pricing page or research). Everything else is automatic, and you can watch each step live:

1. **Understand**: the orchestrator turns your words and files into a precise question: who decides, where, at what price, over what time, and which outside factors matter.
2. **Research**: facts from your files and the web. Internal numbers from your files (targets, burn, roadmaps) are kept from the simulated people; they only see what a customer could.
3. **Map influence**: the countries and blocs pressing on your markets, for every country in the world.
4. **Build people**: each country's real job, income and age data become people with a name, face, tagline, story, values, typical day, tools they use today and the outside pressures their work exposes them to. Groups are sized automatically from real headcounts.
5. **Each person decides**: privately, in their own words, several times across your crowd models.
6. **Companies meet** (B2B): buying groups argue it out and buy, pilot, defer or reject.
7. **Society talks**: everyone sees their contacts' posts, then posts, replies or stays quiet, and may change their mind as news lands. Meetings join the same feed.
8. **Answer**: corrected for the gap between saying and doing, scaled to real headcounts, with a likely range, breakdowns, reasons, and one-click changes to test on the same people.

Then explore: the **Society** feed (replay it round by round), **People** (every person has a full profile with their posts, their circle and a live chat), countries, groups, outside influence, pricing, meetings and the method behind the number.

## Any model, any provider

All model calls go through [LiteLLM](https://docs.litellm.ai/docs/providers): NVIDIA NIM, OpenAI, Anthropic, Gemini, Azure, Mistral, Groq, DeepSeek, OpenRouter, Together, xAI, Ollama and any OpenAI-compatible server. On the Models page pick a provider and model for two roles:

- **Orchestrator**: understands your question and files, researches, writes the analysis. A few calls per run, so use your strongest model. (Optionally a separate model for research and the report.)
- **Crowd**: plays every person: answers, posts, replies, meetings and chats. Thousands of calls per run, so use a fast, inexpensive model. You can mix in more crowd models to cancel out any one model's habits.

For NVIDIA NIM, paste a key from build.nvidia.com, or point the endpoint at your own NIM deployment.

Keys are saved in `backend/var/settings.json` on your machine and never committed.

## Accuracy

The **Accuracy** page runs Oracle on questions with known outcomes, scores the error, and fits the say/do correction from the results. Built-in cases are famous votes and adoption numbers that models may already know, so their scores are optimistic. Add cases from after your models' training cutoff for an honest test.

Simulations are not ground truth. Treat results as a well-structured, explainable estimate, and check them against real-world tests.

## Country data

`backend/scripts/build_world.py` rebuilds the country file from the World Bank and ILOSTAT open APIs (no keys). 168 countries use surveyed occupation data; the rest use a model fitted on those surveys. Taiwan comes from national statistics. Run it again to refresh the numbers.

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
