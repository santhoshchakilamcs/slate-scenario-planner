"""Scenario engine: deterministic counterfactual replay of a slate.

The slate is a set of titles, each with a first Top 10 run: a release
week and a list of (week, hours_viewed). The baseline scenario is the
slate as observed. A scenario changes the plan and recomputes slate
outcomes; every change is a stated, deterministic rule:

- delay(title, k weeks): the title's whole run shifts by k weeks.
  Its weekly shape is preserved, so its own total is unchanged
  except for the collision rule below.
- collision penalty: when a shifted title enters a calendar week it
  was not in before, and another slate title is also active that
  week, the shifted title's hours that week are scaled by
  (1 - COLLISION_PENALTY). The baseline applies no penalty: observed
  data already embeds whatever real overlap effects existed. Only
  *newly created* collisions cost hours. This is an assumption, not
  a measured effect, and it is stated as such in the README.
- budget_shift(donor, recipient, pct): the recipient's whole run
  scales by (1 + pct) and the donor's by (1 - pct). Shape is
  preserved. Assumption: marketing weight moves opening demand;
  decay shape is unchanged. Also an assumption, not causal evidence.

Outcomes per scenario: slate total hours, peak-week load (max weekly
slate total) and its week, per-title totals. Deltas are vs baseline.
"""
from __future__ import annotations

import copy

import pandas as pd

COLLISION_PENALTY = 0.05
BUDGET_SHIFT_PCT = 0.10
DELAY_WEEKS_KPOP = 4


def slate_from_weekly(weekly: pd.DataFrame) -> dict:
    """First-run weekly rows -> {title: [(week, hours), ...]} sorted."""
    slate = {}
    for title, g in weekly.groupby("show_title"):
        g = g.sort_values("week")
        slate[title] = [(pd.Timestamp(w), float(h)) for w, h in
                        zip(g["week"], g["weekly_hours_viewed"])]
    return slate


def release_week(slate: dict, title: str) -> pd.Timestamp:
    return slate[title][0][0]


def weekly_totals(slate: dict) -> pd.DataFrame:
    """Per calendar week: total hours and number of active slate titles."""
    rows = []
    for title, run in slate.items():
        for week, hours in run:
            rows.append((week, title, hours))
    df = pd.DataFrame(rows, columns=["week", "title", "hours"])
    totals = (df.groupby("week")
              .agg(total_hours=("hours", "sum"),
                   active_titles=("title", "nunique"))
              .reset_index().sort_values("week"))
    return totals


def slate_summary(slate: dict) -> dict:
    totals = weekly_totals(slate)
    peak_row = totals.loc[totals["total_hours"].idxmax()]
    return {
        "n_titles": len(slate),
        "total_hours": float(totals["total_hours"].sum()),
        "peak_week": str(pd.Timestamp(peak_row["week"]).date()),
        "peak_week_hours": float(peak_row["total_hours"]),
        "span_weeks": int(len(totals)),
        "first_week": str(totals["week"].min().date()),
        "last_week": str(totals["week"].max().date()),
    }


def per_title_totals(slate: dict) -> dict:
    return {t: float(sum(h for _, h in run)) for t, run in slate.items()}


def _active_weeks(slate: dict, exclude: str | None = None) -> dict:
    """week -> set of active titles (optionally excluding one title)."""
    active: dict = {}
    for title, run in slate.items():
        if title == exclude:
            continue
        for week, _ in run:
            active.setdefault(week, set()).add(title)
    return active


def delay_title(slate: dict, title: str, k_weeks: int,
                penalty: float = COLLISION_PENALTY) -> dict:
    """Shift one title's run by k weeks, applying the collision penalty
    to weeks it newly enters while another slate title is active."""
    if title not in slate:
        raise KeyError(f"title not in slate: {title}")
    if k_weeks == 0:
        return copy.deepcopy(slate)
    new_slate = copy.deepcopy(slate)
    baseline_active = _active_weeks(slate, exclude=title)
    baseline_weeks = {w for w, _ in slate[title]}
    shifted = []
    for week, hours in slate[title]:
        new_week = week + pd.Timedelta(weeks=k_weeks)
        h = hours
        # Newly entered week (not in the title's baseline run) with
        # another slate title already active there: collision cost.
        if new_week not in baseline_weeks and new_week in baseline_active:
            h = hours * (1 - penalty)
        shifted.append((new_week, h))
    new_slate[title] = shifted
    return new_slate


