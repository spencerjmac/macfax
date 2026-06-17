"""
Backtest: derive Efficiency Landscape tier-line thresholds (Champion /
Contender / Playoff) for the NBA from 10 seasons (2016-2025) of our own
NBATeamSeasonRatings, using playoff_finish/conference_seed filled in by
nba_sync_playoff_results.

Tests both gap-based (max_net - DELTA) and rank-based (adj_net of the Nth
ranked team) formulations for the Champion and Contender lines, and checks
adj_net=0 as the Playoff line. Reports champion/finalist capture rates so the
final constants are picked empirically rather than guessed.

Usage:
    python manage.py backtest_nba_landscape
"""

import csv
import os
from collections import Counter

from django.conf import settings
from django.core.management.base import BaseCommand

from nba.models import NBATeamSeasonRatings

SEASONS = list(range(2016, 2026))

OUTPUT_DIR = os.path.join(settings.BASE_DIR, "backtest_output")

CHAMPION_GAP_GRID = [3, 4, 5, 6, 8]
CONTENDER_GAP_GRID = [8, 10, 12, 14]
CHAMPION_RANK_GRID = [3, 4, 5, 6]
CONTENDER_RANK_GRID = [6, 8, 10]

FINALS_FINISHES = {"Champion", "Runner-Up"}


def load_season_data():
    data_by_season = {}
    for year in SEASONS:
        rows = list(
            NBATeamSeasonRatings.objects.filter(
                season__year=year, season_type="regular",
            ).values("team__abbreviation", "adj_net", "playoff_finish")
        )
        rows.sort(key=lambda r: r["adj_net"], reverse=True)
        data_by_season[year] = rows
    return data_by_season


def _evaluate(data_by_season, champion_line_fn, contender_line_fn):
    """
    champion_line_fn(rows) -> float, contender_line_fn(rows) -> float.
    Returns capture-rate + tier-size metrics across all seasons.
    """
    champ_hits = champ_total = 0
    finals_hits = finals_total = 0
    above_champ_counts, above_contender_counts = [], []

    for rows in data_by_season.values():
        champion_line = champion_line_fn(rows)
        contender_line = contender_line_fn(rows)

        above_champ = sum(1 for r in rows if r["adj_net"] >= champion_line)
        above_contender = sum(
            1 for r in rows if contender_line <= r["adj_net"] < champion_line
        )
        above_champ_counts.append(above_champ)
        above_contender_counts.append(above_contender)

        for r in rows:
            if r["playoff_finish"] == "Champion":
                champ_total += 1
                if r["adj_net"] >= champion_line:
                    champ_hits += 1
            if r["playoff_finish"] in FINALS_FINISHES:
                finals_total += 1
                if r["adj_net"] >= contender_line:
                    finals_hits += 1

    return {
        "champ_capture": champ_hits / champ_total,
        "finals_capture": finals_hits / finals_total,
        "avg_above_champion": sum(above_champ_counts) / len(above_champ_counts),
        "avg_above_contender": sum(above_contender_counts) / len(above_contender_counts),
    }


def evaluate_gap(data_by_season, champ_delta, contender_delta):
    return _evaluate(
        data_by_season,
        champion_line_fn=lambda rows: rows[0]["adj_net"] - champ_delta,
        contender_line_fn=lambda rows: rows[0]["adj_net"] - contender_delta,
    )


def evaluate_rank(data_by_season, champ_rank, contender_rank):
    return _evaluate(
        data_by_season,
        champion_line_fn=lambda rows: rows[champ_rank - 1]["adj_net"],
        contender_line_fn=lambda rows: rows[contender_rank - 1]["adj_net"],
    )


def evaluate_playoff_line(data_by_season):
    below_zero = Counter()
    above_zero = Counter()
    for rows in data_by_season.values():
        for r in rows:
            finish = r["playoff_finish"] or "Missed"
            bucket = below_zero if r["adj_net"] < 0 else above_zero
            bucket[finish] += 1
    return below_zero, above_zero


