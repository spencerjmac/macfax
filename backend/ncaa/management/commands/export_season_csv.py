"""
Management command: export_season_csv

Flattens one NCAA season into two wide CSVs — every stored team metric and
every stored player metric — for offline analysis / sharing.

  teams   = Team identity + TeamSeasonMetrics + TeamSeasonRatings
            + TeamSeasonProjection + TeamRosterFit (projections are the ones
            built for this season, i.e. projected_season_year == season)
  players = Player identity + team + PlayerSeasonStats + PlayerMarketValue
            + PlayerSeasonProjection

Rows are the union of every source, so a team/player that only has a
projection (no played games yet) still gets a row.

Usage:
  python manage.py export_season_csv --season 2026
  python manage.py export_season_csv --season 2026 --out-dir ../metrics_output
  python manage.py export_season_csv --season 2026 --players-only --no-text
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

# Columns holding prose / JSON blobs — noisy in a spreadsheet, dropped by --no-text.
TEXT_FIELDS = {
    "projection_summary",
    "driver_breakdown",
    "fit_summary",
    "offensive_strengths",
    "offensive_weaknesses",
    "defensive_strengths",
    "defensive_weaknesses",
    "off_penalties",
    "def_penalties",
    "classification_reason",
}

SKIP_FIELDS = {
    "id",
    "team",
    "player",
    "season",
    "from_season",
    "projected_season_year",
    "conference",  # emitted once as an identity column
    "is_pre_tournament",  # fixed by the --pre-tournament flag
}


def _concrete_names(model):
    return [
        f.name
        for f in model._meta.get_fields()
        if getattr(f, "concrete", False) and f.name not in SKIP_FIELDS
    ]


def _cell(value):
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, separators=(",", ":"))
    return value


class Command(BaseCommand):
    help = "Export one NCAA season's team + player metrics to CSV."

    def add_arguments(self, parser):
        parser.add_argument("--season", type=int, required=True,
                            help="Ending year (2026 = 2025-26 season)")
        parser.add_argument("--out-dir", type=str, default=".")
        parser.add_argument("--teams-only", action="store_true", default=False)
        parser.add_argument("--players-only", action="store_true", default=False)
        parser.add_argument("--no-text", action="store_true", default=False,
                            help="Drop prose/JSON columns (summaries, driver blobs)")
        parser.add_argument("--pre-tournament", action="store_true", default=False,
                            help="Use pre-tournament metric/rating snapshots")

    def handle(self, *args, **opts):
        from ncaa.models import Season

        year = opts["season"]
        try:
            season = Season.objects.get(year=year)
        except Season.DoesNotExist:
            raise CommandError(f"No Season row for year={year}")

        out_dir = Path(opts["out_dir"]).expanduser().resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        tag = season.display_name.replace("-", "_").replace("/", "_")

        if not opts["players_only"]:
            path = out_dir / f"ncaa_team_metrics_{tag}.csv"
            n, cols = self._export_teams(season, path, opts)
            self.stdout.write(self.style.SUCCESS(
                f"teams   {n:>6} rows x {cols:>3} cols -> {path}"))

        if not opts["teams_only"]:
            path = out_dir / f"ncaa_player_metrics_{tag}.csv"
            n, cols = self._export_players(season, path, opts)
            self.stdout.write(self.style.SUCCESS(
                f"players {n:>6} rows x {cols:>3} cols -> {path}"))

    # ------------------------------------------------------------------ teams

    def _export_teams(self, season, path, opts):
        from ncaa.models import (
            Team,
            TeamRosterFit,
            TeamSeasonMetrics,
            TeamSeasonProjection,
            TeamSeasonRatings,
        )

        pre = opts["pre_tournament"]
        metrics = {
            m.team_id: m
            for m in TeamSeasonMetrics.objects.filter(
                season=season, is_pre_tournament=pre
            ).select_related("conference")
        }
        ratings = {
            r.team_id: r
            for r in TeamSeasonRatings.objects.filter(
                season=season, is_pre_tournament=pre
            )
        }
        projections = {
            p.team_id: p
            for p in TeamSeasonProjection.objects.filter(
                projected_season_year=season.year
            )
        }
        fits = {
            f.team_id: f
            for f in TeamRosterFit.objects.filter(projected_season_year=season.year)
        }

        team_ids = set(metrics) | set(ratings) | set(projections) | set(fits)
        teams = {t.id: t for t in Team.objects.filter(id__in=team_ids)}

        sources = [
            ("", "metrics", TeamSeasonMetrics, metrics),
            ("", "ratings", TeamSeasonRatings, ratings),
            ("proj_", "proj", TeamSeasonProjection, projections),
            ("fit_", "fit", TeamRosterFit, fits),
        ]
        header, plan = self._build_plan(
            ["team_id", "team_slug", "team_name", "conference", "is_d1", "elevation"],
            sources,
            opts["no_text"],
        )

        rows = []
        for team_id in sorted(team_ids, key=lambda t: teams[t].name if t in teams else ""):
            team = teams.get(team_id)
            metric = metrics.get(team_id)
            conf = metric.conference if metric and metric.conference_id else None
            row = [
                team_id,
                getattr(team, "slug", ""),
                getattr(team, "name", ""),
                conf.code if conf else "",
                getattr(team, "is_d1", ""),
                _cell(getattr(team, "elevation", None)),
            ]
            row += self._source_cells(plan, sources, team_id)
            rows.append(row)

        rows.sort(key=lambda r: r[2])
        self._write(path, header, rows)
        return len(rows), len(header)

    # ---------------------------------------------------------------- players

    def _export_players(self, season, path, opts):
        from ncaa.models import (
            Player,
            PlayerMarketValue,
            PlayerSeasonProjection,
            PlayerSeasonStats,
            Team,
        )

        stats = {
            s.player_id: s
            for s in PlayerSeasonStats.objects.filter(season=season)
        }
        values = {
            v.player_id: v for v in PlayerMarketValue.objects.filter(season=season)
        }
        projections = {
            p.player_id: p
            for p in PlayerSeasonProjection.objects.filter(
                projected_season_year=season.year
            )
        }

        player_ids = set(stats) | set(values) | set(projections)
        players = {p.id: p for p in Player.objects.filter(id__in=player_ids)}
        team_ids = {s.team_id for s in stats.values() if s.team_id}
        team_ids |= {p.team_id for p in projections.values() if p.team_id}
        teams = {t.id: t for t in Team.objects.filter(id__in=team_ids)}

        # Conference comes off the team's season metrics row.
        from ncaa.models import TeamSeasonMetrics

        conf_by_team = {
            m.team_id: (m.conference.code if m.conference_id else "")
            for m in TeamSeasonMetrics.objects.filter(
                season=season, is_pre_tournament=opts["pre_tournament"]
            ).select_related("conference")
        }

        sources = [
            ("", "stats", PlayerSeasonStats, stats),
            ("mv_", "mv", PlayerMarketValue, values),
            ("proj_", "proj", PlayerSeasonProjection, projections),
        ]
        header, plan = self._build_plan(
            [
                "player_id",
                "espn_athlete_id",
                "player_name",
                "position",
                "jersey",
                "team_id",
                "team_name",
                "conference",
            ],
            sources,
            opts["no_text"],
        )

        rows = []
        for player_id in player_ids:
            player = players.get(player_id)
            stat = stats.get(player_id)
            proj = projections.get(player_id)
            team_id = (stat.team_id if stat else None) or (proj.team_id if proj else None)
            team = teams.get(team_id)
            row = [
                player_id,
                getattr(player, "espn_athlete_id", "") or "",
                getattr(player, "display_name", ""),
                getattr(player, "position", "") or "",
                getattr(player, "jersey", "") or "",
                team_id or "",
                getattr(team, "name", ""),
                conf_by_team.get(team_id, ""),
            ]
            row += self._source_cells(plan, sources, player_id)
            rows.append(row)

        rows.sort(key=lambda r: (r[6], r[2]))
        self._write(path, header, rows)
        return len(rows), len(header)

    # ------------------------------------------------------------------ util

    def _build_plan(self, identity_cols, sources, no_text):
        """Header + per-source field list, renaming duplicate column names."""
        header = list(identity_cols)
        seen = set(header)
        plan = []
        for prefix, label, model, _rows in sources:
            stem = prefix.rstrip("_")
            fields = []
            for name in _concrete_names(model):
                if no_text and name in TEXT_FIELDS:
                    continue
                # Don't double up: "projected_adj_o" already reads as a projection.
                col = name if (stem and name.startswith(stem)) else f"{prefix}{name}"
                while col in seen:
                    col = f"{col}_{label}"
                header.append(col)
                seen.add(col)
                fields.append(name)
            plan.append(fields)
        return header, plan

    def _source_cells(self, plan, sources, key):
        cells = []
        for fields, (_prefix, _label, _model, rows) in zip(plan, sources):
            obj = rows.get(key)
            if obj is None:
                cells += [""] * len(fields)
            else:
                cells += [_cell(getattr(obj, f, None)) for f in fields]
        return cells

    def _write(self, path, header, rows):
        with open(path, "w", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(header)
            writer.writerows(rows)
