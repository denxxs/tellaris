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
- Design tokens are in `frontend/app/globals.css` (fog/panel/ink, iris for actions and influence, yes=teal, no=raspberry). Fonts: Bricolage Grotesque (display), IBM Plex Sans (UI).
