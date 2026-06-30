"""
backtest_bpr_shrinkage_sweep — Test whether relaxing prior-SD shrinkage closes the
Macfax BPR vs EvanMiya gap in cross-season game prediction.

The EM bake-off (backtest_em_bakeoff) found Δ(bpr − em) RMSE = +0.834 with
Macfax β1=0.296 vs EM β1=0.952. The diagnostic: prior-SD shrinkage compresses
player coefficients too aggressively. Higher sd_scale → less shrinkage → wider
spread → higher β1. This sweep tests whether that closes Δ on HELD-OUT games.

ANTI-OVERFITTING: best multiplier is selected on TRAIN folds only. Verdict is
reported on the single held-out fold (most recent), untouched during selection.

Performance: uses bpr_from_state() — runs only fit_prior_informed_rapm (~10s)
instead of the full pipeline (~3 min) for each non-baseline multiplier.

Read-only. No DB writes.

Usage:
    python manage.py backtest_bpr_shrinkage_sweep
    python manage.py backtest_bpr_shrinkage_sweep --verbose
    python manage.py backtest_bpr_shrinkage_sweep --multipliers 1.0 2.0 4.0 6.0
"""
from __future__ import annotations

import math
from collections import defaultdict

import numpy as np
from django.core.management.base import BaseCommand

from ncaa.analytics.player_value.bpr.constants import (
    MIN_OFF_POSS_BPR,
    OBPR_PLAUSIBLE_RANGE,
)
from ncaa.analytics.player_value.bpr.evan_miya_reference import (
    load_em_ratings,
    normalize_team_name,
)
from ncaa.analytics.player_value.bpr.game_prediction import (
    _fit_ols,
    _metrics,
    _team_strength,
    predict_margin_and_prob,
)
from ncaa.analytics.player_value.bpr.pipeline import bpr_from_state, run_bpr_season
from ncaa.management.commands.backtest_bpr_margin import (
    _build_folds,
    _load_adj_em,
    _load_games,
    _load_player_data,
)
from ncaa.management.commands.backtest_em_bakeoff import _match_em_to_macfax
from ncaa.models import PlayerSeasonStats

DEFAULT_MULTIPLIERS = [0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0]
EM_MIN_POSS = 400
MIN_COV = 0.40


def _build_player_bpr_map_with_names(player_bpr_map: dict, train_year: int) -> list[dict]:
    """
    Join in-memory BPR values with PSS names/teams for EM matching.
    Returns list of dicts: player_id, player__display_name, team__name, bpr, box_bpr, off_poss
    """
    pss = {
        r["player_id"]: r
        for r in PlayerSeasonStats.objects.filter(
            season__year=train_year,
        ).values("player_id", "player__display_name", "team__name")
    }
    rows = []
    for pid, vals in player_bpr_map.items():
        meta = pss.get(pid)
        if not meta:
            continue
        rows.append({
            "player_id":           pid,
            "player__display_name": meta["player__display_name"],
            "team__name":          meta["team__name"],
            "bpr":                 vals["bpr"],
            "box_bpr":             vals["box_bpr"],
            "off_poss":            vals["off_poss"] or 0.0,
        })
    return rows


