"""Run the full pipeline from the committed processed files and write
results.json + the HTML report.

Outputs:
- results/results.json
- results/report.html
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd

from src import forecast, pipeline, report, scenarios, scorecard

ROOT = Path(__file__).resolve().parent
RESULTS_JSON = ROOT / "results" / "results.json"
REPORT_HTML = ROOT / "results" / "report.html"


def _clean(value):
    """JSON-safe value: round finite floats, map NaN/inf to None."""
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            return None
        return round(value, 3)
    return value


def run() -> dict:
    meta, weekly, provenance = pipeline.load_processed()
    weekly["week"] = pd.to_datetime(weekly["week"])

    # Slate + evaluation set, derived from the processed files.
    slate_df = pipeline.build_slate(weekly, meta)
    slate_titles = list(slate_df["show_title"])
    slate_weekly = weekly[weekly["show_title"].isin(set(slate_titles))]
    slate = scenarios.slate_from_weekly(slate_weekly)

    eval_df = pipeline.eval_titles(weekly, meta, min_run_weeks=4)
    eval_result = forecast.evaluate_one_step(eval_df)
    eval_trajs = [(t, g.sort_values("week")["weekly_hours_viewed"]
                   .to_numpy(dtype=float))
                  for t, g in eval_df.groupby("show_title")]
    shape = forecast.median_shape(eval_trajs, max_weeks=4)

    score = scorecard.score_slate(slate, shape)
    scen, scen_meta = scenarios.build_scenarios(slate)
    compared = scenarios.compare_scenarios(scen)
    weekly_by_scenario = {n: scenarios.weekly_totals(s)
                          for n, s in scen.items()}

    # Named titles for the shape chart (median shape + 3 slate titles),
    # plus every evaluation title's own curve, all normalised by each
    # title's full-run peak so they are comparable with the median.
    shape_titles = {}
    for t in ["KPop Demon Hunters", "Plankton: The Movie",
              "Despicable Me 4"]:
        if t in slate:
            full = [x[1] for x in slate[t]]
            peak = max(full)
            shape_titles[t] = [round(v / peak, 3)
                               for v in full[:4]]
    all_titles = {}
    for t, hours in eval_trajs:
        peak = float(max(hours))
        all_titles[t] = [round(float(v) / peak, 3)
                         for v in hours[:4]]

    per_title = eval_result.pop("per_title")
    last_week = eval_df.groupby("show_title")["week"].max()
    per_title["last_week"] = per_title["title"].map(
        lambda t: str(last_week[t].date()))
    results = {
        "project": "slate-scenario-planner",
        "generated": str(date.today()),
        "description": ("Personal project: content-slate scenario planning "
                        "on public Netflix Top 10 + IMDb data."),
        "data": {
            "netflix_source": provenance["netflix_source"],
            "netflix_sha256": provenance["netflix_sha256"],
            "netflix_weeks": provenance["netflix_weeks"],
            "netflix_rows": provenance["netflix_rows"],
            "netflix_unique_titles": provenance["netflix_unique_titles"],
            "imdb_sources": provenance["imdb_sources"],
            "imdb_matched_titles": provenance["imdb_matched_titles"],
            "imdb_match_rate_pct": provenance["imdb_match_rate_pct"],
            "animated_movies_matched": provenance["animated_movies_matched"],
            "animated_film_first_run_rows": provenance["animated_film_first_run_rows"],
            "download_date": provenance["download_date"],
        },
        "slate": {
            "rule": ("Animated movies (IMDb genre contains Animation) whose "
                     "first Top 10 run started on/after 2025-01-01 and whose "
                     "IMDb startYear is within 1 year before the first Top 10 "
                     "week (excludes catalogue re-entries)."),
            "n_titles": len(slate_titles),
            "titles": slate_titles,
            "first_week": str(slate_weekly["week"].min().date()),
            "last_week": str(slate_weekly["week"].max().date()),
            "total_hours_baseline": compared["baseline"]["summary"]["total_hours"],
        },
        "forecast": {
            "method": ("One-step-ahead: fit on all first-run weeks except "
                       "the last, predict the last week. Decay = log-linear "
                       "fit on post-peak weeks, slope capped at 0, falls back "
                       "to naive with <2 post-peak points. Naive = repeat last "
                       "week. Shape = last week x pooled median post-peak "
                       "retention (leave-one-out)."),
            "n_titles": eval_result["n_titles"],
            "pooled_retention_all": round(eval_result["pooled_retention_all"], 4),
            "mape_decay_pct": round(eval_result["mape_decay_pct"], 2),
            "mape_naive_pct": round(eval_result["mape_naive_pct"], 2),
            "mape_shape_pct": round(eval_result["mape_shape_pct"], 2),
            "mae_decay": round(eval_result["mae_decay"], 1),
            "mae_naive": round(eval_result["mae_naive"], 1),
            "mae_shape": round(eval_result["mae_shape"], 1),
            "n_decay_fallbacks": eval_result["n_decay_fallbacks"],
            "per_title": [
                {k: _clean(v) for k, v in row.items()}
                for row in per_title.to_dict("records")],
        },
        "median_shape_first4w": {str(k): round(v, 3)
                                 for k, v in shape.items()},
        "scorecard": [
            {k: _clean(v) for k, v in row.items()}
            for row in score.to_dict("records")],
        "scorecard_thresholds": {
            "ahead_of_plan": "> 1.20",
            "on_track": "0.80 - 1.20",
            "at_risk": "0.60 - 0.80",
            "below_plan": "< 0.60",
            "insufficient_data": "first run of 1 week",
        },
        "scenarios": {
            name: {
                "description": scen_meta[name],
                "summary": {k: (round(v, 2) if isinstance(v, float) else v)
                            for k, v in comp["summary"].items()},
                "per_title_hours": {t: round(v, 1)
                                    for t, v in
                                    comp["per_title_hours"].items()},
                "per_title_delta_hours": {t: round(v, 1)
                                          for t, v in
                                          comp["per_title_delta_hours"].items()},
            }
            for name, comp in compared.items()
        },
        "assumptions": [
            "A title's first Top 10 run is its release run; later re-entries are catalogue returns, not new releases.",
            "Delay scenarios preserve a title's weekly shape; only newly created same-week collisions cost hours (5% that week). The 5% is an assumption, not a measured effect.",
            "Budget shift scales a title's whole run by +/-10% with shape preserved; the effect is illustrative, not causal evidence.",
            "Top 10 data covers only titles that reached the Top 10; hours viewed are Netflix-reported weekly aggregates, not title-level streaming logs.",
            "Forecasts are illustrative. The decay model is fit per title on very short runs (4-10 weeks); MAPE is reported honestly against the naive baseline.",
        ],
    }

    RESULTS_JSON.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_JSON.write_text(json.dumps(results, indent=2))
    slate_weekly_first = pipeline.first_runs(slate_weekly)
    html_doc = report.build_report(
        results, weekly_by_scenario,
        {"median_shape": shape, "titles": shape_titles,
         "all_titles": all_titles},
        score, scen_meta,
        chart_data={"slate": slate,
                    "slate_weekly_first": slate_weekly_first})
    REPORT_HTML.write_text(html_doc)
    print(f"wrote {RESULTS_JSON}")
    print(f"wrote {REPORT_HTML}")
    print(f"slate titles: {len(slate_titles)}")
    print(f"forecast MAPE decay {results['forecast']['mape_decay_pct']:.2f}% "
          f"vs naive {results['forecast']['mape_naive_pct']:.2f}% "
          f"vs shape {results['forecast']['mape_shape_pct']:.2f}%")
    for name, comp in compared.items():
        s = comp["summary"]
        print(f"scenario {name}: total {s['total_hours'] / 1e9:.3f}B "
              f"({s['total_hours_delta_pct']:+.2f}%), peak week "
              f"{s['peak_week']} {s['peak_week_hours'] / 1e6:.1f}M "
              f"({s['peak_week_hours_delta_pct']:+.2f}%)")
    return results


if __name__ == "__main__":
    run()
