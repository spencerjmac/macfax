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

logger = logging.getLogger(__name__)

# ── Calibration constants ──────────────────────────────────────────────────────
REPLACEMENT_LEVEL = 2.0        # BPR units added above zero to form demand signal
SHRINKAGE_RETURNER = 0.10      # 10% regression to league mean for returning players
SHRINKAGE_ACQUISITION = 0.20   # 20% for trades/signings (higher projection uncertainty)
SLOPE = 0.48                   # forward-predictive OLS from 2024→2025 pair (r=0.392, RMSE=4.83)
                               # 2025→2026 excluded: stored BPR for 2025 season was computed under an
                               # earlier pipeline version and is materially different from current output
                               # (e.g. Amen Thompson stored ≈5.7 vs freshly-computed 9.43).
                               # That pair measures stale inputs → 2026 outcomes, not the current model.
                               # Provisional — re-derive from pooled data when 2026→2027 actuals available.
WINS_PER_EM = 2.46             # wins per 1 pt of adj_em (OLS-calibrated from 2025-26 season)
WINS_INTERCEPT = 44.3          # empirical intercept: league avg wins at adj_em=0 in our scale
SIGMA_EM = 5.5                 # forward RMSE from 2024→2025 backtest (4.83), rounded up from pooled (5.41)
                               # ±1 SIGMA_EM = ±13.5 wins at WINS_PER_EM=2.46 — wide but honest
WINS_ADDED_SCALAR = 0.38       # converts (minutes_share × bpr) → wins added

# ── Projection Value wiring (docs/bpr_audit/09) ───────────────────────────────
# Team forecasts consume projection_value (0.25·z(BPR)+0.75·z(BPM)), NOT raw
# BPR — forward-validated: pooled r=0.601 vs 0.583 pure BPR (3 pairs).
# PV_SLOPE / PV_SIGMA_EM calibrated on minutes-weighted team-mean PV(Y) →
# adj_net(Y+1), pairs 2022→23/23→24/24→25 (n=90): slope=3.58, r=0.304,
# pooled RMSE=4.32. Centered (two-pass league-baseline) form — no intercept.
# The legacy BPR-based projection is still computed and logged for comparison;
# projected_* DB fields carry the PV-based numbers.
PV_SLOPE = 3.58
PV_SIGMA_EM = 4.5              # pooled forward RMSE 4.32, rounded up
PV_WINS_INTERCEPT = 41.0       # centered PV-EM: league-average team = .500.
                               # (Legacy WINS_INTERCEPT=44.3 was fit to the
                               # uncentered legacy scale whose league-mean EM
                               # was negative — do not reuse it here.)
