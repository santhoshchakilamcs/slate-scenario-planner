# Slate Scenario Planner

A personal project that plans a content slate the way a media-science data
scientist would: forecast how titles perform, simulate what happens when
the schedule slips, and keep a scorecard on every title. Built to fill the
scenario-planning gap for the Netflix Data Scientist 5, Media Science role
(JR42778, founding data scientist for Netflix Animation Studios).

**This is a personal project on public data.** It does not claim animation
industry experience, slate-planning ownership, or any job experience. All
numbers below are computed from the cited public sources by the code in
this repo, and `verify_results.py` recomputes every headline number from
the committed data.

## What it answers

- **Forecast:** can a simple decay curve predict a title's next week
  better than just repeating last week?
- **Scenario:** what happens to the slate if the biggest title slips 4
  weeks, if two tentpoles release the same week, or if marketing weight
  moves to the tentpole?
- **Scorecard:** which titles are on track, at risk, or below plan in
  their first month, against the slate's typical trajectory shape?

## Data (real public data only)

| Source | What | Coverage |
|---|---|---|
| Netflix Top 10, official file — https://www.netflix.com/tudum/top10/data/all-weeks-global.tsv | Weekly Top 10 hours viewed by title | 11,280 rows, weeks 2021-07-04 to 2026-11-22, 3,591 unique titles |
| IMDb public datasets — https://datasets.imdbws.com/title.basics.tsv.gz and title.ratings.tsv.gz | titleType, genres, startYear, averageRating, numVotes | 3,388 of 3,591 Netflix titles matched on normalized title (94.3%) |

Downloaded 2026-11-26. Full provenance (URLs, row counts, SHA-256 of the
Netflix file) is in `data/processed/provenance.json`. The raw downloads
live in `data/raw/` (gitignored); the committed files are the small
processed extracts (`data/processed/`, ~377 KB total).

Matching is on normalized title (lowercase, punctuation stripped). 203
Netflix titles did not match any IMDb row and are excluded from the
animated set; the match rate is reported, not hidden.

## The slate

14 animated movies whose first Top 10 run started on/after 2025-01-01
and whose IMDb release year is within 1 year before that first week. The
year-gap rule separates new-to-Netflix releases from catalogue titles
re-entering the Top 10 years after release (e.g. Bee Movie, released
2007, first Top 10 week 2025).

A title's *first run* is its first maximal run of consecutive weeks in
the Top 10. Later re-entries are catalogue returns, not new releases.

| Title | First week | Run | Peak | Run total |
|---|---|---|---|---|
| Wallace & Gromit: Vengeance Most Fowl | 2025-01-12 | 1 wk | 6.3M | 6.3M |
| The Witcher: Sirens of the Deep | 2025-02-16 | 1 wk | 7.3M | 7.3M |
| Despicable Me 4 | 2025-03-02 | 5 wks | 15.9M | 53.3M |
| Plankton: The Movie | 2025-03-09 | 4 wks | 21.0M | 53.4M |
| My Hero Academia: You're Next | 2025-04-27 | 1 wk | 2.2M | 2.2M |
| The Rose of Versailles | 2025-05-04 | 1 wk | 2.5M | 2.5M |
| The Wild Robot | 2025-05-25 | 3 wks | 9.9M | 19.8M |
| KPop Demon Hunters | 2025-06-22 | 63 wks | 50.2M | 1,128.8M |
| Mahavatar Narsimha | 2025-09-21 | 3 wks | 6.6M | 14.5M |
| The Twits | 2025-10-19 | 3 wks | 13.9M | 29.8M |
| Dr. Seuss's The Sneetches | 2025-11-09 | 1 wk | 3.1M | 3.1M |
| Cosmic Princess Kaguya! | 2026-01-25 | 3 wks | 2.9M | 7.1M |
| The Bad Guys 2 | 2026-03-29 | 1 wk | 7.4M | 7.4M |
| Emi Martinez: The Kid Who Stops Time | 2026-05-31 | 2 wks | 2.4M | 3.8M |

Baseline slate total: **1.339B hours**. Peak week: **2025-08-31, 50.2M
hours** (KPop Demon Hunters alone that week).

