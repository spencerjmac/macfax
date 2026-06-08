from rest_framework.views import APIView
from rest_framework.response import Response
from .models import WorldCupTeam
from .serializers import WorldCupTeamSerializer


class WorldCupRankingsView(APIView):
    def get(self, request):
        teams = WorldCupTeam.objects.all().order_by("elo_rank")
        serializer = WorldCupTeamSerializer(teams, many=True)
        return Response({"teams": serializer.data})
