"""
build_elo — compute Elo ratings for all 48 2026 FIFA World Cup teams.

Downloads ~154 years of international match data from the martj42 dataset,
runs a chronological Elo calculation, and writes WorldCupTeam records.

Usage:
    uv run python manage.py build_elo
    uv run python manage.py build_elo --refresh   # re-fetch CSV from source
"""

import json
import logging
import os
import urllib.request
from datetime import date
from pathlib import Path

import pandas as pd
from django.core.management.base import BaseCommand

from world_cup.elo_match_model import win_expectancy
from world_cup.models import WorldCupTeam

logger = logging.getLogger(__name__)

RESULTS_CSV_URL = "https://raw.githubusercontent.com/martj42/international_results/master/results.csv"
SHOOTOUTS_CSV_URL = "https://raw.githubusercontent.com/martj42/international_results/master/shootouts.csv"
DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
CACHE_PATH = DATA_DIR / "results_cache.csv"
SHOOTOUTS_CACHE_PATH = DATA_DIR / "shootouts_cache.csv"
TEAMS_PATH = DATA_DIR / "teams.json"

WC_GROUP_STAGE_END: dict[int, date] = {
    1990: date(1990, 6, 21),
    1994: date(1994, 6, 28),
    1998: date(1998, 6, 26),
    2002: date(2002, 6, 14),
    2006: date(2006, 6, 23),
    2010: date(2010, 6, 25),
    2014: date(2014, 6, 26),
    2018: date(2018, 6, 28),
    2022: date(2022, 12,  2),
    2026: date(2026, 6, 27),
}

# eloratings.net pre-tournament reference values (for validation output)
VALIDATION_BENCHMARKS = {
    "Spain":       2155,
    "Argentina":   2113,
    "France":      2062,
    "England":     2020,
    "Brazil":      1988,
    "Portugal":    1984,
    "Colombia":    1977,
    "Netherlands": 1944,
    "Germany":     1925,
}

# 2026 World Cup co-hosts (USA, Canada, Mexico) play their group-stage matches
# on home soil with full home-crowd support. Layer a flat Elo bonus onto their
# base rating to reflect that advantage in the rankings/insights.
HOST_ELO_BONUS = 100.0

# Alternative dataset names to try for teams with name changes or aliases
DATASET_ALIASES = {
    "DR Congo": ["DR Congo", "Congo DR", "Democratic Republic of Congo"],
    "Ivory Coast": ["Ivory Coast", "Côte d'Ivoire", "Cote d'Ivoire"],
    "Curacao": ["Curacao", "Curaçao"],
}


def get_k_factor(tournament: str, match_date=None) -> float:
    t = tournament.lower().strip()

    if "fifa world cup" in t and "qualif" not in t and "qualifying" not in t:
        if match_date is not None:
            year = match_date.year
            cutoff = WC_GROUP_STAGE_END.get(year)
            if cutoff is not None:
                return 50.0 if match_date.date() <= cutoff else 60.0
        return 50.0

    if any(x in t for x in [
        "uefa european championship",
        "uefa euro ",
        "copa america",
        "africa cup of nations",
        "afc asian cup",
        "concacaf gold cup",
        "gold cup",
        "afcon",
    ]) and "qualif" not in t and "qualifying" not in t:
        return 40.0

    if "nations league" in t:
        return 30.0

    if any(x in t for x in ["qualif", "qualifying", "qualification"]):
        return 25.0

    return 20.0


def goal_diff_multiplier(goal_diff: int) -> float:
    if goal_diff <= 1:
        return 1.0
    elif goal_diff == 2:
        return 1.5
    elif goal_diff == 3:
        return 1.75
    else:
        return 1.75 + (goal_diff - 3) / 8.0


