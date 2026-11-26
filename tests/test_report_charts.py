"""Tests for the advanced report charts (9 SVG charts)."""
import pandas as pd

from src import report


def _fixture():
    results = {
        "slate": {"n_titles": 3, "first_week": "2025-03-02",
                  "last_week": "2025-03-23"},
        "forecast": {
            "n_titles": 2, "mape_decay_pct": 10.0, "mape_naive_pct": 20.0,
            "mape_shape_pct": 15.0, "n_decay_fallbacks": 0,
            "pooled_retention_all": 0.85,
            "per_title": [
                {"title": "Alpha", "actual_last_week": 10_000_000.0,
                 "decay_pred": 9_000_000.0, "naive_pred": 11_000_000.0,
                 "shape_pred": 9_500_000.0, "last_week": "2025-03-23"},
                {"title": "Beta", "actual_last_week": 5_000_000.0,
                 "decay_pred": 5_500_000.0, "naive_pred": 6_000_000.0,
                 "shape_pred": 4_800_000.0, "last_week": "2025-03-30"},
            ],
        },
        "median_shape_first4w": {"0": 0.79, "1": 1.0, "2": 0.58, "3": 0.43},
        "scenarios": {
            "baseline": {
                "summary": {"total_hours": 100_000_000.0,
                            "total_hours_delta_pct": 0.0,
                            "peak_week": "2025-03-09",
                            "peak_week_hours": 30_000_000.0,
                            "peak_week_hours_delta_pct": 0.0},
                "per_title_hours": {"Alpha": 60_000_000.0,
                                    "Beta": 30_000_000.0,
                                    "Gamma": 10_000_000.0}},
            "tentpole_slips_4w": {
                "summary": {"total_hours": 100_000_000.0,
                            "total_hours_delta_pct": 0.0,
                            "peak_week": "2025-03-16",
                            "peak_week_hours": 35_000_000.0,
                            "peak_week_hours_delta_pct": 16.67}},
        },
    }
    weekly = {
        "baseline": pd.DataFrame(
            {"week": pd.to_datetime(["2025-03-02", "2025-03-09",
                                     "2025-03-16", "2025-03-23"]),
             "total_hours": [40e6, 30e6, 20e6, 10e6]}),
        "tentpole_slips_4w": pd.DataFrame(
            {"week": pd.to_datetime(["2025-03-02", "2025-03-09",
                                     "2025-03-16", "2025-03-23"]),
             "total_hours": [40e6, 25e6, 25e6, 10e6]}),
    }
    shape_series = {"median_shape": {0: 0.79, 1: 1.0, 2: 0.58, 3: 0.43},
                    "titles": {"Alpha": [0.8, 1.0, 0.6, 0.4]},
                    "all_titles": {"Alpha": [0.8, 1.0, 0.6, 0.4],
                                   "Beta": [0.7, 1.0, 0.5, 0.3]}}
    sc = pd.DataFrame([{"title": "Alpha", "release_week": "2025-03-02",
                        "run_weeks": 4, "peak_hours": 20_000_000.0,
                        "actual_first4w_hours": 60_000_000.0,
                        "forecast_first4w_hours": 55_000_000.0,
                        "actual_vs_forecast": 1.09, "status": "on track"}])
    slate = {
        "Alpha": [(pd.Timestamp("2025-03-02"), 20e6),
                  (pd.Timestamp("2025-03-09"), 15e6),
                  (pd.Timestamp("2025-03-16"), 12e6),
                  (pd.Timestamp("2025-03-23"), 10e6)],
        "Beta": [(pd.Timestamp("2025-03-09"), 8e6),
                 (pd.Timestamp("2025-03-16"), 6e6)],
        "Gamma": [(pd.Timestamp("2025-03-16"), 4e6)],
    }
    slate_weekly = pd.DataFrame([
        {"week": pd.Timestamp("2025-03-02"), "show_title": "Alpha",
         "weekly_rank": 3, "weekly_hours_viewed": 20e6},
        {"week": pd.Timestamp("2025-03-09"), "show_title": "Alpha",
         "weekly_rank": 2, "weekly_hours_viewed": 15e6},
        {"week": pd.Timestamp("2025-03-16"), "show_title": "Alpha",
         "weekly_rank": 4, "weekly_hours_viewed": 12e6},
        {"week": pd.Timestamp("2025-03-23"), "show_title": "Alpha",
         "weekly_rank": 5, "weekly_hours_viewed": 10e6},
        {"week": pd.Timestamp("2025-03-09"), "show_title": "Beta",
         "weekly_rank": 6, "weekly_hours_viewed": 8e6},
        {"week": pd.Timestamp("2025-03-16"), "show_title": "Beta",
         "weekly_rank": 7, "weekly_hours_viewed": 6e6},
        {"week": pd.Timestamp("2025-03-16"), "show_title": "Gamma",
         "weekly_rank": 8, "weekly_hours_viewed": 4e6},
    ])
    meta = {"baseline": "as observed",
            "tentpole_slips_4w": "delayed"}
    return results, weekly, shape_series, sc, slate, slate_weekly, meta