class Command(BaseCommand):
    help = "Backtest Efficiency Landscape Champion/Contender/Playoff tier-line thresholds for NBA"

    def handle(self, *args, **options):
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        self.stdout.write(f"Loading {len(SEASONS)} seasons of NBATeamSeasonRatings (2016-2025)...")
        data_by_season = load_season_data()

        for year, rows in data_by_season.items():
            if len(rows) != 30:
                self.stdout.write(self.style.WARNING(
                    f"  {year}: expected 30 teams, got {len(rows)}"
                ))

        rows_out = []

        self.stdout.write("\n=== Gap-based (max_net - DELTA) ===")
        self.stdout.write(
            f"{'ChampΔ':<8}{'ContΔ':<8}{'ChampCap':<10}{'FinalsCap':<11}"
            f"{'AvgChamp#':<11}{'AvgCont#'}"
        )
        for champ_delta in CHAMPION_GAP_GRID:
            for contender_delta in CONTENDER_GAP_GRID:
                if contender_delta <= champ_delta:
                    continue
                m = evaluate_gap(data_by_season, champ_delta, contender_delta)
                self.stdout.write(
                    f"{champ_delta:<8}{contender_delta:<8}{m['champ_capture']:<10.0%}"
                    f"{m['finals_capture']:<11.0%}{m['avg_above_champion']:<11.2f}"
                    f"{m['avg_above_contender']:.2f}"
                )
                rows_out.append({
                    "method": "gap", "champion_param": champ_delta,
                    "contender_param": contender_delta, **m,
                })

        self.stdout.write("\n=== Rank-based (adj_net of Nth-ranked team) ===")
        self.stdout.write(
            f"{'ChampN':<8}{'ContN':<8}{'ChampCap':<10}{'FinalsCap':<11}"
            f"{'AvgChamp#':<11}{'AvgCont#'}"
        )
        for champ_rank in CHAMPION_RANK_GRID:
            for contender_rank in CONTENDER_RANK_GRID:
                if contender_rank <= champ_rank:
                    continue
                m = evaluate_rank(data_by_season, champ_rank, contender_rank)
                self.stdout.write(
                    f"{champ_rank:<8}{contender_rank:<8}{m['champ_capture']:<10.0%}"
                    f"{m['finals_capture']:<11.0%}{m['avg_above_champion']:<11.2f}"
                    f"{m['avg_above_contender']:.2f}"
                )
                rows_out.append({
                    "method": "rank", "champion_param": champ_rank,
                    "contender_param": contender_rank, **m,
                })

        out_path = os.path.join(OUTPUT_DIR, "nba_landscape_backtest.csv")
        with open(out_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "method", "champion_param", "contender_param",
                "champ_capture", "finals_capture",
                "avg_above_champion", "avg_above_contender",
            ])
            writer.writeheader()
            writer.writerows(rows_out)
        self.stdout.write(f"\nWrote {len(rows_out)} configs to {out_path}")

        self.stdout.write("\n=== Playoff line (adj_net = 0) ===")
        below_zero, above_zero = evaluate_playoff_line(data_by_season)
        self.stdout.write("adj_net < 0:")
        for finish, count in sorted(below_zero.items(), key=lambda kv: -kv[1]):
            self.stdout.write(f"  {finish:<14}: {count}")
        self.stdout.write("adj_net >= 0:")
        for finish, count in sorted(above_zero.items(), key=lambda kv: -kv[1]):
            self.stdout.write(f"  {finish:<14}: {count}")

        below_total = sum(below_zero.values())
        below_missed_or_r1 = below_zero.get("Missed", 0) + below_zero.get("Round 1", 0)
        above_total = sum(above_zero.values())
        above_made_playoffs = above_total - above_zero.get("Missed", 0)
        self.stdout.write(
            f"\n{below_missed_or_r1}/{below_total} ({below_missed_or_r1/below_total:.0%}) of "
            f"adj_net<0 teams missed playoffs or lost Round 1"
        )
        self.stdout.write(
            f"{above_made_playoffs}/{above_total} ({above_made_playoffs/above_total:.0%}) of "
            f"adj_net>=0 teams made the playoffs"
        )
