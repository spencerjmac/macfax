"""
Scenario models — ScenarioSnapshot.

Persisted scenario results for user-defined hypothetical rosters.
The scenario computation itself is stateless; this model stores the result
for retrieval without recomputation.
"""

from django.db import models

from .base import Season
from .teams import Team


class ScenarioSnapshot(models.Model):
    """
    Persisted scenario result for a user-defined hypothetical roster.

    Created only when the user explicitly saves a scenario.  Ephemeral
    (un-saved) scenarios are computed in memory and returned without a
    DB write.

    scenario_input  — the ScenarioRosterRequest JSON as submitted by the client
    scenario_result — the full ScenarioResult JSON as returned by compute_scenario()

    The scenario_result JSON must be self-contained: if the PlaceholderArchetype
    table changes in the future, a saved snapshot must still be renderable from
    its stored JSON alone.
    """

    team = models.ForeignKey(
        Team, on_delete=models.CASCADE, related_name="scenario_snapshots",
    )
    from_season = models.ForeignKey(
        Season, on_delete=models.CASCADE, related_name="scenario_snapshots",
    )
    projected_season_year = models.IntegerField()

    name = models.CharField(
        max_length=120, blank=True, default="",
        help_text="User-defined scenario name.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    scenario_input = models.JSONField(
        help_text="Serialized ScenarioRosterRequest as submitted by the client.",
    )
    scenario_result = models.JSONField(
        help_text="Serialized ScenarioResult as returned by compute_scenario().",
    )

    # Quick-access summary fields (denormalized from scenario_result for list views)
    projected_adj_em = models.FloatField(null=True, blank=True)
    projected_national_rank = models.IntegerField(null=True, blank=True)
    n_manual_players = models.IntegerField(default=0)

    class Meta:
        app_label = "core"
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["team", "from_season"]),
        ]

    def __str__(self) -> str:
        label = self.name or f"Scenario {self.pk}"
        return f"{label} — {self.team.name} ({self.from_season.year}→{self.projected_season_year})"
