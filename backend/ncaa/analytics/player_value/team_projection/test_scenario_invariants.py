"""
Phase 1 remediation: scenario projection invariant tests.

These are the acceptance gate for the partial-roster correctness fix:

  TEST 1 — Baseline equivalence: POSTing a team's exact stored player
           projections to /api/outlook/scenario/ reproduces the stored
           TeamSeasonProjection ratings within ±0.15 pts (the replacement
           pad share is ~0, so the scenario is a near-no-op).
  TEST 2 — Subset invariant: submitting only the top-4 players of a baseline
           roster must NOT project better than the full baseline roster
           (this was the renormalization bug: 4 players inflated to fill
           all 200 team-minutes).
  TEST 3 — Monotonicity: adding a player clearly better than replacement
           level to a partial roster must strictly increase projected EM
           (the user-reported "adding a good transfer lowers the projection"
           paradox).

Fixtures mirror the two-pass baseline pipeline: base aggregates are computed
for every seeded team first, league means are taken over those, then each
team's stored TeamSeasonProjection is produced by the same engine call the
scenario view makes (project_team with roster_fit=None), guaranteeing the
stored baseline and the scenario view share one D1 context.
"""

from __future__ import annotations

from django.test import TestCase

from ncaa.analytics.player_value.team_projection.constants import (
    REPLACEMENT_FILL_DBPR,
    REPLACEMENT_FILL_OBPR,
)
from ncaa.analytics.player_value.team_projection.engine import (
    D1Context,
    PlayerProjectionInput,
    project_team,
)
from ncaa.models import (
    Player,
    PlayerSeasonProjection,
    Season,
    Team,
    TeamSeasonProjection,
    TeamSeasonRatings,
)

SCENARIO_URL = "/api/outlook/scenario/"
SEASON_YEAR = 2025

# (slug, [(obpr, dbpr, share, recruitment_type, uncertainty), ...])
# Shares sum to exactly 5.0 per team. Bench players sit above the derived
# replacement-fill level so the subset invariant is a real constraint.
_ROSTERS = {
    "inv-strong": [
        (5.0, 2.5, 0.85, "returner", 0.20),
        (4.2, 2.0, 0.80, "returner", 0.22),
        (3.5, 1.8, 0.70, "returner", 0.25),
        (3.0, 1.5, 0.65, "transfer", 0.35),
        (2.0, 1.0, 0.55, "returner", 0.30),
        (1.5, 0.8, 0.50, "transfer", 0.40),
        (1.0, 0.6, 0.50, "returner", 0.35),
        (0.8, 0.5, 0.45, "newcomer", 0.70),
    ],
    "inv-average": [
        (3.0, 1.5, 0.85, "returner", 0.25),
        (2.5, 1.2, 0.80, "transfer", 0.35),
        (2.0, 1.0, 0.70, "returner", 0.28),
        (1.5, 0.9, 0.65, "returner", 0.30),
        (1.2, 0.7, 0.55, "transfer", 0.40),
        (1.0, 0.6, 0.50, "returner", 0.35),
        (0.9, 0.5, 0.50, "newcomer", 0.70),
        (0.8, 0.5, 0.45, "newcomer", 0.75),
    ],
    "inv-weak": [
        (1.5, 0.8, 0.85, "returner", 0.30),
        (1.2, 0.7, 0.80, "returner", 0.32),
        (1.0, 0.6, 0.70, "transfer", 0.40),
        (0.9, 0.6, 0.65, "returner", 0.35),
        (0.8, 0.5, 0.55, "newcomer", 0.70),
        (0.7, 0.5, 0.50, "returner", 0.38),
        (0.7, 0.4, 0.50, "transfer", 0.45),
        (0.6, 0.4, 0.45, "newcomer", 0.75),
    ],
}


def _engine_inputs(roster) -> list[PlayerProjectionInput]:
    return [
        PlayerProjectionInput(
            player_id=i + 1,
            projected_obpr=obpr,
            projected_dbpr=dbpr,
            projected_bpr=obpr + dbpr,
            minutes_share_p2=share,
            recruitment_type=rtype,
            projection_uncertainty=unc,
        )
        for i, (obpr, dbpr, share, rtype, unc) in enumerate(roster)
    ]


