"""
Backtest: derive thresholds for the 10-item NBA Crystal Ball Championship
Checklist from 10 seasons (2016-2025, 300 team-seasons) of our own
NBATeamSeasonRatings + playoff_finish/conference_seed
(from nba_sync_playoff_results) + NBAPlayerSeasonStats.bpr (2022+ only).

For each of the 10 criteria, sweeps a grid of candidate thresholds and
reports champion pass-rate (x/10, with named misses) and field pass-rate
(% of 300 team-seasons). Selection rule: maximize champion capture, then
minimize field pass-rate among ties (best discrimination). If the max
capture is < 8/10, the misses are reported as accepted outliers.

Final combined run wires the selected thresholds into the real
nba_crystal_ball_views.CHECKS-equivalent and reports the passedCount
distribution for champions vs. the field.

Usage:
    python manage.py backtest_nba_checklist
"""

import csv
import os

import numpy as np
from django.conf import settings
from django.core.management.base import BaseCommand

from nba.models import NBASeason, NBATeamSeasonRatings, NBAPlayerSeasonStats
from api.checklist_utils import _item
from api.nba_crystal_ball_views import _build_nba_season_context

SEASONS = list(range(2016, 2026))

OUTPUT_DIR = os.path.join(settings.BASE_DIR, "backtest_output")

KNOWN_CHAMPIONS = {
    2016: "CLE", 2017: "GSW", 2018: "GSW", 2019: "TOR", 2020: "LAL",
    2021: "MIL", 2022: "GSW", 2023: "DEN", 2024: "BOS", 2025: "OKC",
}


# ---------------------------------------------------------------------------
# Candidate-threshold check factories
# ---------------------------------------------------------------------------

def _make_net_rating_rank(n):
    def _check(r, ctx):
        rank = ctx.get("net_ranks", {}).get(r.team_id)
        if rank is None:
            return _item("net_rating_rank", "Net Rating Top-N", False, "N/A", f"Rank ≤ {n}")
        passed = rank <= n
        return _item("net_rating_rank", "Net Rating Top-N", passed, f"#{rank}", f"Rank ≤ {n}")
    return _check


def _make_net_rating_z(min_z):
    def _check(r, ctx):
        stats = ctx.get("stats", {})
        mean = stats.get("adj_net_mean", 0.0)
        std = stats.get("adj_net_std", 1.0)
        if r.adj_net is None:
            return _item("net_rating_z", "Elite Net Rating", False, "N/A", f"Z ≥ {min_z}")
        z = (r.adj_net - mean) / std if std else 0
        passed = z >= min_z
        return _item("net_rating_z", "Elite Net Rating", passed, f"{z:.2f}", f"Z ≥ {min_z}")
    return _check


def _make_top_conference_seed(n):
    def _check(r, ctx):
        seed = ctx.get("conf_seeds", {}).get(r.team_id)
        if seed is None:
            return _item("top_conference_seed", "Top Conference Seed", False, "N/A", f"Seed ≤ {n}")
        passed = seed <= n
        return _item("top_conference_seed", "Top Conference Seed", passed, f"#{seed}", f"Seed ≤ {n}")
    return _check


def _make_elite_offense(n):
    def _check(r, ctx):
        rank = ctx.get("off_ranks", {}).get(r.team_id)
        if rank is None:
            return _item("elite_offense", "Elite Offense", False, "N/A", f"Rank ≤ {n}")
        passed = rank <= n
        return _item("elite_offense", "Elite Offense", passed, f"#{rank}", f"Rank ≤ {n}")
    return _check


def _make_elite_defense(n):
    def _check(r, ctx):
        rank = ctx.get("def_ranks", {}).get(r.team_id)
        if rank is None:
            return _item("elite_defense", "Elite Defense", False, "N/A", f"Rank ≤ {n}")
        passed = rank <= n
        return _item("elite_defense", "Elite Defense", passed, f"#{rank}", f"Rank ≤ {n}")
    return _check


def _make_ffi_z(min_z):
    def _check(r, ctx):
        stats = ctx.get("stats", {})
        mean = stats.get("ffi_mean", 0.0)
        std = stats.get("ffi_std", 1.0)
        if r.ffi is None:
            return _item("ffi_z", "Four Factor Index", False, "N/A", f"Z ≥ {min_z}")
        z = (r.ffi - mean) / std if std else 0
        passed = z >= min_z
        return _item("ffi_z", "Four Factor Index", passed, f"{z:.2f}", f"Z ≥ {min_z}")
    return _check


def _make_efg_margin_z(min_z):
    def _check(r, ctx):
        stats = ctx.get("stats", {})
        mean = stats.get("efg_margin_mean", 0.0)
        std = stats.get("efg_margin_std", 1.0)
        if r.efg_margin is None:
            return _item("efg_margin_z", "eFG Margin", False, "N/A", f"Z ≥ {min_z}")
        z = (r.efg_margin - mean) / std if std else 0
        passed = z >= min_z
        return _item("efg_margin_z", "eFG Margin", passed, f"{z:.2f}", f"Z ≥ {min_z}")
    return _check