def _score_fold(
    player_bpr_map: dict,
    train_year: int,
    test_year: int,
    games_by_year: dict,
    team_roster: dict,
    adj_em_map: dict,
    em_records: list,
) -> dict | None:
    """
    Run the matched-universe EM bake-off for a single fold with in-memory BPR.
    Returns dict with bpr_rmse, em_rmse, delta, b1_bpr, b1_em, n_games.
    Returns None if insufficient data.
    """
    # Build macfax rows with names from PSS
    macfax_rows = _build_player_bpr_map_with_names(player_bpr_map, train_year)
    if not macfax_rows:
        return None

    matched, _ = _match_em_to_macfax(em_records, macfax_rows)
    if len(matched) < 50:
        return None

    # Build per-predictor rating dicts (matched universe only — same player_ids)
    macfax_pr = {
        (m["player_id"], train_year): {
            "bpr": m["macfax_bpr"], "box_bpr": m["macfax_box_bpr"],
            "off_poss": m["off_poss"],
            "baseline_obpr": None, "baseline_dbpr": None,
        }
        for m in matched
    }
    em_pr = {
        (m["player_id"], train_year): {
            "bpr": m["em_adj_bpr"], "box_bpr": None,
            "off_poss": m["off_poss"],
            "baseline_obpr": None, "baseline_dbpr": None,
        }
        for m in matched
    }

    train_games = games_by_year.get(train_year, [])
    test_games  = games_by_year.get(test_year, [])

    # Fit OLS per predictor on FULL train games (min_poss=0 — matched universe already filtered)
    b0m, b1m, b2m, sigm = _fit_ols(train_games, "bpr", train_year, macfax_pr, team_roster, adj_em_map, 0)
    b0e, b1e, b2e, sige = _fit_ols(train_games, "bpr", train_year, em_pr, team_roster, adj_em_map, 0)

    # Predict all test games (defer coverage filter)
    fold_mac, fold_em = {}, {}
    for g in test_games:
        gid = g["id"]
        hm, hcm = _team_strength(g["home_team_id"], train_year, test_year, "bpr", macfax_pr, team_roster, adj_em_map, 0)
        am, acm = _team_strength(g["away_team_id"], train_year, test_year, "bpr", macfax_pr, team_roster, adj_em_map, 0)
        he, hce = _team_strength(g["home_team_id"], train_year, test_year, "bpr", em_pr, team_roster, adj_em_map, 0)
        ae, ace = _team_strength(g["away_team_id"], train_year, test_year, "bpr", em_pr, team_roster, adj_em_map, 0)

        cov_m = min(hcm, acm)
        cov_e = min(hce, ace)
        actual = float(g["home_score"] - g["away_score"])

        pm, p_hm = predict_margin_and_prob(hm, am, bool(g["neutral_site"]), b0m, b1m, b2m, sigm)
        pe, p_he = predict_margin_and_prob(he, ae, bool(g["neutral_site"]), b0e, b1e, b2e, sige)

        fold_mac[gid] = {"pred": pm, "actual": actual, "p_home": p_hm,
                         "home_won": 1 if actual > 0 else 0, "coverage": cov_m}
        fold_em[gid]  = {"pred": pe, "actual": actual, "p_home": p_he,
                         "home_won": 1 if actual > 0 else 0, "coverage": cov_e}

    # Intersect: game passes if BOTH meet coverage threshold
    valid = {gid for gid in fold_mac if fold_mac[gid]["coverage"] >= MIN_COV
             and fold_em[gid]["coverage"] >= MIN_COV}

    res_mac = [fold_mac[gid] for gid in valid]
    res_em  = [fold_em[gid]  for gid in valid]

    if len(res_mac) < 50:
        return None

    mm = _metrics(res_mac)
    me = _metrics(res_em)
    return {
        "bpr_rmse": mm["rmse"], "em_rmse": me["rmse"],
        "delta": mm["rmse"] - me["rmse"],
        "bpr_wa": mm["win_acc"], "em_wa": me["win_acc"],
        "b1_bpr": b1m, "b1_em": b1e,
        "n_games": len(res_mac),
        "n_matched": len(matched),
    }


