"""
Backtest: evaluate the National Champion Checklist (Crystal Ball) — current
15-item checklist (post-bugfix) vs a candidate 14-item list — against every
D1 team-season, 2005-2026 (skip 2020, no tournament).

Reports, for both "current" and "candidate":
  - per-criterion champion pass-rate (with names of any misses)
  - per-criterion field pass-rate (% of all D1 team-seasons passing)
  - per-criterion tournament-team pass-rate
  - overall passedCount distribution for champions / all D1 / tournament teams
  - a before/after spotlight table for 5 known historical near-misses
    (Florida 2007, Duke 2015, Villanova 2016, Baylor 2021, Kansas 2022)

Candidate changes vs current 15:
  DROP: Balanced Dominance, Elite AdjEM, 3-Point %  (3 removed)
  MODIFY: Title Favorite -> AdjEM rank <= 22 (was gap-from-max <= 6.0)
          Elite Efficiency -> Def rank <= 35 (was <= 45)
          FT% -> Z >= -0.50 (was -0.28)
          WAB -> > 5.0, with games_played < 27 treated as an exception
                 (mirrors the UConn-rule treatment of short/anomalous seasons)
  ADD: Strength of Schedule (sos_rank <= 33)
       No Glaring Weakness (worst of 8 adjusted four-factor ranks <= --weakness-rank)

  15 - 3 + 2 = 14 candidate criteria.

Usage:
    python manage.py backtest_checklist
    python manage.py backtest_checklist --weakness-rank 150
"""

import csv
import os
from collections import defaultdict

import numpy as np
from django.conf import settings
from django.core.management.base import BaseCommand

from ncaa.models import Season, TeamSeasonRatings, TeamSeasonMetrics
from api.crystal_ball_views import (
    _build_season_context,
    _item,
    CHECKS as CURRENT_CHECKS,
    _check_trapezoid,
    _check_win_pct,
    _check_ap_poll,
    _check_efg_margin,
    _check_ftr_margin,
    _check_reb_edge,
    _check_tov_edge,
    _check_ffi,
)

SEASONS = [y for y in range(2005, 2027) if y != 2020]

OUTPUT_DIR = os.path.join(settings.BASE_DIR, "backtest_output")

# Known historical near-misses, with the criteria they're spotlighted on.
SPOTLIGHT = [
    (2007, "Florida", ["ft_pct"]),
    (2015, "Duke", ["title_favorite", "ft_pct"]),
    (2016, "Villanova", ["rebounding_edge"]),
    (2021, "Baylor", ["title_favorite", "wab", "sos"]),
    (2022, "Kansas", ["title_favorite"]),
]


# ---------------------------------------------------------------------------
# Candidate checklist criteria
# ---------------------------------------------------------------------------

def _check_title_favorite_v2(r, ctx):
    rank = ctx.get("em_ranks", {}).get(r.team_id)
    if rank is None:
        return _item("title_favorite", "Title Favorite (AdjEM Top-22)", False,
                      "N/A", "Rank <= 22")
    passed = rank <= 22
    return _item("title_favorite", "Title Favorite (AdjEM Top-22)", passed,
                  f"#{rank}", "Rank <= 22", f"AdjEM rank #{rank}")


def _check_elite_efficiency_v2(r, ctx):
    off_rank = ctx.get("off_ranks", {}).get(r.team_id)
    def_rank = ctx.get("def_ranks", {}).get(r.team_id)
    if off_rank is None or def_rank is None:
        return _item("elite_efficiency", "Elite Efficiency", False,
                      "N/A", "Off Rank <= 16, Def Rank <= 35")
    passed = off_rank <= 16 and def_rank <= 35
    return _item("elite_efficiency", "Elite Efficiency", passed,
                  f"Off: #{off_rank} / Def: #{def_rank}",
                  "Off Rank <= 16, Def Rank <= 35",
                  f"Offensive rank #{off_rank}, Defensive rank #{def_rank}")


def _check_ft_pct_v2(r, ctx):
    stats = ctx.get("stats", {})
    metrics = ctx.get("metrics_map", {}).get(r.team_id)
    MIN_Z_FT = -0.50

    ft_mean = stats.get("ft_pct_mean", 0.70)
    ft_std = stats.get("ft_pct_std", 0.03)
    threshold = ft_mean + (MIN_Z_FT * ft_std)

    ft_pct = None
    if metrics and metrics.total_fta:
        ft_pct = metrics.total_ftm / metrics.total_fta

    if ft_pct is None:
        return _item("ft_pct", "Free Throw %", False,
                      "N/A", f">= {threshold * 100:.1f}%", "FT% data unavailable")

    ft_z = (ft_pct - ft_mean) / ft_std if ft_std else 0
    passed = ft_z >= MIN_Z_FT
    return _item("ft_pct", "Free Throw %", passed,
                  f"{ft_pct * 100:.1f}%", f">= {threshold * 100:.1f}%",
                  f"FT%: {ft_pct * 100:.1f}% (Z: {ft_z:.2f})")


