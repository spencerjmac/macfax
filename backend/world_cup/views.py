from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .elo_match_model import match_outcome_probs, simulate_group
from .models import WorldCupTeam
from .serializers import WorldCupTeamSerializer


class WorldCupRankingsView(APIView):
    def get(self, request):
        teams = WorldCupTeam.objects.all().order_by("elo_rank")
        serializer = WorldCupTeamSerializer(teams, many=True)
        return Response({"teams": serializer.data})


class WorldCupMatchupView(APIView):
    """
    GET /api/world-cup/matchup/?teamA=<name>&teamB=<name>

    Hypothetical-game win/draw/loss probabilities for two teams, based on
    Elo rating (neutral venue — host bonus already baked into elo_rating).
    """

    def get(self, request):
        name_a = request.query_params.get("teamA")
        name_b = request.query_params.get("teamB")
        if not name_a or not name_b:
            return Response(
                {"error": "teamA and teamB query params are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            team_a = WorldCupTeam.objects.get(name=name_a)
            team_b = WorldCupTeam.objects.get(name=name_b)
        except WorldCupTeam.DoesNotExist:
            return Response(
                {"error": "Team not found"}, status=status.HTTP_404_NOT_FOUND
            )

        p_a, p_draw, p_b = match_outcome_probs(team_a.elo_rating, team_b.elo_rating)

        return Response(
            {
                "teamA": WorldCupTeamSerializer(team_a).data,
                "teamB": WorldCupTeamSerializer(team_b).data,
                "win_pct_a": p_a,
                "draw_pct": p_draw,
                "win_pct_b": p_b,
                "elo_diff": team_a.elo_rating - team_b.elo_rating,
            }
        )


class WorldCupGroupView(APIView):
    """
    GET /api/world-cup/group/<group>/

    Probability of each team winning / advancing from a 4-team group, via
    exact enumeration of the round-robin (every team plays every other team
    in the group once).
    """

    def get(self, request, group):
        group = group.upper()
        teams = list(WorldCupTeam.objects.filter(group=group).order_by("-elo_rating"))
        if not teams:
            return Response(
                {"error": f"No teams found for group '{group}'"},
                status=status.HTTP_404_NOT_FOUND,
            )
        if len(teams) != 4:
            return Response(
                {"error": f"Group '{group}' has {len(teams)} teams, expected 4"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        result = simulate_group(teams)

        teams_data = []
        for entry in result["standings"]:
            data = WorldCupTeamSerializer(entry["team"]).data
            data["win_group_pct"] = entry["win_group_pct"]
            data["advance_pct"] = entry["advance_pct"]
            teams_data.append(data)

        return Response(
            {
                "group": group,
                "teams": teams_data,
                "fixtures": result["fixtures"],
            }
        )