def run_elo_calculation(
    matches_df: pd.DataFrame,
    pso_winners: dict[tuple, str] | None = None,
) -> dict:
    ratings: dict[str, float] = {}

    for _, row in matches_df.sort_values("date").iterrows():
        home = row["home_team"]
        away = row["away_team"]
        home_score = int(row["home_score"])
        away_score = int(row["away_score"])
        tournament = str(row["tournament"])
        is_neutral = str(row["neutral"]).upper() == "TRUE"

        if home not in ratings:
            ratings[home] = 1500.0
        if away not in ratings:
            ratings[away] = 1500.0

        home_adv = 0.0 if is_neutral else 100.0

        we_home = win_expectancy(ratings[home], ratings[away], home_adv)
        we_away = 1.0 - we_home

        if home_score > away_score:
            w_home, w_away = 1.0, 0.0
        elif home_score < away_score:
            w_home, w_away = 0.0, 1.0
        else:
            w_home, w_away = 0.5, 0.5

        if pso_winners:
            pso_key = (str(row["date"].date()), home, away)
            pso_winner = pso_winners.get(pso_key)
            if pso_winner is not None:
                if pso_winner == home:
                    w_home, w_away = 0.75, 0.5
                elif pso_winner == away:
                    w_home, w_away = 0.5, 0.75

        K = get_k_factor(tournament, match_date=row["date"])
        G = goal_diff_multiplier(abs(home_score - away_score))

        ratings[home] = ratings[home] + K * G * (w_home - we_home)
        ratings[away] = ratings[away] + K * G * (w_away - we_away)

    return ratings


