# No assumptions: tracker

Goal: every number in the simulation comes from published data, for all 202 countries. Where no
data exists, the value is left empty or estimated by a method tested on countries where the truth
is known, with its error published. Settings that are choices (crowd size, rounds) stay as named
settings with a sensitivity test. Status: done, open, or setting.

## 1. Hand-set numbers in the code

| What | Where | Now | Data to use | Status |
|---|---|---|---|---|
| Unused old occupation guesses (weights, income multipliers, tech scores, base shares) | `data/occupations.json` | Removed | n/a | done |
| Contact data licence | `scripts/build_contacts.py` | GPL-3.0 repo, corrected 2022 version (compatible with AGPL; no effect on hosted use) | n/a | done |
| How many people hear a story (mass 85%, broad 45%, niche 7%) | `research/news.py` `REACH_BASE` | Hand-set | Surveys asking how much people heard about specific stories (Pew), Wikipedia pageviews per capita, Google Trends | open |
| Foreign news travel (x0.2, x0.06, x0.8) | `research/news.py` | Hand-set | GDELT: how often each country's media covers the others | open |
| News fade (half-life 60 days) | `research/news.py` `HALF_LIFE_DAYS` | Hand-set | Wikipedia pageview decay after real events | open |
| News items per person (4), per run (14), relevance cutoff (0.15) | `research/news.py` | Hand-set | News-use diaries (Reuters Digital News Report) | open |
| Feed weights (contact 1.0, reshared 0.8, friend of friend 0.25, stranger 0.03, freshness 0.55, 5 posts) and engagement weights (1 / 1.5 / 2) | `simulate/feed.py` | Hand-set | Published cascade studies (depth and breadth of sharing); fit simulated spread to real spread | open |
| Memory fade (0.85 per round), items recalled (6, and 8 in one place), importance formula and per-kind weights | `simulate/memory.py`, `simulate/society.py` | Hand-set | Forgetting-curve research; sensitivity test | open |
| Opinion update (new view = halfway to the answer) and "changed mind" threshold (8 points) | `simulate/memory.py`, `simulate/society.py` | Hand-set | Panel surveys measuring how much people move; fit | open |
| Say vs do correction (buying 0.85 / -0.55, beliefs 0.9 / 0) | `simulate/calibrate.py` | Hand-set | Purchase intent vs purchase research, then backtests | open |
| Contacts per person (was: half the daily total plus a random amount) | `simulate/diffusion.py` | Measured spread: negative binomial dispersion from 10 CC BY diary surveys (BEL, CHN, GMB, ITA, NLD, RUS, THA, TWN, ZAF, ZMB); others use the median (k = 2.35). POLYMOD is CC BY-NC, so not used | socialcontactdata.org | done |
| Personality traits referenced in prompts, always empty | `population/models.py`, `scenario/lenses.py` | Empty | WVS items, Global Preferences Survey (risk, trust, patience; 76 countries); otherwise remove from prompts | open |
| Income spread within a job | `population/realdata.py` | Lognormal with the country's household-income Gini; median Gini where missing | No global source of pay spread within jobs. Keep as a labelled model; use World Bank PIP for missing Ginis | open |
| Earnings where there is no earnings survey | `population/realdata.py` | GDP per person / 12 x typical job ratio | ILO modelled wages; labelled | open |
| Company type size bands (small business 2-100, mid-market 100-2000, enterprise 2000+) | `data/occupations.json` | Convention | Cite one standard definition and use it | open |
| B2B buying committee roles and membership | `simulate/committee.py` | Chosen per scenario | No public data: setting with sensitivity test | setting |
| Crowd size, rounds, samples per person, bootstrap | `scenario/models.py` | Settings | Sensitivity test; pick where the answer stops changing | setting |
| Equal weighting of countries and groups | `scenario/compiler.py` | Choice | Report equal and population-weighted side by side | open |

## 2. Coverage of the 202 countries

| Data | Own data now | Target | Source | Status |
|---|---|---|---|---|
| Labour force (simulatable) | 187 | 202 | Territory statistics offices | open |
| Workplace size by job | 98 (89 income-group average) | ~170, rest by a tested model | World Bank Enterprise Surveys (registration), India PLFS (registration), national registers | open |
| Enterprise size above 250 | US shape everywhere | Own data | Enterprise Surveys, national registers | open |
| Workplace vs enterprise size | Mixed | Both, labelled | ILO, SUSB, Eurostat, OECD | open |
| Public sector share | ~105 | Same, plus a tested model | ILOSTAT | open |
| Detailed jobs inside ISCO groups | US mix everywhere | ~15 own, rest borrowed and tested | UK ONS, Canada and Australia censuses, Brazil PNAD, Mexico ENOE, Chile, Peru, Colombia | open |
| Earnings by job | ~130 | All, labelled | ILOSTAT, ILO modelled | open |
| Survey views | 65 | ~150 own, rest borrowed from the most similar surveyed country (flagged, tested) | Joint WVS/EVS, Afrobarometer, Arab Barometer, Latinobarometro (registration), Asian Barometer (registration) | open |
| Daily contacts | Prem projections for 176 (means); spread from 10 diary surveys, median elsewhere | Means from real surveys where they exist | socialcontactdata.org (CC BY only) | open |
| Friendships | 178 measured, 24 estimated | Better estimates (target: 65% within 2x) | UNESCO students abroad, UN Tourism arrivals, national migrant counts | open |
| Services trade | 786 lists estimated | Partner-reported figures | Eurostat, OECD | open |

## 3. Structural gaps

| Gap | Fix | Status |
|---|---|---|
| The LLM chooses the audience (groups, countries) | Show it, check it against data where a published count exists, flag the rest | open |
| The LLM plays each person, untested | Hold out real WVS answers and check the LLM predicts them; compare models | open |
| Backtests may leak (models know famous outcomes) | Events after the model's training cutoff; disguised names and dates | open |
| Sources from different years | Record the year of every figure; align where possible | open |
| WVS is non-profit only | Paid version needs a WVS licence or views from commercially usable surveys | open |
| Restricted datasets | Download script and instructions for each; app says what's missing | open |
| No per-country data quality label | Label every figure measured / borrowed / estimated, shown in results | open |

## 4. Proof

| Step | Status |
|---|---|
| LLM people vs held-out survey answers | open |
| Fit news and feed numbers to real spread curves | open |
| Backtests on product launches after the model cutoff, against baselines | open |
| Sensitivity tests | open |
| Paper | open |
