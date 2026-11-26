"""Verify every headline number in results.json by recomputing it from
the committed processed files. Exits non-zero on any mismatch.

This does not trust results.json: it re-runs the pipeline, forecast,
scenario, and scorecard computations from data/processed/ and compares
each value against the file (tolerance 1e-6 relative for floats).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src import forecast, pipeline, scenarios, scorecard  # noqa: E402

RESULTS_JSON = ROOT / "results" / "results.json"

failures = []


def check(name, got, expected, rel_tol=1e-6):
    if isinstance(expected, float) or isinstance(got, float):
        ok = abs(float(got) - float(expected)) <= rel_tol * max(
            abs(float(expected)), 1e-9)
    else:
        ok = got == expected
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {name}: got={got!r} expected={expected!r}")
    if not ok:
        failures.append(name)


def main() -> int:
    results = json.loads(RESULTS_JSON.read_text())
    meta, weekly, provenance = pipeline.load_processed()
    weekly["week"] = pd.to_datetime(weekly["week"])

    # --- data block ---
    d = results["data"]
    check("netflix_rows", d["netflix_rows"], provenance["netflix_rows"])
    check("netflix_unique_titles", d["netflix_unique_titles"],
          provenance["netflix_unique_titles"])
    check("imdb_matched_titles", d["imdb_matched_titles"],
          provenance["imdb_matched_titles"])
    check("imdb_match_rate_pct", d["imdb_match_rate_pct"],
          provenance["imdb_match_rate_pct"])
    check("animated_movies_matched", d["animated_movies_matched"],
          provenance["animated_movies_matched"])

    # --- slate ---
    slate_df = pipeline.build_slate(weekly, meta)
    check("slate_n_titles", results["slate"]["n_titles"], len(slate_df))
    check("slate_titles", results["slate"]["titles"],
          list(slate_df["show_title"]))
    slate = scenarios.slate_from_weekly(
        weekly[weekly["show_title"].isin(set(slate_df["show_title"]))])
    base_total = scenarios.slate_summary(slate)["total_hours"]
    check("slate_total_hours_baseline",
          results["slate"]["total_hours_baseline"], base_total)

    # --- forecast ---
    eval_df = pipeline.eval_titles(weekly, meta, min_run_weeks=4)
    ev = forecast.evaluate_one_step(eval_df)
    f = results["forecast"]
    check("forecast_n_titles", f["n_titles"], ev["n_titles"])
    check("mape_decay_pct", f["mape_decay_pct"],
          round(ev["mape_decay_pct"], 2))
    check("mape_naive_pct", f["mape_naive_pct"],
          round(ev["mape_naive_pct"], 2))
    check("mape_shape_pct", f["mape_shape_pct"],
          round(ev["mape_shape_pct"], 2))
    check("n_decay_fallbacks", f["n_decay_fallbacks"],
          ev["n_decay_fallbacks"])
    check("pooled_retention_all", f["pooled_retention_all"],
          round(ev["pooled_retention_all"], 4))
    last_w = eval_df.groupby("show_title")["week"].max()
    got_lw = {r["title"]: r["last_week"] for r in f["per_title"]}
    for t, w in last_w.items():
        check(f"per_title[{t}].last_week", got_lw[t], str(w.date()))

    # --- median shape ---
    eval_trajs = [(t, g.sort_values("week")["weekly_hours_viewed"]
                   .to_numpy(dtype=float))
                  for t, g in eval_df.groupby("show_title")]
    shape = forecast.median_shape(eval_trajs, max_weeks=4)
    for k, v in shape.items():
        check(f"median_shape[{k}]",
              results["median_shape_first4w"][str(k)], round(v, 3))

    # --- scorecard ---
    score = scorecard.score_slate(slate, shape)
    got_sc = {r["title"]: (r["status"],
                           None if r["actual_vs_forecast"] is None
                           else round(r["actual_vs_forecast"], 3))
              for r in results["scorecard"]}
    for _, r in score.iterrows():
        exp = got_sc[r["title"]]
        check(f"scorecard[{r['title']}].status", r["status"], exp[0])
        recomputed = r["actual_vs_forecast"]
        if exp[1] is not None and pd.notna(recomputed):
            check(f"scorecard[{r['title']}].ratio",
                  round(recomputed, 3), exp[1])

    # --- scenarios ---
    scen, _ = scenarios.build_scenarios(slate)
    compared = scenarios.compare_scenarios(scen)
    for name, comp in compared.items():
        s = comp["summary"]
        rs = results["scenarios"][name]["summary"]
        check(f"scenario[{name}].total_hours", rs["total_hours"],
              round(s["total_hours"], 2))
        check(f"scenario[{name}].total_delta_pct",
              rs["total_hours_delta_pct"],
              round(s["total_hours_delta_pct"], 2))
        check(f"scenario[{name}].peak_week", rs["peak_week"], s["peak_week"])
        check(f"scenario[{name}].peak_week_hours",
              rs["peak_week_hours"], round(s["peak_week_hours"], 2))
        for t, v in comp["per_title_hours"].items():
            check(f"scenario[{name}].title[{t}]",
                  results["scenarios"][name]["per_title_hours"][t],
                  round(v, 1))

    print()
    if failures:
        print(f"VERIFY FAILED: {len(failures)} mismatch(es): {failures}")
        return 1
    print("VERIFY OK: all headline numbers recompute from the processed data.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