class ScenarioInvariantTests(TestCase):
    """Invariant gate for the Phase 1 partial-roster fix."""

    @classmethod
    def setUpTestData(cls):
        cls.season = Season.objects.create(
            year=SEASON_YEAR,
            display_name=f"{SEASON_YEAR - 1}-{str(SEASON_YEAR)[2:]}",
            is_current=True,
        )

        # Pass 1: base aggregates per team → league means (mirrors service.py)
        aggregates = {}
        for slug, roster in _ROSTERS.items():
            inputs = _engine_inputs(roster)
            base_off = sum(p.minutes_share_p2 * p.projected_obpr for p in inputs)
            base_def = sum(p.minutes_share_p2 * p.projected_dbpr for p in inputs)
            aggregates[slug] = (inputs, base_off, base_def)

        n_teams = len(_ROSTERS)
        league_mean_off = sum(a[1] for a in aggregates.values()) / n_teams
        league_mean_def = sum(a[2] for a in aggregates.values()) / n_teams

        # Ratings rows drive the view's avg_adj_o / avg_adj_d
        avg_o, avg_d = 108.0, 108.0
        cls.d1_context = D1Context(
            avg_adj_o=avg_o,
            avg_adj_d=avg_d,
            league_mean_base_off=league_mean_off,
            league_mean_base_def=league_mean_def,
            n_projected_teams=n_teams,
        )

        # Pass 2: store per-team baseline via the same engine the view calls
        cls.baselines = {}
        seq = 0
        for slug, (inputs, base_off, base_def) in aggregates.items():
            team = Team.objects.create(slug=slug, name=slug.title(), is_d1=True)
            TeamSeasonRatings.objects.create(
                team=team, season=cls.season,
                wins=15, losses=10, games_played=25, rank_adj_em=100,
                adj_em=0.0, adj_o=avg_o, adj_d=avg_d,
                adj_tempo=68.0, adj_efg_pct=51.0,
            )
            result = project_team(inputs, None, cls.d1_context)
            proj = TeamSeasonProjection.objects.create(
                team=team,
                from_season=cls.season,
                projected_season_year=SEASON_YEAR + 1,
                base_team_offense=base_off,
                base_team_defense=base_def,
                base_team_roster_strength=base_off + base_def,
                returner_minutes_fraction=result.returner_minutes_fraction,
                continuity_score=result.continuity_score,
                continuity_value_score=result.continuity_value_score,
                continuity_adjustment_off=result.continuity_adjustment_off,
                continuity_adjustment_def=result.continuity_adjustment_def,
                transfer_dependence_score=result.transfer_dependence_score,
                transfer_fit_risk_score=result.transfer_fit_risk_score,
                projected_adj_o=result.projected_adj_o,
                projected_adj_d=result.projected_adj_d,
                projected_adj_em=result.projected_adj_em,
                team_projection_uncertainty=result.team_projection_uncertainty,
                projected_adj_o_low=result.projected_adj_o_low,
                projected_adj_o_high=result.projected_adj_o_high,
                projected_adj_d_low=result.projected_adj_d_low,
                projected_adj_d_high=result.projected_adj_d_high,
                projected_adj_em_low=result.projected_adj_em_low,
                projected_adj_em_high=result.projected_adj_em_high,
            )
            cls.baselines[slug] = proj

            for row_idx, (obpr, dbpr, share, rtype, unc) in enumerate(_ROSTERS[slug]):
                seq += 1
                player = Player.objects.create(
                    espn_athlete_id=f"inv_{slug}_{row_idx}",
                    display_name=f"{slug} Player {row_idx}",
                    short_name=f"P{seq}",
                    position="G",
                )
                PlayerSeasonProjection.objects.create(
                    player=player,
                    team=team,
                    from_season=cls.season,
                    projected_season_year=SEASON_YEAR + 1,
                    recruitment_type=rtype,
                    projected_obpr=obpr,
                    projected_dbpr=dbpr,
                    projected_bpr=obpr + dbpr,
                    minutes_share_p2=share,
                    mpg_p2=share * 40.0,
                    role_bucket="G",
                    projection_uncertainty=unc,
                    rotation_rank=row_idx + 1,
                )

    # ── helpers ──────────────────────────────────────────────────────────────

    def _post_scenario(self, slug: str, players: list[dict]) -> dict:
        res = self.client.post(
            SCENARIO_URL,
            data={
                "from_season_year": SEASON_YEAR,
                "team_slug": slug,
                "players": players,
            },
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200, res.content)
        return res.json()

    def _stored_player_payloads(self, slug: str) -> list[dict]:
        rows = PlayerSeasonProjection.objects.filter(
            team__slug=slug, from_season=self.season
        ).order_by("rotation_rank")
        return [
            {
                "player_id": row.player_id,
                "player_name": row.player.display_name,
                "projected_obpr": row.projected_obpr,
                "projected_dbpr": row.projected_dbpr,
                "projected_bpr": row.projected_bpr,
                "minutes_share": row.minutes_share_p2,
                "recruitment_type": row.recruitment_type,
                "projection_uncertainty": row.projection_uncertainty,
            }
            for row in rows
        ]

    def _top4_payloads(self, slug: str) -> list[dict]:
        payloads = self._stored_player_payloads(slug)
        return sorted(payloads, key=lambda p: p["projected_bpr"], reverse=True)[:4]

    # ── TEST 1: baseline equivalence ─────────────────────────────────────────

    def test_baseline_equivalence(self):
        """Exact stored roster → scenario reproduces stored projection ±0.15."""
        for slug, stored in self.baselines.items():
            with self.subTest(team=slug):
                data = self._post_scenario(slug, self._stored_player_payloads(slug))
                self.assertAlmostEqual(
                    data["projected_adj_o"], stored.projected_adj_o, delta=0.15
                )
                self.assertAlmostEqual(
                    data["projected_adj_d"], stored.projected_adj_d, delta=0.15
                )
                self.assertAlmostEqual(
                    data["projected_adj_em"], stored.projected_adj_em, delta=0.15
                )
                self.assertAlmostEqual(data["pool_fill_fraction"], 1.0, delta=0.01)
                self.assertEqual(data["replacement_fill_share"], 0.0)

    # ── TEST 2: subset invariant ─────────────────────────────────────────────

    def test_subset_never_beats_baseline(self):
        """Top-4 subset of a baseline roster must not out-project the full roster."""
        for slug, stored in self.baselines.items():
            with self.subTest(team=slug):
                data = self._post_scenario(slug, self._top4_payloads(slug))
                self.assertLessEqual(
                    data["projected_adj_em"],
                    stored.projected_adj_em + 0.15,
                    f"{slug}: 4-player subset projected {data['projected_adj_em']} "
                    f"vs full-roster baseline {stored.projected_adj_em} — "
                    "partial roster must not beat the roster it is a subset of",
                )
                # The pad must be reported, and reported as a partial pool
                self.assertLess(data["pool_fill_fraction"], 1.0)
                self.assertGreater(data["replacement_fill_share"], 0.0)

    # ── TEST 3: monotonicity ─────────────────────────────────────────────────

    def test_adding_above_replacement_player_increases_em(self):
        """Adding a player 2.0 BPR above replacement fill strictly raises EM."""
        slug = "inv-strong"
        top4 = self._top4_payloads(slug)
        base_data = self._post_scenario(slug, top4)

        added = {
            "player_id": 777001,
            "player_name": "Portal Addition",
            "projected_obpr": REPLACEMENT_FILL_OBPR + 1.2,
            "projected_dbpr": REPLACEMENT_FILL_DBPR + 0.8,
            "projected_bpr": REPLACEMENT_FILL_OBPR + REPLACEMENT_FILL_DBPR + 2.0,
            "minutes_share": 0.5,
            "recruitment_type": "transfer",
            "projection_uncertainty": 0.4,
        }
        with_transfer = self._post_scenario(slug, top4 + [added])

        self.assertGreater(
            with_transfer["projected_adj_em"],
            base_data["projected_adj_em"],
            "Adding an above-replacement transfer must strictly increase "
            "projected EM (user-reported transfer paradox)",
        )
