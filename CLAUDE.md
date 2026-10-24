# Product Oracle

Multi-agent world simulation for predicting how products (and any scenario described in a paragraph) will land across countries, jobs and segments. Works with any LLM provider.

Read `docs/vision.md` first. It has the full vision, architecture and plan from the original planning chat.

- Commit as denxxs <dennis.sag@gmail.com>.
- Do not copy code from MiroFish (AGPL-3.0). Ideas only.

## Layout and commands
- `backend/` Python 3.11 FastAPI + LiteLLM. Run: `cd backend && python -m oracle`. Tests: `python -m pytest`.
- `frontend/` Next.js 15 + Tailwind v4. Run: `npm run dev`. Check: `npx tsc --noEmit && npx eslint app components lib`.
- `./dev.ps1` starts both. Runtime data (DB, API keys) lives in `backend/var/` (gitignored).
- `mock/oracle` is the offline model used for tests and demo mode; keep `oracle/llm/mock.py` handlers in sync when adding LLM tasks.
- UI follows the design-taste-frontend skill's app rules, "framed sheet" style (`.taste-skill/direction.json`): tinted L-frame + white sheet, colour on data only. Tokens in `frontend/app/globals.css`: teal `--yes` (main series), amber `--no`, blue `--flow` (outside influence); near-black primary button; no violet/indigo, gradients or resting shadows. Font: IBM Plex Sans (Plex Mono for IDs/model names only). Titles 22px, answer figure 36px max.
- Signature element: the crowd (`components/run/Crowd.tsx`), one square per simulated person, plus the live world map.
- Check UI with `node .claude/skills/design-taste-frontend/scripts/lint.mjs --app frontend/app frontend/components` and `inspect.mjs --app <url>`.
- Country data: `backend/scripts/build_world.py` rebuilds `oracle/data/countries.json` for every country from World Bank + ILOSTAT (hand-tuned overrides in `countries_curated.json`). Influence edges: hand-written `influence.json` + rules in `oracle/world/rules.py`. Headcounts: `oracle/population/headcount.py`.
- People: `backend/scripts/build_people.py` builds `oracle/data/people.json` (World Bank, ILOSTAT, Global Findex) and `isco_within.json` (BLS OEWS + crosswalks in `backend/var/datasets/`). Survey views: `scripts/build_views.py` turns the user-downloaded WVS wave 7 zip into `var/datasets/wvs_pool.json` (never committed: WVS forbids redistribution); `oracle/population/views.py` matches each person to a real respondent.
- Society: `oracle/simulate/society.py` (feed of posts, replies, news, meetings, shifts; stored in the `feed` table). UI in `frontend/components/run/Society.tsx`. Profiles at `/runs/[id]/people/[pid]`; avatars are DiceBear Notionists (CC0), drawn locally.
- Context files: `oracle/files.py` (PDF, DOCX, PPTX, XLSX, CSV, MD, HTML, TXT) stored in `backend/var/files/`; facts with `public=false` never reach simulated people.
- Providers: catalogue in `oracle/providers.py` (includes NVIDIA NIM). Roles: planner (orchestrator), analyst (defaults to planner), crowd (list).
