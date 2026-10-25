# Changes guide

Ten features borrowed (as ideas only) from other simulation projects: MiroFish, OASIS, AgentSociety, Stanford's Generative Agents, Concordia, TinyTroupe and commercial tools such as Aaru and Synthetic Users. Each section covers what was done, what it does, how it works and how to test it.

| # | Feature | Idea from | Status |
|---|---|---|---|
| 1 | [Track record](#1-track-record) | Aaru and other commercial tools (published predictions) | Done |
| 2 | [Memory and reflection](#2-memory-and-reflection) | Generative Agents, AgentSociety | Done |
| 3 | [Asking a group](#3-asking-a-group) | TinyTroupe, Synthetic Users | Done |
| 4 | [Knowledge graph](#4-knowledge-graph) for each simulation | MiroFish | Done |
| 5 | [Ranked feed](#5-ranked-feed) with likes, reshares and a viral mode | OASIS | Done |
| 6 | [Current news and the timeline](#6-current-news-and-the-timeline) | AgentSociety, Concordia | Done |
| 7 | Mid-run news | MiroFish | Folded into 6 |
| 8 | Personas from your customer data | Electric Twin, Synthetic Users | Next |
| 9 | Shareable reports | Commercial tools | Planned |
| 10 | Bigger, cheaper crowds | OASIS | Planned |

---

## 1. Track record

### What it does

Lets you prove (or disprove) that Tellaris predicts well. You save a simulation's answer *before* the real outcome is known, then enter what really happened once it is. Tellaris scores itself and can learn its say/do correction from your own results instead of built-in defaults.

The existing "Past events" check on the Accuracy page replays famous votes and launches that models may already know, so its scores flatter Tellaris. A tracked prediction can't have been memorised: the outcome didn't exist when the prediction was made.

### What was done

- **Run page:** a **Track this prediction** button on finished runs (not shown for number questions). It opens a small panel to pick the date the real answer will be known and, optionally, where it will come from. Once saved, the button becomes "Tracked, resolves <date>" and links to the track record. On demo-model runs the panel warns that tracking only tries out the flow.
- **Accuracy page:** a new **Track record** section at the top:
  - totals: tracked, scored, average error in points, and the share of results that fell inside Tellaris's likely range;
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

- Tellaris's likely range is narrow (often ±1–2 points). It only counts the randomness of the simulation, not how wrong the model can be, so real results rarely land inside it. Widening the range using the track record's own errors is a natural follow-up.
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

---

## 3. Asking a group

### What it does

After a simulation finishes, you can put a follow-up question to everyone, or to any group in it, without running it again. For example: "What price would make you say yes?", "Which of these three names do you trust?", "How much do you worry about money, 0 to 10?". Each person answers in character, from what they decided and what they remember. The answers come back like a small survey: a chart, a short summary, themes and quotes.

### What was done

- **Run page:** a new **Ask a group** tab on finished runs.
  - **Who to ask:** everyone; any group from the breakdowns (country, region, age, gender, income, type of work, group, company); or one of the suggested **Where it works / where it struggles** spots, such as "Under 30s in India".
  - **Your question**, and an **answer type**: open answer, multiple choice (2–8 options), a number (with an optional unit), or 0 to 10.
  - **People to ask:** 5 to 200 (default 40). The model call count is shown.
- **Results**, newest first, saved with the run:
  - a two- or three-sentence summary;
  - a chart for the answer type: option shares, the typical number with its range, or the spread of 0–10 scores;
  - the same split by **people who leaned yes** and **people who leaned no**, e.g. what price yes-leaners would pay versus no-leaners;
  - **themes**: select one to see only the answers behind it;
  - every answer, with the person's name, job, age and country, linking to their profile.
- **Where it works:** each hot and cold spot has an **Ask them why** link that opens Ask a group with that group already chosen.
- **Backend:** a new `interviews` table (existing tables untouched) and the endpoints below.

### How it works

1. **Finding the group.** The group is a set of breakdown keys, e.g. `{"age": "18-29", "country": "IND"}`. People match when every key matches, using the same definitions as Where it works (`aggregate.breakdowns()`). Spots now carry their keys, so a spot maps straight to a group.
2. **Picking people.** A plain random sample of the group, without repeats. The same question to the same group picks the same people. People are not picked by how many real people they stand for, because the numbers are weighted afterwards; doing both would count big countries twice. Random picking also means smaller countries get heard.
3. **Asking.** One model call per person, with their profile, their first answer and reasons, and their reflection if they had one (feature 2). Answers come back as text plus the structured value for the type. Multiple-choice answers are matched to the exact option.
4. **Summing up.** Each answer counts for the real people that person stands for, so the numbers describe the group, not the sample. Choice gives weighted shares, numbers give the weighted median and 10th–90th percentiles, and 0–10 gives the weighted average plus counts per score. Everything is split by yes and no leaners when each side has at least 3 people. One summary call to the analyst model writes the summary and groups answers into up to six themes, which must point at real answers.
5. **Runs in the background.** Asking returns at once; the tab checks progress every second until the interview is done.

**API**

| Method | Path | Does |
|---|---|---|
| POST | `/api/runs/{id}/interviews` | Start an interview. Body: `question`, `kind` (open, choice, number, scale), `options`, `unit`, `group`, `limit` |
| GET | `/api/runs/{id}/interviews` | A run's interviews, newest first |
| GET | `/api/interviews/{iid}` | One interview (poll while running) |
| DELETE | `/api/interviews/{iid}` | Remove it |

**Files:** `backend/oracle/simulate/interview.py` (new), `backend/oracle/simulate/aggregate.py` (spot keys, `breakdowns()`), `backend/oracle/store.py`, `backend/oracle/api/app.py`, `backend/oracle/llm/mock.py` (offline `interview_answer`, `interview_digest`), `backend/tests/test_interview.py`, `frontend/components/run/AskGroup.tsx` (new), `frontend/components/run/WhereItWorks.tsx`, `frontend/app/runs/[id]/page.tsx`, `frontend/lib/api.ts`, `frontend/lib/types.ts`.

### How to test

Automated: `cd backend && python -m pytest tests/test_interview.py`. It checks:
- a multiple-choice question to one country asks only that country, and the option shares add up to 100%;
- number and 0–10 questions give a sensible median, range and counts;
- group labels read correctly ("India", "Under 30s");
- the same question picks the same people;
- bad requests are refused (one option only, a group nobody is in, an unknown run).

By hand:
1. Open any finished simulation that has a Where it works tab. Runs from before this change have no spot shortcuts until re-run, but the group pickers still work.
2. **Where it works** → **Ask them why** on a spot. The **Ask a group** tab opens with that group chosen.
3. Ask "Which of these names would you trust?" as **Multiple choice** with three options. Watch the progress bar, then read the chart, the yes/no split, the themes and the quotes.
4. Choose **Ask everyone instead**, ask "What is the most you'd pay a month?" as **A number** with unit USD. The typical answer and its range appear.
5. Ask an open question and select a theme to filter the quotes.
6. Reload the page. The interviews are still there. **Remove** deletes one.

### Known limits

- People answer from what they decided and remember in this run, not from new research. Questions far from the topic get plausible but ungrounded answers.
- Results are not tracked like predictions yet. A "track this answer" option would be a small addition to feature 1.
- With the demo model, answers and themes are canned; real models answer in each person's voice.

---

## 4. Knowledge graph

### What it does

Every simulation maps the world around the question:
- **entities:** the product, competitors and alternatives, companies, regulators and rules, technologies, kinds of people, places, events, and the ideas people argue about (price, trust, privacy, habit);
- **links:** how they relate ("competes with", "regulates", "aimed at", "slows").

The map does three jobs:
- **Grounding:** each simulated person is told the few links that touch *them*, such as the competitor popular in their country or the rule that applies to their kind of company, not the whole map.
- **Counting:** after the run, Tellaris counts which entities people brought up in their answers and posts, and how those people leaned.
- **Exploring:** a new **Knowledge graph** tab lets you explore it all.

### What was done

- **The Knowledge graph tab:**
  - **An interactive map:**
    - the product sits in the centre;
    - nodes are coloured by kind and sized by how many people talked about them (or by number of connections; switch with **Size by**);
    - links have arrows, and links that come only from your private files are dashed.
  - **Moving around:** drag the background to move, drag a node to place it (it stays where you drop it), pinch or Ctrl + scroll to zoom, or use **+**, **−**, **Fit** and **All labels**.
  - **Hover** a node to highlight its neighbours and see a tooltip: kind, number of links, how many people brought it up and how they leaned.
  - **Select** a node to open it in the side panel:
    - what it is, and where it mainly applies;
    - **What people said**: how many people brought it up, their average leaning, and quotes with avatars that link to profiles;
    - **Connections**: each link in plain words with the fact behind it; select one to jump to that node;
    - **Where this comes from**: the facts it was built from, with source links, and private sources from your files marked.
  - **Legend chips** double as filters: select a kind to hide or show it.
  - **Find…** highlights matching nodes; Enter selects the first match.
  - **Show as a list** gives a sortable table of every entity (kind, people, leaning, links), for accessibility and quick scanning.
  - With nothing selected, the side panel shows **Most talked about**, ranked.
  - It works with a keyboard (Tab to a node, Enter to select), in dark mode, and on phones, where the map uses a taller layout.
- **Setup:** a **Knowledge graph** switch under How to simulate, on by default. It adds one model call.
- **Live progress:** a new stage, "Mapping the topic", between research and influence.

### How it works

1. **Building it** (`backend/oracle/research/graph.py`, `build_graph`). One orchestrator call reads:
   - the title, question, what people see, countries, alternatives, groups and outside factors;
   - every fact from your files and the web, numbered, with internal facts marked.

   It returns up to 30 entities and 60 links, citing fact numbers.
2. **Cleaning it** (`clean`):
   - names are de-duplicated and every entity gets a unique id;
   - there is exactly one product node;
   - links to unknown entities and repeated links are dropped, and so are entities nothing connects to;
   - cited facts are attached as sources.
3. **Privacy:**
   - a link is private if it cites any internal fact from your files;
   - an entity is private only if everything known about it is internal;
   - the product is always public;
   - private items are drawn for you, dashed and marked, and never reach simulated people.
4. **Grounding people** (`context_for`). For each person, public links are scored by what touches them:
   - the product;
   - their country (named place, or an entity that applies there);
   - their kind of work matching a customer or company entity;
   - competitors and rules.

   Links that apply only to other countries are skipped. The top four are added to their prompt as "What someone in your position would likely know about who and what is involved". **The business lens keeps its locked prompt and doesn't get this yet**: the B2B golden test confirms B2B results are unchanged. Once tracked predictions (feature 1) show grounding helps, it can be switched on for B2B too.
5. **Counting mentions** (`mentions`). Each entity's name and aliases (e.g. "price" also matches "cost", "budget") are searched in every person's answer (quote, reasons, objections) and every post and reply. For each entity it records how many distinct people mentioned it, their average leaning, and up to six example snippets cut at word boundaries.
6. **Storage:** saved in the run's results (`results.graph`). No new table.
7. **Drawing** (`frontend/components/run/KnowledgeGraph.tsx`):
   - **Layout:** `d3-force` (a new dependency) runs the physics: links, repulsion, collision padding and gentle centring. The layout is computed once up front, then stays live while dragging.
   - **Sharp at every size:** the drawing uses real pixels, so text and lines stay crisp at any zoom and panel size.
   - **Colours:** one fixed palette by kind, checked with the data-visualisation palette validator for light and dark mode. Light mode has one colour-blind warning (red vs green); it's allowed because every node has a text label and the legend names each kind. The product is drawn in ink and ideas in neutral grey. New `--kg-1`…`--kg-7` tokens are in `globals.css`.

**Files:** `backend/oracle/research/graph.py` (new), `backend/oracle/pipeline.py` (graph stage, grounding, mentions), `backend/oracle/simulate/reaction.py` (optional "what you'd know" lines), `backend/oracle/scenario/models.py` (`knowledge_graph` setting), `backend/oracle/llm/mock.py` (offline `knowledge_graph`), `backend/tests/test_graph.py`, `frontend/components/run/KnowledgeGraph.tsx` (new), `frontend/app/runs/[id]/page.tsx`, `frontend/components/composer/ScenarioEditor.tsx`, `frontend/lib/types.ts`, `frontend/app/globals.css`, `frontend/package.json` (`d3-force`).

### How to test

Automated: `cd backend && python -m pytest tests/test_graph.py tests/test_golden.py`. It checks:
- cleaning merges duplicates, drops unlinked entities and broken links, and keeps one product;
- links citing internal facts are private, while the product stays public with its private sources marked;
- an Indian person is told about the Indian competitor and not the US one (and the reverse), and never about private links;
- a run has a graph whose links all point at real entities, and mentions with examples;
- switching the graph off removes it;
- B2B results are unchanged.

By hand:
1. Run a simulation. Naming competitors or a rule in the question gives a richer map, e.g. "Would people in India, Brazil and the US pay $4 a month for Penny, an app that tracks spending? Competitors: Walnut, Mint."
2. Open the **Knowledge graph** tab. Hover nodes, drag a few, use **Fit** and **All labels**, and pinch or Ctrl + scroll to zoom.
3. Select the most talked-about node. Read the quotes and select a person to open their profile. Back on the graph, select a connection in the side panel to jump along the map.
4. Turn a kind off with its legend chip, search with **Find…**, switch **Size by** to Connections, then try **Show as a list**.
5. Attach a document with an internal number (say, your monthly burn) and run again. Anything built only from it is dashed and marked "Only you see this".
6. **Adjust setup first** → How to simulate → switch **Knowledge graph** off. The tab disappears.

### Known limits

- With the demo model, the map is built from the setup alone (product, groups, places, outside factors and four common ideas), so it's small. Real models produce up to 30 entities with facts.
- Mentions are matched by name and alias, so a person who describes a competitor without naming it isn't counted.
- The graph is built once per run, before people react. It doesn't grow from what people say yet.

---

## 5. Ranked feed

### What it does

The society can now run on three kinds of feed. You pick one under **How to simulate → Feed style**:
- **Word of mouth** (the default, and how it worked before): people see only what their own contacts say.
- **Ranked feed:** a platform picks what each person sees, by freshness, engagement (likes, reshares, replies) and closeness. People can **like** posts and **reshare** one to their contacts, so a popular post reaches friends of friends and strangers.
- **Viral:** the same platform with engagement weighted much more heavily. A few popular posts reach almost everyone.

You can test "what if this goes viral instead of spreading by word of mouth?" on the same people, and see how far each post travelled.

### What was done

- **Setup:** a **Feed style** choice under How to simulate, shown when Society is on. The hint under it explains each style. It costs no extra model calls.
- **Society tab:** a new **How far posts travelled** card:
  - **Seen per post:** the average number of people each post reached.
  - **Outside their circle:** the share of views from people the author doesn't know.
  - **Likes** and **Reshares** (ranked and viral only).
  - **Furthest-reaching posts:** the top five posts, each with a bar showing reach among the author's contacts (grey) and beyond their circle (blue), plus likes and reshares. Select one to open the author's profile.
  - **Try another feed:** reruns the same people with only the feed changed.
  - **Against the original run** (on a rerun): where the conversation ended, outside reach and adoption at the end of the time frame, side by side.
- **Posts:** each post now shows its likes, who reshared it ("Reshared by Ana and Vikram and 4 more") and "Seen by 40, 33 beyond their circle". **Most discussed** ordering now counts likes and reshares too.
- **Run header:** a "Ranked feed" or "Viral feed" pill. On a feed rerun, the summary line adds "after the conversation ±x points" next to the usual comparison.
- **Same people on every what-if:** every run now records the seed it used, and what-ifs reuse it. This applies to all what-ifs, not just feed reruns, so comparisons carry less random noise.

### How it works

1. **Picking each feed** (`backend/oracle/simulate/feed.py`, `pick`). At the start of each round, every person gets a feed of up to 5 posts and replies.
   - **Word of mouth** keeps the original rule exactly: contacts' posts from the last two rounds, newest first.
   - **Ranked and viral** score every post from the last three rounds:
     `score = closeness × freshness^age × (1 + weight × engagement)^power`
     - **closeness:** a contact's own post 1.0; reshared by a contact 0.8 (0.9 viral); a friend of a friend 0.25 (0.45); a stranger 0.03 (0.25).
     - **engagement:** likes + 1.5 × replies + 2 × reshares.
     - **weight and power:** 0.3 and 1 for ranked; 1.0 and 1.6 for viral, so popular posts pull away.
     - posts already shown to the person drop to 30% of their score, and a small seeded jitter breaks ties.
2. **Telling people why they see something.** In the prompt, posts that aren't a contact's own carry a tag ("reshared by Ana", "a friend of a friend", "popular outside your circle") and their like, reshare and reply counts.
3. **Liking and resharing.** On ranked and viral feeds, each turn can also return `like` (up to 3 post ids) and `reshare` (one id). They only count for posts the person was actually shown, at most one like per post per person and one reshare per post per person. They're applied after everyone has acted, so the order people act in doesn't matter. A reshare is also saved to the person's memory.
4. **Counting reach** (`record_seen`). Every time a post is shown to someone new, `seen` goes up, and `seen_outside` too if that person isn't the author's contact. This is counted in every style, so word of mouth shows reach as well.
5. **Results:**
   - `results.diffusion.feed` holds the style, totals, outside share, average and top reach, and the five furthest-travelled posts.
   - Like, reshare and seen counts live on the feed items themselves. No new table.
   - On a what-if, `results.comparison.society` holds both runs' after-talk opinion, outside share and end adoption.
6. **Same people on what-ifs:**
   - A run with no seed now gets a random one, stored as `results.seed`.
   - `POST /api/runs/{id}/whatif` accepts `config_patch` (change just these settings) and reuses that seed.
7. **What the feed changes and what it doesn't.** The feed shapes the conversation: opinion after the talk, the Bass adoption curve and reflection. First reactions, and so the headline answer, come before any talk and don't move. That's why the comparison shows "after the conversation" separately.
8. **B2B unchanged.** Word of mouth is the default and makes exactly the same draws as before. The like and reshare fields are only asked for on ranked and viral feeds, so the default prompt is word for word the same. The B2B golden test passes.

**Files:** `backend/oracle/simulate/feed.py` (new), `backend/oracle/simulate/society.py` (feed choice, `FeedTurn`, likes and reshares, reach summary), `backend/oracle/scenario/models.py` (`feed_style`), `backend/oracle/pipeline.py` (seed, society comparison), `backend/oracle/api/app.py` (`config_patch`, seed reuse), `backend/oracle/llm/mock.py` (offline likes and reshares), `backend/tests/test_feed.py`, `frontend/components/run/FeedReach.tsx` (new), `frontend/components/run/Society.tsx`, `frontend/components/composer/ScenarioEditor.tsx`, `frontend/app/runs/[id]/page.tsx`, `frontend/lib/types.ts`, `frontend/lib/api.ts`.

### How to test

Automated: `cd backend && python -m pytest tests/test_feed.py tests/test_golden.py`. It checks:
- word of mouth shows only contacts, even when a stranger's post is very popular;
- the ranked feed reaches friends of friends, strangers and contacts' reshares, and labels why each is shown;
- viral puts a popular stranger's post above a contact's, while ranked doesn't;
- likes and reshares only count on posts the person saw, once each;
- on the same people, outside reach is 0 for word of mouth, higher for ranked and higher again for viral, and no post has more likes than viewers;
- a what-if from a run with no seed reuses its seed and gets exactly the same people;
- B2B results are unchanged.

By hand:
1. New simulation, e.g. "Would people in India and Brazil pay $3 a month for Penny, an app that tracks spending automatically?" Choose **Adjust setup first**, then How to simulate → **Feed style: Viral**, and run.
2. The header shows a **Viral feed** pill. Open the **Society** tab: **How far posts travelled** shows most views coming from beyond people's circles, and top posts reaching nearly everyone.
3. Under the conversation, set **Order: Most discussed**. Posts show likes, "Reshared by …" (select a name to open their profile) and "Seen by …".
4. In the card, select **Word of mouth** under **Try another feed**. The new run opens. In its Society tab, **Against the original run** compares opinion after the talk, outside reach and adoption. The header line shows "after the conversation ±x points".

With the demo model the numbers show the mechanics only. With real models, people decide for themselves what to like and reshare.

### Known limits

- Feeds hold 5 posts a round. With few posts around, the ranked feed fills the spare places with friends of friends, which raises its outside share. Real feeds do the same.
- The ranking weights are hand-set, not fitted to any real platform.
- Likes and reshares only change who sees what. They don't change anyone's view directly; that happens through what people read.
- Older runs have no reach data, so the card doesn't appear on them.

---

## 6. Current news and the timeline

*This also covers #7 (mid-run news). Fetching news partway through a run would add nothing, since a run takes minutes and the news doesn't change in that time. What #7 was meant for is now covered by what-if events and by "Refresh with today's news".*

### What it does

Tellaris is a real-world helper, not a made-up world. Every run now starts from the world as it is today:
- **Real current affairs, automatically.** Tellaris searches the news around the question for every run, whatever the type of question. It keeps stories that are relevant and recent enough to matter, each with its real date, outlet and link.
- **People only know the news they'd come across.** A story everyone's talking about reaches most people in that country. Specialist news reaches only the people it concerns: an RBI circular reaches an Indian finance worker, not an Indian Gen Z student. Foreign news rarely travels unless it's huge.
- **Real time.** The conversation runs through real calendar periods, from today to the end of the time frame.
- **Real scheduled events**, such as a rule taking effect or a launch date, are found in the news and land in the period they happen.
- **What-if events are optional,** and you place them on the timeline yourself: "a rival cuts its price in month 5", "a new law in year 3". They're always shown as assumptions. Tellaris also runs the same people with real news only, so you can see exactly what your assumptions change.
- **An "as of" date on every result,** and **Refresh with today's news** on tracked predictions.

### What was done

- **Setup:**
  - **Current news** switch under How to simulate (on by default, two extra model calls).
  - New **What-if events** section. Each event has:
    - what happens, and details;
    - **When:** the picker uses the time frame's own units: months for up to 18 months ("Month 3 (Jan 2027)"), quarters up to 4 years, years beyond ("Year 3 (2029)");
    - **Where:** everywhere or one country;
    - **How widely heard:** everyone, widely covered, or only the people it concerns (with "Who follows it closely");
    - **Effect:** helps, hurts or mixed.
- **Live progress:** a "Read the news" stage.
- **New tab, "News and timeline":**
  - **The timeline:** a chart from Today to the end of the time frame showing the share leaning yes (per period) and projected adoption (monthly).
    - Markers: solid for real scheduled events, hollow for your what-ifs, with dashed lines when they're what-ifs.
    - The dashed lines show the base case without your what-ifs, with a sentence comparing where they end.
    - Hovering reads out both figures at any point.
    - Select an event, on the chart or in the list, for its details, how many people heard it and its source.
  - **The world right now:** every news item with:
    - date, how long ago, outlet, and the headline linking to the article;
    - how widely it was covered, which countries, whether it helps or hurts the case, and whether it's still in effect or takes effect later;
    - **Known by:** the share of simulated people who know it, overall and per country;
    - a country filter.

    When no news was used, it says why: search off, news off, or nothing relevant found.
- **Run header:** "News as of 20 Oct 2026".
- **Profiles:** a **News they know** card. Profile chat knows those stories too.
- **Track record:** **Refresh with today's news** on open predictions. It reruns the same people with fresh news. The new run marks stories that are "New since the original run" and shows how far the answer moved.
- **Backtests** switch news off: today's news would leak into past cases.

### How it works

1. **Finding the news** (`backend/oracle/research/news.py`, `gather_news`):
   - **Planning searches:** one model call writes 6–8 news searches about the category and the world around it (prices, the economy people feel, regulation, competitors, trends, upcoming events), not just the product name.
   - **Searching:** news search (DuckDuckGo News, or Tavily in news mode) returns results **with publish dates from the source**. Results without a date, or dated after today, are dropped.
   - **Selecting:** a second call picks 4–14 items. Each item must point to one numbered result, and its date, outlet and link are copied from that result, never written by the model. The model judges:
     - **reach:** mass, broad or niche;
     - **audiences:** who follows it closely;
     - **age skew**;
     - **stance;**
     - **relevance;**
     - **whether it's still in effect;**
     - **any scheduled future date it announces.**
2. **Relevant and recent:**
   - `score = relevance × 0.5^(age in days / 60)`;
   - stories still in effect (a law, a price change) don't fall below 60% of their relevance;
   - items scoring under 0.15 are dropped, and at most 14 are kept.
3. **Who knows what** (`know_chance`, `assign`):
   - starting chance by reach: 85% mass, 45% broad, 7% niche;
   - foreign news is cut to a fifth (mass) or a sixteenth (other);
   - global news is at 80%;
   - if the story concerns the person's work or interests (matched against their sector, job, group and information sources), it rises to at least 80%;
   - age skew raises or lowers it by up to 30%, and openness adjusts it slightly;
   - each person gets their top four known stories, chosen by a fixed draw, so reruns agree.
4. **Into the prompts:** every person's prompt now starts with today's date (so real models don't reason as if it's their training year) and "News you've come across recently", with dates and outlets. This applies to all question types, B2B included.
5. **The timeline** (`backend/oracle/simulate/timeline.py`):
   - Society rounds become equal periods of the time frame. With 12 months and 3 rounds, each round is 4 months, labelled "Oct 2026 to Feb 2027".
   - Events land in the period they fall in:
     - real scheduled ones from the news (`upcoming` dates within the time frame);
     - your what-ifs.
   - In each period, people hear an event by the same rules as news.
   - People are told "It is now Feb 2027 to Jun 2027" and the news they heard that period.
6. **No more invented news:** the model-written outside factors no longer appear as news items each round. They still act through the influence map and what people feel. This is the one deliberate change to B2B numbers: in the golden test, opinion after the conversation went from 5.6% to 9.3%. The headline and everything else are identical. The golden file was re-recorded on purpose.
7. **Base case:** when a run has what-if events, the conversation runs a second time on the same people with real events only. Its opinion and adoption curves are stored as `results.timeline.base`. This costs a second conversation, and setup includes it in the model-call estimate.
8. **Storage:**
   - `results.as_of`, `results.news`, `results.news_status` and `results.timeline` hold the date, the news items, why news is missing if it is, and the periods, events, curves and base case;
   - `persona.news` holds the stories each person knows;
   - `spec.events` holds your what-ifs;
   - on a rerun, `results.comparison.new_news` lists the new stories.
   - No new table.

**Files:** `backend/oracle/research/news.py` (new), `backend/oracle/simulate/timeline.py` (new), `backend/oracle/simulate/society.py` (periods and events instead of invented news), `backend/oracle/simulate/reaction.py` (today's date and news), `backend/oracle/pipeline.py` (news stage, assignment, timeline, base case), `backend/oracle/scenario/models.py` (`events`, `TimelineEvent`, `news` setting), `backend/oracle/population/models.py` (`news` on a person), `backend/oracle/api/app.py` (chat knows the news), `backend/oracle/backtest/runner.py` (news off), `backend/oracle/llm/mock.py` (offline search planning and selection), `backend/tests/test_news.py`, `backend/tests/golden_b2b.json` (re-recorded), `frontend/components/run/NewsTimeline.tsx` (new), `frontend/components/composer/ScenarioEditor.tsx`, `frontend/app/runs/[id]/page.tsx`, `frontend/app/runs/[id]/people/[pid]/page.tsx`, `frontend/components/track/TrackRecord.tsx`, `frontend/components/run/Overview.tsx`, `frontend/lib/types.ts`.

### How to test

Automated: `cd backend && python -m pytest tests/test_news.py tests/test_golden.py`. It uses a fake news search, so no internet is needed. It checks:
- recent news outranks old news, unless the old story is still in effect;
- a niche finance story reaches an Indian finance worker (70% or more) but not an Indian student (under 12%) or a Brazilian, while mass news reaches the student;
- who knows what is the same on reruns, and finance people know finance news more often;
- time labels follow the horizon (months, quarters, years), and periods and events map to the right rounds;
- real scheduled events keep their source, and what-ifs outside the time frame are left out;
- a full run uses only news from the search results, with real dates, and people's profiles carry news from those results;
- a what-if "rival goes free" lands in the right period, reaches people, and ends lower than the base case;
- switching news off removes it;
- B2B results match the re-recorded golden file.

By hand (needs a search provider in Models; DuckDuckGo is free and the default):
1. Run "Would people in India and Brazil pay $3 a month for Penny, an app that tracks spending automatically?" The live progress shows "Read the news". The header says "News as of" today's date.
2. Open **News and timeline**. Check the stories are real (select a headline to open the article) and dated. Compare **Known by** across countries.
3. Open a few people from the **People** tab. Their **News they know** differs by country and job. Ask one in chat what they've heard lately.
4. Start a new run with **Adjust setup first** → **What-if events** → add "Walnut makes its app free", Month 5, India, Widely covered, Makes a yes less likely. In the timeline, a hollow marker sits at month 5, and the dashed base-case lines show the result with real news only.
5. Try a 5-year question: the When picker switches to years.
6. On **Accuracy**, track a run, then select **Refresh with today's news** on it.

With the demo model, the stories are real (search is real), but the demo picks and judges them with simple rules, so its "helps / hurts" labels are rough. A real model judges them properly.

### Known limits

- News search covers roughly the last year and depends on the search provider. Smaller markets and non-English news can be thin.
- Backtests run without news, because news search can't reliably return only stories from before a past date.
- Reach and audiences are the model's judgement, and the matching to people is by keywords.
- What-if events affect the conversation (opinion after talking, adoption), not first reactions, which happen today before the events.
- The base case doubles the cost of the conversation when you add what-if events.
