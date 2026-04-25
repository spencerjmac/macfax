"""
core.models — re-exports all models from domain submodules.

All existing `from ncaa.models import X` imports continue to work unchanged.
"""

from .base import (
    Season,
    Conference,
    NationalAverages,
    DataProcessingJob,
    PipelineConfig,
)

from .teams import (
    Team,
    TeamExternalId,
    TeamSeasonStats,
    TeamSeasonRatings,
    TeamSeasonMetrics,
    TeamRosterFit,
    TeamSeasonProjection,
)

from .games import (
    GameLog,
    Game,
    TeamGameStats,
    ScoringEvent,
)

from .players import (
    Player,
    PlayerRecruitingProfile,
    PlayerGameStats,
    PlayerSeasonStats,
    PlayerSeasonProjection,
    PlayerGameStint,
    BPRModelArtifact,
    PlaceholderArchetype,
)

__all__ = [
    # base
    "Season",
    "Conference",
    "NationalAverages",
    "DataProcessingJob",
    "PipelineConfig",
    # teams
    "Team",
    "TeamExternalId",
    "TeamSeasonStats",
    "TeamSeasonRatings",
    "TeamSeasonMetrics",
    "TeamRosterFit",
    "TeamSeasonProjection",
    # games
    "GameLog",
    "Game",
    "TeamGameStats",
    "ScoringEvent",
    # players
    "Player",
    "PlayerRecruitingProfile",
    "PlayerGameStats",
    "PlayerSeasonStats",
    "PlayerSeasonProjection",
    "PlayerGameStint",
    "BPRModelArtifact",
    "PlaceholderArchetype",
]
