"""Data pipeline: load, clean, join, and build the animation slate.

Sources (all public):
- Netflix Top 10 global weekly data, official file from
  https://www.netflix.com/tudum/top10/data/all-weeks-global.tsv
  (columns: week, category, weekly_rank, show_title, season_title,
  weekly_hours_viewed, runtime, weekly_views, cumulative_weeks_in_top_10).
- IMDb public datasets (https://datasets.imdbws.com/): title.basics.tsv.gz
  and title.ratings.tsv.gz, used only for titleType / genres / startYear /
  averageRating / numVotes, matched on normalized primaryTitle.

A title's *run* is a maximal run of consecutive weeks in the Top 10
(gap > 7 days starts a new run). The *first run* is the release run:
catalogue titles re-enter the Top 10 repeatedly, so only the first run
is used for trajectories, forecasting, and scenarios.
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"

NETFLIX_TSV = RAW_DIR / "all-weeks-global.tsv"
IMDB_BASICS = RAW_DIR / "title.basics.tsv.gz"
IMDB_RATINGS = RAW_DIR / "title.ratings.tsv.gz"

FULL_METADATA = PROCESSED_DIR / "imdb_metadata.csv"
ANIMATED_WEEKLY = PROCESSED_DIR / "animated_films_weekly.csv"
PROVENANCE = PROCESSED_DIR / "provenance.json"

CATEGORIES_FILM = ("Films (English)", "Films (Non-English)")


def normalize_title(title: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    t = str(title).lower()
    t = re.sub(r"[^a-z0-9]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def load_netflix(path: Path = NETFLIX_TSV) -> pd.DataFrame:
    df = pd.read_csv(path, sep="\t")
    df["week"] = pd.to_datetime(df["week"])
    df["weekly_hours_viewed"] = pd.to_numeric(
        df["weekly_hours_viewed"], errors="coerce")
    df = df.dropna(subset=["week", "show_title", "weekly_hours_viewed"])
    df = df.sort_values(["show_title", "week"]).reset_index(drop=True)
    return df


def extract_imdb_metadata(netflix_titles, basics_path=IMDB_BASICS,
                          ratings_path=IMDB_RATINGS) -> pd.DataFrame:
    """Stream IMDb basics/ratings, keep rows matching a Netflix title.

    Matching is on normalized primaryTitle. When several IMDb rows match
    one Netflix title, prefer movie > tvSeries > tvMiniSeries > tvSpecial
    > tvMovie > video, then earliest startYear. Returns one row per
    matched Netflix title with genre / year / rating info.
    """
    norm_to_title = {}
    for t in sorted(set(netflix_titles)):
        norm_to_title.setdefault(normalize_title(t), t)
    keep_cols = ["tconst", "titleType", "primaryTitle", "originalTitle",
                 "startYear", "genres"]
    matches = []
    for chunk in pd.read_csv(basics_path, sep="\t", compression="gzip",
                             usecols=keep_cols, dtype=str, chunksize=500_000,
                             na_filter=False):
        chunk["norm"] = chunk["primaryTitle"].map(normalize_title)
        hit = chunk[chunk["norm"].isin(norm_to_title)]
        if not hit.empty:
            hit = hit.assign(netflix_title=hit["norm"].map(norm_to_title))
            matches.append(hit.drop(columns=["norm"]))
    meta = (pd.concat(matches, ignore_index=True) if matches
            else pd.DataFrame(columns=keep_cols + ["netflix_title"]))
    pref = {"movie": 0, "tvSeries": 1, "tvMiniSeries": 2, "tvSpecial": 3,
            "tvMovie": 4, "video": 5}
    meta["pref"] = meta["titleType"].map(pref).fillna(9)
    meta["startYear"] = pd.to_numeric(meta["startYear"], errors="coerce")
    meta = meta.sort_values(["netflix_title", "pref", "startYear"])
    meta = meta.drop_duplicates(subset=["netflix_title"], keep="first")
    ratings = pd.read_csv(ratings_path, sep="\t", compression="gzip",
                          dtype=str)
    ratings = ratings[ratings["tconst"].isin(set(meta["tconst"]))]
    meta = meta.merge(ratings, on="tconst", how="left")
    meta = meta.drop(columns=["pref"])
    return meta.reset_index(drop=True)


def add_runs(df: pd.DataFrame) -> pd.DataFrame:
    """Mark consecutive-week runs per title (gap > 7 days starts a new run)."""
    df = df.sort_values(["show_title", "week"]).copy()
    df["prev_week"] = df.groupby("show_title")["week"].shift(1)
    gap = (df["week"] - df["prev_week"]).dt.days
    df["new_run"] = gap.isna() | (gap > 7)
    df["run_id"] = df.groupby("show_title")["new_run"].cumsum()
    df["week_index"] = df.groupby(["show_title", "run_id"]).cumcount()
    return df.drop(columns=["prev_week"])


def first_runs(df: pd.DataFrame) -> pd.DataFrame:
    """First (release) run per title, with week_index 0..n-1."""
    df = add_runs(df)
    return df[df["run_id"] == 1].copy()


def animated_films(metadata: pd.DataFrame) -> pd.DataFrame:
    """IMDb-matched titles that are movies with Animation in genres."""
    m = metadata[(metadata["titleType"] == "movie")
                 & metadata["genres"].str.contains("Animation", na=False)]
    return m.reset_index(drop=True)


def build_slate(netflix: pd.DataFrame, metadata: pd.DataFrame,
                start: str = "2025-01-01", max_year_gap: int = 1
                ) -> pd.DataFrame:
    """The scenario slate: animated films whose first run started on/after
    `start` and whose IMDb startYear is within `max_year_gap` years before
    the first Top 10 week.

    The year-gap rule separates new-to-Netflix releases from catalogue
    titles re-entering the Top 10 years after release (e.g. Bee Movie,
    first Top 10 week 2025 but released 2007).
    """
    anim = animated_films(metadata)
    films = netflix[netflix["category"].isin(CATEGORIES_FILM)
                    & netflix["show_title"].isin(set(anim["netflix_title"]))]
    films = films.merge(anim[["netflix_title", "startYear"]],
                        left_on="show_title", right_on="netflix_title",
                        how="left")
    runs = first_runs(films)
    summary = runs.groupby("show_title").agg(
        first_week=("week", "min"), run_weeks=("week", "nunique"),
        run_total=("weekly_hours_viewed", "sum"),
        peak_hours=("weekly_hours_viewed", "max"),
        startYear=("startYear", "first")).reset_index()
    summary["year_gap"] = (summary["first_week"].dt.year
                           - summary["startYear"])
    slate = summary[(summary["first_week"] >= pd.Timestamp(start))
                    & (summary["year_gap"] >= 0)
                    & (summary["year_gap"] <= max_year_gap)]
    return slate.sort_values("first_week").reset_index(drop=True)


def eval_titles(netflix: pd.DataFrame, metadata: pd.DataFrame,
                min_run_weeks: int = 4) -> pd.DataFrame:
    """Animated films whose first run has at least `min_run_weeks` weeks:
    the one-step-ahead forecast evaluation set."""
    anim = animated_films(metadata)
    films = netflix[netflix["category"].isin(CATEGORIES_FILM)
                    & netflix["show_title"].isin(set(anim["netflix_title"]))]
    runs = first_runs(films)
    counts = runs.groupby("show_title")["week"].nunique()
    keep = set(counts[counts >= min_run_weeks].index)
    return runs[runs["show_title"].isin(keep)].reset_index(drop=True)


def load_processed():
    """Load the committed processed files (no big downloads needed)."""
    import json
    meta = pd.read_csv(FULL_METADATA)
    weekly = pd.read_csv(ANIMATED_WEEKLY, parse_dates=["week"])
    provenance = json.loads(PROVENANCE.read_text())
    return meta, weekly, provenance
