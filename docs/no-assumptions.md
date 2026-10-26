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
| News fade (was: half-life 60 days, 'lasting' floor 0.6) | `research/news.py` | Split into memory and attention, both measured. Memory: memory chain model fitted to ~14,000 people's recall of news (Meeter, Murre & Janssen 2005): 84% remembered after a month, 57% after a year; ranks stories and lowers the chance someone still remembers an old one. Attention: Wikipedia pageviews of 157 news stories (2023-24): half gone in 0.84 days, 4% left after a week (R² 0.999); for the feed. Stories still in effect don't fade | `data/news_decay.json`, `scripts/fit_news_decay.py` | done |
| News items per person (was 4) and relevance cutoff (was 0.15) | `research/news.py` | Removed: each person carries every item they came across; the distil step already drops irrelevant results. Items per run (14) stays as a prompt budget | n/a | done (14: setting) |
| Feed weights (was: contact 1.0, reshared 0.8, friend of friend 0.25, stranger 0.03, engagement 1 / 1.5 / 2, power) | `simulate/feed.py` | Ranked feed: share of slots from unconnected people = Meta's own figure for US Facebook feeds (Widely Viewed Content Report Q2 2026: 36.6% unconnected vs 49.6% friends, groups, followed pages: 42.5%). Viral feed: TikTok, 10.3% of views from followed accounts (Zannettou et al., CHI 2024; 347 users, 9.2M views). Within each pool: attention for the post's age x Facebook's interaction points (like 1, reshare 5, comment 30; internal note 2017, reported by CNN 2021). Posts per day on the topic (5) stays a setting | Meta transparency report; data-donation study; Facebook Papers | done (5: setting) |
| Feed freshness and post lifetime (was: 0.55 per round, 3 rounds) | `simulate/feed.py` | A round is a day (the network is daily contacts); a post keeps the measured attention share for its age (Wikipedia pageviews), no cut-off | `data/news_decay.json` | done |
| Feed: repeat-post penalty (was x0.3) and ranking jitter (was ±10%) | `simulate/feed.py` | Removed: a post already shown is not shown again; ties broken by id; the only randomness is the draw of unconnected slots at the measured share | n/a | done |
| Memory fade (was: 0.85 per round) | `simulate/memory.py` | Recall of news events per day (Meeter et al. 2005), a round being a day | `data/news_decay.json` | done |
| Memory: items recalled (was 6 and 8), importance formula and per-kind weights | `simulate/memory.py`, `simulate/society.py` | Removed: people see everything they still remember, each memory kept by a fixed draw against the measured news-recall curve; what matters to them is the person's own judgement | n/a | done |
| Opinion update (was: halfway to the answer) and "changed mind" threshold (was 8 points) | `simulate/memory.py`, `simulate/society.py` | Removed: their view is what they answer (as in every other round); a change is a different point on the Juster scale they answer on, its finest step | n/a | done |
| Say vs do correction (was buying 0.85 / -0.55, beliefs 0.9 / 0) | `simulate/calibrate.py` | Identity until backtests fit it: people answer on the Juster probability scale, which a meta-analysis found empirically unbiased for real buyers (Wright & MacRae 2007, JAMS 35:617-624). Backtests measure any gap for simulated people. The fit's prior strength (1.0) is a setting | Wright & MacRae 2007; backtests | done |
| Contacts per person (was: half the daily total plus a random amount) | `simulate/diffusion.py` | Measured spread: negative binomial dispersion from 10 CC BY diary surveys (BEL, CHN, GMB, ITA, NLD, RUS, THA, TWN, ZAF, ZMB); others use the median (k = 2.35). POLYMOD is CC BY-NC, so not used | socialcontactdata.org | done |
| Personality traits referenced in prompts, always empty | `scenario/lenses.py`, `simulate/society.py` | Removed from prompts; the card only ever shows measured fields, and each person carries a real survey respondent's own answers | n/a | done |
| Income spread within a job | `population/realdata.py` | Lognormal with the country's Gini (a labelled model: no global source of pay spread within jobs). Gini: World Bank; else SWIID 9.92 (CC0, 42 countries); else the 3 most similar countries (16, flagged): hidden-country test error 4.4 Gini points vs 4.85 for the median rule | World Bank, SWIID | done |
| Earnings where there is no earnings survey | `population/realdata.py` | ILO labour income per worker (modelled labour share x GDP / employed) x 0.834, the median ratio of employees' mean earnings to it in 128 countries with both. Hidden-country test: median log error 0.26 vs 0.36 for the old GDP/12 rule | ILOSTAT, World Bank | done |
| Company type size bands (was 2-100, 100-2000, 2000+) | `data/occupations.json` | Gartner IT Glossary: small <100, midsize 100-999, large 1,000+. Start-up: EU small enterprise (<50). Scale-up: OECD-Eurostat high-growth (10+) below the EU large line (<250) | Gartner; EU 2003/361/EC; Eurostat-OECD 2007 | done |
| B2B buying committee roles and membership | `simulate/committee.py` | Chosen per scenario | No public data: setting with sensitivity test | setting |
| Crowd size, rounds, samples per person, bootstrap | `scenario/models.py` | Settings | Sensitivity test; pick where the answer stops changing | setting |
| Weighting of countries and groups | `population/sampler.py` | Population weighting by real headcounts is the default; equal is a user option, used automatically only when a size is unknown (and reported in results.sizes) | n/a | done |

## 2. Coverage of the 202 countries

| Data | Own data now | Target | Source | Status |
|---|---|---|---|---|
| Labour force (simulatable) | 187 | 202 | Territory statistics offices | open |
| Workplace size by job | 99: 98 from ILOSTAT + India from PLFS 2025 (455,930 workers; 20+ split at 50 with the income-group average); 88 use the income-group average | ~170, rest by a tested model | World Bank Enterprise Surveys tested and rejected: on 74 countries with the truth, their shape misplaces 33% of workers vs 16% for the income-group average, and adjusting the average by them doesn't help (docs/enterprise_surveys_test.json). National registers remain | open |
| Enterprise size above 250 | OECD/SUSB where available; income-group average elsewhere; US shape for the finer classes | Own data | Enterprise Surveys tested and rejected for the 50-249 vs 250+ split (error 0.13 direct, 0.062 adjusted vs 0.054 for the average; 40 countries) | open |
| Workplace vs enterprise size | Mixed | Both, labelled | ILO, SUSB, Eurostat, OECD | open |
| Public sector share | ~106 (ILOSTAT + India PLFS 2025) | Same, plus a tested model | ILOSTAT, PLFS | open |
| Detailed jobs inside ISCO groups | US mix everywhere | ~15 own, rest borrowed and tested | UK ONS, Canada and Australia censuses, Brazil PNAD, Mexico ENOE, Chile, Peru, Colombia | open |
| Earnings by job | ~130 | All, labelled | ILOSTAT, ILO modelled | open |
| Survey views | All 189 simulatable countries. Own survey in 139: WVS7 65, EVS 26, Afrobarometer R10/R9 36, Latinobarómetro 6, Arab Barometer 7, Asian Barometer 1 (barometer questions kept only if within 0.10 of WVS in shared countries). The other 50 borrow real respondents from the 3 most similar WVS countries (same region, closest income; any region if those differ >2.7x in income): median gap 0.077 vs 0.109 for a random neighbour, flagged in every profile | Better stand-ins if a wider survey appears | docs/views_harmonisation.json | done |
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
