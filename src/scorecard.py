"""Scorecard: per-title status / risk flags for the slate.

For each slate title, the first 4 weeks of its first run are compared
with a shape-model forecast: peak hours x the slate median fraction of
peak by weeks since release (computed from the forecast evaluation
titles). Ratio = actual first-4-weeks hours / forecast first-4-weeks
hours.

Thresholds (stated in README and results.json):
- ratio > 1.20            -> "ahead of plan"
- 0.80 <= ratio <= 1.20   -> "on track"
- 0.60 <= ratio < 0.80    -> "at risk"
- ratio < 0.60            -> "below plan"
- run of 1 week           -> "insufficient data" (the forecast is
  trivially the peak itself, so no signal)

In delay scenarios, a title whose release week moved vs baseline is
additionally flagged "delayed". The flag is the risk status; "delayed"
is recorded separately as release_moved.
"""
from __future__ import annotations

import pandas as pd

HORIZON_WEEKS = 4
AHEAD = 1.20
ON_TRACK_LOW = 0.80
AT_RISK_LOW = 0.60


def flag_ratio(ratio: float) -> str:
    if ratio > AHEAD:
        return "ahead of plan"
    if ratio >= ON_TRACK_LOW:
        return "on track"
    if ratio >= AT_RISK_LOW:
        return "at risk"
    return "below plan"


def score_slate(slate: dict, shape: dict) -> pd.DataFrame:
    """Score each slate title over its first HORIZON_WEEKS weeks."""
    rows = []
    for title, run in slate.items():
        run = sorted(run)
        peak = max(h for _, h in run)
        m = min(len(run), HORIZON_WEEKS)
        actual = sum(h for _, h in run[:m])
        if len(run) == 1:
            rows.append({
                "title": title,
                "release_week": str(run[0][0].date()),
                "run_weeks": len(run),
                "peak_hours": peak,
                "actual_first4w_hours": actual,
                "forecast_first4w_hours": peak,
                "actual_vs_forecast": None,
                "status": "insufficient data",
                "release_moved": False,
            })
            continue
        forecast = peak * sum(shape.get(i, shape[max(shape)])
                              for i in range(m))
        ratio = actual / forecast if forecast > 0 else 0.0
        rows.append({
            "title": title,
            "release_week": str(run[0][0].date()),
            "run_weeks": len(run),
            "peak_hours": peak,
            "actual_first4w_hours": actual,
            "forecast_first4w_hours": forecast,
            "actual_vs_forecast": ratio,
            "status": flag_ratio(ratio),
            "release_moved": False,
        })
    df = pd.DataFrame(rows).sort_values("release_week").reset_index(drop=True)
    return df


def mark_delayed(scorecard: pd.DataFrame, baseline: dict,
                 scenario: dict) -> pd.DataFrame:
    """Flag titles whose release week moved vs the baseline slate."""
    df = scorecard.copy()
    moved = set()
    for title in scenario:
        if scenario[title][0][0] != baseline[title][0][0]:
            moved.add(title)
    df["release_moved"] = df["title"].isin(moved)
    return df
