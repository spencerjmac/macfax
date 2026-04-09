"""
NBA Ratings Configuration — macfax NBA app

All constants in this file are PROVISIONAL until validated by backtesting.
Run `python manage.py nba_backtest_ratings` (Phase 3) to derive data-driven values.

Key differences from NCAA config:
  - prior_games is much smaller (5 vs ~15) because 82 games provides far more signal
  - home_court_adj is estimated lower than NCAA (2.5 vs ~3.2)
  - B2B penalty is real in the NBA due to travel and condensed schedule
  - FFI weights are NOT ported from NCAA — they need NBA-specific backtesting
"""

# ─────────────────────────────────────────────────────────────────────────────
# Iterative adjusted-ratings config
# ─────────────────────────────────────────────────────────────────────────────

NBA_RATINGS_CONFIG = {
    # Solver settings
    "iterations": 8,
    "convergence_threshold": 0.001,
    # Shrinkage toward league average.
    # Small because 82-game schedule provides strong signal (NCAA uses ~15).
    "prior_games": 5.0,
    # League-average priors — update at season start from actual league averages.
    # 2025-26 approximate values.
    "prior_ortg": 115.0,
    "prior_drtg": 115.0,
    # Context adjustments — PROVISIONAL, estimated from recent NBA data.
    # Positive = helps the home/rested team's offense.
    "home_court_adj": 2.5,
    # Bonus per extra day of rest (beyond 1 day), capped at 3 days.
    "rest_adj_per_day": 0.4,
    # Shared penalty for both offense and defense on back-to-back nights.
    "b2b_penalty": 1.8,
    # Games to include: filter counts_toward_regular_season=True
    "season_type_filter": "regular",
    "_note": (
        "PROVISIONAL — all adjustments estimated, not backtested. "
        "Run nba_backtest_ratings (Phase 3) to derive data-driven coefficients."
    ),
}

# ─────────────────────────────────────────────────────────────────────────────
# Four Factor Index weights — PROVISIONAL
# ─────────────────────────────────────────────────────────────────────────────

NBA_FFI_WEIGHTS = {
    # Using the same weights as the NCAA formula until NBA-specific backtesting is run.
    # NCAA weights: eFG 47%, TOV 24%, REB 21%, FTR 8%  (Oliver's original coefficients).
    "efg_margin": 0.47,
    "tov_edge": 0.24,
    "oreb_edge": 0.21,
    "fta_margin": 0.08,
    # Scale: FFI_100 = clamp(50 + 20 * FFI_z, 0, 100)  — same as NCAA formula.
    "scale_midpoint": 50.0,
    "scale_multiplier": 20.0,
    "_note": (
        "Using NCAA weights/scale until NBA-specific backtesting (nba_backtest_ffi) is run."
    ),
}

# ─────────────────────────────────────────────────────────────────────────────
# Pace normalization
# ─────────────────────────────────────────────────────────────────────────────

NBA_PACE_CONFIG = {
    # NBA pace is possessions per 48 minutes (not per 40 like NCAA).
    "minutes_per_game": 48,
    # Historical NBA pace band for context/visualization thresholds.
    # Tight band — update each season from actual league data.
    "pace_low_threshold": 96.0,
    "pace_high_threshold": 104.0,
    "pace_league_avg": 99.5,  # approximate 2025-26
}

# ─────────────────────────────────────────────────────────────────────────────
# Season ingestion config
# ─────────────────────────────────────────────────────────────────────────────

NBA_INGEST_CONFIG = {
    # Minimum seconds between nba_api calls to respect rate limits.
    "api_call_sleep_seconds": 0.6,
    # How many seasons to backfill (Phase 3 backtesting needs ~10-15 seasons).
    "backfill_default_start_year": 2016,
    "backfill_default_end_year": 2025,
    # nba_api endpoint families used in Phase 2.
    # PlayByPlayV3 / GameRotation / LeagueDashLineups come in Phase 4.
    "phase2_endpoints": [
        "LeagueGameLog",
        "TeamGameLog",
        "BoxScoreTraditionalV3",
        "CommonTeamRoster",
        "CommonAllPlayers",
    ],
}