One honest outlier dominates everything: KPop Demon Hunters ran 63
consecutive weeks in the Top 10, peaked in week 11 (not week 1 — a
slow-burn phenomenon), and accounts for 84% of the slate's total hours.
Every slate-level result below is mostly a KPop result; the report says
so wherever it matters.

## Forecast check (one-step-ahead, 22 titles)

Evaluation set: animated movies with a first run of 4+ weeks. Fit on all
weeks except the last, predict the last week.

| Model | MAPE | MAE |
|---|---|---|
| Decay curve (log-linear fit on post-peak weeks, slope capped at 0) | **16.79%** | 1.02M hours |
| Naive (repeat last week) | 50.59% | 3.16M hours |
| Median-shape (last week x pooled median post-peak retention, leave-one-out) | 32.94% | — |

The decay model beats naive clearly, and it never fell back to naive
(0 fallbacks in 22 titles). Pooled post-peak week-over-week retention:
0.849. The median first-run shape (fraction of peak by weeks since
release) is 0.79 / 1.00 / 0.58 / 0.43 — titles typically peak in week 2,
not week 1. Per-title predictions are in `results/results.json`.

## Scenarios (deterministic counterfactual replay)

The baseline is the slate as observed. A scenario changes the plan and
recomputes slate totals; the rules are fixed in `src/scenarios.py`:

- **Delay:** a title's whole run shifts by k weeks, shape preserved.
- **Collision penalty (5%):** when a shifted title enters a calendar
  week it was not in before while another slate title is also active
  there, that week's hours are scaled by 0.95. The baseline applies no
  penalty — observed data already embeds real overlap effects. Only
  newly created collisions cost hours. The 5% is an assumption, not a
  measured effect.
- **Budget shift (10%):** the recipient's whole run scales by 1.10 and
  the donor's by 0.90, shape preserved. Illustrative, not causal
  evidence.

| Scenario | What changed | Slate total | Peak-week load |
|---|---|---|---|
| baseline | as observed | 1.339B | 2025-08-31, 50.2M |
| tentpole_slips_4w | KPop Demon Hunters delayed 4 weeks | 1.339B (+0.00%) | 2025-09-28, 56.8M (+13.15%) |
| tentpoles_collide | Plankton: The Movie moved to release the same week as Despicable Me 4 (2025-03-02) | 1.338B (−0.08%) | 2025-08-31, 50.2M (+0.00%) |
| budget_shift_to_tentpole | 10% marketing weight from My Hero Academia: You're Next (smallest peak, 2.2M) to KPop Demon Hunters | 1.452B (+8.41%) | 2025-08-31, 55.2M (+10.00%) |

What the scenarios actually say:

- **Delaying the tentpole 4 weeks costs nothing in total hours**
  (+0.00%) — a 63-week run still overlaps the same titles — but it
  moves KPop's peak into Mahavatar Narsimha's release window, so the
  peak-week load rises 13.15% to 56.8M. The risk is a load spike, not
  lost hours.
