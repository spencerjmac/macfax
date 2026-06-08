from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
import numpy as np

from ncaa.models import TeamSeasonRatings, TeamSeasonMetrics

class AnalyzeCriteriaView(APIView):
    permission_classes = [AllowAny]
    
    def get(self, request):
        UCONN_EXCLUSIONS = {
            (2014, "Connecticut"),
            (2023, "Connecticut")
        }

        champions = TeamSeasonRatings.all_objects.filter(
            is_pre_tournament=True,
            tournament_finish="Champ"
        ).select_related('team', 'season')

        results = []

        for champ in champions:
            year = champ.season.year
            team_name = champ.team.name
            
            if (year, team_name) in UCONN_EXCLUSIONS:
                continue

            # Get all teams for the season to calculate mean/std
            all_ratings = list(TeamSeasonRatings.all_objects.filter(
                season=champ.season,
                is_pre_tournament=True
            ))
            
            all_metrics = list(TeamSeasonMetrics.all_objects.filter(
                season=champ.season,
                is_pre_tournament=True,
                team__in=[r.team for r in all_ratings]
            ))
            
            metrics_map = {m.team_id: m for m in all_metrics}

            # Calculate arrays for the field
            adjo_arr = [r.adj_o for r in all_ratings if r.adj_o is not None]
            adjd_arr = [r.adj_d for r in all_ratings if r.adj_d is not None]
            adjem_arr = [r.adj_em for r in all_ratings if r.adj_em is not None]
            
            win_pct_arr = []
            fg3_pct_arr = []
            ft_pct_arr = []
            
            for r in all_ratings:
                games = r.games_played or 0
                if games > 0:
                    win_pct_arr.append(r.wins / games)
                    
                m = metrics_map.get(r.team_id)
                if m:
                    if m.total_fg3a and m.total_fg3a > 0:
                        fg3_pct_arr.append(m.total_fg3m / m.total_fg3a)
                    if m.total_fta and m.total_fta > 0:
                        ft_pct_arr.append(m.total_ftm / m.total_fta)

            stats = {
                "adjo": (np.mean(adjo_arr), np.std(adjo_arr)),
                "adjd": (np.mean(adjd_arr), np.std(adjd_arr)),
                "adjem": (np.mean(adjem_arr), np.std(adjem_arr)),
                "win_pct": (np.mean(win_pct_arr), np.std(win_pct_arr)),
                "fg3_pct": (np.mean(fg3_pct_arr), np.std(fg3_pct_arr)),
                "ft_pct": (np.mean(ft_pct_arr), np.std(ft_pct_arr))
            }
            
            games = champ.games_played or 0
            win_pct = (champ.wins / games) if games > 0 else 0
            
            m = metrics_map.get(champ.team_id)
            fg3_pct = (m.total_fg3m / m.total_fg3a) if (m and m.total_fg3a) else 0
            ft_pct = (m.total_ftm / m.total_fta) if (m and m.total_fta) else 0
            
            def z(val, key):
                return (val - stats[key][0]) / stats[key][1]
                
            champ_z = {
                "year": year,
                "team": team_name,
                "adjo_z": z(champ.adj_o, "adjo"),
                "adjd_z": z(champ.adj_d, "adjd"),
                "adjem_z": z(champ.adj_em, "adjem"),
                "win_pct_z": z(win_pct, "win_pct"),
                "fg3_pct_z": z(fg3_pct, "fg3_pct"),
                "ft_pct_z": z(ft_pct, "ft_pct")
            }
            
            results.append(champ_z)

        return Response({
            "results": results,
            "thresholds": {
                "adjo_z": min(r['adjo_z'] for r in results),
                "adjd_z": max(r['adjd_z'] for r in results),
                "adjem_z": min(r['adjem_z'] for r in results),
                "win_pct_z": min(r['win_pct_z'] for r in results),
                "fg3_pct_z": min(r['fg3_pct_z'] for r in results),
                "ft_pct_z": min(r['ft_pct_z'] for r in results)
            }
        })