def _make_tov_edge_z(min_z):
    def _check(r, ctx):
        stats = ctx.get("stats", {})
        mean = stats.get("tov_edge_mean", 0.0)
        std = stats.get("tov_edge_std", 1.0)
        if r.tov_edge is None:
            return _item("tov_edge_z", "Turnover Edge", False, "N/A", f"Z ≥ {min_z}")
        z = (r.tov_edge - mean) / std if std else 0
        passed = z >= min_z
        return _item("tov_edge_z", "Turnover Edge", passed, f"{z:.2f}", f"Z ≥ {min_z}")
    return _check


def _make_no_glaring_weakness(n):
    def _check(r, ctx):
        factors = ctx.get("factor_ranks", {}).get(r.team_id)
        if not factors:
            return _item("no_glaring_weakness", "No Glaring Weakness", False, "N/A", f"Worst rank ≤ {n}")
        worst_rank = max(factors.values())
        passed = worst_rank <= n
        return _item("no_glaring_weakness", "No Glaring Weakness", passed, f"#{worst_rank}", f"Worst rank ≤ {n}")
    return _check


def _make_star_player(min_bpr):
    def _check(r, ctx):
        season_year = ctx.get("season_year")
        if season_year is not None and season_year < 2022:
            return _item("star_player", "Star Player Impact", True, "N/A", f"≥ {min_bpr} (exempt before 2022)")
        best = ctx.get("team_max_bpr", {}).get(r.team_id)
        if best is None:
            return _item("star_player", "Star Player Impact", False, "N/A", f"≥ {min_bpr}")
        passed = best >= min_bpr
        return _item("star_player", "Star Player Impact", passed, f"{best:.1f}", f"≥ {min_bpr}")
    return _check


# ---------------------------------------------------------------------------
# Criteria definitions: key, label, factory, candidate grid
# ---------------------------------------------------------------------------

CRITERIA = [
    ("net_rating_rank",    "Net Rating Top-N",     _make_net_rating_rank,    [3, 4, 5, 6, 7, 8]),
    ("net_rating_z",       "Elite Net Rating",     _make_net_rating_z,       [0.75, 1.0, 1.25, 1.5, 1.75, 2.0]),
    ("top_conference_seed", "Top Conference Seed", _make_top_conference_seed, [1, 2, 3, 4]),
    ("elite_offense",      "Elite Offense",        _make_elite_offense,      [5, 6, 8, 10, 12, 15]),
    ("elite_defense",      "Elite Defense",        _make_elite_defense,      [5, 8, 10, 12, 15, 18, 20]),
    ("ffi_z",              "Four Factor Index",    _make_ffi_z,              [0.5, 0.75, 1.0, 1.25, 1.5]),
    ("efg_margin_z",       "eFG Margin",           _make_efg_margin_z,       [0.25, 0.5, 0.75, 1.0, 1.25]),
    ("tov_edge_z",         "Turnover Edge",        _make_tov_edge_z,         [-0.5, -0.25, 0, 0.25, 0.5]),
    ("no_glaring_weakness", "No Glaring Weakness", _make_no_glaring_weakness, [15, 18, 20, 22, 25]),
    ("star_player",        "Star Player Impact",   _make_star_player,        [4, 5, 6, 7, 8]),
]


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_season_data():
    data = {}
    for year in SEASONS:
        season = NBASeason.objects.filter(year=year).first()
        if not season:
            continue
        ratings = list(
            NBATeamSeasonRatings.objects.filter(
                season=season, season_type="regular", adj_net__isnull=False,
            ).select_related("team")
        )
        if len(ratings) != 30:
            print(f"  WARNING: {year} has {len(ratings)} rated teams (expected 30)")
        player_stats_qs = None
        if year >= 2022:
            player_stats_qs = NBAPlayerSeasonStats.objects.filter(
                season=season, season_type="regular", bpr__isnull=False,
            )
        ctx = _build_nba_season_context(ratings, year, player_stats_qs)
        champ = next((r for r in ratings if r.playoff_finish == "Champion"), None)
        data[year] = (ratings, ctx, champ)
    return data


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------

