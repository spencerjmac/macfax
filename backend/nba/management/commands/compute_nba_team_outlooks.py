"""
compute_nba_team_outlooks — builds projected 2026-27 roster slots and
team-level projection fields for all 30 TeamSeasonOutlook rows.

Pipeline per team:
  1. Roster assembly: NBAPlayerSeasonStats for source season
  2. Apply TeamOutseasonMove adjustments (adds/removals) if seeded
  3. Per-player BPR projection (shrinkage toward league average)
  4. Minutes allocation (adapted from NCAA Phase 2)
  5. Team rating projection
  6. Roster construction metrics
  7. DB writes: NBAProjectedRosterSlot + TeamSeasonOutlook projection fields

Usage:
    python manage.py compute_nba_team_outlooks
    python manage.py compute_nba_team_outlooks --source-season 2026
    python manage.py compute_nba_team_outlooks --team oklahoma-city-thunder
"""

import logging

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Avg

from nba.models import (
    NBASeason,
    NBATeam,
    NBAPlayer,
    NBAPlayerSeasonStats,
    NBATeamSeasonRatings,
    NBAModelCalibration,
    TeamSeasonOutlook,
    TeamOutseasonMove,
    NBAProjectedRosterSlot,
)
from nba.utils.name_utils import normalize_name

logger = logging.getLogger(__name__)

# Stamped onto every NBAProjectedRosterSlot and TeamSeasonOutlook write so
# mixed-version rows are detectable (Phase 2 P1 forensics).
# History: "2.0" Phase 2 (ceiling + self-centering intercept, incl. Phase 4
# rookie priors); "2.2-nopin" Phase 4.6 Stage A — 4.5 pin reverted (its bins
# were unconditional, survivor-biased, and pinned per-game rates as season
# shares); "2.3" Phase 4.6 Stage B — pin re-enabled on the operator-approved
# additive effective-MPG model (bin effect + wins slope, clamped).
PIPELINE_VERSION = "2.3"

# ── Calibration constants ──────────────────────────────────────────────────────
REPLACEMENT_LEVEL = 2.0        # BPR units added above zero to form demand signal
SHRINKAGE_RETURNER = 0.10      # 10% regression to league mean for returning players
SHRINKAGE_ACQUISITION = 0.20   # 20% for trades/signings (higher projection uncertainty)
# SLOPE — HUMAN-REVIEWED CONSTANT, do not auto-update.
# Derivation: `manage.py derive_nba_slope --pairs 2022:2023,2023:2024,2024:2025`
# (Phase 2 Stage 2, 2026-07-07, operator-approved decision tree).
#   Pooled through-origin OLS, actual adj_net(Y+1) ~ (excess_off + excess_def),
#   N=90 (3 pairs × 30), r=0.456, RMSE=4.63. Allocator: MINUTES_CEIL=1.80.
#   Pairs included: 2022→23, 2023→24, 2024→25 — each passed the fresh-BPR
#   lineage check (mean |stored − fresh| = 0.109/0.084/0.115, threshold 0.5).
#   2025→2026 excluded: stored 2025 BPR predates the current BPR pipeline
#   (e.g. Amen Thompson stored ≈5.7 vs freshly-computed 9.43).
#   History: 0.48 (2024→25 single pair, old allocator CEIL=1.20; its target
#   ratings were also corrupted by a missing season_type='regular' filter —
#   playoff rows overwrote 16 teams' actual adj_net).
SLOPE = 0.453
WINS_PER_EM = 2.46             # wins per 1 pt of adj_em (OLS-calibrated from 2025-26 season)
# WINS_INTERCEPT (legacy, removed Phase 2): 44.3 was OLS-fit on an uncentered
# legacy scale whose league-mean EM was ~-1.34. A fixed intercept cannot
# guarantee league closure (Σ wins = 1230). Wins now use a self-centering
# effective intercept computed per run: 41.0 - WINS_PER_EM × league_mean_em.
SIGMA_EM = 4.7                 # pooled forward RMSE 4.63 (legacy BPR path, N=90, same
                               # derive_nba_slope run as SLOPE above), rounded up to
                               # one decimal. History: 5.5 (single pair, old allocator).
WINS_ADDED_SCALAR = 0.38       # converts (minutes_share × bpr) → wins added

# ── Projection Value wiring (docs/bpr_audit/09) ───────────────────────────────
# Team forecasts consume projection_value (0.25·z(BPR)+0.75·z(BPM)), NOT raw
# BPR — forward-validated: pooled r=0.601 vs 0.583 pure BPR (3 pairs).
# Centered (two-pass league-baseline) form — no intercept. The legacy BPR
# projection is still computed and logged for comparison; projected_* DB
# fields carry the PV-based numbers.
#
# PV_SLOPE — HUMAN-REVIEWED CONSTANT, do not auto-update.
# Derivation: `manage.py derive_nba_slope --pairs 2022:2023,2023:2024,2024:2025`
# (Phase 2 Stage 2, 2026-07-07, operator-approved decision tree).
#   Pooled through-origin OLS, actual adj_net(Y+1) ~ (team_pv − league_pv_mean),
#   team_pv = minutes-share-weighted mean pv_effective under MINUTES_CEIL=1.80.
#   N=90, r=0.478, RMSE=4.58. Same lineage gate + 2025→2026 exclusion as SLOPE.
#   History: 3.58 (old allocator CEIL=1.20 weights; its 2024→25 targets also
#   carried the playoff-row season_type corruption — see SLOPE note).
PV_SLOPE = 5.591
PV_SIGMA_EM = 4.6              # pooled forward RMSE 4.58 (PV path, N=90, same run),
                               # rounded up. History: 4.5 (old allocator pooling).
# PV_WINS_INTERCEPT (removed Phase 2): the fixed 41.0 assumed projected EM is
# exactly mean-zero. handle() now computes effective_intercept =
# 41.0 − WINS_PER_EM × league_mean_em each full-league run, guaranteeing closure.
MIN_MPG = 5.0                  # minimum MPG to include player in source roster
MINUTES_FLOOR = 0.02           # minimum projected minutes share (~0.4 MPG equiv)
MINUTES_CEIL = 1.80            # NBA star ceiling (~36 MPG equiv). Replaces the
                               # NCAA-derived 1.20 (= 24 MPG) which clamped every
                               # NBA star, flattened rotations, and compressed
                               # league quality spread (Phase 2 P2 fix).
POWER_EXPONENT = 2.0           # demand concentration exponent
TOTAL_SHARES = 5.0             # 200 team-minutes / 40-min game

