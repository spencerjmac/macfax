"""
NBA Ratings Configuration — macfax NBA app

Constants derived from 11-season backtest (2016–2026) via nba_eval_model.
Run `python manage.py nba_eval_model --season YYYY` to regenerate NBAModelCalibration.

Key differences from NCAA config:
  - prior_games is much smaller (5 vs ~15) because 82 games provides far more signal
  - home_court_adj lower than NCAA (2.1 vs ~3.2) — empirical 11-season avg
  - B2B penalty is real in the NBA due to travel and condensed schedule
  - FFI weights derived from NBA data — diverge from Oliver's original NCAA coefficients
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
    # Context adjustments — empirical 11-season averages (2016–2026) from nba_eval_model.
    # Positive = helps the home/rested team's offense.
    # 2021 COVID bubble (HCA=0.50) excluded from HCA average; included in B2B.
    "home_court_adj": 2.1,
    # Bonus per extra day of rest (beyond 1 day), capped at 3 days.
    "rest_adj_per_day": 0.4,
    # Shared penalty for both offense and defense on back-to-back nights.
    # Empirical: home_b2b ≈ -1.8, away_b2b ≈ +2.4; using midpoint 2.1.
    "b2b_penalty": 2.1,
    # Games to include: filter counts_toward_regular_season=True
    "season_type_filter": "regular",
}

# ─────────────────────────────────────────────────────────────────────────────
# Four Factor Index weights — PROVISIONAL
# ─────────────────────────────────────────────────────────────────────────────

NBA_FFI_WEIGHTS = {
    # Empirical weights from 11-season OLS backtest (2016–2026) via nba_eval_model.
    # TOV is substantially more predictive than Oliver's NCAA formula; OREB less so.
    # Avg proposed weights across seasons: eFG=0.484, TOV=0.342, OREB=0.121, FTA=0.053
    "efg_margin": 0.48,
    "tov_edge": 0.34,
    "oreb_edge": 0.12,
    "fta_margin": 0.06,
    # Scale: FFI_100 = clamp(50 + 20 * FFI_z, 0, 100)  — same as NCAA formula.
    "scale_midpoint": 50.0,
    "scale_multiplier": 20.0,
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
