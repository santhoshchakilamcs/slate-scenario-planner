"""Title-performance forecasting on first-run weekly hours.

Models (all fit per title on its first Top 10 run):
- decay: log-linear fit log(hours) = a + b * t on the post-peak segment
  (from the peak week onward). The slope is capped at 0: this is a decay
  model, it never extrapolates growth. Needs >= 2 post-peak points in
  the training window, otherwise it falls back to naive.
- naive: repeat the last observed week (persistence baseline).
- shape: last observed week times the pooled median post-peak
  week-over-week retention ratio across the other titles
  (leave-one-out).

Evaluation is one-step-ahead: for each title with a first run of >= 4
weeks, fit on all weeks except the last and predict the last week.
MAPE and MAE are reported per method. Nothing is hidden: if a model
does not beat naive, the README says so.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _peak_index(hours) -> int:
    return int(np.argmax(np.asarray(hours, dtype=float)))


def decay_forecast(train_hours):
    """One-step decay forecast. Returns (prediction, used_fallback, slope,
    n_fit_points)."""
    h = np.asarray(train_hours, dtype=float)
    h = h[h > 0]
    if len(h) == 0:
        return 0.0, True, 0.0, 0
    peak = _peak_index(h)
    seg = h[peak:]
    if len(seg) < 2:
        return float(h[-1]), True, 0.0, len(seg)
    t = np.arange(len(seg), dtype=float)
    # log-linear least squares on the post-peak segment
    slope, intercept = np.polyfit(t, np.log(seg), 1)
    slope = min(float(slope), 0.0)  # decay model: never extrapolate growth
    pred = float(np.exp(intercept + slope * len(seg)))
    return pred, False, slope, len(seg)


def naive_forecast(train_hours) -> float:
    h = np.asarray(train_hours, dtype=float)
    return float(h[-1]) if len(h) else 0.0


def pooled_retention(trajectories, exclude_title=None) -> float:
    """Median post-peak week-over-week ratio h[t+1]/h[t] across titles."""
    ratios = []
    for title, hours in trajectories:
        if exclude_title is not None and title == exclude_title:
            continue
        h = np.asarray(hours, dtype=float)
        if len(h) < 2:
            continue
        peak = _peak_index(h)
        for t in range(max(peak, 0), len(h) - 1):
            if h[t] > 0:
                ratios.append(h[t + 1] / h[t])
    if not ratios:
        return 1.0
    return float(np.median(ratios))


def shape_forecast(train_hours, retention: float) -> float:
    return float(naive_forecast(train_hours) * retention)


def median_shape(trajectories, max_weeks: int = 4):
    """Median fraction of peak hours by weeks since release (week 0).

    Each trajectory is divided by its own peak; the median across titles
    at each week offset is the slate's typical shape. Only the first
    `max_weeks` offsets are returned (scorecard horizon).
    """
    by_offset: dict[int, list[float]] = {}
    for _, hours in trajectories:
        h = np.asarray(hours, dtype=float)
        if len(h) == 0 or h.max() <= 0:
            continue
        for i, v in enumerate(h[:max_weeks]):
            by_offset.setdefault(i, []).append(v / h.max())
    return {i: float(np.median(v)) for i, v in sorted(by_offset.items())}


def evaluate_one_step(eval_df: pd.DataFrame) -> dict:
    """One-step-ahead evaluation over first runs of >= 4 weeks.

    Returns metrics per method plus a per-title prediction table.
    """
    trajs = []
    for title, g in eval_df.groupby("show_title"):
        g = g.sort_values("week")
        trajs.append((title, g["weekly_hours_viewed"].to_numpy(dtype=float)))
    retention_all = pooled_retention(trajs)
    rows = []
    for title, hours in trajs:
        train, actual = hours[:-1], float(hours[-1])
        decay_pred, fallback, slope, n_fit = decay_forecast(train)
        loo = pooled_retention(trajs, exclude_title=title)
        shape_pred = shape_forecast(train, loo)
        naive_pred = naive_forecast(train)
        rows.append({
            "title": title,
            "n_weeks": len(hours),
            "actual_last_week": actual,
            "decay_pred": decay_pred,
            "decay_fallback_to_naive": fallback,
            "decay_slope": slope,
            "decay_fit_points": n_fit,
            "naive_pred": naive_pred,
            "shape_pred": shape_pred,
            "shape_retention_loo": loo,
        })
    pred = pd.DataFrame(rows)

    def mape(col):
        return float((abs(pred[col] - pred["actual_last_week"])
                      / pred["actual_last_week"]).mean() * 100)

    def mae(col):
        return float(abs(pred[col] - pred["actual_last_week"]).mean())

    return {
        "n_titles": len(pred),
        "pooled_retention_all": retention_all,
        "mape_decay_pct": mape("decay_pred"),
        "mape_naive_pct": mape("naive_pred"),
        "mape_shape_pct": mape("shape_pred"),
        "mae_decay": mae("decay_pred"),
        "mae_naive": mae("naive_pred"),
        "mae_shape": mae("shape_pred"),
        "n_decay_fallbacks": int(pred["decay_fallback_to_naive"].sum()),
        "per_title": pred,
    }