- **Same-week tentpoles cost little in total** (−0.08%, about 1.05M
  hours: 5% of Plankton's 21.0M opening week) but concentrate load:
  the shared opening week jumps to 33.8M hours from 13.8M.
- **Moving marketing weight to the tentpole pays the most** (+8.41%),
  because the tentpole is 84% of the slate. That is arithmetic under
  the stated linear assumption, not proof that marketing causes it.

## Scorecard (first 4 weeks vs shape-model forecast)

Forecast = peak hours x the slate median shape (0.79 / 1.00 / 0.58 /
0.43). Thresholds: >1.20 ahead of plan; 0.80–1.20 on track; 0.60–0.80
at risk; <0.60 below plan. Titles with a 1-week run are "insufficient
data" — the forecast would be trivially the peak itself.

| Title | Actual vs forecast | Status |
|---|---|---|
| Despicable Me 4 | 1.05 | on track |
| Plankton: The Movie | 0.91 | on track |
| The Wild Robot | 0.84 | on track |
| KPop Demon Hunters | 0.95 | on track |
| Mahavatar Narsimha | 0.92 | on track |
| The Twits | 0.90 | on track |
| Cosmic Princess Kaguya! | 1.03 | on track |
| Emi Martinez: The Kid Who Stops Time | 0.88 | on track |
| Wallace & Gromit, The Witcher: Sirens of the Deep, My Hero Academia, The Rose of Versailles, Dr. Seuss's The Sneetches, The Bad Guys 2 | — | insufficient data |

All eight scorable titles land on track (0.84–1.05). That is a finding
about the shape model, not a surprise: the median shape describes the
typical animated-film trajectory well. Note the shape benchmark is
computed from the same 22-title population it scores (each title is
~1/22 of the median), so mild in-sample optimism applies.

## Report charts (9, in results/report.html)

All charts are inline SVG (no PNG), computed from the committed data by
`src/report.py`. Interactivity is vanilla JS only, inline in the HTML —
no external libraries, so the report stays self-contained.

1. **Bump chart:** Top 10 rank movement of the 14 slate titles over
   time (rank 1 at top), each line labelled at its last week.
2. **Small multiples:** per-title weekly trajectory sparklines, each
   panel scaled to its own peak.
3. **Forecast vs actual (connected scatter):** each title's naive,
   shape, and decay one-step-ahead predictions connected, coloured by
   title; hover for title, week, actual, and predicted hours.
4. **Slate total hours by scenario** (bars).
5. **Peak-week load by scenario** (bars).
6. **Waterfall/bridge:** how each scenario moves total slate hours
   away from the baseline. The floating bars are alternatives, not
   cumulative steps; the y axis is zoomed to the deltas and labelled
   in billions so the truncation is visible.
7. **First-run shapes:** every evaluation title's own decay curve in
   grey behind the bold median shape, plus three named titles.
8. **Titles x weeks heatmap** of hours viewed (log colour scale;
   blank = title not in the Top 10 that week).
9. **Slate composition treemap:** rectangle area = share of total
   slate hours (KPop Demon Hunters is 84.3% of the area).

## Limitations (read before citing any number)

- Top 10 data covers only titles that reached the Top 10; hours viewed
  are Netflix-reported weekly aggregates, not title-level streaming logs.
- The 5% collision penalty and the ±10% budget-shift effect are stated
  assumptions, not measured causal effects.
- Forecasts are illustrative. The decay model is fit per title on very
  short runs (4–10 weeks for most titles); KPop's 63-week run is the
  exception, and it dominates slate totals.
- Genre comes from IMDb matching on title text; 5.7% of Netflix titles
  did not match, and a few matches may be wrong titles with the same
  name (e.g. "The Crown" matched a 2024 Animation entry with no
  rating — it is not in the film slate, but matching noise exists).
- This project does not claim animation-domain job experience,
  slate-planning ownership, or Scala/Java.

## Repo layout

```
download_data.py        download sources, build processed files
run_all.py              pipeline -> forecast -> scenarios -> scorecard -> results + report
verify_results.py       recompute every headline number in results.json from the data
src/pipeline.py         load, clean, join, runs, slate rules
src/forecast.py         decay / naive / shape models, one-step evaluation
src/scenarios.py        delay, collision penalty, budget shift, comparisons
src/scorecard.py        status / risk flags
src/report.py           static HTML report, 10 inline SVG charts (no PNG),
                        vanilla-JS tooltips + legend toggles, self-contained
data/processed/         committed extracts (imdb_metadata.csv,
                        animated_films_weekly.csv, provenance.json)
results/results.json    all computed numbers
results/report.html     10 charts + scorecard + scenario tables
tests/                  pytest suite (23 tests)
```

## Run it

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python download_data.py   # re-downloads sources (231 MB IMDb file), rebuilds processed files
.venv/bin/python run_all.py         # writes results/results.json + results/report.html
.venv/bin/python -m pytest tests/ -q
.venv/bin/python verify_results.py  # must print VERIFY OK
```

`run_all.py` and the tests run from the committed processed files alone —
no download needed.

## Push

The GitHub repo `slate-scenario-planner` does not exist yet. Once it is
created (empty), push this directory with the snapshot procedure used
for the other gap projects (text only, no PNG, no `data/raw/`).