class Command(BaseCommand):
    help = "Backtest NBA Crystal Ball checklist thresholds (10 criteria, 2016-2025)"

    def handle(self, *args, **options):
        os.makedirs(OUTPUT_DIR, exist_ok=True)

        self.stdout.write(f"Loading {len(SEASONS)} seasons of NBATeamSeasonRatings (2016-2025)...")
        data_by_season = load_season_data()
        self.stdout.write(f"Loaded {len(data_by_season)} seasons.\n")

        sweep_rows = []
        selected = {}  # key -> (threshold, check_fn, champ_pass, champ_total, field_pass_rate)

        for key, label, factory, grid in CRITERIA:
            self.stdout.write(f"=== {label} ({key}) ===")
            self.stdout.write(f"{'Threshold':<12}{'ChampPass':<12}{'FieldPass%':<12}Misses")

            best = None  # (champ_pass, -field_pass_rate, threshold) for selection
            for threshold in grid:
                check_fn = factory(threshold)
                champ_pass = 0
                champ_misses = []
                field_pass = 0
                field_total = 0
                for year, (ratings, ctx, champ) in data_by_season.items():
                    for r in ratings:
                        item = check_fn(r, ctx)
                        field_total += 1
                        if item["pass"]:
                            field_pass += 1
                        if champ is not None and r.team_id == champ.team_id:
                            if item["pass"]:
                                champ_pass += 1
                            else:
                                champ_misses.append((year, r.team.abbreviation))

                field_pass_rate = field_pass / field_total if field_total else 0.0
                champ_total = len(data_by_season)

                self.stdout.write(
                    f"{threshold!s:<12}{champ_pass}/{champ_total:<9}{field_pass_rate * 100:<12.1f}"
                    + (", ".join(f"{y} {t}" for y, t in champ_misses) if champ_misses else "")
                )

                sweep_rows.append({
                    "criterion": key,
                    "threshold": threshold,
                    "champ_pass": champ_pass,
                    "champ_total": champ_total,
                    "champ_misses": "; ".join(f"{y} {t}" for y, t in champ_misses),
                    "field_pass": field_pass,
                    "field_total": field_total,
                    "field_pass_rate": round(field_pass_rate, 4),
                })

                # Selection: maximize champ_pass, then minimize field_pass_rate
                candidate = (champ_pass, -field_pass_rate, threshold)
                if best is None or candidate[:2] > best[:2]:
                    best = candidate
                    selected[key] = (threshold, check_fn, champ_pass, champ_total, field_pass_rate, champ_misses)

            chosen = selected[key]
            self.stdout.write(self.style.SUCCESS(
                f"  -> selected {chosen[0]} (champ {chosen[2]}/{chosen[3]}, "
                f"field {chosen[4] * 100:.1f}%)"
            ))
            if chosen[2] < chosen[3]:
                misses = ", ".join(f"{y} {t}" for y, t in chosen[5])
                self.stdout.write(self.style.WARNING(f"  misses (accepted outliers): {misses}"))
            self.stdout.write("")

        # ---- threshold sweep CSV ----
        sweep_path = os.path.join(OUTPUT_DIR, "nba_checklist_threshold_sweep.csv")
        with open(sweep_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "criterion", "threshold", "champ_pass", "champ_total", "champ_misses",
                "field_pass", "field_total", "field_pass_rate",
            ])
            writer.writeheader()
            writer.writerows(sweep_rows)
        self.stdout.write(f"Wrote {len(sweep_rows)} rows to {sweep_path}\n")

        # ---- Final combined run ----
        self.stdout.write("=== Final combined run (selected thresholds) ===")
        final_checks = [(key, selected[key][1]) for key, _, _, _ in CRITERIA]

        backtest_rows = []
        champ_passcounts = []
        field_passcounts = []

        for year, (ratings, ctx, champ) in data_by_season.items():
            for r in ratings:
                items = {key: fn(r, ctx) for key, fn in final_checks}
                passed = sum(1 for i in items.values() if i["pass"])
                total = len(items)

                is_champ = champ is not None and r.team_id == champ.team_id
                field_passcounts.append(passed)
                if is_champ:
                    champ_passcounts.append(passed)

                row = {
                    "season": year,
                    "team": r.team.abbreviation,
                    "playoff_finish": r.playoff_finish or "",
                    "conference_seed": r.conference_seed,
                    "adj_net": round(r.adj_net, 2) if r.adj_net is not None else None,
                    "adj_off": round(r.adj_off, 2) if r.adj_off is not None else None,
                    "adj_def": round(r.adj_def, 2) if r.adj_def is not None else None,
                    "ffi": round(r.ffi, 2) if r.ffi is not None else None,
                    "passedCount": passed,
                    "totalCount": total,
                }
                for key, item in items.items():
                    row[key] = item["pass"]
                backtest_rows.append(row)

        backtest_path = os.path.join(OUTPUT_DIR, "nba_checklist_backtest.csv")
        with open(backtest_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(backtest_rows[0].keys()))
            writer.writeheader()
            writer.writerows(backtest_rows)
        self.stdout.write(f"Wrote {len(backtest_rows)} rows to {backtest_path}\n")

        champ_arr = np.array(champ_passcounts)
        field_arr = np.array(field_passcounts)
        self.stdout.write("\n=== passedCount distribution (out of 10) ===")
        self.stdout.write(
            f"  champions: n={len(champ_arr)} mean={champ_arr.mean():.2f} "
            f"median={np.median(champ_arr):.1f} min={champ_arr.min()} max={champ_arr.max()}"
        )
        self.stdout.write(
            f"  field:     n={len(field_arr)} mean={field_arr.mean():.2f} "
            f"median={np.median(field_arr):.1f} min={field_arr.min()} max={field_arr.max()}"
        )

        # ---- Selected thresholds summary ----
        self.stdout.write("\n=== Selected thresholds (for nba_crystal_ball_config.py) ===")
        for key, label, _, _ in CRITERIA:
            threshold, _, champ_pass, champ_total, field_pass_rate, _ = selected[key]
            self.stdout.write(
                f"  {key:<22} {threshold!s:<8} champ {champ_pass}/{champ_total}  field {field_pass_rate * 100:.1f}%"
            )