class Command(BaseCommand):
    help = "Shrinkage sweep: test whether less prior-SD shrinkage closes the BPR vs EM gap"

    def add_arguments(self, parser):
        parser.add_argument(
            "--multipliers", type=float, nargs="+", default=DEFAULT_MULTIPLIERS,
            help="SD scale multipliers to sweep (applied to tuned baseline scale)",
        )
        parser.add_argument(
            "--held-out-fold", type=int, default=None,
            help="Override held-out test year (default: most recent fold)",
        )
        parser.add_argument(
            "--verbose", action="store_true", default=False,
        )

    def handle(self, *args, **options):
        multipliers  = options["multipliers"]
        held_out_arg = options["held_out_fold"]
        verbose      = options["verbose"]

        W = 90
        self.stdout.write(f"\nLoading data...")
        player_ratings, team_roster = _load_player_data()
        adj_em_map    = _load_adj_em()
        games_by_year = _load_games()
        folds = _build_folds("bpr", player_ratings, adj_em_map, games_by_year, None)
        if not folds:
            self.stdout.write("ERROR: No BPR folds.")
            return

        # Partition folds
        if held_out_arg:
            held_out = next(((tr, te) for tr, te in folds if te == held_out_arg), folds[-1])
        else:
            held_out = folds[-1]
        train_folds = [f for f in folds if f != held_out]

        self.stdout.write(
            f"  {len(folds)} total folds  |  train: {[f for f in train_folds]}  "
            f"|  held-out: {held_out[0]}→{held_out[1]}"
        )

        # ── Phase 1: Build intermediate state once per train year ──────────────
        all_train_years = list({tr for tr, te in train_folds + [held_out]})
        state_cache: dict = {}
        tuned_scales: dict = {}

        self.stdout.write(f"\nBuilding BPR state for {len(all_train_years)} train years...")
        for train_year in sorted(all_train_years):
            self.stdout.write(f"  {train_year}: running full pipeline (persist=False)...", ending="")
            result = run_bpr_season(
                season_year=train_year,
                persist=False,
                verbose=False,
            )
            state = result.get("_intermediate_state")
            if state is None:
                self.stdout.write(" SKIP (no intermediate state — no stint data?)")
                continue
            state_cache[train_year] = state
            off = state["tuned_sd_scale_off"]
            dff = state["tuned_sd_scale_def"]
            tuned_scales[train_year] = (off, dff)
            self.stdout.write(f" done  tuned_off={off:.3f}  tuned_def={dff:.3f}")

        if not state_cache:
            self.stdout.write("ERROR: No state built for any year.")
            return

        # ── Phase 2: Sweep multipliers on TRAIN folds ─────────────────────────
        self.stdout.write(f"\nSweeping {len(multipliers)} multipliers × {len(train_folds)} train folds...")

        # Pre-load EM records per train year (reused across multipliers)
        em_records_cache: dict = {}
        for train_year in state_cache:
            try:
                em_records_cache[train_year] = [
                    r for r in load_em_ratings(train_year)
                    if (r["possessions"] or 0) >= EM_MIN_POSS
                ]
            except KeyError:
                self.stdout.write(f"  WARNING: No EM data for {train_year} — folds using this year skipped")

        # For each multiplier, for each train fold, compute player_bpr_map + score
        train_results: dict[float, list] = {m: [] for m in multipliers}
        baseline_player_maps: dict[int, dict] = {}  # cache mult=1.0 maps per year

        for mult in multipliers:
            self.stdout.write(f"\n  mult={mult:.2f}")
            for train_year, test_year in train_folds:
                state = state_cache.get(train_year)
                em_recs = em_records_cache.get(train_year)
                if state is None or em_recs is None:
                    continue

                tuned_off, tuned_def = tuned_scales[train_year]
                eff_off = tuned_off * mult
                eff_def = tuned_def * mult

                if mult == 1.0 and train_year in baseline_player_maps:
                    bpr_map = baseline_player_maps[train_year]
                elif mult == 1.0:
                    # Recompute baseline (mult=1.0 = tuned scales = standard run)
                    bpr_map = bpr_from_state(state, eff_off, eff_def)
                    baseline_player_maps[train_year] = bpr_map
                else:
                    bpr_map = bpr_from_state(state, eff_off, eff_def)

                fold_r = _score_fold(
                    bpr_map, train_year, test_year,
                    games_by_year, team_roster, adj_em_map, em_recs,
                )
                if fold_r is None:
                    self.stdout.write(f"    {train_year}→{test_year} skipped")
                    continue
                train_results[mult].append(fold_r)
                if verbose:
                    self.stdout.write(
                        f"    {train_year}→{test_year}  n={fold_r['n_games']:4d}  "
                        f"Δ={fold_r['delta']:+.3f}  β1_bpr={fold_r['b1_bpr']:.3f}  β1_em={fold_r['b1_em']:.3f}"
                    )

        # ── Phase 3: Aggregate TRAIN results + select best multiplier ──────────
        def _agg(fold_list):
            if not fold_list:
                return None
            n_total   = sum(f["n_games"] for f in fold_list)
            bpr_rmse  = np.mean([f["bpr_rmse"] for f in fold_list])
            em_rmse   = np.mean([f["em_rmse"]  for f in fold_list])
            delta     = bpr_rmse - em_rmse
            b1_bpr    = np.mean([f["b1_bpr"] for f in fold_list])
            b1_em     = np.mean([f["b1_em"]  for f in fold_list])
            return {"n": n_total, "bpr_rmse": bpr_rmse, "em_rmse": em_rmse,
                    "delta": delta, "b1_bpr": b1_bpr, "b1_em": b1_em}

        train_agg = {m: _agg(train_results[m]) for m in multipliers}

        # Baseline sanity check
        baseline_agg = train_agg.get(1.0)
        PART_A_BPR_RMSE = 13.386
        if baseline_agg:
            diff = abs(baseline_agg["bpr_rmse"] - PART_A_BPR_RMSE)
            if diff > 0.15:
                self.stdout.write(
                    f"\nWARNING: mult=1.0 bpr_RMSE={baseline_agg['bpr_rmse']:.3f} "
                    f"diverges from Part A ({PART_A_BPR_RMSE:.3f}) by {diff:.3f} — "
                    f"different fold subset (train-only vs all folds); expected if held-out is large."
                )

        # Best multiplier: argmin Δ(bpr − em) on TRAIN folds
        valid_mults = [(m, train_agg[m]) for m in multipliers if train_agg[m] is not None]
        best_mult, best_train = min(valid_mults, key=lambda x: x[1]["delta"])

        # β1 monotonicity check
        ordered = [(m, train_agg[m]["b1_bpr"]) for m in sorted(multipliers) if train_agg[m] is not None]
        b1_monotone = all(ordered[i][1] <= ordered[i+1][1] for i in range(len(ordered)-1))

        # ── Print TRAIN sweep table ────────────────────────────────────────────
        self.stdout.write(f"\n{'='*W}")
        self.stdout.write(f"TRAIN SWEEP (folds: {[f'{tr}→{te}' for tr,te in train_folds]})")
        self.stdout.write(f"{'='*W}")
        hdr = f"  {'mult':>6}  {'eff_off':>8}  {'eff_def':>8}  {'bpr_RMSE':>9}  {'em_RMSE':>9}  {'Δ(b−e)':>8}  {'b1_bpr':>7}  {'b1_em':>7}"
        self.stdout.write(hdr)
        self.stdout.write("  " + "─" * (len(hdr) - 2))

        for m in multipliers:
            agg = train_agg.get(m)
            if agg is None:
                self.stdout.write(f"  {m:>6.2f}  no data")
                continue
            # Use first fold's train year for scale display
            ty0 = train_folds[0][0] if train_folds else list(tuned_scales.keys())[0]
            t_off, t_def = tuned_scales.get(ty0, (1.0, 1.0))
            marker = " ◄ BEST" if m == best_mult else ""
            self.stdout.write(
                f"  {m:>6.2f}  {t_off*m:>8.4f}  {t_def*m:>8.4f}  "
                f"{agg['bpr_rmse']:>9.3f}  {agg['em_rmse']:>9.3f}  "
                f"{agg['delta']:>+8.3f}  {agg['b1_bpr']:>7.3f}  {agg['b1_em']:>7.3f}"
                + marker
            )

        self.stdout.write(f"\n  β1 monotone with mult: {'YES ✓' if b1_monotone else 'NO ✗ — check override wiring'}")

        # ── Phase 4: Evaluate HELD-OUT fold at baseline + best_mult ───────────
        self.stdout.write(f"\n{'='*W}")
        self.stdout.write(f"HELD-OUT VERDICT — fold {held_out[0]}→{held_out[1]}")
        self.stdout.write(f"{'='*W}")

        held_train_year, held_test_year = held_out
        held_state = state_cache.get(held_train_year)
        held_em    = em_records_cache.get(held_train_year)

        if held_state is None or held_em is None:
            self.stdout.write("ERROR: Cannot evaluate held-out fold (no state or EM data).")
        else:
            held_tuned_off, held_tuned_def = tuned_scales[held_train_year]
            held_results = {}

            for m_eval in [1.0, best_mult]:
                eff_off = held_tuned_off * m_eval
                eff_def = held_tuned_def * m_eval
                bpr_map = bpr_from_state(held_state, eff_off, eff_def)
                r = _score_fold(bpr_map, held_train_year, held_test_year,
                                games_by_year, team_roster, adj_em_map, held_em)
                held_results[m_eval] = r
                if r:
                    self.stdout.write(
                        f"  mult={m_eval:.2f}  n={r['n_games']:,}  "
                        f"bpr_RMSE={r['bpr_rmse']:.3f}  em_RMSE={r['em_rmse']:.3f}  "
                        f"Δ={r['delta']:+.3f}  β1_bpr={r['b1_bpr']:.3f}"
                    )

            r_base = held_results.get(1.0)
            r_best = held_results.get(best_mult)

            if r_base and r_best:
                gap_closed_pct = (1 - r_best["delta"] / r_base["delta"]) * 100 if r_base["delta"] != 0 else 0.0

                self.stdout.write(f"\n  Baseline Δ:   {r_base['delta']:+.3f}")
                self.stdout.write(f"  Best Δ:       {r_best['delta']:+.3f}  (mult={best_mult:.2f})")
                self.stdout.write(f"  Gap closed:   {gap_closed_pct:.1f}%")

                if r_best["delta"] <= 0.10:
                    verdict = "GAP CLOSED — Macfax BPR effectively matches EM"
                elif gap_closed_pct > 30:
                    verdict = f"GAP NARROWED (partial, {gap_closed_pct:.0f}%) — EM still leads but gap shrinks"
                else:
                    verdict = "NO IMPROVEMENT (structural) — shrinkage is not the root cause"

                self.stdout.write(f"\n  VERDICT: {verdict}")

                # WinAcc direction agreement
                wa_agrees = (r_best["bpr_wa"] - r_best["em_wa"]) < (r_base["bpr_wa"] - r_base["em_wa"])
                self.stdout.write(f"  WinAcc direction agrees: {'YES' if wa_agrees else 'NO'}")

        # ── Phase 5: Small-sample guardrail ────────────────────────────────────
        self.stdout.write(f"\n{'─'*W}")
        self.stdout.write("SMALL-SAMPLE GUARDRAIL (baseline vs best_mult, held-out train year)")
        if held_state:
            plausible_max = OBPR_PLAUSIBLE_RANGE[1]

            for m_check, label in [(1.0, "baseline"), (best_mult, f"best (mult={best_mult:.2f})")]:
                eff_off = held_tuned_off * m_check
                eff_def = held_tuned_def * m_check
                bpr_map = bpr_from_state(held_state, eff_off, eff_def)

                low_poss = [v for v in bpr_map.values()
                            if MIN_OFF_POSS_BPR <= (v["off_poss"] or 0) < 400
                            and v["bpr"] is not None]
                if not low_poss:
                    self.stdout.write(f"  {label}: no low-poss players found")
                    continue
                bprs = np.array([v["bpr"] for v in low_poss])
                n_blown = int(np.sum(np.abs(bprs) > plausible_max))
                self.stdout.write(
                    f"  {label}: n_low_poss={len(low_poss):,}  "
                    f"p5={np.percentile(bprs,5):+.2f}  p50={np.percentile(bprs,50):+.2f}  "
                    f"p95={np.percentile(bprs,95):+.2f}  max|bpr|={np.max(np.abs(bprs)):.2f}  "
                    f"blown_up(>±{plausible_max:.0f})={n_blown}"
                )
                if n_blown > len(low_poss) * 0.05:
                    self.stdout.write(
                        f"  NOTE: {n_blown}/{len(low_poss)} low-poss players outside ±{plausible_max}. "
                        f"Global shrinkage cut destabilizes small samples — possession-aware shrinkage needed."
                    )

        self.stdout.write("")
