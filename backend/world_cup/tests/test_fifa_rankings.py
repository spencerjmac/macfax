import pytest

from world_cup.fifa_rankings import (
    FifaRanking,
    FifaRankingMetadata,
    FifaRankingsError,
    extract_latest_fifa_ranking_metadata,
    parse_fifa_rankings_response,
    update_team_config_rankings,
)


def test_extract_latest_fifa_ranking_metadata_from_next_data():
    html = """
    <html>
      <script id="__NEXT_DATA__" type="application/json">
        {
          "props": {
            "pageProps": {
              "pageData": {
                "ranking": {
                  "allAvailableDates": [
                    {"id": "FRS_Male_Football_20260401", "date": "2026-06-11"}
                  ],
                  "lastUpdateDate": "2026-06-11T10:00:59.636Z",
                  "nextUpdateDate": "2026-07-20T12:00:00.000Z"
                }
              }
            }
          }
        }
      </script>
    </html>
    """

    metadata = extract_latest_fifa_ranking_metadata(html)

    assert metadata.schedule_id == "FRS_Male_Football_20260401"
    assert metadata.published_date == "2026-06-11"
    assert metadata.last_update_date == "2026-06-11T10:00:59.636Z"
    assert metadata.next_update_date == "2026-07-20T12:00:00.000Z"


def test_parse_fifa_rankings_response_uses_total_points_and_localized_name():
    rankings = parse_fifa_rankings_response(
        {
            "Results": [
                {
                    "Rank": 25,
                    "PrevRank": 24,
                    "IdCountry": "KOR",
                    "TotalPoints": 1591.630886,
                    "TeamName": [{"Locale": "en-GB", "Description": "Korea Republic"}],
                }
            ]
        }
    )

    assert rankings == [
        FifaRanking(
            rank=25,
            country_code="KOR",
            name="Korea Republic",
            total_points=1591.630886,
            previous_rank=24,
        )
    ]


def test_update_team_config_rankings_matches_world_cup_aliases_by_country_code():
    teams = [
        {"name": "South Korea", "dataset_name": "South Korea", "fifa_rank": 99, "fifa_points": 0},
        {"name": "Ivory Coast", "dataset_name": "Ivory Coast", "fifa_rank": 99, "fifa_points": 0},
    ]
    rankings = [
        FifaRanking(rank=25, country_code="KOR", name="Korea Republic", total_points=1591.630886),
        FifaRanking(rank=33, country_code="CIV", name="Côte d'Ivoire", total_points=1540.869533),
    ]

    result = update_team_config_rankings(
        teams,
        rankings,
        FifaRankingMetadata(
            schedule_id="FRS_Male_Football_20260401",
            published_date="2026-06-11",
            last_update_date=None,
            next_update_date=None,
        ),
    )

    assert result.missing_teams == []
    assert result.teams[0]["fifa_rank"] == 25
    assert result.teams[0]["fifa_points"] == 1591.63
    assert result.teams[1]["fifa_rank"] == 33
    assert result.teams[1]["fifa_points"] == 1540.87
    assert [change.team_name for change in result.changes] == ["South Korea", "Ivory Coast"]


def test_parse_fifa_rankings_response_rejects_empty_payload():
    with pytest.raises(FifaRankingsError, match="did not include any ranking rows"):
        parse_fifa_rankings_response({"Results": []})
