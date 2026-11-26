"""Tests for the scenario engine."""
import pandas as pd

from src import scenarios


def _slate():
    m = 1_000_000
    return {
        "Alpha": [(pd.Timestamp("2025-03-02"), 100.0 * m),
                  (pd.Timestamp("2025-03-09"), 60.0 * m),
                  (pd.Timestamp("2025-03-16"), 36.0 * m)],
        "Beta": [(pd.Timestamp("2025-03-09"), 80.0 * m),
                 (pd.Timestamp("2025-03-16"), 40.0 * m)],
        "Gamma": [(pd.Timestamp("2025-03-23"), 50.0 * m)],
    }


def test_weekly_totals():
    totals = scenarios.weekly_totals(_slate())
    by_week = dict(zip(totals["week"].astype(str), totals["total_hours"]))
    assert by_week["2025-03-02"] == 100_000_000.0
    assert by_week["2025-03-09"] == 140_000_000.0
    assert by_week["2025-03-16"] == 76_000_000.0
    assert by_week["2025-03-23"] == 50_000_000.0


def test_delay_preserves_total_when_no_new_collision():
    slate = _slate()
    # Gamma moves +1 week to 2025-03-30: no other title active there.
    new = scenarios.delay_title(slate, "Gamma", 1)
    assert scenarios.per_title_totals(new)["Gamma"] == 50_000_000.0
    assert scenarios.slate_summary(new)["total_hours"] == \
        scenarios.slate_summary(slate)["total_hours"]


def test_delay_applies_collision_penalty_only_on_new_weeks():
    slate = _slate()
    # Beta moves -1 week to 2025-03-02: its new week Mar 2 has Alpha active
    # (new collision, 5% off Beta's 80). Its Mar 9 week was already shared
    # with Alpha in baseline, so no penalty there.
    new = scenarios.delay_title(slate, "Beta", -1)
    beta = dict(new["Beta"])
    assert abs(beta[pd.Timestamp("2025-03-02")] - 80_000_000.0 * 0.95) < 1e-3
    assert beta[pd.Timestamp("2025-03-09")] == 40_000_000.0
    base_total = scenarios.slate_summary(slate)["total_hours"]
    new_total = scenarios.slate_summary(new)["total_hours"]
    assert abs((base_total - new_total) - 4_000_000.0) < 1e-3


def test_budget_shift_scales_whole_runs():
    slate = _slate()
    new = scenarios.budget_shift(slate, donor="Gamma", recipient="Alpha",
                                 pct=0.10)
    assert scenarios.per_title_totals(new)["Alpha"] == 196_000_000.0 * 1.10
    assert scenarios.per_title_totals(new)["Gamma"] == 50_000_000.0 * 0.90
    assert scenarios.per_title_totals(new)["Beta"] == 120_000_000.0


def test_budget_shift_rejects_same_title():
    import pytest
    with pytest.raises(ValueError):
        scenarios.budget_shift(_slate(), donor="Alpha", recipient="Alpha")


def test_build_scenarios_keys_and_rules():
    slate = _slate()
    scen, meta = scenarios.build_scenarios(slate)
    assert set(scen) == {"baseline", "tentpole_slips_4w",
                         "tentpoles_collide", "budget_shift_to_tentpole"}
    # biggest total is Alpha (196) -> delayed 4 weeks
    assert scen["tentpole_slips_4w"]["Alpha"][0][0] == pd.Timestamp(
        "2025-03-30")
    # tentpoles: Alpha peak 100, Beta peak 80 (>= 10); closest pair is
    # Alpha (Mar 2) / Beta (Mar 9): Beta moves -1 week to Mar 2
    assert scen["tentpoles_collide"]["Beta"][0][0] == pd.Timestamp(
        "2025-03-02")
    # budget shift: smallest peak is Gamma (50) -> Alpha
    assert scenarios.per_title_totals(
        scen["budget_shift_to_tentpole"])["Alpha"] == 196_000_000.0 * 1.10
    comp = scenarios.compare_scenarios(scen)
    assert comp["baseline"]["summary"]["total_hours_delta_pct"] == 0.0
    assert "tentpole" in meta["tentpoles_collide"].lower() or \
        "Beta" in meta["tentpoles_collide"]
