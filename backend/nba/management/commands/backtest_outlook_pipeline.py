"""
backtest_outlook_pipeline — leak-free out-of-sample backtest of the outlook pipeline.

Projects a completed target season using ONLY pre-season information, then scores
against what actually happened. REPORT-ONLY: every write (seeded target outlooks,
reconstructed moves, computed projections) happens inside a transaction that is
rolled back at the end, so the database is left untouched.

Leak-free construction:
  - the projection is driven by SOURCE-season player stats/BPR (fully in the past);
  - offseason moves are reconstructed from OPENING-DAY target rosters — each
    player's FIRST regular game of the target season — diffed against compute's
    source base roster. It never uses end-of-target rosters, which would leak
    mid-season trades into a "pre-season" projection and flatter the model.

Known fidelity limits (uniform across teams, noted so misses read right):
  - target-season additions are all created as `signed`, so a drafted rookie
    gets replacement BPR (0.0) rather than a rookie prior — good rookies are
    understated. This backtest scores the veteran-roster→wins mapping, not
    rookie valuation.

Usage:
  python manage.py backtest_outlook_pipeline --source-season 2025 --target-season 2026
"""

import math
from collections import defaultdict

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from nba.management.commands.compute_nba_team_outlooks import MIN_MPG
from nba.models import (
    NBAGame,
    NBAPlayerGameStats,
    NBAPlayerSeasonStats,
    NBAProjectedRosterSlot,
    NBASeason,
    NBATeam,
    NBATeamSeasonRatings,
    TeamOutseasonMove,
    TeamSeasonOutlook,
)