def test_full_report_has_nine_svgs():
    results, weekly, shape_series, sc, slate, slate_weekly, meta = _fixture()
    html_doc = report.build_report(
        results, weekly, shape_series, sc, meta,
        chart_data={"slate": slate, "slate_weekly_first": slate_weekly})
    assert html_doc.count("<svg") == 9
    assert 'id="tooltip"' in html_doc
    assert "addEventListener" in html_doc


def test_report_without_chart_data_degrades_gracefully():
    results, weekly, shape_series, sc, slate, slate_weekly, meta = _fixture()
    html_doc = report.build_report(results, weekly, shape_series, sc, meta)
    # scatter + totals + peaks + waterfall + shape + treemap
    assert html_doc.count("<svg") == 6


def test_bump_chart_lines_and_end_labels():
    _, _, _, _, _, slate_weekly, _ = _fixture()
    svg = report.bump_chart("t", slate_weekly)
    # Alpha (4 pts) and Beta (2 pts) are polylines; Gamma (1 pt) a circle
    assert svg.count("<polyline") == 2
    assert "Alpha" in svg and "Beta" in svg and "Gamma" in svg
    assert "Top 10 rank" in svg


def test_small_multiples_panels():
    _, _, _, _, slate, _, _ = _fixture()
    svg = report.small_multiples("t", slate)
    assert "Alpha" in svg and "Beta" in svg and "Gamma" in svg
    assert "peak 20.0M" in svg
    assert svg.count("<polyline") == 2  # Alpha, Beta; Gamma is one point


def test_connected_scatter_points_and_diagonal():
    results, _, _, _, _, _, _ = _fixture()
    svg = report.connected_scatter("t", results["forecast"]["per_title"])
    # 2 titles x 3 models = 6 tooltip points: 2 circles (decay) + 2
    # squares (naive) + 2 triangles (shape); plus 1 legend circle and
    # 1 legend triangle
    assert svg.count("data-tip=") == 6
    assert svg.count("<circle") == 3
    assert svg.count("<polygon") == 3
    assert svg.count("<polyline") == 2  # one connector per title
    assert 'stroke-dasharray="5,4"' in svg
    assert "Alpha — week 2025-03-23" in svg


def test_waterfall_delta_labels():
    scen = {
        "baseline": {"summary": {"total_hours": 100_000_000.0}},
        "up": {"summary": {"total_hours": 110_000_000.0}},
        "down": {"summary": {"total_hours": 99_000_000.0}},
    }
    svg = report.waterfall_chart("t", scen)
    assert "+10.0M" in svg
    assert "-1.0M" in svg
    assert "0.10B" in svg  # baseline bar label


def test_heatmap_cells_and_empty_cells():
    _, _, _, _, slate, _, _ = _fixture()
    svg = report.heatmap_chart("t", slate)
    # 3 titles x 4 weeks = 12 cells; 7 have data (tooltips), 5 are empty
    assert svg.count("data-tip=") == 7
    assert svg.count('fill="#f0f0f0"') == 5
    assert "log scale" in svg


def test_treemap_areas_match_shares():
    hours = {"Alpha": 60.0, "Beta": 30.0, "Gamma": 10.0}
    rects = report._treemap_layout(sorted(hours.items(), key=lambda kv: -kv[1]),
                                   0, 0, 100, 100, horizontal=False)
    assert len(rects) == 3
    total_area = 100 * 100
    by_label = {r[0]: r for r in rects}
    alpha_area = by_label["Alpha"][4] * by_label["Alpha"][5]
    assert abs(alpha_area / total_area - 0.6) < 0.01
    svg = report.treemap_chart("t", hours)
    assert "60.0%" in svg
    assert svg.count("data-tip=") == 3


def test_shape_chart_individual_curves_behind_median():
    _, _, shape_series, _, _, _, _ = _fixture()
    svg = report.shape_chart("t", shape_series)
    assert svg.count('stroke="#cccccc"') == 2  # two individual curves
    assert "individual titles (2)" in svg
    assert "median shape" in svg
    assert "Alpha" in svg
