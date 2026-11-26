"""Tests for the scorecard and the HTML report."""
import pandas as pd

from src import report, scorecard


def test_flag_ratio_thresholds():
    assert scorecard.flag_ratio(1.21) == "ahead of plan"
    assert scorecard.flag_ratio(1.20) == "on track"
    assert scorecard.flag_ratio(0.80) == "on track"
    assert scorecard.flag_ratio(0.79) == "at risk"
    assert scorecard.flag_ratio(0.60) == "at risk"
    assert scorecard.flag_ratio(0.59) == "below plan"


def test_score_slate_marks_one_week_titles_insufficient():
    slate = {
        "Solo": [(pd.Timestamp("2025-03-02"), 100.0)],
        "Duo": [(pd.Timestamp("2025-03-02"), 100.0),
                (pd.Timestamp("2025-03-09"), 50.0)],
    }
    shape = {0: 1.0, 1: 0.5, 2: 0.25, 3: 0.12}
    sc = scorecard.score_slate(slate, shape)
    solo = sc[sc["title"] == "Solo"].iloc[0]
    duo = sc[sc["title"] == "Duo"].iloc[0]
    assert solo["status"] == "insufficient data"
    assert duo["status"] == "on track"
    assert abs(duo["actual_vs_forecast"] - 1.0) < 1e-9


def test_score_slate_flags_below_plan():
    slate = {
        "Weak": [(pd.Timestamp("2025-03-02"), 100.0),
                 (pd.Timestamp("2025-03-09"), 10.0)],
    }
    shape = {0: 1.0, 1: 0.5, 2: 0.25, 3: 0.12}
    sc = scorecard.score_slate(slate, shape)
    # actual 110 vs forecast 100*(1.0+0.5)=150 -> 0.73 -> at risk
    assert sc.iloc[0]["status"] == "at risk"


def test_mark_delayed():
    base = {"A": [(pd.Timestamp("2025-03-02"), 10.0)],
            "B": [(pd.Timestamp("2025-03-09"), 10.0)]}
    scen = {"A": [(pd.Timestamp("2025-03-16"), 10.0)],
            "B": [(pd.Timestamp("2025-03-09"), 10.0)]}
    sc = pd.DataFrame([{"title": "A", "release_week": "2025-03-02"},
                       {"title": "B", "release_week": "2025-03-09"}])
    out = scorecard.mark_delayed(sc, base, scen)
    assert bool(out.loc[out["title"] == "A", "release_moved"].iloc[0]) is True
    assert bool(out.loc[out["title"] == "B", "release_moved"].iloc[0]) is False


def test_build_report_smoke():
    results = {
        "slate": {"n_titles": 2, "first_week": "2025-03-02",
                  "last_week": "2025-03-16"},
        "forecast": {"n_titles": 3, "mape_decay_pct": 10.0,
                     "mape_naive_pct": 20.0, "mape_shape_pct": 15.0,
                     "n_decay_fallbacks": 0, "pooled_retention_all": 0.6},
        "scenarios": {
            "baseline": {"summary": {"total_hours": 300.0,
                                     "total_hours_delta_pct": 0.0,
                                     "peak_week": "2025-03-02",
                                     "peak_week_hours": 100.0,
                                     "peak_week_hours_delta_pct": 0.0}},
            "tentpole_slips_4w": {"summary": {"total_hours": 300.0,
                                              "total_hours_delta_pct": 0.0,
                                              "peak_week": "2025-03-30",
                                              "peak_week_hours": 100.0,
                                              "peak_week_hours_delta_pct": 0.0}},
        },
    }
    weekly = {"baseline": pd.DataFrame(
        {"week": pd.to_datetime(["2025-03-02", "2025-03-09"]),
         "total_hours": [100.0, 80.0]}),
        "tentpole_slips_4w": pd.DataFrame(
            {"week": pd.to_datetime(["2025-03-02", "2025-03-09"]),
             "total_hours": [100.0, 80.0]})}
    shape_series = {"median_shape": {0: 1.0, 1: 0.5}, "titles": {}}
    sc = pd.DataFrame([{"title": "A", "release_week": "2025-03-02",
                        "run_weeks": 2, "peak_hours": 100.0,
                        "actual_first4w_hours": 150.0,
                        "forecast_first4w_hours": 150.0,
                        "actual_vs_forecast": 1.0, "status": "on track"}])
    html_doc = report.build_report(results, weekly, shape_series, sc,
                                   {"baseline": "as observed",
                                    "tentpole_slips_4w": "delayed"})
    assert "<svg" in html_doc
    assert "A" in html_doc
    assert "on track" in html_doc
    assert "tentpole_slips_4w" in html_doc