class Command(BaseCommand):
    help = "Leak-free out-of-sample backtest of the team-outlook pipeline (report-only)."

    def add_arguments(self, parser):
        parser.add_argument("--source-season", type=int, required=True,
                            help="Source season ending year (e.g. 2025 for 2024-25).")
        parser.add_argument("--target-season", type=int, required=True,
                            help="Target season ending year to project+score (e.g. 2026).")
        parser.add_argument("--allocator", choices=["demand", "persistence"], default="demand",
                            help="Minutes allocator passed through to compute (A/B the K1 rewrite).")

    def handle(self, *args, **opts):
        source_year, target_year = opts["source_season"], opts["target_season"]
        source_season = NBASeason.objects.filter(year=source_year).first()
        target_season = NBASeason.objects.filter(year=target_year).first()
        if not source_season or not target_season:
            raise CommandError("source/target NBASeason not found")

        # Actuals — read outside the txn (they must survive rollback).
        actual_wins = self._actual_wins(target_season)      # nba_team_id -> wins
        actual_net = self._actual_net(target_season)        # nba_team_id -> adj_net
        if not actual_wins:
            raise CommandError(f"No regular-season games for {target_season.display_name}.")

        rows, slots = [], {}
        with transaction.atomic():
            self._seed_outlooks(target_season)
            n_moves = self._reconstruct_moves(source_season, target_season)
            self.stdout.write(
                f"Seeded 30 outlooks + {n_moves} leak-free offseason moves "
                f"({source_season.display_name} → {target_season.display_name})."
            )
            call_command("compute_nba_team_outlooks", source_season=source_year,
                         target_season=target_year, allocator=opts["allocator"], verbosity=0)
            rows = self._collect(target_season, actual_wins, actual_net)
            slots = self._collect_slots(target_season)
            transaction.set_rollback(True)   # nothing persists

        self._report(rows, slots, source_season, target_season)

    # ── actuals ────────────────────────────────────────────────────────────
    def _actual_wins(self, season):
        wins = defaultdict(int)
        for g in NBAGame.objects.filter(season=season, game_id__startswith="002"):
            if g.home_score is None or g.away_score is None:
                continue
            wins[g.home_team_id if g.home_score > g.away_score else g.away_team_id] += 1
        return dict(wins)

    def _actual_net(self, season):
        return {
            r.team_id: r.adj_net
            for r in NBATeamSeasonRatings.objects.filter(season=season, season_type="regular")
            if r.adj_net is not None
        }

    # ── seeding + leak-free move reconstruction ──────────────────────────────
    def _seed_outlooks(self, season):
        for t in NBATeam.objects.all():
            TeamSeasonOutlook.objects.get_or_create(
                team_slug=t.slug, season=season,
                defaults={"team_name": t.name, "team_abbr": t.abbreviation,
                          "conference": t.conference},
            )

    def _opening_rosters(self, season):
        """nba_team_id -> set(player_name): each player's FIRST regular game team."""
        open_by_team = defaultdict(set)
        seen = set()
        qs = (NBAPlayerGameStats.objects
              .filter(game__season=season, game__game_id__startswith="002", team__isnull=False)
              .select_related("player", "game")
              .order_by("player_id", "game__date", "game__game_id"))
        for pgs in qs:
            if pgs.player_id in seen:
                continue
            seen.add(pgs.player_id)
            open_by_team[pgs.team_id].add(pgs.player.name)
        return open_by_team

    def _reconstruct_moves(self, source, target):
        open_by_team = self._opening_rosters(target)
        n = 0
        for outlook in TeamSeasonOutlook.objects.filter(season=target):
            nba_team = (NBATeam.objects.filter(slug=outlook.team_slug).first()
                        or NBATeam.objects.filter(abbreviation=outlook.team_abbr).first())
            if not nba_team:
                continue
            base = set(NBAPlayerSeasonStats.objects.filter(
                team=nba_team, season=source, season_type="regular",
                mpg__gte=MIN_MPG, bpr__isnull=False,
            ).values_list("player__name", flat=True))
            opening = open_by_team.get(nba_team.id, set())
            for name in base - opening:      # left the team
                TeamOutseasonMove.objects.create(team=outlook, season=target,
                    move_type="lost", player_name=name, source="sync")
                n += 1
            for name in opening - base:      # joined the team
                TeamOutseasonMove.objects.create(team=outlook, season=target,
                    move_type="signed", player_name=name, source="sync")
                n += 1
        return n

    # ── collect projections (inside txn, before rollback) ────────────────────
    def _collect(self, season, aw, an):
        rows = []
        for o in TeamSeasonOutlook.objects.filter(season=season):
            nt = (NBATeam.objects.filter(slug=o.team_slug).first()
                  or NBATeam.objects.filter(abbreviation=o.team_abbr).first())
            if not nt or o.projected_wins is None:
                continue
            rows.append({
                "abbr": o.team_abbr, "team_id": nt.id,
                "proj_w": o.projected_wins, "act_w": aw.get(nt.id),
                "proj_net": o.projected_adj_net, "act_net": an.get(nt.id),
            })
        return rows

    def _collect_slots(self, season):
        by_team = defaultdict(list)
        for s in (NBAProjectedRosterSlot.objects.filter(season=season)
                  .select_related("team").order_by("-projected_minutes_share")):
            by_team[s.team.team_abbr].append(
                (s.player_name, s.projected_minutes_share or 0.0, s.projected_bpr or 0.0))
        return by_team

    # ── scoring + report ─────────────────────────────────────────────────────
    def _report(self, rows, slots, source, target):
        scored = [r for r in rows if r["act_w"] is not None]
        n = len(scored)
        out = self.stdout.write
        out("")
        out("=" * 72)
        out(f"OUT-OF-SAMPLE BACKTEST  {source.display_name} → {target.display_name}"
            f"   ({n} teams scored)")
        out("=" * 72)
        if not n:
            out("No scorable teams."); return

        errs = [r["proj_w"] - r["act_w"] for r in scored]
        mae = sum(abs(e) for e in errs) / n
        rmse = math.sqrt(sum(e * e for e in errs) / n)
        out(f"Wins:  MAE {mae:.2f}   RMSE {rmse:.2f}   (bias {sum(errs)/n:+.2f})")

        net = [(r["proj_net"], r["act_net"]) for r in scored
               if r["proj_net"] is not None and r["act_net"] is not None]
        if len(net) > 2:
            out(f"AdjEM: r {self._pearson(net):.3f}   (n={len(net)})")

        for label, key in (("OVER-projected (proj ≫ actual)", 1), ("UNDER-projected (proj ≪ actual)", -1)):
            out(""); out(f"── 5 biggest {label} ──")
            ranked = sorted(scored, key=lambda r: key * (r["proj_w"] - r["act_w"]), reverse=True)[:5]
            for r in ranked:
                pe = f"{r['proj_net']:+.1f}" if r["proj_net"] is not None else "n/a"
                ae = f"{r['act_net']:+.1f}" if r["act_net"] is not None else "n/a"
                out(f"  {r['abbr']}: proj {r['proj_w']:>2} vs actual {r['act_w']:>2}  "
                    f"(miss {r['proj_w']-r['act_w']:+d})   projEM {pe} / actEM {ae}")
                for name, share, bpr in slots.get(r["abbr"], [])[:5]:
                    out(f"       {name:<26} {share*20:4.1f} MPG-eq   BPR {bpr:+.2f}")
        out("")

    @staticmethod
    def _pearson(pairs):
        xs, ys = zip(*pairs)
        mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
        num = sum((x - mx) * (y - my) for x, y in pairs)
        dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
        dy = math.sqrt(sum((y - my) ** 2 for y in ys))
        return num / (dx * dy) if dx and dy else 0.0