class Command(BaseCommand):
    help = "Compute Elo ratings for 2026 World Cup teams and write to DB."

    def add_arguments(self, parser):
        parser.add_argument(
            "--refresh",
            action="store_true",
            help="Re-fetch results CSV from GitHub (ignores cache)",
        )

    def handle(self, *args, **options):
        refresh = options["refresh"]

        # ── 1. Fetch / load CSV ──────────────────────────────────────────────
        if refresh or not CACHE_PATH.exists():
            self.stdout.write("Fetching results CSV from GitHub...")
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            urllib.request.urlretrieve(RESULTS_CSV_URL, CACHE_PATH)
            self.stdout.write(f"  Saved to {CACHE_PATH}")
        else:
            self.stdout.write(f"Using cached CSV at {CACHE_PATH}")

        df = pd.read_csv(CACHE_PATH)
        df["date"] = pd.to_datetime(df["date"])
        before = len(df)
        df = df.dropna(subset=["home_score", "away_score", "home_team", "away_team"])
        dropped = before - len(df)
        if dropped:
            self.stdout.write(f"  Dropped {dropped} rows with missing scores")

        # ── 1b. Fetch / load shootouts CSV ───────────────────────────────────
        if refresh or not SHOOTOUTS_CACHE_PATH.exists():
            self.stdout.write("Fetching shootouts CSV from GitHub...")
            urllib.request.urlretrieve(SHOOTOUTS_CSV_URL, SHOOTOUTS_CACHE_PATH)
            self.stdout.write(f"  Saved to {SHOOTOUTS_CACHE_PATH}")
        else:
            self.stdout.write(f"Using cached shootouts CSV at {SHOOTOUTS_CACHE_PATH}")

        shootouts_df = pd.read_csv(SHOOTOUTS_CACHE_PATH)
        shootouts_df["date"] = pd.to_datetime(shootouts_df["date"])

        pso_winners: dict[tuple, str] = {}
        for _, srow in shootouts_df.iterrows():
            key = (str(srow["date"].date()), srow["home_team"], srow["away_team"])
            pso_winners[key] = srow["winner"]

        self.stdout.write(f"  Loaded {len(df):,} matches, {len(shootouts_df):,} PSO records")

        # ── 2. Compute Elo ───────────────────────────────────────────────────
        self.stdout.write("Computing Elo ratings...")
        ratings = run_elo_calculation(df, pso_winners=pso_winners)
        self.stdout.write(f"  Computed ratings for {len(ratings):,} teams")

        # ── 3. Inspect CSV names for alias teams ─────────────────────────────
        all_csv_teams = set(df["home_team"].unique()) | set(df["away_team"].unique())

        def lookup_rating(dataset_name: str) -> tuple[float, str | None]:
            """Return (rating, actual_name_found) or (1500.0, None) on miss."""
            aliases = DATASET_ALIASES.get(dataset_name, [dataset_name])
            for alias in aliases:
                if alias in ratings:
                    return ratings[alias], alias
            return 1500.0, None

        # ── 4. Load teams.json ───────────────────────────────────────────────
        with open(TEAMS_PATH) as f:
            teams_config = json.load(f)

        # ── 5. Build ranked list ─────────────────────────────────────────────
        team_elos = []
        for team in teams_config:
            elo, found_as = lookup_rating(team["dataset_name"])
            if found_as is None:
                self.stderr.write(
                    self.style.WARNING(
                        f"  WARNING: '{team['dataset_name']}' not found in CSV "
                        f"(tried: {DATASET_ALIASES.get(team['dataset_name'], [team['dataset_name']])}). "
                        f"Using 1500 fallback."
                    )
                )
            if team.get("is_host"):
                elo += HOST_ELO_BONUS

            team_elos.append({**team, "elo_rating": elo, "found_as": found_as})

        team_elos.sort(key=lambda t: t["elo_rating"], reverse=True)
        for i, team in enumerate(team_elos, start=1):
            team["elo_rank"] = i
            team["elo_vs_fifa"] = team["fifa_rank"] - i

        # ── 6. Write to DB ───────────────────────────────────────────────────
        self.stdout.write("Writing to database...")
        for team in team_elos:
            WorldCupTeam.objects.update_or_create(
                name=team["name"],
                defaults={
                    "dataset_name": team["dataset_name"],
                    "confederation": team["confederation"],
                    "group": team["group"],
                    "is_host": team["is_host"],
                    "flag_emoji": team.get("flag_emoji", ""),
                    "fifa_rank": team["fifa_rank"],
                    "fifa_points": team.get("fifa_points", 0.0),
                    "elo_rating": round(team["elo_rating"], 1),
                    "elo_rank": team["elo_rank"],
                    "elo_vs_fifa": team["elo_vs_fifa"],
                },
            )
        self.stdout.write(self.style.SUCCESS(f"  Wrote {len(team_elos)} teams to DB"))

        # ── 7. Validation output ─────────────────────────────────────────────
        self.stdout.write("\nValidation against eloratings.net (pre-tournament snapshot):")
        self.stdout.write(f"{'Team':<20} {'Macfax Elo':>12} {'eloratings.net':>15} {'Delta':>8}")
        self.stdout.write("-" * 60)

        elo_by_name = {t["name"]: t["elo_rating"] for t in team_elos}
        any_large_delta = False
        for team_name, ref_elo in VALIDATION_BENCHMARKS.items():
            macfax_elo = elo_by_name.get(team_name)
            if macfax_elo is None:
                self.stdout.write(f"{'  ' + team_name:<20} {'N/A':>12} {ref_elo:>15} {'?':>8}")
                continue
            delta = macfax_elo - ref_elo
            flag = " ⚠️" if abs(delta) > 100 else ""
            self.stdout.write(
                f"{'  ' + team_name:<20} {macfax_elo:>12.1f} {ref_elo:>15} {delta:>+8.1f}{flag}"
            )
            if abs(delta) > 100:
                any_large_delta = True

        if any_large_delta:
            self.stderr.write(
                self.style.WARNING(
                    "\nWARNING: One or more top-10 teams deviate >100 points from eloratings.net reference. "
                    "Check formula or dataset."
                )
            )
        else:
            self.stdout.write(self.style.SUCCESS("\nAll top-10 teams within acceptable range of reference values."))

        # ── 8. Quick preview of top 10 ───────────────────────────────────────
        self.stdout.write("\nTop 10 by Elo:")
        self.stdout.write(f"{'Rank':<6} {'Team':<25} {'Elo':>8} {'FIFA':>6} {'Δ':>6}")
        self.stdout.write("-" * 55)
        for team in team_elos[:10]:
            delta_str = f"{team['elo_vs_fifa']:+d}"
            self.stdout.write(
                f"  {team['elo_rank']:<4} {team['name']:<25} {team['elo_rating']:>8.1f} "
                f"{team['fifa_rank']:>6} {delta_str:>6}"
            )