# ── Rookie priors (HUMAN-REVIEWED CONSTANTS, Phase 4 Stage 2, 2026-07-13) ─────
# Drafted players have no NBA stat to project from; before Phase 4 they were
# hardcoded obpr/dbpr 0.0 and mpg 12.0. Derivation:
#   `manage.py derive_rookie_priors --draft-years 2021,2022,2023,2024`
#   187 rookie outcomes / 4 draft classes, joined NBA.com DraftHistory PERSON_ID
#   → rookie-season stats (draft year D → season D+1), multi-team splits
#   collapsed minutes-weighted, one row per player asserted.
#
# BPR prior is FLAT (pick-independent) — operator decision D1. LOYO
# (leave-one-class-out) pooled BPR MAE: pick-binned map 1.69 beats the old
# hardcoded 0.0 (1.90) but LOSES to a flat global-rookie-mean (1.66). Pick
# carries no rookie-BPR signal, so we use the pooled minutes-weighted mean and
# reject pick-binned BPR. (The old 0.0 was, ironically, only ~1.1 pts off.)
ROOKIE_PRIOR_OBPR = -0.8662    # pooled minutes-weighted rookie obpr, N=187
ROOKIE_PRIOR_DBPR = -0.2714    # pooled minutes-weighted rookie dbpr, N=187
# (total rookie BPR prior = -1.1376; rookies are net-negative players — honest.)

# RETIRED (Phase 4.6 conviction — do not restore): the Phase 4.5 per-game
# pick bins {(1,5): 27.9, (6,14): 20.9, (15,30): 16.4, (31,60): 13.0}.
# Three counts against them, all proven by derive_rookie_priors --v2:
#   1. Per-game means pinned as season shares ignore games played —
#      availability overstates rookie minutes ~2.4x (league rookie share
#      31% pinned vs ~8% real).
#   2. Unconditional on team context: bins learned mostly from lottery-team
#      rookies were applied to contenders (OKC 58→47, DEN promoted to #1).
#   3. Scored against the truth they actually pinned (effective MPG),
#      LOYO MAE 7.74 — beating the 12.0 hardcode (7.89) by a rounding error.
#
# ── Rookie minutes model v2 (HUMAN-REVIEWED, Phase 4.6 Stage B, 2026-07-16) ──
# Additive effective-MPG model, operator-approved at the Stage A gate:
#   eff_mpg = BIN_EFFECT[pick_bin] + WINS_SLOPE × (clamped_prior_wins − 41)
#   pinned share = predicted_eff_mpg / 20
# Derivation: `manage.py derive_rookie_priors --v2` —
#   N=234 picks (rounds 1-2, classes 2021-2024, 27 zero-minute picks
#   INCLUDED — survivor correction), outcome = EFFECTIVE MPG = total rookie
#   minutes / 82 team games (per-game MPG fails league closure by 3-4x),
#   conditioning = drafting team's prior-season actual wins (ex-ante).
#   LOYO MAE 5.79 vs cells 5.90 / 12.0-hardcode 7.89 / 4.5-bins 7.74 /
#   global-mean 7.79. Closure: implied current-class Σeff 616, inside the
#   historical actual band 582-690 (4.5 bins: 980, FAIL). R²=0.397 —
#   residual σ≈6 eff-MPG per rookie; the pin claims the MEAN, not the player.
#   Re-derive when 2026-27 actuals land (also the first MPS-scored class).
ROOKIE_EFF_MPG_BIN_EFFECTS = {(1, 5): 20.79, (6, 14): 15.29, (15, 30): 12.66, (31, 60): 5.66}
ROOKIE_WINS_SLOPE = -0.152     # eff-MPG per prior-season win above/below center
ROOKIE_WINS_CENTER = 41
ROOKIE_WINS_CLAMP = (15, 64)   # observed fit range; 65+ contenders treated as 64 (D3)
ROOKIE_EFF_MPG_FLOOR = 0.5     # a drafted player on a roster is not literally zero (D4)
# Drafted players SKIP shrinkage: the prior IS already a population mean;
# regressing one population mean toward another (SHRINKAGE_ACQUISITION toward
# league BPR) is statistical nonsense. See _project_bpr's is_rookie_prior gate.
#
# STANDING NOTE: the 2026 draft class carries 53 MPS scores and zero outcomes.
# After the 2026-27 season completes it becomes the first testable MPS→rookie-
# BPR pair — revisit a MPS-conditional prior then (filed for summer 2027).


def rookie_eff_mpg(overall_pick, prior_team_wins) -> float:
    """
    Predicted rookie EFFECTIVE MPG (total minutes / 82 team games) from the
    Phase 4.6 additive model. Unknown pick → the 31-60 second-round effect;
    unknown prior wins → league-average context (center, zero slope term).
    """
    effect = ROOKIE_EFF_MPG_BIN_EFFECTS[(31, 60)]
    if overall_pick is not None:
        for (lo, hi), e in ROOKIE_EFF_MPG_BIN_EFFECTS.items():
            if lo <= overall_pick <= hi:
                effect = e
                break
    if prior_team_wins is None:
        wins = ROOKIE_WINS_CENTER
    else:
        wins = max(ROOKIE_WINS_CLAMP[0], min(ROOKIE_WINS_CLAMP[1], prior_team_wins))
    pred = effect + ROOKIE_WINS_SLOPE * (wins - ROOKIE_WINS_CENTER)
    return max(ROOKIE_EFF_MPG_FLOOR, pred)


def _clamp_wins(raw: float) -> int:
    """Round and clamp a projected win total to the physical [0, 82] range."""
    return max(0, min(82, round(raw)))


