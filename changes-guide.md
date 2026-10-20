# Changes guide

Ten features borrowed (as ideas only) from other simulation projects: MiroFish, OASIS, AgentSociety, Stanford's Generative Agents, Concordia, TinyTroupe and commercial tools such as Aaru and Synthetic Users. Each section covers what was done, what it does, how it works and how to test it.

| # | Feature | Idea from | Status |
|---|---|---|---|
| 1 | [Track record](#1-track-record) | Aaru and other commercial tools (published predictions) | Done |
| 2 | [Memory and reflection](#2-memory-and-reflection) | Generative Agents, AgentSociety | Done |
| 3 | Asking a group | TinyTroupe, Synthetic Users | Next |
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

---

## 2. Memory and reflection

### What it does

People in the society now remember what happened to them while they talked it over, and think it over once at the end. You can see why someone changed their mind, what moved the crowd as a whole (contacts' posts, replies, news, their own thinking, a buying meeting), and ask a person in chat why they think what they think: they answer from their memories.

### What was done

- **During the conversation**, each person keeps a memory stream: what they said first, posts from contacts, replies aimed at them, news, the buying meeting they sat in (B2B), and a one-line takeaway they write each round. Every round they see their six most important memories instead of only their first quote.
- **At the end**, each person reflects once on what they remember: how they see it now, their view on the same 0–10 scale, and which memories moved them most.
- **Society tab:** a new **After reflecting** card: where people landed after thinking it over (versus the end of the talk), how many changed their minds, **What moved people** (share of influences by kind), and the biggest moves with their own words.
- **Profile page:**
  - a third figure in the header, **After reflecting**;
  - a new **What they remember** card: a line of how their view moved from start through each round to after reflecting, their reflection in their own words, and every memory by round, with the ones that moved them marked.
- **Chat:** the person's memories and reflection are part of what they know, so "why did you change your mind?" gets a grounded answer.
- **Setup:** a **Memory and reflection** switch under How to simulate (shown when Society is on), on by default. The model call estimate includes it.

### How it works

- `backend/oracle/simulate/memory.py`:
  - `Mind` holds one person's memories and their view after each round.
  - **Importance** is scored without extra model calls:
    - what they said first: 0.9
    - their meeting: 0.9
    - replies to them: 0.85
    - news: 0.8
    - their own takeaway: 0.7
    - contacts' posts: 0.35–0.9, higher when the post disagrees with them or many people reacted to it.
  - **Recall** picks the top memories by importance × 0.85 per round of age, so old memories fade unless they mattered.
- `society.py`: each round's prompt shows **WHAT YOU REMEMBER** (numbered) in place of "what you said before". The round's answer has a new `takeaway` field that becomes a memory. The feed people see, the way views move each round, and the Bass projection are unchanged.
- **Reflection** (`reflect_all`): one model call per person in the conversation, using their 8 most important memories. The new view is half their last view and half the reflection's answer, so one moment of thought can't swing anyone wildly. Influences must point at real memory numbers; anything else is dropped.
- **Kept separate on purpose:** the reflection result is reported as its own number (`results.diffusion.reflection`). It doesn't change the headline answer, the word-of-mouth rounds or the Bass curve. That keeps existing results comparable, and the B2B golden test confirms B2B results are byte-for-byte unchanged.
- **Storage:** each person's memories, view per round and reflection are saved on their existing person record (`mind`). No new table.
- **Cost:** one extra call per person in the conversation (capped by "people in the conversation", default 150). With 3 rounds that is about +33% on the society stage, and less on the whole run.

**Files:** `backend/oracle/simulate/memory.py` (new), `backend/oracle/simulate/society.py`, `backend/oracle/pipeline.py`, `backend/oracle/scenario/models.py` (`memory` setting), `backend/oracle/api/app.py` (chat context), `backend/oracle/llm/mock.py` (offline `reflect`), `backend/tests/test_memory.py`, `frontend/components/people/MindCard.tsx` (new), `frontend/components/run/Society.tsx`, `frontend/app/runs/[id]/people/[pid]/page.tsx`, `frontend/components/composer/ScenarioEditor.tsx`, `frontend/lib/types.ts`.

### How to test

Automated: `cd backend && python -m pytest tests/test_memory.py tests/test_golden.py`. It checks:
- recall prefers important and recent memories, and doesn't store the same item twice;
- a run produces reflections whose influences point at real memories, and the profile returns memories, the view per round and the reflection;
- switching memory off skips reflection;
- B2B results are unchanged.

By hand:
1. Run a simulation with Society on (any example works; the demo model is fine to try the flow).
2. Open the **Society** tab. The **After reflecting** card shows the before and after figures, what moved people, and the biggest moves.
3. Choose a person from that card. Their profile shows **After reflecting** in the header and the **What they remember** card, with memories by round and the ones that moved them marked.
4. In **Talk to …**, ask "Why did you change your mind?". With a real model, the answer refers to things they saw.
5. **Adjust setup first** → How to simulate → switch **Memory and reflection** off. The model call estimate drops, and the run has no reflection card.

### Known limits

- Memories are per run. People don't remember earlier simulations.
- Reflection is reported next to the answer, not folded into it. If tracked predictions (feature 1) show that the post-reflection number is the better predictor, it can become the headline later.
- With the demo model, reflections are canned sentences; real models write them in each person's voice.
