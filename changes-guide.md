# Changes guide

Ten features borrowed (as ideas only) from other simulation projects: MiroFish, OASIS, AgentSociety, Stanford's Generative Agents, Concordia, TinyTroupe and commercial tools such as Aaru and Synthetic Users. Each section covers what was done, what it does, how it works and how to test it.

| # | Feature | Idea from | Status |
|---|---|---|---|
| 1 | [Track record](#1-track-record) | Aaru and other commercial tools (published predictions) | Done |
| 2 | Memory and reflection | Generative Agents, AgentSociety | Next |
| 3 | Asking a group | TinyTroupe, Synthetic Users | Planned |
| 4 | Starting from your documents | MiroFish | Planned |
| 5 | Ranked feed | OASIS | Planned |
| 6 | Timeline of events | AgentSociety, Concordia | Planned |
| 7 | Mid-run news | MiroFish | Planned |
| 8 | Personas from your customer data | Electric Twin, Synthetic Users | Planned |
| 9 | Shareable reports | Commercial tools | Planned |
| 10 | Bigger, cheaper crowds | OASIS | Planned |

---

## 1. Track record

### What it does

Lets you prove (or disprove) that Oracle predicts well. You save a simulation's answer *before* the real outcome is known, then enter what really happened once it is. Oracle scores itself and can learn its say/do correction from your own results instead of built-in defaults.

The existing "Past events" check on the Accuracy page replays famous votes and launches that models may already know, so its scores flatter Oracle. A tracked prediction can't have been memorised: the outcome didn't exist when the prediction was made.

### What was done

- **Run page:** a **Track this prediction** button on finished runs (not shown for number questions). It opens a small panel to pick the date the real answer will be known and, optionally, where it will come from. Once saved, the button becomes "Tracked, resolves <date>" and links to the track record. On demo-model runs the panel warns that tracking only tries out the flow.
- **Accuracy page:** a new **Track record** section at the top:
  - totals: tracked, scored, average error in points, and the share of results that fell inside Oracle's likely range;
  - every prediction with its status (Open, Result due, Scored), what was predicted, the range, the real result and how far off it was;
  - **Enter the real result**: type the real percentage and a source;
  - a predicted-vs-real chart (on the dashed line is a perfect call);
  - **Learn the correction from these**, available once 3 predictions of a kind ("Doing things" or "Opinions and votes") are scored.
- The old check is now labelled **Past events** and marked as optimistic. The "Current correction" card says whether the correction is the default, learned from past events, or learned from tracked predictions, and can be reset.
- **Backend:** a new `predictions` table (existing tables untouched) and the endpoints below.

### How it works

1. **Freezing.** `oracle/backtest/track.py` `freeze()` copies everything needed to score later into the prediction itself: the headline value and its range, the raw "what people said" number, the awareness (reach) used, the correction in use, the question, countries and lens. Editing or re-running the simulation later changes nothing. The date must be in the future.
2. **Scoring.** `resolve()` stores the real result and source, the error (predicted minus real), whether it fell inside the likely range, and `blind: true` (the result was entered after the prediction was frozen).
3. **Summary.** `summary()` computes the counts, average error, share inside the range and points for the chart, split into "doing things" (action) and "opinions and votes" (belief).
4. **Learning the correction.** `fit(kind)` fits the same Platt-style say/do map used by past events (`calibrate.fit_platt`), from "what people said" to what really happened, and saves it with source "track record". For adoption questions the headline is awareness × intent, so both sides are divided by awareness first; the correction only learns the say/do gap, not awareness. All new runs of that kind use it.

**API**

| Method | Path | Does |
|---|---|---|
| POST | `/api/runs/{id}/track` | Freeze a finished run's answer. Body: `resolves_on` (date), `note` |
| GET | `/api/runs/{id}/track` | Predictions made from one run |
| GET | `/api/track` | All predictions plus the summary |
| POST | `/api/track/{pid}/resolve` | Enter the real result. Body: `actual` (0–1), `source` |
| DELETE | `/api/track/{pid}` | Remove a prediction |
| POST | `/api/track/fit/{action\|belief}` | Learn the correction from scored predictions |

**Files:** `backend/oracle/backtest/track.py`, `backend/oracle/store.py` (table and helpers), `backend/oracle/api/app.py`, `backend/tests/test_track.py`, `frontend/components/run/TrackButton.tsx`, `frontend/components/track/TrackRecord.tsx`, `frontend/app/backtest/page.tsx`, `frontend/lib/api.ts`.

### How to test

Automated: `cd backend && python -m pytest tests/test_track.py`. It checks that past dates are refused, values are frozen, a prediction can't be resolved twice, fitting needs 3 scored predictions, the fitted correction is saved and used, and deleting works.

By hand (the demo model is fine for trying the flow):

1. Run any simulation with a share answer, e.g. the "Pineapple on pizza" example.
2. When it finishes, choose **Track this prediction**, keep the suggested date, add a note, then **Track it**. The button changes to "Tracked, resolves …".
3. Open **Accuracy**. The prediction is listed as Open.
4. Choose **Enter the real result**, type a percentage (e.g. 27) and a source, then **Score it**. The error, chart and totals update.
5. Track and score two more runs of the same kind (two more opinion questions, say). **Learn the correction from these** becomes available. Use it, and the "Current correction" card shows "Learned from 3 tracked predictions". **Reset** returns to the default.

For a real test, track questions about things that will be known in weeks or months (an upcoming vote, a launch's first-quarter numbers, a price change), using your real models.

### Known limits

- Oracle's likely range is narrow (often ±1–2 points). It only counts the randomness of the simulation, not how wrong the model can be, so real results rarely land inside it. Widening the range using the track record's own errors is a natural follow-up.
- Only answers given as a share can be tracked. Number answers (e.g. "how much would you pay") are not yet supported.
- A run shows only its latest prediction on the run page. Tracking the same run again is possible through the API but not the UI.
