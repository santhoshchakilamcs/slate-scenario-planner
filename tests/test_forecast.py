"""Tests for the forecasting models."""
import numpy as np
import pandas as pd

from src import forecast


def test_decay_forecast_fits_clean_exponential():
    # hours halving each week: log-linear fit should recover ~0.5 decay
    hours = [100.0, 50.0, 25.0, 12.5]
    pred, fallback, slope, n_fit = forecast.decay_forecast(hours)
    assert not fallback
    assert n_fit == 4
    assert abs(slope - np.log(0.5)) < 1e-6
    assert abs(pred - 6.25) < 1e-6


def test_decay_forecast_falls_back_with_one_post_peak_point():
    # peak at the last training week -> only 1 post-peak point
    hours = [10.0, 20.0, 30.0]
    pred, fallback, slope, n_fit = forecast.decay_forecast(hours)
    assert fallback
    assert pred == 30.0


def test_decay_forecast_never_extrapolates_growth():
    hours = [10.0, 20.0, 40.0, 80.0]  # still rising; peak is last
    pred, fallback, slope, n_fit = forecast.decay_forecast(hours)
    assert fallback  # peak at last week -> 1 post-peak point
    # rising then flat segment: slope capped at 0
    hours2 = [100.0, 120.0, 110.0, 105.0]
    pred2, fb2, slope2, _ = forecast.decay_forecast(hours2)
    assert slope2 <= 0.0
    assert pred2 <= 105.0 + 1e-9


def test_naive_forecast():
    assert forecast.naive_forecast([5.0, 9.0, 7.0]) == 7.0
    assert forecast.naive_forecast([]) == 0.0


def test_pooled_retention_median():
    trajs = [("A", [100.0, 50.0, 25.0]), ("B", [80.0, 40.0, 32.0])]
    r = forecast.pooled_retention(trajs)
    # ratios: 0.5, 0.5, 0.5, 0.8 -> median 0.5
    assert abs(r - 0.5) < 1e-9
    r_loo = forecast.pooled_retention(trajs, exclude_title="A")
    assert abs(r_loo - 0.65) < 1e-9  # median of 0.5, 0.8


def test_median_shape():
    trajs = [("A", [100.0, 50.0, 25.0, 10.0]),
             ("B", [80.0, 40.0, 20.0, 8.0])]
    shape = forecast.median_shape(trajs, max_weeks=4)
    assert shape[0] == 1.0
    assert abs(shape[1] - 0.5) < 1e-9
    assert abs(shape[2] - 0.25) < 1e-9
    assert abs(shape[3] - 0.1) < 1e-9


def test_evaluate_one_step_decay_beats_naive_on_clean_data():
    # Clean exponential decays: decay model should beat naive clearly.
    rows = []
    for title, start in [("A", 100.0), ("B", 80.0), ("C", 60.0)]:
        for i in range(5):
            rows.append({"show_title": title,
                         "week": pd.Timestamp("2025-01-05")
                         + pd.Timedelta(weeks=i),
                         "weekly_hours_viewed": start * (0.5 ** i)})
    df = pd.DataFrame(rows)
    ev = forecast.evaluate_one_step(df)
    assert ev["n_titles"] == 3
    assert ev["mape_decay_pct"] < 0.01
    assert ev["mape_naive_pct"] > 40  # naive repeats last week, ~50% off
    assert ev["n_decay_fallbacks"] == 0