class Command(BaseCommand):
    help = "Compute next-season projected rosters and team outlook metrics for all 30 teams."

    def add_arguments(self, parser):
        parser.add_argument(
            "--source-season", type=int, default=None,
            help="Source season year (default: current season). E.g. 2026 for 2025-26.",
        )
        parser.add_argument(
            "--target-season", type=int, default=None,
            help="Target projection season year (default: source+1). E.g. 2027 for 2026-27.",
        )
        parser.add_argument(
            "--team", type=str, default=None,
            help="Limit to one team slug for debugging (e.g. oklahoma-city-thunder).",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Full compute + validations + reporting, zero DB writes.",
        )
        import argparse
        parser.add_argument(
            "--rookie-pin", action=argparse.BooleanOptionalAction, default=True,
            help=(
                "Pin drafted rookies' minutes shares from the additive "
                "effective-MPG model (Phase 4.6 Stage B, operator-approved). "
                "DEFAULT ON. --no-rookie-pin falls back to pure demand "
                "competition (Stage 2 behavior) for debugging."
            ),
        )
        parser.add_argument(
            "--force", action="store_true",
            help="Overwrite outlooks whose snapshot_frozen_at is set. Without it, "
                 "frozen rows are skipped (they back a published carousel run and "
                 "must not drift mid-series).",
        )

    def handle(self, *args, **options):
        source_year = options["source_season"]
        target_year = options["target_season"]
        team_filter = options["team"]
        dry_run = options["dry_run"]
        self.rookie_pin = options.get("rookie_pin", False)
        self.force = options.get("force", False)
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN — no DB writes"))
        if self.rookie_pin:
            self.stdout.write(
                "Rookie pin ON (default) — additive effective-MPG model (Phase 4.6 Stage B)"
            )
        else:
            self.stdout.write(self.style.WARNING(
                "ROOKIE PIN OFF (--no-rookie-pin) — debug fallback, rookies compete via demand"
            ))

        # Resolve source season
        if source_year is None:
            try:
                source_season = NBASeason.objects.get(is_current=True)
            except NBASeason.DoesNotExist:
                raise CommandError("No current season flagged. Use --source-season YYYY.")
        else:
            try:
                source_season = NBASeason.objects.get(year=source_year)
            except NBASeason.DoesNotExist:
                raise CommandError(f"Season {source_year} not found in DB.")

        if target_year is None:
            target_year = source_season.year + 1

        target_display = f"{target_year - 1}-{str(target_year)[2:]}"
        if dry_run:
            # zero DB writes on dry runs — unsaved instance is fine (never FK'd)
            target_season = (
                NBASeason.objects.filter(year=target_year).first()
                or NBASeason(year=target_year, display_name=target_display)
            )
        else:
            target_season, created = NBASeason.objects.get_or_create(
                year=target_year,
                defaults={"display_name": target_display},
            )
            if created:
                self.stdout.write(f"Created target season {target_season.display_name}")

        self.stdout.write(
            f"Source: {source_season.display_name} → Target: {target_season.display_name}"
        )

        # League averages from source season
        nba_avg_adj_o, nba_avg_adj_d = self._league_rating_averages(source_season)
        self.stdout.write(
            f"League avg adj_o={nba_avg_adj_o:.1f}, adj_d={nba_avg_adj_d:.1f}"
        )

        # BPR league averages (shrinkage targets)
        bpr_qs = NBAPlayerSeasonStats.objects.filter(
            season=source_season,
            season_type="regular",
            mpg__gte=MIN_MPG,
        )
        league_obpr_avg = bpr_qs.filter(obpr__isnull=False).aggregate(v=Avg("obpr"))["v"] or 0.0
        league_dbpr_avg = bpr_qs.filter(dbpr__isnull=False).aggregate(v=Avg("dbpr"))["v"] or 0.0
        league_bpr_avg  = bpr_qs.filter(bpr__isnull=False).aggregate(v=Avg("bpr"))["v"] or 0.0
        from django.db.models import StdDev
        league_bpr_sd = (bpr_qs.filter(bpr__isnull=False)
                         .aggregate(v=StdDev("bpr"))["v"] or 1.0)

        # RAPM-gap sigma — computed once, used in _project_bpr cap
        self.rapm_gap_sigma = self._compute_rapm_gap_sigma(source_season)
        cap_threshold = 1.6 * self.rapm_gap_sigma
        self.stdout.write(
            f"RAPM-gap σ={self.rapm_gap_sigma:.2f}  cap threshold={cap_threshold:.2f}"
        )

        # Season-scoped: a team carries one outlook row per projected season now
        # (season FK + (team_slug, season) unique, migration 0025-0027). Without
        # this filter a second season's rows would double the loop and silently
        # break full_league below.
        outlooks = list(
            TeamSeasonOutlook.objects.filter(season=target_season).order_by("team_abbr")
        )
        if team_filter:
            outlooks = [o for o in outlooks if o.team_slug == team_filter]
        if not outlooks:
            raise CommandError(
                f"No TeamSeasonOutlook rows for season {target_season.display_name}. "
                f"Run: python manage.py seed_team_outlooks --target-season {target_season.year}"
            )

        # Pass 1: assemble rosters + project BPR for all teams, compute league baseline
        team_data = {}
        for outlook in outlooks:
            nba_team = (
                NBATeam.objects.filter(slug=outlook.team_slug).first()
                or NBATeam.objects.filter(abbreviation=outlook.team_abbr).first()
            )
            slots = self._assemble_roster(outlook, nba_team, source_season)
            if not slots:
                logger.warning("No qualifying players for %s — skipping", outlook.team_abbr)
                team_data[outlook.pk] = {"outlook": outlook, "slots": []}
                continue
            for slot in slots:
                slot["projected_obpr"], slot["projected_dbpr"], slot["projected_bpr"] = (
                    self._project_bpr(slot, league_obpr_avg, league_dbpr_avg, league_bpr_avg)
                )
                # Projection Value path (docs/bpr_audit/09): shrink toward the
                # league mean (0 in z-space) exactly like the BPR path; players
                # without a stored PV (draft picks, manual priors) fall back to
                # z(projected_bpr) so the two paths stay on one scale.
                lam = (SHRINKAGE_RETURNER
                       if slot.get("acquisition_type") in ("returner", "extended")
                       else SHRINKAGE_ACQUISITION)
                pv = slot.get("projection_value")
                if pv is None:
                    pv = ((slot.get("projected_bpr") or 0.0) - league_bpr_avg) / league_bpr_sd
                    slot["pv_source"] = "bpr_fallback"
                else:
                    pv = pv * (1.0 - lam)
                    slot["pv_source"] = "stored"
                slot["pv_effective"] = pv
            slots = self._allocate_minutes(slots)
            team_data[outlook.pk] = {"outlook": outlook, "slots": slots}

        # Compute empirical league baseline (average Σ minutes_share×bpr across all teams)
        all_base_off = []
        all_base_def = []
        for td in team_data.values():
            slots = td["slots"]
            if not slots:
                continue
            all_base_off.append(
                sum(s.get("minutes_share", 0) * (s.get("projected_obpr") or 0) for s in slots)
            )
            all_base_def.append(
                sum(s.get("minutes_share", 0) * (s.get("projected_dbpr") or 0) for s in slots)
            )

        league_base_off = sum(all_base_off) / len(all_base_off) if all_base_off else 0.0
        league_base_def = sum(all_base_def) / len(all_base_def) if all_base_def else 0.0

        # League baseline for the Projection Value path: minutes-share-weighted
        # team mean PV, averaged across teams (centers the PV_SLOPE application).
        all_team_pv = []
        for td in team_data.values():
            slots = td["slots"]
            tot = sum(s.get("minutes_share", 0) for s in slots)
            if tot > 0:
                all_team_pv.append(
                    sum(s.get("minutes_share", 0) * s.get("pv_effective", 0.0)
                        for s in slots) / tot)
        league_pv_mean = sum(all_team_pv) / len(all_team_pv) if all_team_pv else 0.0
        self.stdout.write(f"League mean team PV={league_pv_mean:+.3f}")
        self.stdout.write(
            f"League base off={league_base_off:.2f}, def={league_base_def:.2f}"
        )

        # Pass 2a: project team ratings (no wins yet — intercept needs league mean EM)
        computed = []
        for td in team_data.values():
            outlook = td["outlook"]
            slots = td["slots"]
            if not slots:
                continue
            metrics = self._project_team(
                slots, nba_avg_adj_o, nba_avg_adj_d,
                league_base_off, league_base_def,
                league_pv_mean=league_pv_mean,
            )
            computed.append({"outlook": outlook, "slots": slots, "metrics": metrics})

        # Pass 2b: self-centering wins intercept (Phase 2 P3 fix).
        # In a closed 30-team league mean wins = 41, so the intercept must be
        # 41 minus WINS_PER_EM × league_mean_em — a fixed constant cannot
        # guarantee Σ wins ≈ 1230 if projected EM is not exactly mean-zero.
        # Scoped to this projected season so full_league stays correct once other
        # seasons' outlook rows exist (the --team path still yields computed=1 <
        # n_league=30 → full_league False → intercept 41.0 + the DEBUG warning).
        n_league = TeamSeasonOutlook.objects.filter(season=target_season).count()
        full_league = len(computed) == n_league and n_league >= 30
        league_mean_em = (
            sum(c["metrics"]["adj_em"] for c in computed) / len(computed)
            if computed else 0.0
        )
        if full_league:
            effective_intercept = 41.0 - WINS_PER_EM * league_mean_em
            self.stdout.write(
                f"League mean projected EM={league_mean_em:+.3f} → "
                f"effective wins intercept={effective_intercept:.2f}"
            )
        else:
            effective_intercept = 41.0
            self.stdout.write(self.style.WARNING(
                f"DEBUG — non-closing intercept: only {len(computed)}/{n_league} teams "
                "processed; league_mean_em over a partial league is meaningless. "
                "Wins use intercept 41.0. Run all teams for a closing intercept."
            ))

        for c in computed:
            m = c["metrics"]
            m["wins"] = _clamp_wins(effective_intercept + m["adj_em"] * WINS_PER_EM)
            m["floor_wins"] = _clamp_wins(
                effective_intercept + (m["adj_em"] - PV_SIGMA_EM) * WINS_PER_EM
            )
            m["ceil_wins"] = _clamp_wins(
                effective_intercept + (m["adj_em"] + PV_SIGMA_EM) * WINS_PER_EM
            )

        # Validations V1–V4 — run BEFORE any DB write so a failed run writes nothing.
        self._run_validations(computed, full_league)

        # Pass 2c: write DB (skipped entirely on --dry-run)
        total_created = total_teams = 0
        for c in computed:
            outlook, slots, metrics = c["outlook"], c["slots"], c["metrics"]
            if dry_run:
                self._report_team(outlook, slots, metrics)
                total_teams += 1
                continue
            try:
                n = self._write_team(
                    outlook=outlook,
                    slots=slots,
                    metrics=metrics,
                    target_season=target_season,
                )
                total_created += n
                total_teams += 1
            except Exception as exc:
                logger.exception("Error writing %s", outlook.team_abbr)
                self.stderr.write(f"  ERROR {outlook.team_abbr}: {exc}")

        if full_league:
            total_wins = sum(c["metrics"]["wins"] for c in computed)
            self.stdout.write(f"Σ projected wins = {total_wins} (target 1230)")

        self.stdout.write(
            self.style.SUCCESS(
                f"\nDone. {total_teams} teams processed, {total_created} roster slots "
                f"{'(dry run — not written)' if dry_run else 'written'}."
            )
        )

    # ── Team pipeline ──────────────────────────────────────────────────────────

    def _report_team(self, outlook, slots, metrics):
        self.stdout.write(
            f"  {outlook.team_abbr}: {len(slots)} players → "
            f"{metrics['wins']}W [{metrics['floor_wins']}–{metrics['ceil_wins']}]  "
            f"AdjEM {metrics['adj_em']:+.1f} (PV; legacy BPR path "
            f"{metrics['legacy_adj_em']:+.1f}, team_pv={metrics['team_pv']:+.2f})  "
            f"cont={metrics['continuity_score']:.0f}%"
        )

    @transaction.atomic
    def _write_team(self, outlook, slots, metrics, target_season):
        # Frozen-snapshot guard: an outlook backing a published carousel run must
        # not drift mid-series. Skip unless --force. (computed/closure math above
        # still ran over all teams; this only blocks the DB overwrite.)
        if outlook.snapshot_frozen_at is not None and not self.force:
            self.stdout.write(self.style.WARNING(
                f"  SKIP {outlook.team_abbr}: snapshot frozen at "
                f"{outlook.snapshot_frozen_at:%Y-%m-%d} — pass --force to overwrite."
            ))
            return 0

        # Write projected roster slots
        NBAProjectedRosterSlot.objects.filter(team=outlook, season=target_season).delete()
        for slot in slots:
            NBAProjectedRosterSlot.objects.create(
                team=outlook,
                season=target_season,
                player=slot.get("player_obj"),
                prior_stats=slot.get("stats_obj"),
                player_name=slot["player_name"],
                position=slot.get("position", ""),
                archetype=slot.get("archetype"),
                age=slot.get("age"),
                acquisition_type=slot["acquisition_type"],
                projected_obpr=slot.get("projected_obpr"),
                projected_dbpr=slot.get("projected_dbpr"),
                projected_bpr=slot.get("projected_bpr"),
                projected_minutes_share=slot.get("minutes_share"),
                projected_wins_added=slot.get("wins_added"),
                confidence=slot.get("confidence", "medium"),
                pipeline_version=PIPELINE_VERSION,
            )

        # Step 7b: Update TeamSeasonOutlook projection fields
        # Stamp season explicitly (row is fetched season-scoped, so this is
        # normally a no-op — but it keeps the write correct if an unscoped
        # outlook is ever passed in).
        outlook.season = target_season
        outlook.projected_adj_o = metrics["adj_o"]
        outlook.projected_adj_d = metrics["adj_d"]
        outlook.projected_adj_net = metrics["adj_em"]
        outlook.projected_wins = metrics["wins"]
        outlook.projected_losses = 82 - metrics["wins"]
        outlook.projected_floor_wins = metrics["floor_wins"]
        outlook.projected_ceil_wins = metrics["ceil_wins"]
        outlook.continuity_score = metrics["continuity_score"]
        outlook.weighted_effective_age = metrics["weighted_age"]
        outlook.top2_bpr_concentration = metrics["top2_concentration"]
        outlook.pipeline_version = PIPELINE_VERSION
        outlook.save(update_fields=[
            "season",
            "projected_adj_o", "projected_adj_d", "projected_adj_net",
            "projected_wins", "projected_losses",
            "projected_floor_wins", "projected_ceil_wins",
            "continuity_score", "weighted_effective_age", "top2_bpr_concentration",
            "pipeline_version",
        ])

        self._report_team(outlook, slots, metrics)
        return len(slots)

    # ── Validations (Phase 2 Step 4) ───────────────────────────────────────────

    def _run_validations(self, computed, full_league):
        """
        V1 league closure, V2 share closure, V3 allocator monotonicity,
        V4 ceiling census. Runs on computed (pre-write) data; any failure
        aborts the command before a single row is written.
        """
        failures = []

        # V1 — League closure
        if full_league:
            total_wins = sum(c["metrics"]["wins"] for c in computed)
            if abs(total_wins - 1230) > 16:
                failures.append(
                    f"V1 league closure: Σ projected wins = {total_wins}, "
                    f"|{total_wins} - 1230| > 16"
                )
            self.stdout.write(f"V1 league closure: Σ wins = {total_wins} (target 1230)")
        else:
            self.stdout.write("V1 league closure: SKIPPED (partial league run)")

        # V2 — Share closure per team
        v2_bad = []
        for c in computed:
            tot = sum(s.get("minutes_share", 0.0) for s in c["slots"])
            if abs(tot - TOTAL_SHARES) > 0.01:
                v2_bad.append(f"{c['outlook'].team_abbr}={tot:.4f}")
        if v2_bad:
            failures.append(f"V2 share closure: {', '.join(v2_bad)}")
        self.stdout.write(
            f"V2 share closure: {'FAIL ' + ', '.join(v2_bad) if v2_bad else 'OK (all teams Σshare ≈ 5.0)'}"
        )

        # V3 — Allocator monotonicity: shares non-increasing in demand.
        # Phase 4.5: pinned rookies (demand=None) are exempt by design —
        # their share comes from the empirical prior, not demand competition.
        # With the pin off (Phase 4.6 default), rookies compete and are checked.
        pin_enabled = getattr(self, "rookie_pin", False)
        v3_bad = []
        for c in computed:
            comp = [
                s for s in c["slots"]
                if not (pin_enabled and s.get("is_rookie_prior"))
            ]
            ordered = sorted(comp, key=lambda s: s.get("demand", 0.0), reverse=True)
            for prev, cur in zip(ordered, ordered[1:]):
                if cur.get("minutes_share", 0.0) > prev.get("minutes_share", 0.0) + 1e-6:
                    v3_bad.append(
                        f"{c['outlook'].team_abbr}: {cur['player_name']} "
                        f"({cur['minutes_share']:.3f}) > {prev['player_name']} "
                        f"({prev['minutes_share']:.3f}) despite lower demand"
                    )
        if v3_bad:
            failures.append("V3 monotonicity: " + "; ".join(v3_bad[:5]))
        self.stdout.write(
            f"V3 allocator monotonicity (competitive slots): "
            f"{'FAIL (' + str(len(v3_bad)) + ' violations)' if v3_bad else 'OK'}"
        )

        # V4 — Ceiling census (informational)
        league_at_ceil = 0
        per_team = []
        for c in computed:
            n = sum(
                1 for s in c["slots"]
                if s.get("minutes_share", 0.0) >= MINUTES_CEIL - 1e-6
            )
            league_at_ceil += n
            if n:
                per_team.append(f"{c['outlook'].team_abbr}:{n}")
        self.stdout.write(
            f"V4 ceiling census: {league_at_ceil} players at MINUTES_CEIL={MINUTES_CEIL} "
            f"league-wide{'  [' + ' '.join(per_team) + ']' if per_team else ''}"
        )

        # V5 — Pinned-rookie share integrity (Phase 4.5, only when --rookie-pin).
        # Each pinned rookie's final share must equal its prior-derived
        # pinned_share (within the rookie-stack scale/clamp tolerance).
        # With the pin off, report the rookies' competed share census instead.
        if pin_enabled:
            v5_bad = []
            n_pinned = 0
            total_pinned_share = 0.0
            max_pinned = 0.0
            for c in computed:
                for s in c["slots"]:
                    if not s.get("is_rookie_prior"):
                        continue
                    n_pinned += 1
                    sh = s.get("minutes_share", 0.0)
                    total_pinned_share += sh
                    max_pinned = max(max_pinned, sh)
                    if abs(sh - s.get("pinned_share", -1)) > 1e-6:
                        v5_bad.append(
                            f"{c['outlook'].team_abbr}: {s['player_name']} "
                            f"share {sh:.3f} != pinned {s.get('pinned_share'):.3f}"
                        )
            if v5_bad:
                failures.append("V5 pinned-share integrity: " + "; ".join(v5_bad[:5]))
            self.stdout.write(
                f"V5 pinned-rookie shares: {'FAIL (' + str(len(v5_bad)) + ')' if v5_bad else 'OK'}"
                f"  — {n_pinned} pinned rookies, total share {total_pinned_share:.2f}, "
                f"max {max_pinned:.3f} ({max_pinned*20:.0f} MPG-equiv)"
            )
        else:
            rk_share = sum(
                s.get("minutes_share", 0.0)
                for c in computed for s in c["slots"] if s.get("is_rookie_prior")
            )
            n_rk = sum(
                1 for c in computed for s in c["slots"] if s.get("is_rookie_prior")
            )
            total_all = TOTAL_SHARES * len(computed)
            self.stdout.write(
                f"V5 (pin OFF): {n_rk} drafted rookies competed for "
                f"{rk_share:.2f} shares = {rk_share/total_all*100 if total_all else 0:.1f}% "
                f"of league minutes"
            )

        if failures:
            for f in failures:
                self.stderr.write(self.style.ERROR(f"VALIDATION FAILURE — {f}"))
            raise CommandError(
                f"{len(failures)} validation failure(s) — nothing written to DB."
            )

    # ── Roster assembly ────────────────────────────────────────────────────────

    def _prior_team_wins(self, source_season) -> dict:
        """
        Actual regular-season wins per team abbreviation for the source season
        (the rookie model's ex-ante team-context input). Computed once per run
        from NBAGame results — NBATeamSeasonRatings carries no wins field.
        """
        if not hasattr(self, "_team_wins_cache"):
            from nba.models import NBAGame
            wins: dict[str, int] = {}
            qs = NBAGame.objects.filter(
                season=source_season, season_type="regular",
            ).select_related("home_team", "away_team").only(
                "home_score", "away_score",
                "home_team__abbreviation", "away_team__abbreviation",
            )
            for g in qs:
                if g.home_score is None or g.away_score is None:
                    continue
                w = (g.home_team.abbreviation if g.home_score > g.away_score
                     else g.away_team.abbreviation)
                wins[w] = wins.get(w, 0) + 1
            self._team_wins_cache = wins
        return self._team_wins_cache

    @staticmethod
    def _calc_age(dob, as_of) -> "int | None":
        """Player age in full years as of `as_of` date."""
        if dob is None:
            return None
        from datetime import date as _date
        if not isinstance(as_of, _date):
            return None
        return as_of.year - dob.year - ((as_of.month, as_of.day) < (dob.month, dob.day))

    def _assemble_roster(self, outlook, nba_team, source_season):
        """
        Build the list of player projection dicts.

        Base roster: players with qualifying stats for this team last season.
        Then apply TeamOutseasonMove entries if any exist.
        """
        from datetime import date as _date
        # Age reference = October 1 of the projected season (start of next season).
        # source_season.year=2026 means 2025-26; projected season starts Oct 2026.
        age_ref = _date(source_season.year, 10, 1)

        slots = []
        returner_names = set()

        if nba_team:
            qs = (
                NBAPlayerSeasonStats.objects.filter(
                    team=nba_team,
                    season=source_season,
                    season_type="regular",
                    mpg__gte=MIN_MPG,
                    bpr__isnull=False,
                )
                .select_related("player")
                .order_by("-mpg")
            )
            for stats in qs:
                slots.append({
                    "player_name": stats.player.name,
                    "player_obj": stats.player,
                    "stats_obj": stats,
                    "mpg": stats.mpg or 0.0,
                    "obpr": stats.obpr or 0.0,
                    "dbpr": stats.dbpr or 0.0,
                    "bpr": stats.bpr or 0.0,
                    "projection_value": stats.projection_value,
                    "archetype": stats.nba_archetype,
                    "acquisition_type": "returner",
                    "confidence": "high",
                    "age": self._calc_age(stats.player.date_of_birth, age_ref),
                    "position": "",
                })
                returner_names.add(stats.player.name.lower())

        # Apply offseason moves if seeded
        moves = list(TeamOutseasonMove.objects.filter(team=outlook))
        if not moves:
            return slots

        removal_names = set()
        extension_names = set()
        additions = []

        for move in moves:
            name_lower = move.player_name.lower()
            if move.move_type in ("lost", "traded_out", "waived"):
                removal_names.add(name_lower)
            elif move.move_type in ("signed", "traded_in"):
                bpr_data = self._lookup_player_bpr(move.player_name, source_season)
                additions.append({
                    "player_name": move.player_name,
                    "player_obj": bpr_data.get("player_obj"),
                    "stats_obj": bpr_data.get("stats_obj"),
                    "mpg": bpr_data.get("mpg", 20.0),
                    "obpr": bpr_data.get("obpr", 0.0),
                    "dbpr": bpr_data.get("dbpr", 0.0),
                    "bpr": bpr_data.get("bpr", 0.0),
                    "projection_value": (
                        bpr_data["stats_obj"].projection_value
                        if bpr_data.get("stats_obj") is not None else None
                    ),
                    "archetype": bpr_data.get("archetype"),
                    "acquisition_type": move.move_type,
                    "confidence": "medium",
                    "age": None,
                    "position": "",
                })
            elif move.move_type == "drafted":
                # Phase 4.6 Stage B: additive effective-MPG model — bin effect
                # + wins slope on the drafting team's prior-season actual wins
                # (clamped to the observed fit range). Flat BPR prior; and
                # is_rookie_prior=True so _project_bpr skips shrinkage.
                # Resolve DOB opportunistically if the rookie is already in the DB.
                rookie_player = self._resolve_player_by_name(move.player_name)
                additions.append({
                    "player_name": move.player_name,
                    "player_obj": rookie_player,
                    "stats_obj": None,
                    "mpg": rookie_eff_mpg(
                        move.overall_pick,
                        self._prior_team_wins(source_season).get(outlook.team_abbr),
                    ),
                    "obpr": ROOKIE_PRIOR_OBPR,
                    "dbpr": ROOKIE_PRIOR_DBPR,
                    "bpr": ROOKIE_PRIOR_OBPR + ROOKIE_PRIOR_DBPR,
                    "projection_value": None,
                    "archetype": None,
                    "acquisition_type": "drafted",
                    "confidence": "low",
                    "is_rookie_prior": True,
                    "age": self._calc_age(
                        getattr(rookie_player, "date_of_birth", None),
                        _date(source_season.year, 10, 1),
                    ),
                    "position": "",
                })
            elif move.move_type == "extended":
                # Player stays in returner pool; just upgrade their acquisition_type badge.
                extension_names.add(name_lower)

        if removal_names:
            slots = [s for s in slots if s["player_name"].lower() not in removal_names]

        for slot in slots:
            if slot["player_name"].lower() in extension_names:
                slot["acquisition_type"] = "extended"

        existing_names = {s["player_name"].lower() for s in slots}
        for add in additions:
            if add["player_name"].lower() not in existing_names:
                slots.append(add)
                existing_names.add(add["player_name"].lower())

        return slots

    def _resolve_player_by_name(self, player_name: str):
        """
        Resolve a free-text move name to exactly one NBAPlayer, or None.

        Phase 4 P2: the old code fell back to name__icontains, which could
        silently assign the wrong player's entire BPR history to a signing
        (a substring of one name matching another). Resolution is now:
          1. exact case-insensitive match on the raw name,
          2. else exact match on the shared normalized form (diacritics /
             punctuation / Jr-Sr-II-III-IV suffix stripped — nba.utils.name_utils),
          3. else FAIL LOUDLY: log a warning with the attempted name, return None.
        Ambiguity (>1 candidate) at either tier also fails loudly — never guess.
        """
        # tier 1: exact raw (case-insensitive)
        exact = list(NBAPlayer.objects.filter(name__iexact=player_name)[:2])
        if len(exact) == 1:
            return exact[0]
        if len(exact) > 1:
            logger.warning(
                "_resolve_player_by_name: '%s' matches %d players by exact name — "
                "ambiguous, not assigning BPR", player_name, len(exact),
            )
            return None

        # tier 2: normalized form (built once per command run)
        if not hasattr(self, "_norm_index"):
            self._norm_index = {}
            for p in NBAPlayer.objects.all().only("id", "name"):
                self._norm_index.setdefault(normalize_name(p.name), []).append(p)
        candidates = self._norm_index.get(normalize_name(player_name), [])
        if len(candidates) == 1:
            return candidates[0]
        if len(candidates) > 1:
            logger.warning(
                "_resolve_player_by_name: '%s' normalizes to %d players (%s) — "
                "ambiguous, not assigning BPR", player_name, len(candidates),
                ", ".join(c.name for c in candidates),
            )
            return None

        # tier 3: loud fail
        logger.warning(
            "_resolve_player_by_name: no NBAPlayer matched '%s' (exact or "
            "normalized) — signing/trade will get no prior BPR", player_name,
        )
        return None

    def _lookup_player_bpr(self, player_name: str, source_season):
        """
        Find a player's most recent BPR stats (from any team) for use as
        a prior when they sign or are traded to a new team.
        """
        player = self._resolve_player_by_name(player_name)
        if player is None:
            return {}

        stats = (
            NBAPlayerSeasonStats.objects.filter(
                player=player,
                season_type="regular",
                bpr__isnull=False,
            )
            .order_by("-season__year")
            .first()
        )
        if stats is None:
            return {"player_obj": player}

        return {
            "player_obj": player,
            "stats_obj": stats,
            "mpg": stats.mpg or 20.0,
            "obpr": stats.obpr or 0.0,
            "dbpr": stats.dbpr or 0.0,
            "bpr": stats.bpr or 0.0,
            "archetype": stats.nba_archetype,
        }

    # ── BPR projection ─────────────────────────────────────────────────────────

    def _project_bpr(self, slot, league_obpr_avg, league_dbpr_avg, league_bpr_avg):
        """Shrinkage toward league mean, then RAPM-inflation cap."""
        # Phase 4 D3: drafted rookies carry a population-mean prior, not an
        # observed stat. Shrinking one population mean toward another (the
        # league BPR mean) is statistical nonsense — pass the prior through
        # untouched. The RAPM cap below is already a no-op (stats_obj is None).
        if slot.get("is_rookie_prior"):
            return slot["obpr"], slot["dbpr"], slot["bpr"]

        lam = (
            SHRINKAGE_RETURNER
            if slot["acquisition_type"] in ("returner", "extended")
            else SHRINKAGE_ACQUISITION
        )
        proj_obpr = slot["obpr"] * (1 - lam) + league_obpr_avg * lam
        proj_dbpr = slot["dbpr"] * (1 - lam) + league_dbpr_avg * lam
        proj_bpr  = slot["bpr"]  * (1 - lam) + league_bpr_avg  * lam

        # ── RAPM-inflation cap ────────────────────────────────────────────────
        # When prior-informed RAPM >> Box BPR by more than 1.5σ, the gap is
        # likely lineup-context absorption rather than genuine player impact.
        # Cap applied to the local projection only — DB values unchanged.
        stats_obj = slot.get("stats_obj")
        if stats_obj is not None:
            box_obpr = stats_obj.box_obpr
            box_dbpr = stats_obj.box_dbpr
            if box_obpr is None or box_dbpr is None:
                logger.warning(
                    "No box_bpr for %s — skipping inflation cap",
                    slot.get("player_name", "?"),
                )
            else:
                box_bpr_val = box_obpr + box_dbpr
                rapm_gap_bpr  = proj_bpr  - box_bpr_val
                rapm_gap_obpr = proj_obpr - box_obpr
                rapm_gap_dbpr = proj_dbpr - box_dbpr
                cap_threshold = 1.6 * self.rapm_gap_sigma

                if rapm_gap_bpr > cap_threshold:
                    excess = rapm_gap_bpr - cap_threshold
                    orig_bpr = proj_bpr
                    proj_bpr -= excess
                    if abs(rapm_gap_bpr) > 0:
                        proj_obpr -= excess * (rapm_gap_obpr / rapm_gap_bpr)
                        proj_dbpr -= excess * (rapm_gap_dbpr / rapm_gap_bpr)
                    self.stdout.write(
                        f"  [RAPM cap] {slot.get('player_name', '?'):<28} "
                        f"bpr {orig_bpr:+.2f}→{proj_bpr:+.2f}  "
                        f"box={box_bpr_val:+.2f}  gap={rapm_gap_bpr:.2f}  "
                        f"excess={excess:.2f}"
                    )

        return proj_obpr, proj_dbpr, proj_bpr

    def _compute_rapm_gap_sigma(self, source_season) -> float:
        """
        Standard deviation of (bpr - box_bpr) across qualifying players.

        Measures how wide the spread is between lineup-adjusted RAPM (bpr) and
        box-score BPR.  Used as the cap threshold scale: gaps > 1.5σ are treated
        as lineup-context inflation rather than genuine player impact.
        """
        import statistics

        qs = NBAPlayerSeasonStats.objects.filter(
            season=source_season,
            season_type="regular",
            gp__gte=20,
            mpg__gte=12,
            bpr__isnull=False,
            box_obpr__isnull=False,
            box_dbpr__isnull=False,
        ).only("bpr", "box_obpr", "box_dbpr")

        gaps = [
            float(row.bpr) - (float(row.box_obpr) + float(row.box_dbpr))
            for row in qs
        ]

        if len(gaps) < 20:
            logger.warning(
                "_compute_rapm_gap_sigma: only %d qualifying players — using fallback σ=3.5",
                len(gaps),
            )
            return 3.5

        sigma = statistics.stdev(gaps)
        logger.info("RAPM-gap σ=%.3f from %d players", sigma, len(gaps))
        return sigma

    # ── Minutes allocation ─────────────────────────────────────────────────────

    def _allocate_minutes(self, slots):
        """
        Adapted from NCAA Phase 2 minutes/engine.py.

        demand = BPR_component (above replacement) + MPG_component
        Power transform concentrates minutes in the top rotation.
        Water-fill normalize to TOTAL_SHARES = 5.0.

        Phase 4.5: drafted rookies (is_rookie_prior) have their share PINNED
        directly from the empirical pick→MPG prior, then veterans compete for
        the remainder. Rationale: NBA rookie minutes are a development
        investment, not a talent meritocracy — our own N=187 derivation shows
        picks 1-5 average 27.9 MPG at −1.1 BPR, which the demand function
        (dominated by the BPR term under POWER_EXPONENT=2) structurally cannot
        express. Convention: share × 20 = MPG-equiv (MINUTES_CEIL 1.80 = 36 MPG).
        """
        # Phase 4.6 rollback gate: pin only when --rookie-pin is passed.
        # Default OFF → every slot (rookies included) competes via demand,
        # which is exactly the Phase 4 Stage 2 allocator.
        pin_enabled = getattr(self, "rookie_pin", False)
        pinned = [s for s in slots if pin_enabled and s.get("is_rookie_prior")]
        competitive = [s for s in slots if not (pin_enabled and s.get("is_rookie_prior"))]

        # Pinned rookie shares straight from the prior MPG (share = mpg / 20).
        for s in pinned:
            # slot "mpg" for drafted rookies IS the additive model's predicted
            # effective MPG (see _assemble_roster); floor already applied there.
            prior_eff_mpg = s.get("mpg") or ROOKIE_EFF_MPG_FLOOR
            s["pinned_share"] = max(MINUTES_FLOOR, min(MINUTES_CEIL, prior_eff_mpg / 20.0))

        pinned_total = sum(s["pinned_share"] for s in pinned)
        remaining_pool = TOTAL_SHARES - pinned_total

        # Guard: a rookie-stacked roster could starve the veteran pool. Keep at
        # least 2.5 shares (half the team) competitive by scaling pinned down.
        MIN_COMPETITIVE_POOL = 2.5
        if competitive and remaining_pool < MIN_COMPETITIVE_POOL and pinned_total > 0:
            scale = (TOTAL_SHARES - MIN_COMPETITIVE_POOL) / pinned_total
            logger.warning(
                "Rookie-stacked roster: pinned share %.2f leaves only %.2f for "
                "%d veterans — scaling pinned by %.3f to preserve a %.1f competitive pool",
                pinned_total, remaining_pool, len(competitive), scale, MIN_COMPETITIVE_POOL,
            )
            for s in pinned:
                s["pinned_share"] *= scale
            pinned_total = sum(s["pinned_share"] for s in pinned)
            remaining_pool = TOTAL_SHARES - pinned_total

        # No veterans at all (degenerate; NBA rosters always have returners):
        # pinned absorb the whole pool.
        if not competitive:
            scale = (TOTAL_SHARES / pinned_total) if pinned_total > 0 else 1.0
            for s in pinned:
                s["demand"] = None
                s["pinned_share"] *= scale
                s["minutes_share"] = s["pinned_share"]
            return slots

        # Competitive slots compete for the remaining pool via the existing
        # demand → power → clamp → water-fill path (target = remaining_pool).
        demands = []
        for slot in competitive:
            bpr_above_repl = max(0.0, (slot.get("projected_bpr") or 0.0) + REPLACEMENT_LEVEL)
            mpg_component = (slot.get("mpg") or 15.0) / 36.0
            demands.append(bpr_above_repl + mpg_component)

        powered = [d ** POWER_EXPONENT for d in demands]
        total = sum(powered) or 1.0
        raw = [p / total * remaining_pool for p in powered]
        clamped = [max(MINUTES_FLOOR, min(MINUTES_CEIL, s)) for s in raw]
        normalized = self._water_fill(clamped, remaining_pool)

        for slot, demand, share in zip(competitive, demands, normalized):
            slot["demand"] = demand
            slot["minutes_share"] = share

        for s in pinned:
            s["demand"] = None  # exempt from V3 monotonicity (pinned, not demand-ranked)
            s["minutes_share"] = s["pinned_share"]

        return slots

    @staticmethod
    def _water_fill(shares, target, max_iter=25):
        shares = list(shares)
        for _ in range(max_iter):
            total = sum(shares)
            if abs(total - target) < 1e-6:
                break
            delta = (target - total) / len(shares)
            shares = [
                max(MINUTES_FLOOR, min(MINUTES_CEIL, s + delta))
                for s in shares
            ]
        return shares

    # ── Team rating projection ─────────────────────────────────────────────────

    def _project_team(self, slots, nba_avg_adj_o, nba_avg_adj_d,
                      league_base_off, league_base_def, league_pv_mean=0.0):
        """
        Project team efficiency ratings and roster metrics — NOT wins.

        Formula (two-pass, relative to league baseline):
          base_off = Σ(minutes_share_i × projected_obpr_i)
          adj_o = nba_avg_adj_o + SLOPE × (base_off − league_base_off)
          adj_d = nba_avg_adj_d − SLOPE × (base_def − league_base_def)
          adj_em (primary) = PV_SLOPE × (team_pv − league_pv_mean)

        Wins are computed by handle() after all teams' adj_em are known:
          effective_intercept = 41.0 − WINS_PER_EM × league_mean_em
          wins = clamp(round(effective_intercept + adj_em × WINS_PER_EM), 0, 82)
        so the league closes (Σ wins ≈ 1230) regardless of EM centering.
        """
        base_off = sum(
            s.get("minutes_share", 0.0) * (s.get("projected_obpr") or 0.0)
            for s in slots
        )
        base_def = sum(
            s.get("minutes_share", 0.0) * (s.get("projected_dbpr") or 0.0)
            for s in slots
        )

        # ── Legacy BPR-based projection (kept for comparison logging) ─────────
        adj_o = nba_avg_adj_o + SLOPE * (base_off - league_base_off)
        adj_d = nba_avg_adj_d - SLOPE * (base_def - league_base_def)
        legacy_adj_em = adj_o - adj_d

        # ── PRIMARY: Projection Value path (docs/bpr_audit/09) ────────────────
        # projected adj_em from the forward-validated blend, centered on the
        # league PV baseline. The off/def split above still drives the
        # per-side ratings, rescaled so they sum to the PV-based adj_em.
        tot_share = sum(s.get("minutes_share", 0.0) for s in slots)
        team_pv = (sum(s.get("minutes_share", 0.0) * s.get("pv_effective", 0.0)
                       for s in slots) / tot_share) if tot_share > 0 else 0.0
        adj_em = PV_SLOPE * (team_pv - league_pv_mean)
        # Preserve the legacy off/def SHAPE around the PV total
        legacy_split = (adj_o - nba_avg_adj_o) - (nba_avg_adj_d - adj_d)  # == legacy_adj_em
        off_frac = 0.5
        if abs(legacy_split) > 1e-9:
            off_frac = (adj_o - nba_avg_adj_o) / legacy_split
            off_frac = max(-1.0, min(2.0, off_frac))
        adj_o = nba_avg_adj_o + adj_em * off_frac
        adj_d = nba_avg_adj_d - adj_em * (1.0 - off_frac)

        # Wins computed by handle() with the self-centering effective intercept.

        # Wins added per player
        for slot in slots:
            share = slot.get("minutes_share") or 0.0
            bpr   = slot.get("projected_bpr") or 0.0
            slot["wins_added"] = share * bpr * WINS_ADDED_SCALAR

        # Continuity: fraction of projected minutes from returning players
        returner_share = sum(
            s.get("minutes_share", 0.0)
            for s in slots
            if s["acquisition_type"] in ("returner", "extended")
        )
        continuity_score = returner_share / TOTAL_SHARES * 100

        # Weighted effective age (only players with age populated)
        total_share = sum(s.get("minutes_share", 0.0) for s in slots) or 1.0
        aged_slots = [(s["age"], s.get("minutes_share", 0.0)) for s in slots if s.get("age")]
        weighted_age = (
            sum(a * sh for a, sh in aged_slots) / total_share
            if aged_slots else None
        )

        # Star concentration: top-2 players by wins added
        all_wins_added = sorted(
            [s.get("wins_added", 0.0) for s in slots], reverse=True
        )
        total_wins_added = sum(all_wins_added)
        top2_concentration = (
            sum(all_wins_added[:2]) / total_wins_added
            if total_wins_added > 0 else None
        )

        return {
            "adj_o": adj_o,
            "adj_d": adj_d,
            "adj_em": adj_em,
            "legacy_adj_em": legacy_adj_em,
            "team_pv": team_pv,
            "continuity_score": continuity_score,
            "weighted_age": weighted_age,
            "top2_concentration": top2_concentration,
        }

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _league_rating_averages(self, season):
        """Pull mean adj_o and adj_d from NBATeamSeasonRatings for the source season."""
        agg = NBATeamSeasonRatings.objects.filter(
            season=season,
            season_type="regular",
            adj_off__isnull=False,
            adj_def__isnull=False,
        ).aggregate(avg_o=Avg("adj_off"), avg_d=Avg("adj_def"))
        return agg.get("avg_o") or 115.0, agg.get("avg_d") or 115.0
