# Product Oracle — Vision

Saved from the planning chat on 2026-10-20.

## Origin
Started from MiroFish (open-source swarm prediction engine). Its step 2 (OASIS social-media simulation) kept getting stuck, and MiroFish is built for social-media reaction prediction, not product/market prediction. MiroFish is AGPL-3.0, so this is a fresh repo (ideas only, no MiroFish code).

## What it is
A "product vision driver" and general prediction engine:
- Simulate a world of people across all job types (B2B SaaS founders, analysts at large Indian IT firms like Infosys/Cognizant, CFOs, students, officials, etc.).
- Pick target countries (e.g. USA, India). Countries that influence them (e.g. the EU via GDPR / AI Act / EU clients of Indian IT firms) are pulled in automatically.
- See how a product will land, by country and segment, and how to make it land better.
- Also: predict anything from a plain paragraph.
- Must work with any LLM provider.
- Goal: very strong, meaning calibrated probabilities with measured accuracy (no tool can predict anything perfectly).

## Architecture
1. **Scenario builder**: LLM turns a paragraph into a structured scenario: what is predicted, outcomes, time horizon, countries, populations, outside forces, simulation modes.
2. **Live research**: web search for current facts (regs, prices, news, competitors).
3. **Influence map**: graph of countries linked by trade, regulation, client relationships, media, diaspora. Outside forces are attached as events to exposed personas (no need to simulate the EU's population).
4. **Population builder**: thousands of personas weighted by real labor/census data (occupation, company type, seniority, income, budget authority, risk appetite).
5. **Simulation modes** (pluggable):
   - a. individual reactions (buy/support? objections? price?)
   - b. group decisions (B2B buying committees, boards, households)
   - c. social spread (word of mouth, media; OASIS could fit here)
   - d. change over time (economy and policy over months)
6. **Report**: probabilities by country/segment, reasons, what would change the outcome, follow-up questions to any persona.

## What makes it strong
- Any provider via LiteLLM (OpenAI, Anthropic, Gemini, Mistral, Ollama, OpenRouter...). Cheap model for the crowd, strong model for planning and reports.
- Multi-model ensemble to cancel out single-model bias.
- Many runs per question, so results are ranges (e.g. 62%, likely 55-70%).
- Skeptic calibration to fix LLM positivity bias ("everyone loves it").
- Backtesting on past events (launches, elections, policies), scored for accuracy.

## Stack (proposed)
Python + FastAPI backend, LiteLLM, a graph database for the influence map, Next.js frontend.

## Plan
- **MVP (~6-8 weeks)**: scenario builder, population builder, individual reactions (5a), report. 2-3 countries, any LLM.
- **Strong version (~4-6 months)**: live research, influence map, all simulation modes, ensembles, backtesting.
- **Hardest parts**: persona realism, backtesting, cost at scale.
- **First build step**: scenario builder + population builder.

## Related tools to borrow ideas from
OASIS (camel-ai), AgentSociety (Tsinghua), TinyTroupe (Microsoft), AgentTorch (MIT), SocioVerse (Fudan), Concordia (DeepMind). Competitors in synthetic users / simulated market research: Aaru, Artificial Societies.
