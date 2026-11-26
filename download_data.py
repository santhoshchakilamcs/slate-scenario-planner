"""Download the public sources and build the committed processed files.

Sources:
- Netflix Top 10 global weekly data (official):
  https://www.netflix.com/tudum/top10/data/all-weeks-global.tsv
- IMDb public datasets:
  https://datasets.imdbws.com/title.basics.tsv.gz
  https://datasets.imdbws.com/title.ratings.tsv.gz

Outputs (committed, under ~1 MB total):
- data/processed/imdb_metadata.csv: IMDb metadata for all Netflix Top 10
  titles matched (titleType, genres, startYear, averageRating, numVotes).
- data/processed/animated_films_weekly.csv: first-run weekly rows for all
  IMDb-matched animated movies (week, category, show_title,
  weekly_hours_viewed, weekly_rank, cumulative_weeks_in_top_10).
- data/processed/provenance.json: download-time facts (source URLs,
  row counts, week range, match rate, file hashes).

Raw downloads live in data/raw/ (gitignored).
Run: python download_data.py [--force]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
from pathlib import Path

import pandas as pd

from src import pipeline

NETFLIX_URL = "https://www.netflix.com/tudum/top10/data/all-weeks-global.tsv"
IMDB_BASICS_URL = "https://datasets.imdbws.com/title.basics.tsv.gz"
IMDB_RATINGS_URL = "https://datasets.imdbws.com/title.ratings.tsv.gz"


def _download(url: str, dest: Path, force: bool = False) -> None:
    if dest.exists() and not force:
        print(f"exists, skipping: {dest}")
        return
    print(f"downloading {url} -> {dest}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=600) as r, open(dest, "wb") as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
    print(f"  {dest.stat().st_size:,} bytes, sha256 "
          f"{hashlib.sha256(dest.read_bytes()).hexdigest()[:16]}...")


def main(force: bool = False) -> None:
    pipeline.RAW_DIR.mkdir(parents=True, exist_ok=True)
    pipeline.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    _download(NETFLIX_URL, pipeline.NETFLIX_TSV, force)
    _download(IMDB_BASICS_URL, pipeline.IMDB_BASICS, force)
    _download(IMDB_RATINGS_URL, pipeline.IMDB_RATINGS, force)

    netflix = pipeline.load_netflix()
    print(f"Netflix rows: {len(netflix):,}; weeks "
          f"{netflix['week'].min().date()}..{netflix['week'].max().date()}; "
          f"unique titles: {netflix['show_title'].nunique():,}")
    meta = pipeline.extract_imdb_metadata(netflix["show_title"].unique())
    match_rate = len(meta) / netflix["show_title"].nunique() * 100
    print(f"IMDb matched titles: {len(meta):,} ({match_rate:.1f}% of "
          f"{netflix['show_title'].nunique():,} Netflix titles)")
    meta.to_csv(pipeline.FULL_METADATA, index=False)

    anim = pipeline.animated_films(meta)
    print(f"animated movies matched: {len(anim)}")

    films = netflix[netflix["category"].isin(pipeline.CATEGORIES_FILM)
                    & netflix["show_title"].isin(set(anim["netflix_title"]))]
    first = pipeline.first_runs(films)
    first = first[["week", "category", "show_title", "season_title",
                   "weekly_rank", "weekly_hours_viewed", "runtime",
                   "weekly_views", "cumulative_weeks_in_top_10"]]
    first.to_csv(pipeline.ANIMATED_WEEKLY, index=False)
    print(f"animated-film first-run weekly rows: {len(first):,} "
          f"({first['show_title'].nunique()} titles)")

    provenance = {
        "netflix_source": NETFLIX_URL,
        "netflix_sha256": hashlib.sha256(
            pipeline.NETFLIX_TSV.read_bytes()).hexdigest(),
        "netflix_rows": int(len(netflix)),
        "netflix_weeks": (f"{netflix['week'].min().date()} to "
                          f"{netflix['week'].max().date()}"),
        "netflix_unique_titles": int(netflix["show_title"].nunique()),
        "imdb_sources": [IMDB_BASICS_URL, IMDB_RATINGS_URL],
        "imdb_matched_titles": int(len(meta)),
        "imdb_match_rate_pct": round(match_rate, 1),
        "animated_movies_matched": int(len(anim)),
        "animated_film_first_run_rows": int(len(first)),
        "download_date": "2026-11-26",
    }
    pipeline.PROVENANCE.write_text(json.dumps(provenance, indent=2))
    print(f"committed: {pipeline.FULL_METADATA} "
          f"({pipeline.FULL_METADATA.stat().st_size:,} bytes), "
          f"{pipeline.ANIMATED_WEEKLY} "
          f"({pipeline.ANIMATED_WEEKLY.stat().st_size:,} bytes), "
          f"{pipeline.PROVENANCE}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    main(force=args.force)
