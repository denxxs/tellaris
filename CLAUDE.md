# Project Tellaris

Multi-agent world simulation for predicting how products (and any scenario described in a paragraph) will land across countries, jobs and segments. Works with any LLM provider.

Read `docs/vision.md` first for the vision, architecture and plan.

## Ground rules
- Every number in the simulation needs a published source. If no data exists, leave the value empty; never guess or hand-tune.
- Never commit secrets (API keys, tokens) or anything in `backend/var/`.
- Some datasets (World Values Survey) forbid redistribution: build from the user's own download and keep the result in `backend/var/`.
- Tests must pass before a commit: `cd backend && python -m pytest`, and the frontend checks below.

## Layout and commands
- `backend/` Python 3.11 FastAPI + LiteLLM. Run: `cd backend && python -m oracle`. Tests: `python -m pytest`.
- `frontend/` Next.js 15 + Tailwind v4. Run: `npm run dev`. Check: `npx tsc --noEmit && npx eslint app components lib`.
- `./dev.ps1` starts both. Runtime data (DB, API keys) lives in `backend/var/` (gitignored).
- `mock/oracle` is the offline model used for tests and demo mode; keep `oracle/llm/mock.py` handlers in sync when adding LLM tasks.
- UI style, "framed sheet": tinted L-frame + white sheet, colour on data only. Tokens in `frontend/app/globals.css`: teal `--yes` (main series), amber `--no`, blue `--flow` (outside influence); near-black primary button; no violet/indigo, gradients or resting shadows. Font: IBM Plex Sans (Plex Mono for IDs/model names only). Titles 22px, answer figure 36px max.
- Signature element: the crowd (`components/run/Crowd.tsx`), one square per simulated person, plus the live world map.
- Country data: `backend/scripts/build_world.py` rebuilds `oracle/data/countries.json` for every country from World Bank + ILOSTAT. Missing figures stay empty (no guesses); territories without labour-force data are kept for names/ties but can't be simulated (`Country.simulatable`). `countries_curated.json` holds only display names, aliases and mock-mode name pools. Ties between countries: `backend/scripts/build_ties.py` builds `oracle/data/ties.json` and `friendships.json` from CEPII BACI 2024 (goods trade), services trade (national surveys such as RBI first, then countries' own reported figures, then OECD-WTO BaTIS estimates; each list records its source), Meta SCI x Facebook users (friendships; users from `scripts/fetch_facebook_users.py`, which needs a Meta token in `var/meta_token.txt`, never committed) and UN migrant stock; countries without SCI (China, Iran...) get friendships estimated from migrant links, with a held-out check in `friendships.json`; read by `oracle/world/ties.py` and `influence.py`. No hand-written links. Headcounts: `oracle/population/headcount.py`. Company size and public sector: `scripts/build_firms.py` -> `oracle/data/firms.json` (ILOSTAT workplace size by job and public-sector share, OECD SDBS and US Census SUSB enterprise sizes), read by `oracle/population/firms.py`; sizes are classes ("50-99 people"), never invented headcounts. Contacts: `scripts/build_contacts.py` -> `oracle/data/contacts.json` (Prem et al. 2021 daily contacts by age and setting; how unequal contacts are between people from CC BY diary surveys in `var/datasets/contacts_surveys/`), used by `oracle/simulate/diffusion.py`.
- People: `backend/scripts/build_people.py` builds `oracle/data/people.json` (World Bank, ILOSTAT, Global Findex) and `isco_within.json` (BLS OEWS + crosswalks in `backend/var/datasets/`). Survey views: `scripts/build_views.py` turns the user-downloaded WVS wave 7 zip into `var/datasets/wvs_pool.json` (never committed: WVS forbids redistribution); `oracle/population/views.py` matches each person to a real respondent.
- Society: `oracle/simulate/society.py` (feed of posts, replies, news, meetings, shifts; stored in the `feed` table). UI in `frontend/components/run/Society.tsx`. Profiles at `/runs/[id]/people/[pid]`; avatars are DiceBear Notionists (CC0), drawn locally.
- Context files: `oracle/files.py` (PDF, DOCX, PPTX, XLSX, CSV, MD, HTML, TXT) stored in `backend/var/files/`; facts with `public=false` never reach simulated people.
- Providers: catalogue in `oracle/providers.py` (includes NVIDIA NIM). Roles: planner (orchestrator), analyst (defaults to planner), crowd (list).