def budget_shift(slate: dict, donor: str, recipient: str,
                 pct: float = BUDGET_SHIFT_PCT) -> dict:
    """Scale the recipient's whole run by (1 + pct) and the donor's by
    (1 - pct)."""
    if donor not in slate or recipient not in slate:
        raise KeyError("donor/recipient not in slate")
    if donor == recipient:
        raise ValueError("donor and recipient must differ")
    new_slate = copy.deepcopy(slate)
    new_slate[recipient] = [(w, h * (1 + pct)) for w, h in slate[recipient]]
    new_slate[donor] = [(w, h * (1 - pct)) for w, h in slate[donor]]
    return new_slate


def build_scenarios(slate: dict) -> dict:
    """Named scenarios, derived from the slate by fixed rules:

    - baseline: as observed.
    - tentpole_slips_4w: the largest-total title is delayed 4 weeks.
    - tentpoles_collide: among titles with peak >= 10M hours/week
      ("tentpoles"), the pair with the smallest release gap is found and
      the later one is moved to release in the same week as the earlier
      one (same-week tentpole collision).
    - budget_shift_to_tentpole: 10% of marketing weight moves from the
      smallest-peak title to the largest-peak title.
    """
    totals = per_title_totals(slate)
    peaks = {t: max(h for _, h in run) for t, run in slate.items()}
    biggest = max(totals, key=totals.get)
    smallest_peak = min(peaks, key=peaks.get)
    tentpoles = sorted([t for t, p in peaks.items() if p >= 10_000_000],
                       key=lambda t: release_week(slate, t))
    if len(tentpoles) < 2:
        raise ValueError("need at least two tentpole titles for scenarios")
    gaps = [(release_week(slate, tentpoles[i + 1])
             - release_week(slate, tentpoles[i]), i)
            for i in range(len(tentpoles) - 1)]
    _, i = min(gaps)
    earlier, later = tentpoles[i], tentpoles[i + 1]
    k_collide = int((release_week(slate, earlier)
                     - release_week(slate, later)).days // 7)

    scenarios = {"baseline": copy.deepcopy(slate)}
    scenarios["tentpole_slips_4w"] = delay_title(
        slate, biggest, DELAY_WEEKS_KPOP)
    scenarios["tentpoles_collide"] = delay_title(
        slate, later, k_collide)
    scenarios["budget_shift_to_tentpole"] = budget_shift(
        slate, donor=smallest_peak, recipient=biggest)
    meta = {
        "baseline": "As observed: each title releases in its first Top 10 week.",
        "tentpole_slips_4w": (
            f"Largest-total title ({biggest}) delayed {DELAY_WEEKS_KPOP} weeks. "
            "Shape preserved; newly created collisions cost 5% that week."),
        "tentpoles_collide": (
            f"{later} moved to release the same week as {earlier} "
            f"({release_week(slate, earlier).date()}); its overlapping weeks "
            "take the 5% collision penalty."),
        "budget_shift_to_tentpole": (
            f"10% marketing weight from smallest-peak title ({smallest_peak}) "
            f"to largest-peak title ({biggest}); whole runs scale, shape kept."),
    }
    return scenarios, meta


def compare_scenarios(scenarios: dict) -> dict:
    """Summary + per-title totals for each scenario, with deltas vs baseline."""
    base = slate_summary(scenarios["baseline"])
    base_totals = per_title_totals(scenarios["baseline"])
    out = {}
    for name, slate in scenarios.items():
        summary = slate_summary(slate)
        totals = per_title_totals(slate)
        summary["total_hours_delta_pct"] = (
            (summary["total_hours"] - base["total_hours"])
            / base["total_hours"] * 100)
        summary["peak_week_hours_delta_pct"] = (
            (summary["peak_week_hours"] - base["peak_week_hours"])
            / base["peak_week_hours"] * 100)
        out[name] = {
            "summary": summary,
            "per_title_hours": totals,
            "per_title_delta_hours": {
                t: totals[t] - base_totals[t] for t in totals},
        }
    return out