def _check_wab_v2(r, ctx):
    wab = r.wab
    games = r.games_played or 0

    if games < 27:
        return _item("wab", "WAB (Wins Above Bubble)", True,
                      f"{wab:.1f}" if wab is not None else "N/A",
                      "> 5 (or <27-game season exception)",
                      f"Short season ({games} games) - exempted, WAB={wab}")

    if wab is None:
        return _item("wab", "WAB (Wins Above Bubble)", False,
                      "N/A", "> 5", "WAB unavailable")

    passed = wab > 5.0
    return _item("wab", "WAB (Wins Above Bubble)", passed,
                  f"{wab:.1f}", "> 5", f"WAB: {wab:.1f}")


def _check_sos(r, ctx):
    rank = r.sos_rank
    if rank is None:
        return _item("sos", "Strength of Schedule", False,
                      "N/A", "Rank <= 33", "SOS rank unavailable")
    passed = rank <= 33
    return _item("sos", "Strength of Schedule", passed,
                  f"#{rank}", "Rank <= 33", f"SOS rank #{rank}")


def _make_no_glaring_weakness_check(weakness_rank):
    def _check(r, ctx):
        ranks = ctx.get("extra_ranks", {}).get(r.team_id)
        if not ranks:
            return _item("no_glaring_weakness", "No Glaring Weakness", False,
                          "N/A", f"All 8 factor ranks <= {weakness_rank}")
        worst_stat = max(ranks, key=ranks.get)
        worst_rank = ranks[worst_stat]
        passed = worst_rank <= weakness_rank
        return _item("no_glaring_weakness", "No Glaring Weakness", passed,
                      f"Worst: {worst_stat} #{worst_rank}",
                      f"All 8 factor ranks <= {weakness_rank}",
                      "Ranks: " + ", ".join(f"{k}#{v}" for k, v in ranks.items()))
    return _check


CANDIDATE_KEYS_ORDER = [
    "trapezoid", "title_favorite", "win_pct", "elite_efficiency",
    "ap_poll_week6", "efg_margin", "ftr_margin", "rebounding_edge",
    "turnover_edge", "four_factor_index", "wab", "ft_pct", "sos",
    "no_glaring_weakness",
]

CURRENT_KEYS_ORDER = [
    "trapezoid", "balanced_dominance", "title_favorite", "win_pct",
    "elite_efficiency", "three_point_pct", "elite_adjem", "ap_poll_week6",
    "efg_margin", "ftr_margin", "rebounding_edge", "turnover_edge",
    "four_factor_index", "wab", "ft_pct",
]


# ---------------------------------------------------------------------------
# Data loading & per-season context
# ---------------------------------------------------------------------------

def _rank_map(ratings, value_fn, descending):
    sorted_r = sorted(ratings, key=value_fn, reverse=descending)
    return {r.team_id: idx + 1 for idx, r in enumerate(sorted_r)}


def _build_extra_ranks(ratings):
    """Per-team ranks for the 8 adjusted four-factor components used by
    the 'No Glaring Weakness' candidate check. rank 1 = best in D1."""
    rank_maps = {
        "efg_off": _rank_map(ratings, lambda r: r.adj_efg_pct, True),       # higher better
        "tov_off": _rank_map(ratings, lambda r: r.adj_tov_pct, False),      # lower better
        "orb": _rank_map(ratings, lambda r: r.adj_orb_pct, True),           # higher better
        "ftr_off": _rank_map(ratings, lambda r: r.adj_ftr, True),           # higher better
        "efg_def": _rank_map(ratings, lambda r: r.adj_opp_efg_pct, False),  # lower better
        "tov_def": _rank_map(ratings, lambda r: r.adj_opp_tov_pct, True),   # higher better
        "drb": _rank_map(ratings, lambda r: r.adj_drb_pct, True),           # higher better
        "ftr_def": _rank_map(ratings, lambda r: r.adj_opp_ftr, False),      # lower better
    }
    return {
        r.team_id: {stat: rank_maps[stat][r.team_id] for stat in rank_maps}
        for r in ratings
    }