MIN_MPG = 5.0                  # minimum MPG to include player in source roster
MINUTES_FLOOR = 0.02           # minimum projected minutes share (~0.4 MPG equiv)
MINUTES_CEIL = 1.20            # maximum projected minutes share (~24 MPG equiv)
POWER_EXPONENT = 2.0           # demand concentration exponent
TOTAL_SHARES = 5.0             # 200 team-minutes / 40-min game


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

    def handle(self, *args, **options):
        source_year = options["source_season"]
        target_year = options["target_season"]
        team_filter = options["team"]

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

        outlooks = list(TeamSeasonOutlook.objects.all().order_by("team_abbr"))
        if team_filter:
            outlooks = [o for o in outlooks if o.team_slug == team_filter]

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

        # Pass 2: project team ratings + write DB
        total_created = total_teams = 0
        for td in team_data.values():
            outlook = td["outlook"]
            slots = td["slots"]
            if not slots:
                continue
            try:
                n = self._write_team(
                    outlook=outlook,
                    slots=slots,
                    target_season=target_season,
                    nba_avg_adj_o=nba_avg_adj_o,
                    nba_avg_adj_d=nba_avg_adj_d,
                    league_base_off=league_base_off,
                    league_base_def=league_base_def,
                    league_pv_mean=league_pv_mean,
                )
                total_created += n
                total_teams += 1
            except Exception as exc:
                logger.exception("Error writing %s", outlook.team_abbr)
                self.stderr.write(f"  ERROR {outlook.team_abbr}: {exc}")

        self.stdout.write(
            self.style.SUCCESS(
                f"\nDone. {total_teams} teams processed, {total_created} roster slots written."
            )
        )

    # ── Team pipeline ──────────────────────────────────────────────────────────

    @transaction.atomic
    def _write_team(
        self,
        outlook,
        slots,
        target_season,
        nba_avg_adj_o,
        nba_avg_adj_d,
        league_base_off,
        league_base_def,
        league_pv_mean=0.0,
    ):
        # Project team ratings + roster metrics
        metrics = self._project_team(slots, nba_avg_adj_o, nba_avg_adj_d,
                                     league_base_off, league_base_def,
                                     league_pv_mean=league_pv_mean)

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
            )

        # Step 7b: Update TeamSeasonOutlook projection fields
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
        outlook.save(update_fields=[
            "projected_adj_o", "projected_adj_d", "projected_adj_net",
            "projected_wins", "projected_losses",
            "projected_floor_wins", "projected_ceil_wins",
            "continuity_score", "weighted_effective_age", "top2_bpr_concentration",
        ])

        self.stdout.write(
            f"  {outlook.team_abbr}: {len(slots)} players → "
            f"{metrics['wins']}W [{metrics['floor_wins']}–{metrics['ceil_wins']}]  "
            f"AdjEM {metrics['adj_em']:+.1f} (PV; legacy BPR path "
            f"{metrics['legacy_adj_em']:+.1f}, team_pv={metrics['team_pv']:+.2f})  "
            f"cont={metrics['continuity_score']:.0f}%"
        )
        return len(slots)

    # ── Roster assembly ────────────────────────────────────────────────────────

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
                additions.append({
                    "player_name": move.player_name,
                    "player_obj": None,
                    "stats_obj": None,
                    "mpg": 12.0,
                    "obpr": 0.0,
                    "dbpr": 0.0,
                    "bpr": 0.0,
                    "projection_value": None,
                    "archetype": None,
                    "acquisition_type": "drafted",
                    "confidence": "low",
                    "age": None,
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

    def _lookup_player_bpr(self, player_name: str, source_season):
        """
        Find a player's most recent BPR stats (from any team) for use as
        a prior when they sign or are traded to a new team.
        """
        player = (
            NBAPlayer.objects.filter(name__iexact=player_name).first()
            or NBAPlayer.objects.filter(name__icontains=player_name).first()
        )
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
        """
        demands = []
        for slot in slots:
            bpr_above_repl = max(0.0, (slot.get("projected_bpr") or 0.0) + REPLACEMENT_LEVEL)
            mpg_component = (slot.get("mpg") or 15.0) / 36.0
            demands.append(bpr_above_repl + mpg_component)

        powered = [d ** POWER_EXPONENT for d in demands]
        total = sum(powered) or 1.0
        raw = [p / total * TOTAL_SHARES for p in powered]
        clamped = [max(MINUTES_FLOOR, min(MINUTES_CEIL, s)) for s in raw]
        normalized = self._water_fill(clamped, TOTAL_SHARES)

        for slot, share in zip(slots, normalized):
            slot["minutes_share"] = share

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
        Project team efficiency ratings and win total.

        Formula (two-pass, relative to league baseline):
          base_off = Σ(minutes_share_i × projected_obpr_i)
          adj_o = nba_avg_adj_o + SLOPE × (base_off − league_base_off)
          adj_d = nba_avg_adj_d − SLOPE × (base_def − league_base_def)
          wins  = round(41 + adj_em / WINS_PER_EM)
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

        wins = max(5, min(77, round(PV_WINS_INTERCEPT + adj_em * WINS_PER_EM)))
        floor_wins = max(5, min(77, round(PV_WINS_INTERCEPT + (adj_em - PV_SIGMA_EM) * WINS_PER_EM)))
        ceil_wins  = max(5, min(77, round(PV_WINS_INTERCEPT + (adj_em + PV_SIGMA_EM) * WINS_PER_EM)))

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
            "wins": wins,
            "floor_wins": floor_wins,
            "ceil_wins": ceil_wins,
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
