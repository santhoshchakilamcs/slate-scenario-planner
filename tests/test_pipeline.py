"""Tests for the pipeline: normalization, run detection, slate rules."""
import pandas as pd

from src import pipeline


def test_normalize_title():
    assert pipeline.normalize_title("KPop Demon Hunters") == "kpop demon hunters"
    assert pipeline.normalize_title("The Boss Baby: Family Business") == \
        "the boss baby family business"
    assert pipeline.normalize_title("  Wallace & Gromit! ") == "wallace gromit"


def _weekly(rows):
    """rows: list of (title, week_str, hours)."""
    return pd.DataFrame(
        [{"show_title": t, "week": pd.Timestamp(w), "weekly_hours_viewed": h,
          "category": "Films (English)"} for t, w, h in rows])


def test_add_runs_splits_on_gap():
    df = _weekly([
        ("A", "2025-01-05", 10), ("A", "2025-01-12", 8),
        ("A", "2025-03-02", 5), ("A", "2025-03-09", 4),
        ("B", "2025-01-05", 7),
    ])
    out = pipeline.add_runs(df)
    a = out[out["show_title"] == "A"].sort_values("week")
    assert list(a["run_id"]) == [1, 1, 2, 2]
    assert list(a["week_index"]) == [0, 1, 0, 1]


def test_first_runs_keeps_release_run_only():
    df = _weekly([
        ("A", "2025-01-05", 10), ("A", "2025-01-12", 8),
        ("A", "2025-03-02", 5),
    ])
    first = pipeline.first_runs(df)
    assert len(first) == 2
    assert first["week"].max() == pd.Timestamp("2025-01-12")


def test_animated_films_filter():
    meta = pd.DataFrame([
        {"titleType": "movie", "genres": "Action,Animation,Comedy"},
        {"titleType": "movie", "genres": "Drama"},
        {"titleType": "tvSeries", "genres": "Animation,Drama"},
    ])
    out = pipeline.animated_films(meta)
    assert len(out) == 1
    assert out.iloc[0]["genres"] == "Action,Animation,Comedy"


def test_build_slate_excludes_catalogue_reentries():
    meta = pd.DataFrame([
        {"netflix_title": "New Film", "titleType": "movie",
         "genres": "Animation", "startYear": 2025},
        {"netflix_title": "Old Film", "titleType": "movie",
         "genres": "Animation", "startYear": 2007},
        {"netflix_title": "Live Film", "titleType": "movie",
         "genres": "Comedy", "startYear": 2025},
    ])
    df = _weekly([
        ("New Film", "2025-06-01", 10), ("New Film", "2025-06-08", 6),
        ("Old Film", "2025-06-01", 9),
        ("Live Film", "2025-06-01", 9),
    ])
    slate = pipeline.build_slate(df, meta)
    assert list(slate["show_title"]) == ["New Film"]
    assert slate.iloc[0]["run_total"] == 16