def load_season_data():
    data = {}
    for year in SEASONS:
        season = Season.objects.filter(year=year).first()
        if not season:
            continue
        ratings = list(
            TeamSeasonRatings.all_objects
            .filter(season=season, team__is_d1=True, games_played__gt=0, is_pre_tournament=True)
            .select_related("team")
        )
        if not ratings:
            continue
        metrics_qs = TeamSeasonMetrics.all_objects.filter(season=season, is_pre_tournament=True)
        metrics_map = {m.team_id: m for m in metrics_qs}
        data[year] = (ratings, metrics_map)
    return data


def _run(rating, ctx, checks):
    items = [fn(rating, ctx) for fn in checks]
    passed = sum(1 for i in items if i["pass"])
    return {
        "passedCount": passed,
        "totalCount": len(items),
        "score": round(passed / len(items) * 100, 1),
        "items": {i["key"]: i for i in items},
    }


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------

class Command(BaseCommand):
    help = "Backtest the National Champion Checklist: current 15 vs candidate 14"

    def add_arguments(self, parser):
        parser.add_argument(
            "--weakness-rank", type=int, default=180,
            help="Rank threshold (out of ~360 D1 teams) for the 'No Glaring Weakness' "
                 "candidate criterion. Default 180 (top half of D1).",
        )

    def handle(self, *args, **options):
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        weakness_rank = options["weakness_rank"]
        no_glaring_weakness = _make_no_glaring_weakness_check(weakness_rank)

        candidate_checks = [
            _check_trapezoid,
            _check_title_favorite_v2,
            _check_win_pct,
            _check_elite_efficiency_v2,
            _check_ap_poll,
            _check_efg_margin,
            _check_ftr_margin,
            _check_reb_edge,
            _check_tov_edge,
            _check_ffi,
            _check_wab_v2,
            _check_ft_pct_v2,
            _check_sos,
            no_glaring_weakness,
        ]

        self.stdout.write(f"Loading season data ({SEASONS[0]}-{SEASONS[-1]}, skip 2020)...")
        data_by_season = load_season_data()
        self.stdout.write(f"Loaded {len(data_by_season)} seasons.\n")

        # Aggregation buckets, keyed by (mode, criterion_key)
        stats = {
            "current": defaultdict(lambda: {
                "champ_pass": 0, "champ_total": 0, "champ_misses": [],
                "field_pass": 0, "field_total": 0,
                "tourney_pass": 0, "tourney_total": 0,
            }),
            "candidate": defaultdict(lambda: {
                "champ_pass": 0, "champ_total": 0, "champ_misses": [],
                "field_pass": 0, "field_total": 0,
                "tourney_pass": 0, "tourney_total": 0,
            }),
        }
        labels = {"current": {}, "candidate": {}}
        passcounts = {
            "current": {"champ": [], "field": [], "tourney": []},
            "candidate": {"champ": [], "field": [], "tourney": []},
        }
        spotlight_results = {}
        csv_rows = []

        for year, (ratings, metrics_map) in data_by_season.items():
            ctx = _build_season_context(ratings, metrics_map)
            if not ctx:
                continue
            ctx["metrics_map"] = metrics_map
            ctx["extra_ranks"] = _build_extra_ranks(ratings)

            champ = next((r for r in ratings if r.tournament_finish == "Champ"), None)

            for r in ratings:
                cur = _run(r, ctx, CURRENT_CHECKS)
                cand = _run(r, ctx, candidate_checks)

                is_champ = champ is not None and r.team_id == champ.team_id
                is_tourney = r.tournament_seed is not None

                for mode, result, key_order in (
                    ("current", cur, CURRENT_KEYS_ORDER),
                    ("candidate", cand, CANDIDATE_KEYS_ORDER),
                ):
                    for key in key_order:
                        item = result["items"][key]
                        labels[mode].setdefault(key, item["label"])
                        s = stats[mode][key]
                        s["field_total"] += 1
                        if item["pass"]:
                            s["field_pass"] += 1
                        if is_tourney:
                            s["tourney_total"] += 1
                            if item["pass"]:
                                s["tourney_pass"] += 1
                        if is_champ:
                            s["champ_total"] += 1
                            if item["pass"]:
                                s["champ_pass"] += 1
                            else:
                                s["champ_misses"].append((year, r.team.name))

                passcounts["current"]["field"].append(cur["passedCount"])
                passcounts["candidate"]["field"].append(cand["passedCount"])
                if is_tourney:
                    passcounts["current"]["tourney"].append(cur["passedCount"])
                    passcounts["candidate"]["tourney"].append(cand["passedCount"])
                if is_champ:
                    passcounts["current"]["champ"].append(cur["passedCount"])
                    passcounts["candidate"]["champ"].append(cand["passedCount"])

                csv_row = {
                    "season": year,
                    "team": r.team.name,
                    "tournament_finish": r.tournament_finish or "",
                    "tournament_seed": r.tournament_seed,
                    "current_passed": cur["passedCount"],
                    "current_total": cur["totalCount"],
                    "candidate_passed": cand["passedCount"],
                    "candidate_total": cand["totalCount"],
                }
                for key in CURRENT_KEYS_ORDER:
                    csv_row[f"cur_{key}"] = cur["items"][key]["pass"]
                for key in CANDIDATE_KEYS_ORDER:
                    csv_row[f"cand_{key}"] = cand["items"][key]["pass"]
                csv_rows.append(csv_row)

                for spot_year, spot_team, _ in SPOTLIGHT:
                    if year == spot_year and r.team.name == spot_team:
                        spotlight_results[(year, spot_team)] = (cur, cand)

        # ---- CSV output ----
        out_path = os.path.join(OUTPUT_DIR, "checklist_backtest.csv")
        with open(out_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(csv_rows[0].keys()))
            writer.writeheader()
            writer.writerows(csv_rows)
        self.stdout.write(f"Wrote {len(csv_rows)} rows to {out_path}\n")

        # ---- Per-criterion tables ----
        self._print_criterion_table("CURRENT (15 criteria, post-bugfix)",
                                      CURRENT_KEYS_ORDER, labels["current"], stats["current"])
        self._print_criterion_table(
            f"CANDIDATE (14 criteria, weakness-rank<={weakness_rank})",
            CANDIDATE_KEYS_ORDER, labels["candidate"], stats["candidate"])

        # ---- passedCount distributions ----
        self.stdout.write("\n=== passedCount distribution ===")
        for mode, total in (("current", 15), ("candidate", 14)):
            self.stdout.write(f"\n{mode.upper()} (out of {total}):")
            for bucket in ("champ", "field", "tourney"):
                vals = passcounts[mode][bucket]
                if not vals:
                    continue
                arr = np.array(vals)
                self.stdout.write(
                    f"  {bucket:<8}: n={len(arr):<5} mean={arr.mean():.2f} "
                    f"median={np.median(arr):.1f} min={arr.min()} max={arr.max()}"
                )

        # ---- Spotlight before/after ----
        self.stdout.write("\n=== Spotlight: known historical near-misses ===")
        for year, team, keys in SPOTLIGHT:
            res = spotlight_results.get((year, team))
            if res is None:
                self.stdout.write(f"  {year} {team}: not found in data")
                continue
            cur, cand = res
            self.stdout.write(
                f"\n  {year} {team}: current {cur['passedCount']}/{cur['totalCount']}, "
                f"candidate {cand['passedCount']}/{cand['totalCount']}"
            )
            for key in keys:
                cur_item = cur["items"].get(key)
                cand_item = cand["items"].get(key)
                cur_str = f"{'PASS' if cur_item['pass'] else 'FAIL'} ({cur_item['value']} vs {cur_item['threshold']})" if cur_item else "n/a (not in current 15)"
                cand_str = f"{'PASS' if cand_item['pass'] else 'FAIL'} ({cand_item['value']} vs {cand_item['threshold']})" if cand_item else "n/a (not in candidate 14)"
                self.stdout.write(f"    {key:<20} current: {cur_str:<40} candidate: {cand_str}")

    # ------------------------------------------------------------------ #

    def _print_criterion_table(self, title, key_order, label_map, stats_by_key):
        self.stdout.write(f"\n=== {title} ===")
        for key in key_order:
            s = stats_by_key[key]
            label = label_map.get(key, key)
            champ_pct = (s["champ_pass"] / s["champ_total"] * 100) if s["champ_total"] else float("nan")
            field_pct = (s["field_pass"] / s["field_total"] * 100) if s["field_total"] else float("nan")
            tourney_pct = (s["tourney_pass"] / s["tourney_total"] * 100) if s["tourney_total"] else float("nan")
            line = (
                f"  {label:<32} Champ: {s['champ_pass']:>2}/{s['champ_total']:<3} ({champ_pct:5.1f}%)"
                f"  Field: {field_pct:5.1f}%  Tourney: {tourney_pct:5.1f}%"
            )
            self.stdout.write(line)
            if s["champ_misses"]:
                misses = ", ".join(f"{y} {t}" for y, t in s["champ_misses"])
                self.stdout.write(f"    {'misses:':<32} {misses}")
